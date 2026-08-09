import pickle
import re
import hashlib
import numpy as np
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from ocr import extract_text, verify_document, parse_document_fields


load_dotenv()

DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-insecure-key'
    else:
        raise RuntimeError('SECRET_KEY environment variable must be set in production')

TOKEN_MAX_AGE = 60 * 60 * 12  # 12 hours
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-auth')

# Fallback copies of the model's category lists, used for form-input validation
# even if the model bundle itself fails to load - so a broken model file disables
# scoring only, not application submission. Keep in sync with schema/ml_model.md.
DEFAULT_EDUCATION_MAP = {'None': 0, 'Elementary': 1, 'High School': 2, 'Vocational': 3, 'College': 4, 'Postgraduate': 5}
DEFAULT_OCCUPATION_CATEGORIES = ['Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade', 'Office/Clerical', 'Professional', 'Deceased/Not Applicable']
DEFAULT_HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives', 'Informal settler']

# ── LOAD ML MODEL (classifier + regressor combined bundle) ──
try:
    with open('model_combined.pkl', 'rb') as f:
        ml_bundle = pickle.load(f)
    ml_classifier = ml_bundle['classifier']
    ml_regressor = ml_bundle['regressor']
    ml_scaler = ml_bundle['scaler']
    ml_features = ml_bundle['features']
    ml_education_map = ml_bundle['education_map']
    ml_occupation_categories = ml_bundle['occupation_categories']
    ml_housing_situations = ml_bundle['housing_situations']
    ml_regressor_cutoff = ml_bundle['regressor_score_cutoff']
    print(f"ML model loaded successfully! (classifier={ml_bundle.get('classifier_name')}, "
          f"regressor={ml_bundle.get('best_overall_name')})")
except Exception as e:
    ml_classifier = None
    ml_regressor = None
    ml_education_map = DEFAULT_EDUCATION_MAP
    ml_occupation_categories = DEFAULT_OCCUPATION_CATEGORIES
    ml_housing_situations = DEFAULT_HOUSING_SITUATIONS
    ml_regressor_cutoff = None
    print(f"ML model not loaded: {e}")

app = Flask(__name__)
CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if o.strip()]
CORS(app, supports_credentials=True, origins=CORS_ORIGINS)

limiter = Limiter(get_remote_address, app=app, storage_uri="memory://", default_limits=[])

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'none'"
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'
    return response

# Public, unauthenticated, no DB access - meant for uptime pingers to keep the free-tier
# instance from sleeping, and for basic "is it up" checks.
@app.route('/api/health')
def health():
    return jsonify({"status": "ok"})

# Fields every applicant must have for the combined model to score them.
# Applicants who registered before this model was wired in won't have these
# (see schema/ml_model.md) - they're excluded from scoring rather than guessed at.
ML_REQUIRED_FIELDS = [
    'monthly_income', 'housing_situation', 'num_siblings',
    'num_siblings_studying', 'father_education', 'mother_education'
]

STATUS_MESSAGES = {
    'Approved': 'Your scholarship application has been approved.',
    'Rejected': 'Your scholarship application was not approved this time.',
}
STATUS_NOTIF_TYPE = {'Approved': 'approved', 'Rejected': 'rejected'}

def build_feature_row(applicant):
    """Build the {feature_name: value} dict the combined model expects, in the
    encoding it was trained on. Returns (row, True) or (None, False) if this
    applicant predates the fields this model needs."""
    if any(applicant.get(f) is None for f in ML_REQUIRED_FIELDS):
        return None, False

    academic = applicant.get('academic') or {}
    row = {
        'gpa': float(academic.get('gpa') or 0),
        'sex_encoded': 1 if applicant.get('gender') == 'Male' else 0,
        'family_size': int(applicant.get('family_size') or 0),
        'num_siblings': int(applicant.get('num_siblings') or 0),
        'num_siblings_studying': int(applicant.get('num_siblings_studying') or 0),
        'father_education_level': ml_education_map.get(applicant.get('father_education'), 0),
        'mother_education_level': ml_education_map.get(applicant.get('mother_education'), 0),
        'monthly_income': float(applicant.get('monthly_income') or 0),
        'has_other_scholarship': int(bool(applicant.get('has_other_scholarship'))),
    }
    father_occ = applicant.get('father_occupation')
    mother_occ = applicant.get('mother_occupation')
    housing = applicant.get('housing_situation')
    for cat in ml_occupation_categories:
        row[f'father_occ_{cat}'] = 1 if father_occ == cat else 0
        row[f'mother_occ_{cat}'] = 1 if mother_occ == cat else 0
    for cat in ml_housing_situations:
        row[f'housing_{cat}'] = 1 if housing == cat else 0

    return row, True

def score_with_model(row):
    """Run the classifier (eligibility) and regressor (ranking score) on a
    feature row built by build_feature_row(). Returns (ml_score, ml_status)."""
    feature_values = np.array([[row[f] for f in ml_features]])

    features_scaled = ml_scaler.transform(feature_values)
    classifier_pred = ml_classifier.predict(features_scaled)[0]
    ml_status = 'Eligible' if int(classifier_pred) == 1 else 'Not Eligible'

    total_score = float(ml_regressor.predict(feature_values)[0])
    ml_score = round(total_score, 1)

    return ml_score, ml_status

def build_score_breakdown(row, applicant):
    """Simple heuristic breakdown for the admin UI progress bars - a rough
    visual aid, not the model's actual internal feature attribution."""
    gpa_s = round(max(0, min(100, row['gpa'])), 1)
    inc_s = round(max(0, min(100, (1 - min(row['monthly_income'], 100000) / 100000) * 100)), 1)
    fam_s = round(min(100, max(0, (row['family_size'] - 2) / 8 * 100)), 1)
    edu_avg = (row['father_education_level'] + row['mother_education_level']) / 2
    edu_s = round(max(0, min(100, (5 - edu_avg) / 5 * 100)), 1)
    housing_need = {'Owned': 20, 'Rented': 60, 'Living with relatives': 80, 'Informal settler': 100}
    house_s = housing_need.get(applicant.get('housing_situation'), 50)

    return [
        {"label": "GWA Score", "value": gpa_s, "color": "#10b981"},
        {"label": "Income Need Score", "value": inc_s, "color": "#7c3aed"},
        {"label": "Family Size Score", "value": fam_s, "color": "#2563eb"},
        {"label": "Parental Education Need", "value": edu_s, "color": "#f59e0b"},
        {"label": "Housing Need Score", "value": house_s, "color": "#ec4899"},
    ]

# ── UPLOAD CONFIG ──
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
# Serving files back to the browser with a client-supplied Content-Type is a stored-XSS
# vector (e.g. an upload named "photo.png" claiming Content-Type: text/html). Always
# derive the served mimetype from this fixed map instead of trusting the upload metadata.
SAFE_MIME_TYPES = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB, matches the limit shown in the UI
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_mime_for(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return SAFE_MIME_TYPES.get(ext, 'application/octet-stream')

# ── DATABASE CONNECTION (MongoDB Atlas) ──
_mongo_client = MongoClient(os.getenv('MONGO_URI'))
_mongo_db = _mongo_client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]
# Uploaded documents live in GridFS (not local disk) so they survive redeploys
# on hosts with ephemeral filesystems.
_fs = gridfs.GridFS(_mongo_db)
# Logged-out tokens land here until their natural expiry so a stolen/leaked token
# can be invalidated before TOKEN_MAX_AGE runs out. TTL index auto-purges entries.
_mongo_db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)

def get_db():
    return _mongo_db

def oid(id_str):
    """Parse a string into an ObjectId, or None if it isn't a valid one."""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None

def iso(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None

# ── AUTH HELPERS ──
def issue_token(user):
    return _serializer.dumps({
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
    })

def verify_token(token):
    return _serializer.loads(token, max_age=TOKEN_MAX_AGE)

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def revoke_token(token):
    """Blacklist a token until its own natural expiry (logout can't un-sign a
    stateless itsdangerous token, so we track that it's no longer welcome)."""
    try:
        _, issued_at = _serializer.loads(token, max_age=TOKEN_MAX_AGE, return_timestamp=True)
    except (SignatureExpired, BadSignature):
        return
    expires_at = issued_at + timedelta(seconds=TOKEN_MAX_AGE)
    _mongo_db.revoked_tokens.insert_one({"token_hash": hash_token(token), "expires_at": expires_at})

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authentication required"}), 401
        token = auth_header[len('Bearer '):]
        try:
            g.current_user = verify_token(token)
        except SignatureExpired:
            return jsonify({"error": "Session expired, please log in again"}), 401
        except BadSignature:
            return jsonify({"error": "Invalid session"}), 401
        if _mongo_db.revoked_tokens.find_one({"token_hash": hash_token(token)}):
            return jsonify({"error": "Session has been logged out, please log in again"}), 401
        g.current_token = token
        return f(*args, **kwargs)
    return wrapper

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth
        def wrapper(*args, **kwargs):
            if g.current_user.get('role') not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File exceeds the 5MB upload limit"}), 413

@app.errorhandler(429)
def rate_limited(e):
    return jsonify({"error": "Too many attempts. Please wait a minute and try again."}), 429

# ── SERIALIZATION HELPERS ──
def serialize_applicant(doc):
    """Flatten an applicant document (with embedded academic/application) into
    the same flat shape the frontend has always received from the SQL JOINs."""
    academic = doc.get('academic') or {}
    application = doc.get('application') or {}
    return {
        "id": str(doc['_id']),
        "user_id": str(doc['user_id']) if doc.get('user_id') else None,
        "full_name": doc.get('full_name'),
        "email": doc.get('email'),
        "contact_number": doc.get('contact_number'),
        "address": doc.get('address'),
        "gender": doc.get('gender'),
        "date_of_birth": doc.get('date_of_birth'),
        "religion": doc.get('religion'),
        "citizenship": doc.get('citizenship'),
        "father_name": doc.get('father_name'),
        "father_occupation": doc.get('father_occupation'),
        "mother_name": doc.get('mother_name'),
        "mother_occupation": doc.get('mother_occupation'),
        "household_income": doc.get('household_income'),
        "family_size": doc.get('family_size'),
        "barangay": doc.get('barangay'),
        "ml_score": doc.get('ml_score', 0),
        "ml_status": doc.get('ml_status', 'Pending'),
        "created_at": iso(doc.get('created_at')),
        "privacy_consent": doc.get('privacy_consent', False),
        "has_other_scholarship": doc.get('has_other_scholarship', False),
        "other_scholarship_details": doc.get('other_scholarship_details'),
        "course": academic.get('course'),
        "year_level": academic.get('year_level'),
        "gpa": academic.get('gpa'),
        "school": academic.get('school'),
        "school_address": academic.get('school_address'),
        "academic_year": academic.get('academic_year'),
        "semester": academic.get('semester'),
        "application_status": application.get('status'),
        "application_id": str(doc['_id']),
        "submitted_at": iso(application.get('submitted_at')),
        "reviewed_at": iso(application.get('reviewed_at')),
        "reviewed_by_name": application.get('reviewed_by_name'),
        "application_type": application.get('application_type'),
    }

def serialize_document(d):
    return {
        "document_name": d.get('document_name'),
        "status": d.get('status', 'Missing'),
        "uploaded_at": iso(d.get('uploaded_at')),
    }

def serialize_audit_entry(a):
    return {
        "action": a.get('action'),
        "performed_by": a.get('performed_by'),
        "performed_by_role": a.get('performed_by_role'),
        "old_status": a.get('old_status'),
        "new_status": a.get('new_status'),
        "remarks": a.get('remarks'),
        "performed_at": iso(a.get('performed_at')),
    }

def serialize_notification(n):
    return {
        "id": str(n['_id']),
        "applicant_id": str(n['applicant_id']) if n.get('applicant_id') else None,
        "message": n.get('message'),
        "type": n.get('type', 'status_update'),
        "is_read": bool(n.get('is_read', False)),
        "created_at": iso(n.get('created_at')),
    }

# ── NOTIFICATION HELPERS ──
def resolve_notify_user_id(db, applicant_doc):
    """Find the account to notify for an applicant: prefer the linked user_id,
    fall back to matching the applicant's email against users (legacy rows)."""
    if applicant_doc.get('user_id'):
        return applicant_doc['user_id']
    email = applicant_doc.get('email')
    if email:
        match = db.users.find_one({"email": email})
        if match:
            return match['_id']
    return None

def create_notification(db, user_id, applicant_id, message, notif_type='status_update'):
    if not user_id:
        return
    db.notifications.insert_one({
        "user_id": user_id,
        "applicant_id": applicant_id,
        "message": message,
        "type": notif_type,
        "is_read": False,
        "created_at": datetime.utcnow(),
    })

# ── TEST ROUTE ──
@app.route('/api/test')
def test():
    return jsonify({"message": "EcoScholar backend is running!"})

# ── AUTH: LOGIN ──
@app.route('/api/login', methods=['POST'])
@limiter.limit("8 per minute")
def login():
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        db = get_db()
        user = db.users.find_one({"email": email})

        if not user:
            return jsonify({"error": "Invalid email or password"}), 401

        stored = user['password']
        is_hashed = stored.startswith(('pbkdf2:', 'scrypt:'))
        # Legacy plaintext password (pre-hashing) - compare directly, then upgrade it below.
        valid = check_password_hash(stored, password) if is_hashed else stored == password

        if not valid:
            return jsonify({"error": "Invalid email or password"}), 401

        if not is_hashed:
            db.users.update_one({"_id": user['_id']}, {"$set": {"password": generate_password_hash(password)}})

        user_payload = {
            "id": str(user['_id']),
            "full_name": user['full_name'],
            "email": user['email'],
            "role": user['role']
        }

        return jsonify({
            "message": "Login successful",
            "user": user_payload,
            "token": issue_token(user_payload)
        })

    except Exception:
        if DEBUG:
            raise
        return jsonify({"error": "Login failed"}), 500

# ── AUTH: LOGOUT ──
@app.route('/api/logout', methods=['POST'])
@require_auth
def logout():
    revoke_token(g.current_token)
    return jsonify({"message": "Logged out"})


# Personal-info fields collected at registration (mirrors ApplicationForm's Step 1) so an
# applicant doesn't have to retype them when they later submit an application - see
# get_profile() below, which hands these back for ApplicationForm to prefill itself with.
PROFILE_FIELDS = [
    'dob', 'gender', 'religion', 'citizenship', 'contactNumber', 'address',
    'fatherName', 'fatherOccupation', 'fatherEducation',
    'motherName', 'motherOccupation', 'motherEducation',
    'monthlyIncome', 'familySize', 'numSiblings', 'numSiblingsStudying',
    'housingSituation', 'hasOtherScholarship', 'otherScholarshipDetails',
]

def _is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == '')

# ── AUTH: REGISTER ──
@app.route("/api/register", methods=["POST"])
@limiter.limit("8 per minute")
def register():
    data = request.get_json()
    full_name = data.get("full_name", "").strip()
    email     = data.get("email", "").strip().lower()
    password  = data.get("password", "").strip()

    if not full_name or not email or not password:
        return jsonify({"error": "All fields are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    profile_data = {}
    for field in PROFILE_FIELDS:
        value = data.get(field, '')
        profile_data[field] = value.strip() if isinstance(value, str) else value

    required_profile_fields = [f for f in PROFILE_FIELDS if f != 'otherScholarshipDetails']
    missing = [f for f in required_profile_fields if _is_blank(profile_data.get(f))]
    if missing:
        return jsonify({"error": "All personal information fields are required"}), 400

    if profile_data['gender'] not in ('Male', 'Female'):
        return jsonify({"error": "Gender must be Male or Female"}), 400
    if profile_data['fatherEducation'] not in ml_education_map or profile_data['motherEducation'] not in ml_education_map:
        return jsonify({"error": "Invalid education level"}), 400
    if profile_data['fatherOccupation'] not in ml_occupation_categories or profile_data['motherOccupation'] not in ml_occupation_categories:
        return jsonify({"error": "Invalid occupation category"}), 400
    if profile_data['housingSituation'] not in ml_housing_situations:
        return jsonify({"error": "Invalid housing situation"}), 400
    if profile_data['hasOtherScholarship'] not in ('yes', 'no'):
        return jsonify({"error": "Invalid scholarship answer"}), 400
    if profile_data['hasOtherScholarship'] == 'yes' and _is_blank(profile_data.get('otherScholarshipDetails')):
        return jsonify({"error": "Please provide details about your other scholarship"}), 400

    try:
        profile_data['monthlyIncome'] = float(profile_data['monthlyIncome'])
        profile_data['familySize'] = int(profile_data['familySize'])
        profile_data['numSiblings'] = int(profile_data['numSiblings'])
        profile_data['numSiblingsStudying'] = int(profile_data['numSiblingsStudying'])
    except (TypeError, ValueError):
        return jsonify({"error": "Income, family size, and sibling counts must be numbers"}), 400

    try:
        db = get_db()

        if db.users.find_one({"email": email}):
            return jsonify({"error": "An account with this email already exists"}), 409

        result = db.users.insert_one({
            "full_name": full_name,
            "email": email,
            "password": generate_password_hash(password),
            "role": "student",
            "status": "active",
            "created_at": datetime.utcnow(),
            "privacy_consent": True,
            **profile_data,
        })

        user_payload = {"id": str(result.inserted_id), "full_name": full_name, "email": email, "role": "student"}

        return jsonify({
            "message": "Account created successfully",
            "user": user_payload,
            "token": issue_token(user_payload)
        }), 201

    except Exception:
        if DEBUG:
            raise
        return jsonify({"error": "Registration failed"}), 500

# ── AUTH: GET PROFILE (for pre-filling the application form) ──
@app.route('/api/profile', methods=['GET'])
@require_auth
def get_profile():
    db = get_db()
    user = db.users.find_one({"_id": oid(g.current_user['id'])})
    if not user:
        return jsonify({"error": "User not found"}), 404

    profile = {"fullName": user.get('full_name', ''), "email": user.get('email', '')}
    for field in PROFILE_FIELDS:
        value = user.get(field, '')
        if isinstance(value, float):
            profile[field] = str(int(value)) if value.is_integer() else str(value)
        elif isinstance(value, int):
            profile[field] = str(value)
        else:
            profile[field] = value or ''
    return jsonify({"profile": profile})

# ── GET ALL APPLICANTS ──
@app.route('/api/applicants', methods=['GET'])
@require_role('admin')
def get_applicants():
    try:
        db = get_db()
        applicants = [serialize_applicant(a) for a in db.applicants.find({})]
        return jsonify({"applicants": applicants})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET SINGLE APPLICANT ──
@app.route('/api/applicants/<applicant_id>', methods=['GET'])
@require_role('admin')
def get_applicant(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        doc = db.applicants.find_one({"_id": applicant_oid})
        if not doc:
            return jsonify({"applicant": None, "academic": None, "documents": [], "application": None})

        flat = serialize_applicant(doc)
        return jsonify({
            "applicant": flat,
            "academic": doc.get('academic'),
            "documents": [serialize_document(d) for d in doc.get('documents', [])],
            "application": doc.get('application')
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SUBMIT APPLICATION ──
@app.route('/api/apply', methods=['POST'])
@require_auth
def submit_application():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data received"}), 400

    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        db = get_db()

        # ── Check duplicate by EMAIL ──
        existing = db.applicants.find_one({"email": email})
        duplicate_reason = 'email' if existing else None

        # ── Check duplicate by FULL NAME + DATE OF BIRTH ──
        if not existing:
            full_name = data.get('fullName', '').strip()
            dob = data.get('dob', '').strip()
            if full_name and dob:
                existing = db.applicants.find_one({
                    "full_name": {"$regex": f"^{re.escape(full_name)}$", "$options": "i"},
                    "date_of_birth": dob
                })
                if existing:
                    duplicate_reason = 'name_and_birthdate'

        if existing:
            existing_app = {
                "id": str(existing['_id']),
                "application_status": (existing.get('application') or {}).get('status'),
                "submitted_at": iso((existing.get('application') or {}).get('submitted_at')),
                "course": (existing.get('academic') or {}).get('course'),
                "gpa": (existing.get('academic') or {}).get('gpa'),
            }
            try:
                db.duplicate_flags.insert_one({
                    "applicant_id": existing['_id'],
                    "duplicate_of_id": existing['_id'],
                    "reason": duplicate_reason,
                    "flagged_at": datetime.utcnow(),
                    "resolved": False,
                })
            except Exception:
                pass

            return jsonify({
                "error": "A duplicate application was detected.",
                "duplicate_reason": duplicate_reason,
                "existing_application": existing_app
            }), 409

        # Validate required fields
        required_fields = [
            'fullName', 'email', 'contactNumber', 'address',
            'gender', 'dob', 'religion', 'citizenship',
            'fatherName', 'fatherOccupation', 'fatherEducation',
            'motherName', 'motherOccupation', 'motherEducation',
            'monthlyIncome', 'familySize', 'numSiblings', 'numSiblingsStudying',
            'housingSituation',
            'school', 'schoolAddress', 'course',
            'yearLevel', 'gpa', 'academicYear', 'semester'
        ]
        for field in required_fields:
            if data.get(field) in (None, ''):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        if data['gender'] not in ('Male', 'Female'):
            return jsonify({"error": "Gender must be Male or Female"}), 400
        if data['fatherEducation'] not in ml_education_map or data['motherEducation'] not in ml_education_map:
            return jsonify({"error": "Invalid education level"}), 400
        if data['fatherOccupation'] not in ml_occupation_categories or data['motherOccupation'] not in ml_occupation_categories:
            return jsonify({"error": "Invalid occupation category"}), 400
        if data['housingSituation'] not in ml_housing_situations:
            return jsonify({"error": "Invalid housing situation"}), 400

        has_other = data.get('hasOtherScholarship', 'no') == 'yes'
        other_details = data.get('otherScholarshipDetails', '')
        now = datetime.utcnow()

        applicant_doc = {
            "user_id": oid(g.current_user['id']),
            "full_name": data['fullName'],
            "email": email,
            "contact_number": data['contactNumber'],
            "address": data['address'],
            "gender": data['gender'],
            "date_of_birth": data['dob'],
            "religion": data['religion'],
            "citizenship": data['citizenship'],
            "father_name": data['fatherName'],
            "father_occupation": data['fatherOccupation'],
            "father_education": data['fatherEducation'],
            "mother_name": data['motherName'],
            "mother_occupation": data['motherOccupation'],
            "mother_education": data['motherEducation'],
            "monthly_income": float(data['monthlyIncome']),
            "family_size": int(data['familySize']),
            "num_siblings": int(data['numSiblings']),
            "num_siblings_studying": int(data['numSiblingsStudying']),
            "housing_situation": data['housingSituation'],
            "barangay": None,
            "ml_score": 0,
            "ml_status": "Pending",
            "created_at": now,
            "privacy_consent": True,
            "has_other_scholarship": has_other,
            "other_scholarship_details": other_details,
            "academic": {
                "school": data['school'],
                "school_address": data['schoolAddress'],
                "course": data['course'],
                "year_level": data['yearLevel'],
                "gpa": float(data['gpa']),
                "academic_year": data['academicYear'],
                "semester": data['semester'],
            },
            "application": {
                "application_type": data.get('applicationType', 'General'),
                "status": "Newly Submitted",
                "submitted_at": now,
                "reviewed_at": None,
                "reviewed_by_name": None,
                "remarks": None,
            },
            "documents": [],
            "audit_trail": [],
        }

        result = db.applicants.insert_one(applicant_doc)

        return jsonify({
            "message": "Application submitted successfully!",
            "applicant_id": str(result.inserted_id)
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── UPDATE APPLICATION STATUS ──
@app.route('/api/applications/<applicant_id>/status', methods=['PUT'])
@require_role('admin')
def update_status(applicant_id):
    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    data = request.get_json()
    status = data.get('status')
    reviewed_by = g.current_user.get('email', 'Admin')
    old_status = data.get('old_status', '')
    remarks = data.get('remarks', '')

    if not status:
        return jsonify({"error": "Status is required"}), 400

    if status in ('Approved', 'Rejected'):
        return jsonify({
            "error": "Approval/rejection is decided by the eligibility model, not set manually. "
                     "Use the verify-documents action instead."
        }), 400

    notif_message = STATUS_MESSAGES.get(status, f"Your application status was updated to '{status}'.")
    notif_type = STATUS_NOTIF_TYPE.get(status, 'status_update')

    try:
        db = get_db()
        now = datetime.utcnow()

        applicant = db.applicants.find_one({"_id": applicant_oid})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        db.applicants.update_one(
            {"_id": applicant_oid},
            {
                "$set": {
                    "application.status": status,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Status changed to {status}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "admin",
                        "old_status": old_status,
                        "new_status": status,
                        "remarks": remarks,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        create_notification(db, notify_user_id, applicant_oid, notif_message, notif_type)

        return jsonify({
            "message": f"Application {status} successfully",
            "applicant_id": applicant_id,
            "status": status,
            "reviewed_by": reviewed_by
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── VERIFY DOCUMENTS & LET THE MODEL DECIDE ELIGIBILITY ──
@app.route('/api/applications/<applicant_id>/verify', methods=['PUT'])
@require_role('admin')
def verify_and_decide(applicant_id):
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    reviewed_by = g.current_user.get('email', 'Admin')

    try:
        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        row, ok = build_feature_row(applicant)
        if not ok:
            return jsonify({
                "error": "This applicant was submitted before the updated eligibility "
                         "model and can't be auto-decided. Ask them to resubmit using "
                         "the current application form."
            }), 409

        ml_score, ml_status = score_with_model(row)
        final_status = 'Approved' if ml_status == 'Eligible' else 'Rejected'
        old_status = (applicant.get('application') or {}).get('status', '')
        now = datetime.utcnow()

        db.applicants.update_one(
            {"_id": applicant_oid},
            {
                "$set": {
                    "application.status": final_status,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                    "ml_score": ml_score,
                    "ml_status": ml_status,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Documents verified by admin - model decided: {final_status}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "admin",
                        "old_status": old_status,
                        "new_status": final_status,
                        "remarks": f'ML score: {ml_score} ({ml_status})',
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        create_notification(
            db, notify_user_id, applicant_oid,
            STATUS_MESSAGES[final_status], STATUS_NOTIF_TYPE[final_status]
        )

        return jsonify({
            "applicant_id": applicant_id,
            "status": final_status,
            "ml_score": ml_score,
            "ml_status": ml_status,
            "regressor_cutoff": ml_regressor_cutoff,
            "breakdown": build_score_breakdown(row, applicant),
            "reviewed_by": reviewed_by
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET AUDIT TRAIL ──
@app.route('/api/audit-trail/<applicant_id>', methods=['GET'])
@require_role('admin')
def get_audit_trail(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid}, {"audit_trail": 1})
        trail = (applicant or {}).get('audit_trail', [])
        trail = sorted(trail, key=lambda t: t.get('performed_at') or datetime.min, reverse=True)
        return jsonify({"trail": [serialize_audit_entry(t) for t in trail]})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET NOTIFICATIONS ──
@app.route('/api/notifications', methods=['GET'])
@require_auth
def get_notifications():
    try:
        db = get_db()
        user_oid = oid(g.current_user['id'])
        cursor = db.notifications.find({"user_id": user_oid}).sort("created_at", -1).limit(30)
        notifications = [serialize_notification(n) for n in cursor]
        unread_count = db.notifications.count_documents({"user_id": user_oid, "is_read": False})
        return jsonify({"notifications": notifications, "unread_count": unread_count})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── MARK NOTIFICATION READ ──
@app.route('/api/notifications/<notification_id>/read', methods=['PUT'])
@require_auth
def mark_notification_read(notification_id):
    try:
        notif_oid = oid(notification_id)
        if not notif_oid:
            return jsonify({"error": "Invalid notification id"}), 400

        db = get_db()
        db.notifications.update_one(
            {"_id": notif_oid, "user_id": oid(g.current_user['id'])},
            {"$set": {"is_read": True}}
        )
        return jsonify({"message": "Marked as read"})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── MARK ALL NOTIFICATIONS READ ──
@app.route('/api/notifications/read-all', methods=['PUT'])
@require_auth
def mark_all_notifications_read():
    try:
        db = get_db()
        db.notifications.update_many(
            {"user_id": oid(g.current_user['id']), "is_read": False},
            {"$set": {"is_read": True}}
        )
        return jsonify({"message": "All notifications marked as read"})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── UPLOAD DOCUMENT ──
@app.route('/api/upload', methods=['POST'])
@require_auth
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    applicant_id = request.form.get('applicant_id', '')
    document_name = request.form.get('document_name', '')

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant_id"}), 400

    safe_document_name = secure_filename(document_name)
    if not safe_document_name:
        return jsonify({"error": "Invalid document_name"}), 400

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{applicant_id}_{safe_document_name}_{filename}"

        try:
            db = get_db()
            now = datetime.utcnow()

            applicant = db.applicants.find_one(
                {"_id": applicant_oid, "documents.document_name": document_name},
                {"documents.$": 1}
            )
            old_gridfs_id = None
            if applicant and applicant.get('documents'):
                old_gridfs_id = applicant['documents'][0].get('gridfs_id')

            new_gridfs_id = _fs.put(
                file.read(), filename=unique_filename,
                content_type=safe_mime_for(unique_filename)
            )

            result = db.applicants.update_one(
                {"_id": applicant_oid, "documents.document_name": document_name},
                {"$set": {
                    "documents.$.gridfs_id": new_gridfs_id,
                    "documents.$.status": "Uploaded",
                    "documents.$.uploaded_at": now,
                }}
            )

            if result.matched_count == 0:
                db.applicants.update_one(
                    {"_id": applicant_oid},
                    {"$push": {"documents": {
                        "document_name": document_name,
                        "gridfs_id": new_gridfs_id,
                        "status": "Uploaded",
                        "uploaded_at": now,
                    }}}
                )

            # Clean up the previous file now that the new one is safely stored
            if old_gridfs_id:
                try:
                    _fs.delete(old_gridfs_id)
                except Exception:
                    pass

            return jsonify({
                "message": "File uploaded successfully",
                "filename": unique_filename
            })

        except Exception as e:
            app.logger.error(str(e))
            if DEBUG:
                raise
            return jsonify({"error": "Something went wrong. Please try again."}), 500

    return jsonify({"error": "File type not allowed"}), 400

# ── OCR VERIFY DOCUMENT ──
@app.route('/api/verify-document', methods=['POST'])
@require_auth
def verify_document_route():
    data = request.get_json()
    applicant_id = data.get('applicant_id')
    document_name = data.get('document_name')

    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant_id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid})
        if not applicant:
            return jsonify({"error": "Document not found"}), 404

        doc = next((d for d in applicant.get('documents', []) if d.get('document_name') == document_name), None)
        if not doc or not doc.get('gridfs_id'):
            return jsonify({"error": "Document not found"}), 404

        try:
            grid_out = _fs.get(doc['gridfs_id'])
        except gridfs.errors.NoFile:
            return jsonify({"error": "File not found on server"}), 404

        # OCR needs a real file path, so write GridFS bytes to a scratch temp
        # file for the duration of processing only - nothing is kept on disk.
        ext = os.path.splitext(grid_out.filename)[1] or '.bin'
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_verify_{applicant_id}{ext}")
        with open(temp_path, 'wb') as f:
            f.write(grid_out.read())

        try:
            academic = applicant.get('academic') or {}
            applicant_data = {
                "full_name": applicant.get('full_name', ''),
                "school": academic.get('school', ''),
                "course": academic.get('course', ''),
                "address": applicant.get('address') or '',
            }

            extracted_text = extract_text(temp_path)
            result = verify_document(document_name, extracted_text, applicant_data)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        db.applicants.update_one(
            {"_id": applicant_oid, "documents.document_name": document_name},
            {"$set": {"documents.$.status": "Uploaded"}}
        )

        return jsonify(result)

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET APPLICANT DOCUMENTS ──
@app.route('/api/documents/<applicant_id>', methods=['GET'])
@require_auth
def get_documents(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid}, {"documents": 1})
        documents = (applicant or {}).get('documents', [])
        return jsonify({"documents": [serialize_document(d) for d in documents]})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── VIEW A SPECIFIC UPLOADED DOCUMENT FILE ──
@app.route('/api/documents/<applicant_id>/view', methods=['GET'])
@require_auth
def view_document_file(applicant_id):
    document_name = request.args.get('document_name')
    if not document_name:
        return jsonify({"error": "document_name is required"}), 400

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    try:
        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        is_owner = applicant.get('user_id') and str(applicant['user_id']) == g.current_user['id']
        if g.current_user.get('role') != 'admin' and not is_owner:
            return jsonify({"error": "Forbidden"}), 403

        doc = next((d for d in applicant.get('documents', []) if d.get('document_name') == document_name), None)
        if not doc or not doc.get('gridfs_id'):
            return jsonify({"error": "Document not found"}), 404

        try:
            grid_out = _fs.get(doc['gridfs_id'])
        except gridfs.errors.NoFile:
            return jsonify({"error": "File not found on server"}), 404

        return send_file(
            grid_out,
            mimetype=safe_mime_for(grid_out.filename),
            download_name=grid_out.filename,
            as_attachment=False
        )
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET STUDENT APPLICATION BY EMAIL ──
@app.route('/api/student/application', methods=['GET'])
@require_auth
def get_student_application():
    email = request.args.get('email')

    if not email:
        return jsonify({"error": "Email is required"}), 400

    if g.current_user.get('role') != 'admin' and email.strip().lower() != g.current_user.get('email', '').lower():
        return jsonify({"error": "Forbidden"}), 403

    try:
        db = get_db()
        applicant = db.applicants.find_one(
            {"email": email.strip().lower()},
            sort=[("_id", -1)]
        )

        if not applicant:
            return jsonify({"application": None})

        return jsonify({
            "application": serialize_applicant(applicant),
            "documents": [serialize_document(d) for d in applicant.get('documents', [])]
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET DUPLICATE FLAGS ──
@app.route('/api/duplicate-flags', methods=['GET'])
@require_role('admin')
def get_duplicate_flags():
    try:
        db = get_db()
        flags = []
        for f in db.duplicate_flags.find({"resolved": False}).sort("flagged_at", -1):
            a1 = db.applicants.find_one({"_id": f.get('applicant_id')}) or {}
            a2 = db.applicants.find_one({"_id": f.get('duplicate_of_id')}) or {}
            flags.append({
                "id": str(f['_id']),
                "applicant_id": str(f['applicant_id']) if f.get('applicant_id') else None,
                "duplicate_of_id": str(f['duplicate_of_id']) if f.get('duplicate_of_id') else None,
                "reason": f.get('reason'),
                "flagged_at": iso(f.get('flagged_at')),
                "resolved": bool(f.get('resolved', False)),
                "applicant_name": a1.get('full_name'),
                "applicant_email": a1.get('email'),
                "applicant_dob": a1.get('date_of_birth'),
                "duplicate_of_name": a2.get('full_name'),
                "duplicate_of_email": a2.get('email'),
            })
        return jsonify({"flags": flags})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── RESOLVE DUPLICATE FLAG ──
@app.route('/api/duplicate-flags/<flag_id>/resolve', methods=['PUT'])
@require_role('admin')
def resolve_flag(flag_id):
    try:
        flag_oid = oid(flag_id)
        if not flag_oid:
            return jsonify({"error": "Invalid flag id"}), 400

        db = get_db()
        db.duplicate_flags.update_one({"_id": flag_oid}, {"$set": {"resolved": True}})
        return jsonify({"message": "Flag resolved"})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET DASHBOARD STATS ──
@app.route('/api/stats', methods=['GET'])
@require_role('admin')
def get_stats():
    try:
        db = get_db()
        total = db.applicants.count_documents({})
        approved = db.applicants.count_documents({"application.status": "Approved"})
        rejected = db.applicants.count_documents({"application.status": "Rejected"})
        under_review = total - approved - rejected

        return jsonify({
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "under_review": under_review
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCORE SINGLE APPLICANT ──
@app.route('/api/score-applicant/<applicant_id>', methods=['GET'])
@require_role('admin')
def score_applicant(applicant_id):
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid})

        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        row, ok = build_feature_row(applicant)
        if not ok:
            return jsonify({
                "error": "This applicant was submitted before the updated eligibility "
                         "model and can't be scored with it. Ask them to resubmit using "
                         "the current application form."
            }), 409

        ml_score, ml_status = score_with_model(row)

        db.applicants.update_one(
            {"_id": applicant_oid},
            {"$set": {"ml_score": ml_score, "ml_status": ml_status}}
        )

        return jsonify({
            "applicant_id": applicant_id,
            "ml_score": ml_score,
            "ml_status": ml_status,
            "regressor_cutoff": ml_regressor_cutoff,
            "breakdown": build_score_breakdown(row, applicant)
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCORE AND RANK ALL APPLICANTS ──
@app.route('/api/rank-applicants', methods=['GET'])
@require_role('admin')
def rank_applicants():
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    try:
        db = get_db()
        applicants = list(db.applicants.find({
            "application.status": {"$nin": ["Rejected", "Newly Submitted"]}
        }))

        ranked = []
        for applicant in applicants:
            try:
                row, ok = build_feature_row(applicant)
                if not ok:
                    continue  # predates this model - see schema/ml_model.md

                ml_score, ml_status = score_with_model(row)
                academic = applicant.get('academic') or {}

                ranked.append({
                    'id': str(applicant['_id']),
                    'full_name': applicant['full_name'],
                    'course': academic.get('course'),
                    'gpa': row['gpa'],
                    'monthly_income': applicant.get('monthly_income'),
                    'family_size': row['family_size'],
                    'housing_situation': applicant.get('housing_situation'),
                    'has_other_scholarship': row['has_other_scholarship'],
                    'application_status': (applicant.get('application') or {}).get('status'),
                    'ml_score': ml_score,
                    'ml_status': ml_status
                })
            except Exception:
                continue

        # Sort by ML score descending
        ranked.sort(key=lambda x: x['ml_score'], reverse=True)
        for i, r in enumerate(ranked):
            r['rank'] = i + 1

        return jsonify({"ranked": ranked})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── OCR AUTO-FILL ──
@app.route('/api/ocr-autofill', methods=['POST'])
@require_auth
def ocr_autofill():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    doc_type = request.form.get('doc_type', '')

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    try:
        # Save temp file
        filename = secure_filename(file.filename)
        temp_path = os.path.join('uploads', f'temp_{filename}')
        file.save(temp_path)

        # Extract text using OCR
        extracted_text = extract_text(temp_path)

        # Clean up temp file
        os.remove(temp_path)

        # Parse extracted fields
        fields = parse_document_fields(extracted_text, doc_type)

        return jsonify({
            "success": True,
            "extracted_text": extracted_text[:500],
            "fields": fields,
            "doc_type": doc_type
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

if __name__ == '__main__':
    app.run(debug=DEBUG)
