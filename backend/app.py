import re
import io
import secrets
import hashlib
import threading
import imagehash
import pdf2image
import requests
from PIL import Image
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


# Load .env relative to this file, not the process's working directory - otherwise
# whoever launches the server from a different cwd silently gets no .env at all,
# SECRET_KEY falls back to the dev default, and every previously issued session
# token stops verifying (looks like random, unexplained logouts).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-insecure-key'
    else:
        raise RuntimeError('SECRET_KEY environment variable must be set in production')

TOKEN_MAX_AGE = 60 * 60 * 12  # 12 hours
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-auth')

RESET_TOKEN_MAX_AGE = 30 * 60  # 30 minutes
_reset_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-reset')

# Proves the applicant actually controls the email address before they ever see the
# admin-request form - issued only after they type the correct OTP sent to that
# address, so (unlike the old click-a-link version) this is used within the same
# sitting rather than "whenever they next check email" - a shorter window is safer.
ADMIN_APPLY_TOKEN_MAX_AGE = 30 * 60  # 30 minutes
_admin_apply_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-admin-apply')

# Email-verification OTP for new student registrations. A short numeric code
# rather than a signed token, since the user types it in by hand. Stored in
# plaintext (unlike passwords) - it's single-use, expires quickly, and attempts
# are capped, so the threat model that justifies password hashing doesn't apply.
OTP_LENGTH = 6
OTP_MAX_AGE = 10 * 60  # 10 minutes
OTP_MAX_ATTEMPTS = 5

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
# Sent via Resend's HTTP API (not raw SMTP) because Render's free-tier web
# services block outbound traffic to SMTP ports 25/465/587 - the HTTP API
# only needs normal outbound HTTPS (443), which is never blocked.
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'EcoScholar')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')

def send_email(to_email, subject, html_body):
    """Best-effort email send via the Resend HTTP API. Returns True/False and
    never raises - callers must not let a failed send change what's shown to
    the requester, since that would leak whether an email address exists in
    the system."""
    if not RESEND_API_KEY or not SMTP_FROM_EMAIL:
        app.logger.warning('Email not sent (RESEND_API_KEY/SMTP_FROM_EMAIL not configured): %s', subject)
        return False
    try:
        resp = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {RESEND_API_KEY}'},
            json={
                'from': f'{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>',
                'to': [to_email],
                'subject': subject,
                'html': html_body,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        app.logger.error('Email send failed: %s', str(e))
        return False

def send_email_async(to_email, subject, html_body):
    """Fires the SMTP send on a background thread so the request that triggered it
    (approve, add-admin, forgot-password...) never waits on a mail server round-trip.
    Fire-and-forget: nothing here can report success/failure back to the caller,
    which matches how every existing caller already treats send_email's result."""
    threading.Thread(target=send_email, args=(to_email, subject, html_body), daemon=True).start()

# Fixed dropdown options the application form offers - independent of whichever ML
# model is deployed behind it, since these define what an applicant can select, not
# how a particular model encodes them internally. Keep in sync with schema/ml_model.md.
DEFAULT_EDUCATION_MAP = {'None': 0, 'Elementary': 1, 'High School': 2, 'Vocational': 3, 'College': 4, 'Postgraduate': 5}
DEFAULT_OCCUPATION_CATEGORIES = ['Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade', 'Office/Clerical', 'Professional', 'Deceased/Not Applicable']
DEFAULT_HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives', 'Informal settler']
ml_education_map = DEFAULT_EDUCATION_MAP
ml_occupation_categories = DEFAULT_OCCUPATION_CATEGORIES
ml_housing_situations = DEFAULT_HOUSING_SITUATIONS

# The form's "Postgraduate" (no space) doesn't match the trained model's own
# survey-derived label "Post Graduate" (with a space) - translated here rather than
# changing the form's wording, which is a UI decision independent of the training data.
EDUCATION_LABEL_FIX = {'Postgraduate': 'Post Graduate'}

def income_to_bracket(income):
    """Buckets a raw monthly income number into the label the model's
    income_bracket_map expects. The model was trained on bracketed survey data,
    but our form collects an exact number, so this converts one to the other.
    Boundaries/labels must match ecoscholar_encoding_maps.json's income_bracket_map
    exactly."""
    if income is None:
        return None
    income = float(income)
    if income < 5000:
        return "Below ₱ 5,000"
    if income <= 10000:
        return "₱ 5,001 - ₱ 10,000"
    if income <= 15000:
        return "₱ 10,000 - ₱ 15,000"
    if income <= 20000:
        return "₱ 15,000 - ₱ 20,000"
    return "₱ 20,000 Above"

# ── LOAD ML MODEL (EcoScholar classifier + regressor, trained per Chapter III) ──
# ecoscholar_predict.py loads its .joblib/.json files at import time, so a missing or
# corrupt model file raises here - caught the same way the old bundle load was, so
# scoring degrades gracefully without disabling application submission.
try:
    from ecoscholar_predict import score_applicant as _ml_predict, ELIGIBILITY_CUTOFF as ml_regressor_cutoff
    ml_classifier = True   # sentinel only - the real model objects live inside ecoscholar_predict
    ml_regressor = True
    print("ML model loaded successfully! (EcoScholar classifier + regressor)")
except Exception as e:
    _ml_predict = None
    ml_classifier = None
    ml_regressor = None
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
    """Build the flat {field: value} dict ecoscholar_predict.score_applicant()
    expects, mapped from our MongoDB applicant schema. Returns (row, True) or
    (None, False) if this applicant predates the fields the model needs."""
    if any(applicant.get(f) is None for f in ML_REQUIRED_FIELDS):
        return None, False

    academic = applicant.get('academic') or {}
    father_edu = applicant.get('father_education')
    mother_edu = applicant.get('mother_education')
    row = {
        'sex': applicant.get('gender'),
        'household_size': applicant.get('family_size'),
        'siblings': applicant.get('num_siblings'),
        'siblings_studying': applicant.get('num_siblings_studying'),
        'father_education': EDUCATION_LABEL_FIX.get(father_edu, father_edu),
        'mother_education': EDUCATION_LABEL_FIX.get(mother_edu, mother_edu),
        'father_occupation': applicant.get('father_occupation'),
        'mother_occupation': applicant.get('mother_occupation'),
        'monthly_income_bracket': income_to_bracket(applicant.get('monthly_income')),
        'housing_situation': applicant.get('housing_situation'),
        'gwa': academic.get('gpa'),
        'holds_other_scholarship': bool(applicant.get('has_other_scholarship')),
    }
    return row, True

def score_with_model(row):
    """Run the trained EcoScholar classifier (eligibility) and regressor (ranking
    score) on a feature row built by build_feature_row(). Returns (ml_score, ml_status)."""
    result = _ml_predict(row)
    ml_status = 'Eligible' if result['eligible'] else 'Not Eligible'
    return result['priority_score'], ml_status

def build_score_breakdown(applicant):
    """Simple heuristic breakdown for the admin UI progress bars, read straight from
    the applicant's stored raw fields - a rough visual aid, not the model's actual
    internal feature attribution, and intentionally independent of whichever model
    is deployed."""
    academic = applicant.get('academic') or {}
    gpa = float(academic.get('gpa') or 0)
    income = float(applicant.get('monthly_income') or 0)
    family_size = int(applicant.get('family_size') or 0)
    father_edu_level = ml_education_map.get(applicant.get('father_education'), 0)
    mother_edu_level = ml_education_map.get(applicant.get('mother_education'), 0)

    gpa_s = round(max(0, min(100, gpa)), 1)
    inc_s = round(max(0, min(100, (1 - min(income, 100000) / 100000) * 100)), 1)
    fam_s = round(min(100, max(0, (family_size - 2) / 8 * 100)), 1)
    edu_avg = (father_edu_level + mother_edu_level) / 2
    edu_s = round(max(0, min(100, (5 - edu_avg) / 5 * 100)), 1)
    housing_need = {'Owned': 20, 'Rented': 60, 'Living with relatives': 80, 'Informal settler': 100}
    house_s = housing_need.get(applicant.get('housing_situation'), 50)

    return [
        {"label": "GWA Score", "value": gpa_s, "color": "#10b981"},
        {"label": "Income Need Score", "value": inc_s, "color": "#0891b2"},
        {"label": "Family Size Score", "value": fam_s, "color": "#2563eb"},
        {"label": "Parental Education Need", "value": edu_s, "color": "#f59e0b"},
        {"label": "Housing Need Score", "value": house_s, "color": "#ec4899"},
    ]

# Every value in build_score_breakdown() is oriented so that higher = more favorable
# for approval (better grades, lower income, more financial need, etc.), so the
# lowest-scoring component(s) are a reasonable plain-language explanation for a
# rejection - not the model's actual internal feature attribution, same caveat as
# build_score_breakdown() itself.
REJECTION_REASON_TEXT = {
    "GWA Score": "academic performance (GWA) was below the typical threshold for approved applicants",
    "Income Need Score": "estimated household income was higher than typical for approved applicants",
    "Family Size Score": "household/family size was smaller than typical for approved applicants",
    "Parental Education Need": "parents' education level was higher than typical for approved applicants, indicating comparatively lower financial need",
    "Housing Need Score": "housing situation showed less financial need than typical for approved applicants",
}

def generate_rejection_reason(breakdown):
    weakest = sorted(breakdown, key=lambda b: b['value'])[:2]
    reasons = [REJECTION_REASON_TEXT.get(b['label'], b['label']) for b in weakest]
    return "Primary factors: " + "; and ".join(reasons) + "."

# ── ACCEPTED APPLICANT LIMIT ──
DEFAULT_APPLICANT_LIMIT = 20

def get_applicant_limit(db):
    doc = db.settings.find_one({"_id": "global"})
    return (doc or {}).get("max_accepted", DEFAULT_APPLICANT_LIMIT)

# ── RESULT VISIBILITY (Approved/Rejected status + eligibility details) ──
# An LGU can hold back students seeing they've been decided until a chosen date/time
# (results_visible_after), with a manual override that always wins when set: True
# forces results visible early, False force-hides them past their own release date.
# Not configuring either means "always visible" - the same behavior as before this
# setting existed, so a deployment that never touches it sees no change.
GENERIC_REVIEWED_MESSAGE = (
    "Your application has finished review. Results will be available once released "
    "by the program - check back or sign in again later."
)

def are_results_visible(db):
    settings = db.settings.find_one({"_id": "global"}) or {}
    override = settings.get('results_visible_override')
    if override is not None:
        return bool(override)
    visible_after = settings.get('results_visible_after')
    if not visible_after:
        return True
    return datetime.utcnow() >= visible_after

# ── PROGRAM CYCLES (archive-then-clear reset) ──
# A "cycle" is a scholarship program run. Applicants carry a cycle_id; the current
# (live) cycle is whichever program_cycles document has closed_at: None - at most one
# at a time. Before the very first reset, no program_cycles documents exist at all and
# get_current_cycle_id() returns None, which every "current cycle" query below matches
# against applicants with no cycle_id field - i.e. every applicant that predates this
# feature is implicitly "the current cycle" until the first reset closes it out. This
# is exactly the "implicit Cycle 0" backward-compatibility the feature spec calls for,
# with no need to backfill millions of old documents with an explicit id.
def get_current_cycle(db):
    return db.program_cycles.find_one({"closed_at": None})

def get_current_cycle_id(db):
    cycle = get_current_cycle(db)
    return cycle["_id"] if cycle else None

def serialize_cycle(c, applicant_count=None):
    return {
        "id": str(c["_id"]),
        "label": c.get("label"),
        "started_at": iso(c.get("started_at")),
        "closed_at": iso(c.get("closed_at")),
        "started_by": c.get("started_by"),
        "closed_by": c.get("closed_by"),
        "is_current": c.get("closed_at") is None,
        "applicant_count": applicant_count,
    }

def do_program_reset(db, performed_by, new_label=None):
    """Archives the current cycle (or, on a deployment's very first reset, retroactively
    records the implicit pre-tracking cycle as 'Cycle 0') and opens a new one. Nothing is
    deleted - applicants/documents/audit trails all stay exactly where they are; they
    just stop matching get_current_cycle_id() once their cycle's closed_at is set, which
    is what every "current cycle only" query in this file filters on."""
    now = datetime.utcnow()
    current = get_current_cycle(db)
    if current:
        db.program_cycles.update_one(
            {"_id": current["_id"]},
            {"$set": {"closed_at": now, "closed_by": performed_by}}
        )
    elif db.applicants.count_documents({"cycle_id": None}) > 0:
        # First-ever reset with pre-existing data: give that data a real (now-closed)
        # cycle record, and backfill it onto every cycle_id: None applicant so the
        # data model stays consistent going forward - without this, those applicants
        # would show up as an orphaned "0 applicants" Cycle 0 record *and* a separate
        # legacy bucket in list_program_cycles(), both pointing at the same data.
        cycle0_id = db.program_cycles.insert_one({
            "label": "Cycle 0 (before cycle tracking)",
            "started_at": None,
            "closed_at": now,
            "started_by": None,
            "closed_by": performed_by,
        }).inserted_id
        db.applicants.update_many({"cycle_id": None}, {"$set": {"cycle_id": cycle0_id}})

    cycle_count = db.program_cycles.count_documents({})
    new_cycle = {
        "label": (new_label or '').strip() or f"Cycle {cycle_count + 1}",
        "started_at": now,
        "closed_at": None,
        "started_by": performed_by,
        "closed_by": None,
    }
    new_cycle_id = db.program_cycles.insert_one(new_cycle).inserted_id

    # A fresh cycle starts with results hidden by default rather than silently
    # inheriting whatever visibility state the outgoing cycle was left in - an LGU
    # that forgets to re-hide results for the new batch would otherwise leak new
    # decisions the moment the first one is verified.
    db.settings.update_one(
        {"_id": "global"},
        {"$set": {"results_visible_override": False}, "$unset": {"results_visible_after": ""}},
        upsert=True
    )

    return new_cycle_id

def recompute_approvals(db, limit, reviewed_by='System'):
    """Keeps 'Approved' as exactly the top-`limit` applicants (by ml_score) among
    everyone the classifier found Eligible **in the current cycle**. Run after every
    verify decision and whenever the limit changes, since either can promote or bump
    applicants who weren't directly touched by that specific action - a newly-verified
    strong applicant can displace a previously-Approved weaker one, and raising the
    limit can promote applicants who were waiting just below the old cutoff. Scoped to
    the current cycle so re-verifying someone this cycle can never reach back and flip
    an already-archived cycle's decisions."""
    eligible = list(db.applicants.find(
        # A withdrawn applicant can still carry ml_status: "Eligible" from a
        # prior verification - excluded here so recompute never overwrites
        # "Withdrawn" back to Approved/Rejected.
        {"ml_status": "Eligible", "application.status": {"$ne": "Withdrawn"}, "cycle_id": get_current_cycle_id(db)},
        {"ml_score": 1, "application": 1, "full_name": 1, "email": 1, "user_id": 1}
    ))
    eligible.sort(key=lambda a: a.get('ml_score', 0), reverse=True)

    now = datetime.utcnow()
    results_visible = are_results_visible(db)
    for i, applicant in enumerate(eligible):
        should_be = 'Approved' if i < limit else 'Rejected'
        current = (applicant.get('application') or {}).get('status')
        if current == should_be:
            continue

        if should_be == 'Approved':
            remarks = f'A scholarship slot became available (applicant limit: {limit}).'
            notif_message = (STATUS_MESSAGES['Approved'] + ' ' + remarks) if results_visible else GENERIC_REVIEWED_MESSAGE
        else:
            remarks = (
                f'This applicant met the eligibility criteria, but the accepted applicant '
                f'limit ({limit}) was reached by higher-ranked applicants.'
            )
            notif_message = (
                f'Your application met the eligibility criteria, but the accepted applicant '
                f'limit ({limit}) has been reached by higher-ranked applicants. You have been '
                f'waitlisted and may be promoted automatically if a slot opens up.'
            ) if results_visible else GENERIC_REVIEWED_MESSAGE

        db.applicants.update_one(
            {"_id": applicant["_id"]},
            {
                "$set": {
                    "application.status": should_be,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                    "application.rejection_reason": remarks if should_be == 'Rejected' else None,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Auto re-ranked due to applicant limit - now {should_be}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "system",
                        "old_status": current,
                        "new_status": should_be,
                        "remarks": remarks,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        create_notification(
            db, notify_user_id, applicant,
            notif_message, STATUS_NOTIF_TYPE[should_be]
        )

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

def compute_perceptual_hash(file_bytes, filename):
    """Visual fingerprint of a document's first page, used to catch near-identical
    files (re-saved, re-compressed, screenshotted, lightly cropped) that a byte-for-byte
    SHA-256 comparison would miss entirely since re-encoding changes every byte. Returns
    None on any failure (corrupt file, unsupported content) - this is a best-effort
    fraud signal layered on top of the upload, never a reason to reject the upload."""
    try:
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext == 'pdf':
            pages = pdf2image.convert_from_bytes(file_bytes, dpi=150, first_page=1, last_page=1)
            if not pages:
                return None
            image = pages[0]
        else:
            image = Image.open(io.BytesIO(file_bytes))
        return str(imagehash.phash(image))
    except Exception:
        return None

# Hamming distance threshold (out of 64 bits) below which two documents are considered
# a near-duplicate. Chosen conservatively - real re-uploads of the same scanned/photographed
# page (recompressed, lightly cropped, mild lighting shift) typically land under 6-8;
# two different documents of the same type (e.g. two different students' report cards)
# routinely score 20+.
NEAR_DUPLICATE_THRESHOLD = 8

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
# Registration email-verification codes - same absolute-expiry TTL pattern.
_mongo_db.otps.create_index("expires_at", expireAfterSeconds=0)

def get_db():
    return _mongo_db

def generate_otp_code():
    return ''.join(secrets.choice('0123456789') for _ in range(OTP_LENGTH))

OTP_COPY = {
    "register": {
        "subject": "Verify your EcoScholar account",
        "intro": "Enter this on the sign-up page to finish creating your account.",
    },
    "admin_apply": {
        "subject": "Continue your EcoScholar admin application",
        "intro": "Enter this on the admin application page to continue.",
    },
    "admin_setup": {
        "subject": "Set up your EcoScholar admin account",
        "intro": "Enter this code, along with a new password, on the admin setup page to activate your account.",
    },
}

def create_and_send_otp(email, purpose, full_name=''):
    """(Re)issues a verification code for the given purpose - any previous unused
    code for this email+purpose is discarded, so only the most recently sent one
    ever works. `purpose` is one of OTP_COPY's keys (register, admin_apply)."""
    db = get_db()
    db.otps.delete_many({"email": email, "purpose": purpose})
    code = generate_otp_code()
    db.otps.insert_one({
        "email": email,
        "purpose": purpose,
        "code": code,
        "attempts": 0,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(seconds=OTP_MAX_AGE),
    })
    copy = OTP_COPY[purpose]
    html = f"""
        <p>Hi {full_name},</p>
        <p>Your EcoScholar verification code is:</p>
        <p style="font-size:28px;font-weight:700;letter-spacing:4px;color:#2c5580;">{code}</p>
        <p>{copy['intro']} It expires in 10 minutes.</p>
        <p>If you didn't request this, you can safely ignore this email.</p>
    """
    send_email_async(email, copy['subject'], html)

def verify_otp(email, purpose, code):
    """Returns (ok, error_message). Consumes the code on success; on a wrong
    guess it counts against the attempt limit without consuming the code, so a
    typo doesn't cost the user their one shot."""
    db = get_db()
    otp = db.otps.find_one({"email": email, "purpose": purpose})
    if not otp or otp["expires_at"] < datetime.utcnow():
        return False, "This code has expired. Please request a new one."
    if otp["attempts"] >= OTP_MAX_ATTEMPTS:
        return False, "Too many incorrect attempts. Please request a new code."
    if not secrets.compare_digest(otp["code"], (code or '').strip()):
        db.otps.update_one({"_id": otp["_id"]}, {"$inc": {"attempts": 1}})
        return False, "Incorrect code. Please try again."
    db.otps.delete_one({"_id": otp["_id"]})
    return True, None

def oid(id_str):
    """Parse a string into an ObjectId, or None if it isn't a valid one."""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None

def iso(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None

def derive_city(address):
    """Addresses are stored as "street, city, province" (see the registration/
    application address field) - pull out just the city for display in listings."""
    if not address:
        return None
    parts = [p.strip() for p in address.split(',') if p.strip()]
    return parts[-2] if len(parts) >= 2 else None

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

# Three role tiers:
#  - "admin"      Super Admin - a dev/platform-level account. Full unconditional access,
#                  but not part of an LGU's own team: hidden from the Team list and not
#                  reachable through any of the LGU-facing team-management endpoints.
#  - "lgu_admin"  Admin - the one-per-deployment head of an LGU's team. Full access to
#                  everything within this LGU (same as Super Admin, functionally), but
#                  can only come to hold that seat via POST /api/admins/<id>/transfer-admin.
#  - "lgu_member" scoped access via a `permissions` sub-document, granted by whoever
#                  holds can_manage_members (Admin always does; a member can be granted it).
# Permissions are read fresh from the database on every request rather than trusted from
# the token, since revoking one should take effect immediately - not only after the
# member's current session token happens to expire.
ADMIN_PERMISSIONS = ('can_review_applicants', 'can_manage_members', 'can_reset_program')

def is_full_access_role(role):
    """True for Super Admin and the LGU's Admin - both get full, unconditional access
    everywhere; only lgu_member is ever permission-scoped. Use this (not a raw
    role == 'admin' check) anywhere in the codebase that needs "is this caller an
    admin-tier user", so lgu_admin never has to be added to a comparison twice."""
    return role in ('admin', 'lgu_admin')

def has_permission(permission):
    """Same check require_permission enforces as a decorator, exposed as a plain
    function for routes that need to OR it with another condition (e.g. "reviewer
    OR the applicant themself") rather than gate the whole route on it."""
    role = g.current_user.get('role')
    if is_full_access_role(role):
        return True
    if role != 'lgu_member':
        return False
    db = get_db()
    user = db.users.find_one({"_id": oid(g.current_user.get('id'))})
    return bool(user and user.get('permissions', {}).get(permission))

def require_permission(permission):
    def decorator(f):
        @wraps(f)
        @require_auth
        def wrapper(*args, **kwargs):
            if not has_permission(permission):
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
        "rejection_reason": application.get('rejection_reason'),
        "city": derive_city(doc.get('address')),
        "extra_fields": doc.get('extra_fields', {}),
        "cycle_id": str(doc['cycle_id']) if doc.get('cycle_id') else None,
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

def create_notification(db, user_id, applicant, message, notif_type='status_update'):
    """Records the in-app notification and, best-effort, emails the applicant
    the same message - since an applicant who doesn't log back in would
    otherwise never learn their status changed. `applicant` is the applicant
    document (or a projection of it including at least _id/full_name/email)."""
    if not user_id:
        return
    db.notifications.insert_one({
        "user_id": user_id,
        "applicant_id": applicant["_id"],
        "message": message,
        "type": notif_type,
        "is_read": False,
        "created_at": datetime.utcnow(),
    })

    email = applicant.get('email')
    if email:
        html = f"""
            <p>Hi {applicant.get('full_name', '')},</p>
            <p>{message}</p>
            <p>Log in to EcoScholar to see the full details of your application.</p>
        """
        send_email_async(email, 'EcoScholar application update', html)

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

        # Accounts predating this field (or created outside /api/register, like admins)
        # default to verified - only a registration left mid-way should ever hit this.
        if not user.get('email_verified', True):
            return jsonify({
                "error": "Please verify your email before signing in.",
                "needs_verification": True,
                "email": user['email'],
            }), 403

        user_payload = {
            "id": str(user['_id']),
            "full_name": user['full_name'],
            "email": user['email'],
            "role": user['role']
        }
        # Informational only (drives which nav items the frontend shows) - every
        # endpoint re-checks permissions fresh from the database regardless, so a
        # stale cached value here can never grant access the server wouldn't.
        if user['role'] == 'lgu_member':
            user_payload["permissions"] = {p: bool(user.get('permissions', {}).get(p)) for p in ADMIN_PERMISSIONS}

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

        db.users.insert_one({
            "full_name": full_name,
            "email": email,
            "password": generate_password_hash(password),
            "role": "student",
            "status": "active",
            "email_verified": False,
            "created_at": datetime.utcnow(),
            "privacy_consent": True,
            **profile_data,
        })
        create_and_send_otp(email, 'register', full_name)

        return jsonify({
            "message": "Enter the verification code sent to your email to finish creating your account.",
            "email": email,
        }), 201

    except Exception:
        if DEBUG:
            raise
        return jsonify({"error": "Registration failed"}), 500

@app.route('/api/register/verify-otp', methods=['POST'])
@limiter.limit("10 per minute")
def verify_register_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = data.get('code') or ''
    if not email or not code:
        return jsonify({"error": "Email and code are required"}), 400

    ok, error = verify_otp(email, 'register', code)
    if not ok:
        return jsonify({"error": error}), 400

    db = get_db()
    db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
    user = db.users.find_one({"email": email})
    if not user:
        return jsonify({"error": "Account not found"}), 404

    user_payload = {"id": str(user['_id']), "full_name": user['full_name'], "email": user['email'], "role": user['role']}
    return jsonify({
        "message": "Email verified. Your account is ready.",
        "user": user_payload,
        "token": issue_token(user_payload)
    })

@app.route('/api/register/resend-otp', methods=['POST'])
@limiter.limit("5 per minute")
def resend_register_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    generic = {"message": "If that email needs verification, a new code has been sent."}
    if not email:
        return jsonify({"error": "Email is required"}), 400

    db = get_db()
    user = db.users.find_one({"email": email})
    if user and not user.get('email_verified', True):
        create_and_send_otp(email, 'register', user['full_name'])
    return jsonify(generic)

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

# Editable from the Settings page. Email is intentionally excluded - it's the login
# credential and is used to match applicant records, so changing it has wider ripple
# effects than a simple profile edit; out of scope here.
PROFILE_EDITABLE_FIELDS = {'full_name', 'contactNumber', 'address'}

@app.route('/api/profile', methods=['PUT'])
@require_auth
def update_profile():
    data = request.get_json() or {}
    set_fields = {}
    for field in PROFILE_EDITABLE_FIELDS:
        if field in data:
            value = (data.get(field) or '').strip()
            if not value:
                return jsonify({"error": f"{field} cannot be empty"}), 400
            set_fields[field] = value

    if not set_fields:
        return jsonify({"error": "No valid fields provided"}), 400

    db = get_db()
    user_oid = oid(g.current_user['id'])
    db.users.update_one({"_id": user_oid}, {"$set": set_fields})
    user = db.users.find_one({"_id": user_oid})
    return jsonify({
        "message": "Profile updated",
        "fullName": user.get('full_name', ''),
        "contactNumber": user.get('contactNumber', ''),
        "address": user.get('address', ''),
    })

@app.route('/api/change-password', methods=['PUT'])
@require_auth
@limiter.limit("8 per minute")
def change_password():
    data = request.get_json() or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''

    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    db = get_db()
    user_oid = oid(g.current_user['id'])
    user = db.users.find_one({"_id": user_oid})
    if not user:
        return jsonify({"error": "User not found"}), 404

    stored = user['password']
    is_hashed = stored.startswith(('pbkdf2:', 'scrypt:'))
    valid = check_password_hash(stored, current_password) if is_hashed else stored == current_password
    if not valid:
        return jsonify({"error": "Current password is incorrect"}), 401

    db.users.update_one({"_id": user_oid}, {"$set": {"password": generate_password_hash(new_password)}})
    return jsonify({"message": "Password changed successfully"})

# ── AUTH: FORGOT PASSWORD ──
@app.route('/api/forgot-password', methods=['POST'])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Always return the same message regardless of whether the email exists,
    # so this endpoint can't be used to enumerate registered accounts.
    generic = {"message": "If an account exists for that email, a password reset link has been sent."}

    try:
        db = get_db()
        user = db.users.find_one({"email": email})
        if user:
            token = _reset_serializer.dumps({"id": str(user['_id'])})
            reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
            html = f"""
                <p>Hi {user.get('full_name', '')},</p>
                <p>Someone requested a password reset for your EcoScholar account.
                Click below to set a new password - this link expires in 30 minutes.</p>
                <p><a href="{reset_link}">Reset your password</a></p>
                <p>If you didn't request this, you can safely ignore this email.</p>
            """
            send_email_async(user['email'], 'Reset your EcoScholar password', html)
        return jsonify(generic)
    except Exception:
        if DEBUG:
            raise
        return jsonify(generic)

# ── AUTH: RESET PASSWORD ──
@app.route('/api/reset-password', methods=['POST'])
@limiter.limit("8 per minute")
def reset_password():
    data = request.get_json() or {}
    token = data.get('token') or ''
    new_password = data.get('new_password') or ''

    if not token or not new_password:
        return jsonify({"error": "Token and new password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    try:
        payload = _reset_serializer.loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This reset link has expired. Please request a new one."}), 400
    except BadSignature:
        return jsonify({"error": "This reset link is invalid."}), 400

    db = get_db()
    user_oid = oid(payload.get('id'))
    if not user_oid:
        return jsonify({"error": "This reset link is invalid."}), 400

    result = db.users.update_one(
        {"_id": user_oid},
        {"$set": {"password": generate_password_hash(new_password), "password_set": True}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "This reset link is invalid."}), 400

    return jsonify({"message": "Password reset successfully. You can now log in with your new password."})

# ── GET ALL APPLICANTS ──
# `page` is opt-in: omitting it returns every applicant, unchanged from before,
# since the Dashboard/Reports/Ranking pages all need the full set for their own
# aggregation. Passing `page` switches to server-side search/filter/pagination
# for the Applicants/Applications list pages, which only ever need one page at
# a time and don't want to keep fetching the entire collection as it grows.
@app.route('/api/applicants', methods=['GET'])
@require_permission('can_review_applicants')
def get_applicants():
    try:
        db = get_db()
        page_param = request.args.get('page')
        # Opt-in, not opt-out: defaults to every cycle ever (unchanged from before this
        # feature existed) so nothing that already calls this route without the param -
        # Reports, CSV export - silently starts seeing less than it used to. Only the
        # live Applications queue explicitly asks for cycle=current.
        base_query = {"cycle_id": get_current_cycle_id(db)} if request.args.get('cycle') == 'current' else {}

        if page_param is None:
            applicants = [serialize_applicant(a) for a in db.applicants.find(base_query)]
            return jsonify({"applicants": applicants})

        try:
            page = max(1, int(page_param))
        except ValueError:
            return jsonify({"error": "page must be a number"}), 400
        try:
            limit = min(100, max(1, int(request.args.get('limit', 20))))
        except ValueError:
            return jsonify({"error": "limit must be a number"}), 400

        query = dict(base_query)
        status_param = request.args.get('status')
        if status_param and status_param != 'All':
            # Comma-separated so a page's "All" tab can mean "any of these
            # statuses" (e.g. Approved or Rejected) without matching every
            # status in the system.
            statuses = [s.strip() for s in status_param.split(',') if s.strip()]
            query['application.status'] = statuses[0] if len(statuses) == 1 else {'$in': statuses}

        q = (request.args.get('q') or '').strip()
        if q:
            pattern = {"$regex": re.escape(q), "$options": "i"}
            query['$or'] = [{"full_name": pattern}, {"academic.course": pattern}]

        # Whitelisted so `sort` can't be used to inject an arbitrary field path.
        # A leading "-" means descending (e.g. "-submitted_at" = newest first).
        SORT_FIELD_MAP = {
            'submitted_at': 'application.submitted_at',
            'gpa': 'academic.gpa',
            'ml_score': 'ml_score',
            'full_name': 'full_name',
        }
        sort_param = (request.args.get('sort') or '').strip()
        sort_field, sort_dir = 'created_at', -1
        if sort_param:
            direction = -1 if sort_param.startswith('-') else 1
            key = sort_param.lstrip('-')
            if key not in SORT_FIELD_MAP:
                return jsonify({"error": f"sort must be one of {sorted(SORT_FIELD_MAP)} (optionally prefixed with -)"}), 400
            sort_field, sort_dir = SORT_FIELD_MAP[key], direction

        total = db.applicants.count_documents(query)
        cursor = db.applicants.find(query).sort(sort_field, sort_dir).skip((page - 1) * limit).limit(limit)
        applicants = [serialize_applicant(a) for a in cursor]

        return jsonify({
            "applicants": applicants,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": max(1, (total + limit - 1) // limit),
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET SINGLE APPLICANT ──
@app.route('/api/applicants/<applicant_id>', methods=['GET'])
@require_permission('can_review_applicants')
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
@limiter.limit("10 per minute")
def submit_application():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data received"}), 400

    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        db = get_db()
        current_cycle_id = get_current_cycle_id(db)

        # ── Check duplicate by EMAIL ──
        # Scoped to the current cycle only: someone who already applied in a past,
        # now-archived cycle must be able to apply again in a new one - that's the
        # entire point of a program reset. A DIFFERENT check (reused document/photo
        # detection in upload_document) is what catches the same person trying to
        # reapply under a new identity, and that one deliberately stays cross-cycle.
        existing = db.applicants.find_one({"email": email, "cycle_id": current_cycle_id})
        duplicate_reason = 'email' if existing else None

        # ── Check duplicate by FULL NAME + DATE OF BIRTH ──
        if not existing:
            full_name = data.get('fullName', '').strip()
            dob = data.get('dob', '').strip()
            if full_name and dob:
                existing = db.applicants.find_one({
                    "full_name": {"$regex": f"^{re.escape(full_name)}$", "$options": "i"},
                    "date_of_birth": dob,
                    "cycle_id": current_cycle_id,
                })
                if existing:
                    duplicate_reason = 'name_and_birthdate'

        if existing:
            existing_app = {
                "id": str(existing['_id']),
                "application_status": (existing.get('application') or {}).get('status'),
                "ml_status": existing.get('ml_status'),
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

        # Validate required fields - religion/citizenship drop out if this LGU
        # has hidden them (see HIDEABLE_BUILTIN_FIELDS / hidden_builtin_fields).
        hidden_builtin = get_hidden_builtin_fields(db)
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
        required_fields = [f for f in required_fields if f not in hidden_builtin]
        for field in required_fields:
            if data.get(field) in (None, ''):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Validate custom (LGU-defined) extra fields the same way - required ones
        # must be present. These never feed build_feature_row/the ML model.
        submitted_extra = data.get('extraFields') or {}
        custom_fields = list(db.form_fields.find({"enabled": True}))
        extra_fields_to_store = {}
        for cf in custom_fields:
            value = submitted_extra.get(cf['key'], '')
            if cf.get('required') and value in (None, '', []):
                return jsonify({"error": f"Missing required field: {cf['label']}"}), 400
            extra_fields_to_store[cf['key']] = value

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
            "cycle_id": current_cycle_id,
            "full_name": data['fullName'],
            "email": email,
            "contact_number": data['contactNumber'],
            "address": data['address'],
            "gender": data['gender'],
            "date_of_birth": data['dob'],
            "religion": data.get('religion', ''),
            "citizenship": data.get('citizenship', ''),
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
            "extra_fields": extra_fields_to_store,
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
@require_permission('can_review_applicants')
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

        if (applicant.get('application') or {}).get('status') == 'Withdrawn':
            return jsonify({"error": "This application was withdrawn by the applicant and can't be modified."}), 400

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
        create_notification(db, notify_user_id, applicant, notif_message, notif_type)

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

def _verify_and_decide_one(db, applicant_oid, reviewed_by, now):
    """Runs the ML eligibility decision for one applicant - shared by the
    single-applicant and bulk verify routes. Returns (result_dict,
    needs_recompute): needs_recompute is True when this applicant was found
    Eligible, meaning the accepted-applicant pool must be recomputed
    afterward. Callers processing several applicants should batch that into
    one recompute_approvals() call rather than one per applicant, since it
    re-evaluates the entire pool every time it runs."""
    applicant = db.applicants.find_one({"_id": applicant_oid})
    if not applicant:
        return {"error": "Applicant not found"}, False

    if (applicant.get('application') or {}).get('status') == 'Withdrawn':
        return {"error": "This application was withdrawn by the applicant and can't be modified."}, False

    row, ok = build_feature_row(applicant)
    if not ok:
        return {
            "error": "This applicant was submitted before the updated eligibility "
                     "model and can't be auto-decided. Ask them to resubmit using "
                     "the current application form."
        }, False

    ml_score, ml_status = score_with_model(row)
    old_status = (applicant.get('application') or {}).get('status', '')
    breakdown = build_score_breakdown(applicant)

    if ml_status == 'Not Eligible':
        # Ineligible on the classifier's own terms - rejected outright, the
        # accepted-applicant limit never even comes into play for this one.
        final_status = 'Rejected'
        rejection_reason = generate_rejection_reason(breakdown)
        remarks = f'ML score: {ml_score} ({ml_status}) - {rejection_reason}'

        db.applicants.update_one(
            {"_id": applicant_oid},
            {
                "$set": {
                    "application.status": final_status,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                    "ml_score": ml_score,
                    "ml_status": ml_status,
                    "application.rejection_reason": rejection_reason,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Documents verified by admin - model decided: {final_status}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "admin",
                        "old_status": old_status,
                        "new_status": final_status,
                        "remarks": remarks,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        notif_message = (STATUS_MESSAGES[final_status] + ' ' + rejection_reason) if are_results_visible(db) else GENERIC_REVIEWED_MESSAGE
        create_notification(db, notify_user_id, applicant, notif_message, STATUS_NOTIF_TYPE[final_status])
        return {
            "applicant_id": str(applicant_oid), "status": final_status,
            "ml_score": ml_score, "ml_status": ml_status,
            "regressor_cutoff": ml_regressor_cutoff, "breakdown": breakdown,
            "rejection_reason": rejection_reason, "reviewed_by": reviewed_by,
        }, False

    # Eligible on its own - but whether it's actually Approved depends on how
    # it ranks against everyone else within the accepted applicant limit, so
    # the final call is left to recompute_approvals(), run by the caller.
    db.applicants.update_one(
        {"_id": applicant_oid},
        {"$set": {
            "ml_score": ml_score,
            "ml_status": ml_status,
            "application.reviewed_by_name": reviewed_by,
        }}
    )
    return {
        "applicant_id": str(applicant_oid), "status": None,
        "ml_score": ml_score, "ml_status": ml_status,
        "regressor_cutoff": ml_regressor_cutoff, "breakdown": breakdown,
        "rejection_reason": None, "reviewed_by": reviewed_by,
    }, True

# ── VERIFY DOCUMENTS & LET THE MODEL DECIDE ELIGIBILITY ──
@app.route('/api/applications/<applicant_id>/verify', methods=['PUT'])
@require_permission('can_review_applicants')
def verify_and_decide(applicant_id):
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    reviewed_by = g.current_user.get('email', 'Admin')

    try:
        db = get_db()
        now = datetime.utcnow()
        result, needs_recompute = _verify_and_decide_one(db, applicant_oid, reviewed_by, now)
        if "error" in result:
            return jsonify(result), 404 if result["error"] == "Applicant not found" else 409

        if needs_recompute:
            limit = get_applicant_limit(db)
            recompute_approvals(db, limit, reviewed_by=reviewed_by)
            applicant = db.applicants.find_one({"_id": applicant_oid})
            result["status"] = applicant['application']['status']
            result["rejection_reason"] = applicant['application'].get('rejection_reason')

        result["applicant_id"] = applicant_id
        return jsonify(result)

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── BULK VERIFY DOCUMENTS & LET THE MODEL DECIDE ELIGIBILITY ──
@app.route('/api/applications/bulk-verify', methods=['PUT'])
@require_permission('can_review_applicants')
def bulk_verify_and_decide():
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    data = request.get_json() or {}
    ids = data.get('applicant_ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "applicant_ids must be a non-empty list"}), 400
    if len(ids) > 100:
        return jsonify({"error": "Can't process more than 100 applicants at once"}), 400

    reviewed_by = g.current_user.get('email', 'Admin')

    try:
        db = get_db()
        now = datetime.utcnow()
        results = []
        any_needs_recompute = False

        for applicant_id in ids:
            applicant_oid = oid(applicant_id)
            if not applicant_oid:
                results.append({"applicant_id": applicant_id, "error": "Invalid applicant id"})
                continue
            result, needs_recompute = _verify_and_decide_one(db, applicant_oid, reviewed_by, now)
            result["applicant_id"] = applicant_id
            results.append(result)
            any_needs_recompute = any_needs_recompute or needs_recompute

        # Recompute the accepted-applicant pool once at the end, rather than once
        # per eligible applicant - it re-evaluates everyone, so doing it per-item
        # in a batch would be needlessly expensive.
        if any_needs_recompute:
            limit = get_applicant_limit(db)
            recompute_approvals(db, limit, reviewed_by=reviewed_by)
            for r in results:
                if r.get("status") is None and "error" not in r:
                    applicant = db.applicants.find_one({"_id": oid(r["applicant_id"])})
                    r["status"] = applicant['application']['status']
                    r["rejection_reason"] = applicant['application'].get('rejection_reason')

        succeeded = sum(1 for r in results if "error" not in r)
        return jsonify({"results": results, "succeeded": succeeded, "total": len(ids)})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET AUDIT TRAIL ──
@app.route('/api/audit-trail/<applicant_id>', methods=['GET'])
@require_permission('can_review_applicants')
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
@limiter.limit("20 per minute")
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

            file_bytes = file.read()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            phash = compute_perceptual_hash(file_bytes, filename)

            new_gridfs_id = _fs.put(
                file_bytes, filename=unique_filename,
                content_type=safe_mime_for(unique_filename)
            )

            result = db.applicants.update_one(
                {"_id": applicant_oid, "documents.document_name": document_name},
                {"$set": {
                    "documents.$.gridfs_id": new_gridfs_id,
                    "documents.$.status": "Uploaded",
                    "documents.$.uploaded_at": now,
                    "documents.$.file_hash": file_hash,
                    "documents.$.phash": phash,
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
                        "file_hash": file_hash,
                        "phash": phash,
                    }}}
                )

            # Clean up the previous file now that the new one is safely stored
            if old_gridfs_id:
                try:
                    _fs.delete(old_gridfs_id)
                except Exception:
                    pass

            # ── Fraud signal: has this exact file already been uploaded by a
            # DIFFERENT applicant? A byte-for-byte match is a strong indicator of
            # document reuse (shared/borrowed paperwork, or the same fake document
            # submitted under multiple identities). Reuses the existing
            # duplicate_flags mechanism the Dashboard already surfaces.
            reused = db.applicants.find_one(
                {"_id": {"$ne": applicant_oid}, "documents.file_hash": file_hash},
                {"full_name": 1}
            )
            if reused:
                try:
                    db.duplicate_flags.insert_one({
                        "applicant_id": applicant_oid,
                        "duplicate_of_id": reused["_id"],
                        "reason": "duplicate_document",
                        "document_name": document_name,
                        "flagged_at": now,
                        "resolved": False,
                    })
                except Exception:
                    pass
            elif phash:
                # ── Fraud signal: near-duplicate detection via perceptual hashing.
                # Catches the same document re-uploaded after being re-saved,
                # screenshotted, or lightly cropped - all of which change the file's
                # bytes (so the exact-hash check above misses it) but leave the
                # visual content essentially unchanged. Only runs when there was no
                # exact-hash match, since that's already the stronger signal.
                try:
                    this_hash = imagehash.hex_to_hash(phash)
                    best_match_doc, best_match_applicant, best_distance = None, None, None
                    for other in db.applicants.find(
                        {"_id": {"$ne": applicant_oid}, "documents.phash": {"$exists": True, "$ne": None}},
                        {"full_name": 1, "documents.document_name": 1, "documents.phash": 1}
                    ):
                        for d in other.get('documents', []):
                            if not d.get('phash'):
                                continue
                            # imagehash's ImageHash.__sub__ returns numpy.int64, which
                            # bson/pymongo cannot encode - cast to a native int up front
                            # so the flag document below is actually insertable.
                            distance = int(this_hash - imagehash.hex_to_hash(d['phash']))
                            if best_distance is None or distance < best_distance:
                                best_distance, best_match_doc, best_match_applicant = distance, d, other

                    if best_match_applicant and best_distance <= NEAR_DUPLICATE_THRESHOLD:
                        db.duplicate_flags.insert_one({
                            "applicant_id": applicant_oid,
                            "duplicate_of_id": best_match_applicant["_id"],
                            "reason": "near_duplicate_document",
                            "document_name": document_name,
                            "duplicate_of_document_name": best_match_doc.get("document_name"),
                            "similarity_distance": best_distance,
                            "flagged_at": now,
                            "resolved": False,
                        })
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
@limiter.limit("20 per minute")
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
                "monthly_income": applicant.get('monthly_income'),
                "gpa": academic.get('gpa'),
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
        applicant = db.applicants.find_one({"_id": applicant_oid}, {"documents": 1, "user_id": 1})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        is_owner = applicant.get('user_id') and str(applicant['user_id']) == g.current_user['id']
        if not has_permission('can_review_applicants') and not is_owner:
            return jsonify({"error": "Forbidden"}), 403

        documents = applicant.get('documents', [])
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
        if not has_permission('can_review_applicants') and not is_owner:
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

    if not is_full_access_role(g.current_user.get('role')) and email.strip().lower() != g.current_user.get('email', '').lower():
        return jsonify({"error": "Forbidden"}), 403

    try:
        db = get_db()
        query = {"email": email.strip().lower()}
        # A student only ever sees their CURRENT cycle's application here - once a
        # reset closes their old cycle, this correctly goes back to "No Application
        # Found" so they can start fresh, rather than reopening an archived one every
        # time they log in. Admins bypass this (see the masking check below too) since
        # they legitimately need to look up a student's latest record regardless of
        # cycle, e.g. from a support/audit context.
        if not is_full_access_role(g.current_user.get('role')):
            query["cycle_id"] = get_current_cycle_id(db)
        applicant = db.applicants.find_one(query, sort=[("_id", -1)])

        if not applicant:
            return jsonify({"application": None})

        application = serialize_applicant(applicant)
        # Only mask for the applicant viewing their own record - admins/reviewers
        # calling this same endpoint (e.g. from an admin context) always see the
        # real decision, same as every other admin-facing route.
        if not is_full_access_role(g.current_user.get('role')) and application['application_status'] in ('Approved', 'Rejected'):
            if not are_results_visible(db):
                application['application_status'] = 'Pending Verification'
                application['ml_status'] = 'Pending'
                application['ml_score'] = 0
                application['rejection_reason'] = None
                application['reviewed_at'] = None
                application['reviewed_by_name'] = None

        return jsonify({
            "application": application,
            "documents": [serialize_document(d) for d in applicant.get('documents', [])]
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── WITHDRAW APPLICATION ──
# Deliberately does not let a student edit any submitted field (income, GWA,
# etc. feed the eligibility model - allowing edits after submission would
# reopen exactly the kind of post-submission tampering the fraud-detection
# work elsewhere in this codebase is trying to catch). Withdrawing is
# non-destructive: it sets a status, not a delete, so the record stays
# visible to admins and in the audit trail. There's no "undo" - a student who
# changes their mind submits a fresh application instead.
@app.route('/api/student/application/withdraw', methods=['PUT'])
@require_auth
def withdraw_application():
    if is_full_access_role(g.current_user.get('role')):
        return jsonify({"error": "Only the applicant can withdraw their own application"}), 403

    email = g.current_user.get('email', '').strip().lower()

    try:
        db = get_db()
        applicant = db.applicants.find_one({"email": email}, sort=[("_id", -1)])
        if not applicant:
            return jsonify({"error": "No application found"}), 404

        current_status = (applicant.get('application') or {}).get('status')
        if current_status == 'Withdrawn':
            return jsonify({"error": "This application has already been withdrawn"}), 400

        now = datetime.utcnow()
        db.applicants.update_one(
            {"_id": applicant["_id"]},
            {
                "$set": {
                    "application.status": "Withdrawn",
                    "application.reviewed_at": now,
                },
                "$push": {
                    "audit_trail": {
                        "action": "Application withdrawn by applicant",
                        "performed_by": email,
                        "performed_by_role": "student",
                        "old_status": current_status,
                        "new_status": "Withdrawn",
                        "remarks": "Withdrawn by the applicant.",
                        "performed_at": now,
                    }
                }
            }
        )
        return jsonify({"message": "Application withdrawn"})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET DUPLICATE FLAGS ──
@app.route('/api/duplicate-flags', methods=['GET'])
@require_permission('can_review_applicants')
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
                "document_name": f.get('document_name'),
                "duplicate_of_document_name": f.get('duplicate_of_document_name'),
                "similarity_distance": f.get('similarity_distance'),
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
@require_permission('can_review_applicants')
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

# ── ACCEPTED APPLICANT LIMIT SETTING ──
def serialize_settings(db):
    doc = db.settings.find_one({"_id": "global"}) or {}
    current_cycle = get_current_cycle(db)
    return {
        "max_accepted": get_applicant_limit(db),
        "approved_count": db.applicants.count_documents({
            "application.status": "Approved", "cycle_id": get_current_cycle_id(db)
        }),
        "hidden_builtin_fields": get_hidden_builtin_fields(db),
        "results_visible_after": iso(doc.get('results_visible_after')),
        "results_visible_override": doc.get('results_visible_override'),
        "results_visible_now": are_results_visible(db),
        "reset_password_set": bool(doc.get('reset_password_hash')),
        "current_cycle": serialize_cycle(current_cycle) if current_cycle else None,
    }

@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    # Read access is a bit wider than write access: an lgu_member granted only
    # can_reset_program still needs to see reset_password_set/current_cycle to use
    # the Reset Program action at all - none of the other fields here are sensitive
    # enough to gate behind full LGU-admin access just for that one field's sake.
    if not (is_full_access_role(g.current_user.get('role')) or has_permission('can_reset_program')):
        return jsonify({"error": "Forbidden"}), 403
    db = get_db()
    return jsonify(serialize_settings(db))

@app.route('/api/settings', methods=['PUT'])
@require_role('admin', 'lgu_admin')
def update_settings():
    data = request.get_json() or {}
    set_fields = {}
    unset_fields = {}

    if 'max_accepted' in data:
        max_accepted = data.get('max_accepted')
        if not isinstance(max_accepted, int) or isinstance(max_accepted, bool) or max_accepted < 1:
            return jsonify({"error": "max_accepted must be a positive integer"}), 400
        set_fields['max_accepted'] = max_accepted

    if 'hidden_builtin_fields' in data:
        hidden = data.get('hidden_builtin_fields')
        if not isinstance(hidden, list) or any(f not in HIDEABLE_BUILTIN_FIELDS for f in hidden):
            return jsonify({"error": f"hidden_builtin_fields must be a list from {list(HIDEABLE_BUILTIN_FIELDS)}"}), 400
        set_fields['hidden_builtin_fields'] = hidden

    if 'results_visible_after' in data:
        raw = data.get('results_visible_after')
        if raw in (None, ''):
            unset_fields['results_visible_after'] = ''
        else:
            try:
                set_fields['results_visible_after'] = datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
            except (ValueError, AttributeError):
                return jsonify({"error": "results_visible_after must be an ISO date/time string, or null"}), 400

    if 'results_visible_override' in data:
        override = data.get('results_visible_override')
        if override is None:
            unset_fields['results_visible_override'] = ''
        elif isinstance(override, bool):
            set_fields['results_visible_override'] = override
        else:
            return jsonify({"error": "results_visible_override must be true, false, or null"}), 400

    # The reset confirmation password (see POST /api/program-reset) - deliberately
    # separate from the admin's login password, and never read back: GET /api/settings
    # only ever reports whether one is set (reset_password_set), never the hash.
    if 'reset_password' in data:
        reset_password = data.get('reset_password')
        if reset_password in (None, ''):
            unset_fields['reset_password_hash'] = ''
        elif isinstance(reset_password, str) and len(reset_password) >= 6:
            set_fields['reset_password_hash'] = generate_password_hash(reset_password)
        else:
            return jsonify({"error": "reset_password must be at least 6 characters, or null to remove it"}), 400

    if not set_fields and not unset_fields:
        return jsonify({"error": "No valid settings provided"}), 400

    try:
        db = get_db()
        update = {}
        if set_fields:
            update['$set'] = set_fields
        if unset_fields:
            update['$unset'] = unset_fields
        db.settings.update_one({"_id": "global"}, update, upsert=True)
        if 'max_accepted' in set_fields:
            recompute_approvals(db, set_fields['max_accepted'], reviewed_by=g.current_user.get('email', 'Admin'))
        return jsonify({"message": "Settings updated", **serialize_settings(db)})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── LIST PROGRAM CYCLES ──
@app.route('/api/program-cycles', methods=['GET'])
@require_permission('can_review_applicants')
def list_program_cycles():
    db = get_db()
    cycles = list(db.program_cycles.find({}).sort('started_at', -1))
    result = []
    for c in cycles:
        count = db.applicants.count_documents({"cycle_id": c["_id"]})
        result.append(serialize_cycle(c, applicant_count=count))

    legacy_count = db.applicants.count_documents({"cycle_id": None})
    if legacy_count > 0:
        result.append({
            "id": None, "label": "Before cycle tracking (legacy data)",
            "started_at": None, "closed_at": None,
            "started_by": None, "closed_by": None,
            "is_current": len(cycles) == 0,
            "applicant_count": legacy_count,
        })

    return jsonify({"cycles": result})

# ── PROGRAM RESET (archive current cycle, start a new one) ──
# Super Admin and the LGU's Admin always have this (see has_permission); an lgu_member
# only gets it if explicitly granted can_reset_program - this changes what's "live"
# everywhere in the app at once, a meaningfully bigger blast radius than the other two
# permissions, so it's opt-in per member rather than bundled with can_manage_members.
# Nothing is destructive: see do_program_reset()'s docstring.
@app.route('/api/program-reset', methods=['POST'])
@require_permission('can_reset_program')
@limiter.limit("5 per minute")
def program_reset():
    data = request.get_json() or {}
    password = data.get('password') or ''
    label = data.get('label')

    try:
        db = get_db()
        settings_doc = db.settings.find_one({"_id": "global"}) or {}
        reset_hash = settings_doc.get('reset_password_hash')
        if not reset_hash:
            return jsonify({"error": "Set a reset confirmation password in Settings before resetting."}), 400
        if not check_password_hash(reset_hash, password):
            return jsonify({"error": "Incorrect reset confirmation password."}), 403

        outgoing_cycle = get_current_cycle(db)
        outgoing_count = db.applicants.count_documents(
            {"cycle_id": outgoing_cycle["_id"]} if outgoing_cycle else {"cycle_id": None}
        )

        performed_by = g.current_user.get('email', 'Admin')
        new_cycle_id = do_program_reset(db, performed_by, new_label=label)

        return jsonify({
            "message": "Program reset complete. A new cycle has started.",
            "archived_applicant_count": outgoing_count,
            **serialize_settings(db),
            "new_cycle_id": str(new_cycle_id),
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── CUSTOM APPLICATION FORM FIELDS ──
# LGUs collect different extra information beyond the core fields the eligibility
# model needs (see build_feature_row) - these are admin-defined, purely informational
# fields. They are stored under applicant.extra_fields and are NEVER read by
# build_feature_row, so no custom field - however an LGU labels it - can ever influence
# the ML score. That's enforced by build_feature_row simply not looking at them, not by
# a runtime check, so there's no toggle that could accidentally wire one in.
FIELD_TYPES = {'text', 'textarea', 'number', 'date', 'select', 'checkbox'}
FORM_SECTIONS = {'personal', 'school'}

# A small, deliberately short list of existing built-in fields that are genuinely
# optional (never read by build_feature_row) and safe to let an LGU hide entirely.
HIDEABLE_BUILTIN_FIELDS = {
    'religion': 'Religion',
    'citizenship': 'Citizenship',
}

def get_hidden_builtin_fields(db):
    doc = db.settings.find_one({"_id": "global"})
    return (doc or {}).get("hidden_builtin_fields", [])

def serialize_form_field(f):
    return {
        "id": str(f["_id"]),
        "key": f.get("key"),
        "label": f.get("label"),
        "type": f.get("type"),
        "options": f.get("options", []),
        "required": f.get("required", False),
        "enabled": f.get("enabled", True),
        "section": f.get("section"),
        "order": f.get("order", 0),
    }

@app.route('/api/form-fields', methods=['GET'])
@require_auth
def list_form_fields():
    db = get_db()
    query = {} if is_full_access_role(g.current_user.get('role')) else {"enabled": True}
    fields = list(db.form_fields.find(query).sort([("section", 1), ("order", 1)]))
    return jsonify({
        "fields": [serialize_form_field(f) for f in fields],
        "hidden_builtin_fields": get_hidden_builtin_fields(db),
        "hideable_builtin_fields": HIDEABLE_BUILTIN_FIELDS,
    })

@app.route('/api/form-fields', methods=['POST'])
@require_role('admin', 'lgu_admin')
def create_form_field():
    data = request.get_json() or {}
    key = (data.get('key') or '').strip()
    label = (data.get('label') or '').strip()
    field_type = data.get('type')
    section = data.get('section')

    if not key or not re.match(r'^[a-z][a-z0-9_]*$', key):
        return jsonify({"error": "Key is required and must be lowercase letters, numbers, and underscores only"}), 400
    if not label:
        return jsonify({"error": "Label is required"}), 400
    if field_type not in FIELD_TYPES:
        return jsonify({"error": f"Type must be one of {sorted(FIELD_TYPES)}"}), 400
    if section not in FORM_SECTIONS:
        return jsonify({"error": f"Section must be one of {sorted(FORM_SECTIONS)}"}), 400
    if key in HIDEABLE_BUILTIN_FIELDS or key in PROFILE_FIELDS:
        return jsonify({"error": "This key is already used by a built-in field"}), 400

    options = data.get('options') or []
    if field_type == 'select' and (not isinstance(options, list) or not options):
        return jsonify({"error": "Select fields need at least one option"}), 400

    db = get_db()
    if db.form_fields.find_one({"key": key}):
        return jsonify({"error": "A custom field with this key already exists"}), 409

    doc = {
        "key": key,
        "label": label,
        "type": field_type,
        "options": options if field_type == 'select' else [],
        "required": bool(data.get('required', False)),
        "enabled": True,
        "section": section,
        "order": db.form_fields.count_documents({"section": section}),
        "created_at": datetime.utcnow(),
    }
    result = db.form_fields.insert_one(doc)
    doc["_id"] = result.inserted_id
    return jsonify({"field": serialize_form_field(doc)}), 201

@app.route('/api/form-fields/<field_id>', methods=['PUT'])
@require_role('admin', 'lgu_admin')
def update_form_field(field_id):
    field_oid = oid(field_id)
    if not field_oid:
        return jsonify({"error": "Invalid field id"}), 400

    data = request.get_json() or {}
    set_fields = {}
    if 'label' in data:
        label = (data.get('label') or '').strip()
        if not label:
            return jsonify({"error": "Label cannot be empty"}), 400
        set_fields['label'] = label
    if 'required' in data:
        set_fields['required'] = bool(data['required'])
    if 'enabled' in data:
        set_fields['enabled'] = bool(data['enabled'])
    if 'options' in data:
        set_fields['options'] = data['options'] or []

    if not set_fields:
        return jsonify({"error": "No valid fields provided"}), 400

    db = get_db()
    result = db.form_fields.update_one({"_id": field_oid}, {"$set": set_fields})
    if result.matched_count == 0:
        return jsonify({"error": "Field not found"}), 404

    updated = db.form_fields.find_one({"_id": field_oid})
    return jsonify({"field": serialize_form_field(updated)})

@app.route('/api/form-fields/<field_id>', methods=['DELETE'])
@require_role('admin', 'lgu_admin')
def delete_form_field(field_id):
    field_oid = oid(field_id)
    if not field_oid:
        return jsonify({"error": "Invalid field id"}), 400

    db = get_db()
    result = db.form_fields.delete_one({"_id": field_oid})
    if result.deleted_count == 0:
        return jsonify({"error": "Field not found"}), 404
    return jsonify({"message": "Field deleted"})

# ── DOCUMENT REQUIREMENTS ──
# Which documents an LGU asks applicants to upload. The "label" here IS the
# document_name stored against every upload (see upload_document()) - one string
# used consistently as the storage key, the OCR verify_document()/parse_document_fields()
# doc_type, and the label shown to students/admins, rather than three drifting variants.
#
# SELFIE_DOC_LABEL is stored/uploaded exactly like any other requirement (same GridFS
# path, same fraud checks) but the frontend pulls it out of the generic checklist and
# gives it its own "Identity Verification" UI - a live-camera capture on the student
# side, and a side-by-side compare against ID_DOC_LABEL's photo on the admin side, for
# manual visual comparison (not automated face-matching, which is a separate, bigger
# feature - see feature spec Â§1.2).
SELFIE_DOC_LABEL = "Selfie / Face Photo"
ID_DOC_LABEL = "School ID"

DEFAULT_DOC_REQUIREMENTS = [
    {"label": "Enrollment Form", "required": True},
    {"label": "Barangay Endorsement", "required": True},
    {"label": ID_DOC_LABEL, "required": True},
    {"label": "Grade 12 Grades", "required": True},
    {"label": "4Ps Certificate", "required": False},
    {"label": "Proof of Income", "required": True},
    {"label": SELFIE_DOC_LABEL, "required": True},
]

def serialize_doc_requirement(d):
    return {
        "id": str(d["_id"]),
        "label": d.get("label"),
        "required": d.get("required", False),
        "enabled": d.get("enabled", True),
        "order": d.get("order", 0),
    }

def get_doc_requirements_collection(db):
    """Lazy-seeds the default requirements on first use so existing deployments
    (and fresh ones) start with the same documents the form always had."""
    if db.document_requirements.count_documents({}) == 0:
        now = datetime.utcnow()
        db.document_requirements.insert_many([
            {**d, "enabled": True, "order": i, "created_at": now}
            for i, d in enumerate(DEFAULT_DOC_REQUIREMENTS)
        ])
    elif db.document_requirements.count_documents({"label": SELFIE_DOC_LABEL}) == 0:
        # Backfill for deployments seeded before the selfie step existed.
        db.document_requirements.insert_one({
            "label": SELFIE_DOC_LABEL,
            "required": True,
            "enabled": True,
            "order": db.document_requirements.count_documents({}),
            "created_at": datetime.utcnow(),
        })
    return db.document_requirements

@app.route('/api/document-requirements', methods=['GET'])
@require_auth
def list_doc_requirements():
    db = get_db()
    coll = get_doc_requirements_collection(db)
    query = {} if is_full_access_role(g.current_user.get('role')) else {"enabled": True}
    docs = list(coll.find(query).sort("order", 1))
    return jsonify({"requirements": [serialize_doc_requirement(d) for d in docs]})

@app.route('/api/document-requirements', methods=['POST'])
@require_role('admin', 'lgu_admin')
def create_doc_requirement():
    data = request.get_json() or {}
    label = (data.get('label') or '').strip()
    if not label:
        return jsonify({"error": "Label is required"}), 400

    db = get_db()
    coll = get_doc_requirements_collection(db)
    if coll.find_one({"label": label}):
        return jsonify({"error": "A document requirement with this label already exists"}), 409

    doc = {
        "label": label,
        "required": bool(data.get('required', False)),
        "enabled": True,
        "order": coll.count_documents({}),
        "created_at": datetime.utcnow(),
    }
    result = coll.insert_one(doc)
    doc["_id"] = result.inserted_id
    return jsonify({"requirement": serialize_doc_requirement(doc)}), 201

@app.route('/api/document-requirements/<req_id>', methods=['PUT'])
@require_role('admin', 'lgu_admin')
def update_doc_requirement(req_id):
    req_oid = oid(req_id)
    if not req_oid:
        return jsonify({"error": "Invalid requirement id"}), 400

    data = request.get_json() or {}
    set_fields = {}
    if 'label' in data:
        label = (data.get('label') or '').strip()
        if not label:
            return jsonify({"error": "Label cannot be empty"}), 400
        set_fields['label'] = label
    if 'required' in data:
        set_fields['required'] = bool(data['required'])
    if 'enabled' in data:
        set_fields['enabled'] = bool(data['enabled'])

    if not set_fields:
        return jsonify({"error": "No valid fields provided"}), 400

    db = get_db()
    coll = get_doc_requirements_collection(db)
    result = coll.update_one({"_id": req_oid}, {"$set": set_fields})
    if result.matched_count == 0:
        return jsonify({"error": "Requirement not found"}), 404

    updated = coll.find_one({"_id": req_oid})
    return jsonify({"requirement": serialize_doc_requirement(updated)})

@app.route('/api/document-requirements/<req_id>', methods=['DELETE'])
@require_role('admin', 'lgu_admin')
def delete_doc_requirement(req_id):
    req_oid = oid(req_id)
    if not req_oid:
        return jsonify({"error": "Invalid requirement id"}), 400

    db = get_db()
    result = db.document_requirements.delete_one({"_id": req_oid})
    if result.deleted_count == 0:
        return jsonify({"error": "Requirement not found"}), 404
    return jsonify({"message": "Requirement deleted"})

def serialize_admin(u):
    doc = {
        "id": str(u["_id"]),
        "full_name": u.get("full_name", ""),
        "email": u.get("email", ""),
        "office": u.get("office", ""),
        "municipality": u.get("municipality", ""),
        "role": u.get("role", "lgu_member"),
        # Accounts created before this field existed already have a real,
        # self-chosen password, so they default to "activated".
        "password_set": u.get("password_set", True),
        "created_at": iso(u.get("created_at")),
    }
    if doc["role"] == "lgu_member":
        doc["permissions"] = {p: bool(u.get("permissions", {}).get(p)) for p in ADMIN_PERMISSIONS}
    elif doc["role"] == "lgu_admin":
        # Not individually configurable - the Admin seat always has everything, same
        # as Super Admin. Serialized as all-True so the frontend can render it with
        # the same checklist it uses for lgu_member, without branching on role.
        doc["permissions"] = {p: True for p in ADMIN_PERMISSIONS}
    return doc

# ── ADMIN ACCOUNT MANAGEMENT ──
# Super Admin (role="admin") is deliberately invisible and unreachable here - it's a
# dev/platform account, not part of an LGU's own team. This surface only ever manages
# "lgu_admin" (the one Admin seat) and "lgu_member" (scoped team members).
@app.route('/api/admins', methods=['GET'])
@require_permission('can_manage_members')
def list_admins():
    db = get_db()
    admins = list(db.users.find({"role": {"$in": ["lgu_admin", "lgu_member"]}}).sort("created_at", 1))
    return jsonify({"admins": [serialize_admin(a) for a in admins]})

@app.route('/api/admins', methods=['POST'])
@require_permission('can_manage_members')
def create_admin_account():
    """Always creates a plain LGU Member - the Admin seat can only be reached via
    POST /api/admins/<id>/transfer-admin, never created directly."""
    data = request.get_json() or {}
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()

    if not full_name or not email:
        return jsonify({"error": "Full name and email are required"}), 400

    raw = data.get('permissions') or {}
    permissions = {p: bool(raw.get(p)) for p in ADMIN_PERMISSIONS}

    db = get_db()
    if db.users.find_one({"email": email}):
        return jsonify({"error": "An account with this email already exists"}), 409

    admin_doc = create_admin_with_setup_email(
        full_name=full_name,
        email=email,
        role='lgu_member',
        permissions=permissions,
    )
    return jsonify({"admin": serialize_admin(admin_doc)}), 201

@app.route('/api/admins/<admin_id>/permissions', methods=['PUT'])
@require_permission('can_manage_members')
def update_admin_permissions(admin_id):
    """Edits an existing LGU Member's permission checkboxes. Does not touch role -
    the Admin seat can only change hands via transfer_admin_role() below, and Super
    Admin isn't reachable through this endpoint at all (see the role filter below)."""
    admin_oid = oid(admin_id)
    if not admin_oid:
        return jsonify({"error": "Invalid admin id"}), 400
    if str(admin_oid) == g.current_user['id']:
        return jsonify({"error": "You can't change your own permissions"}), 400

    db = get_db()
    target = db.users.find_one({"_id": admin_oid, "role": "lgu_member"})
    if not target:
        return jsonify({"error": "LGU member not found (use Pass Admin Role to change who holds the Admin seat)"}), 404

    data = request.get_json() or {}
    raw = data.get('permissions') or {}
    permissions = {p: bool(raw.get(p)) for p in ADMIN_PERMISSIONS}

    db.users.update_one({"_id": admin_oid}, {"$set": {"permissions": permissions}})
    return jsonify({"admin": serialize_admin(db.users.find_one({"_id": admin_oid}))})

# ── TRANSFER THE ADMIN SEAT ──
# Exactly one lgu_admin can exist at a time. Super Admin can assign the very first one
# (or reassign in an emergency); once the seat is held, only the current holder can pass
# it on - an lgu_member, even with every other permission granted, can never promote
# themselves or a peer directly. The outgoing Admin is demoted to a bare lgu_member
# (all permissions cleared) rather than left with any residual elevated access.
@app.route('/api/admins/<admin_id>/transfer-admin', methods=['POST'])
@require_permission('can_manage_members')
@limiter.limit("5 per minute")
def transfer_admin_role(admin_id):
    target_oid = oid(admin_id)
    if not target_oid:
        return jsonify({"error": "Invalid admin id"}), 400
    if str(target_oid) == g.current_user['id']:
        return jsonify({"error": "You already hold the Admin seat"}), 400

    db = get_db()
    target = db.users.find_one({"_id": target_oid, "role": "lgu_member"})
    if not target:
        return jsonify({"error": "Target must be an existing LGU member"}), 404

    requester_role = g.current_user.get('role')
    current_admin = db.users.find_one({"role": "lgu_admin"})
    if requester_role == 'lgu_member':
        return jsonify({"error": "Only the current Admin (or Super Admin) can pass on the Admin seat"}), 403
    if requester_role == 'lgu_admin' and (not current_admin or str(current_admin['_id']) != g.current_user['id']):
        return jsonify({"error": "Only the current Admin can pass on the Admin seat"}), 403

    if current_admin:
        db.users.update_one(
            {"_id": current_admin["_id"]},
            {"$set": {"role": "lgu_member", "permissions": {p: False for p in ADMIN_PERMISSIONS}}}
        )
    db.users.update_one({"_id": target_oid}, {"$set": {"role": "lgu_admin"}, "$unset": {"permissions": ""}})

    return jsonify({"admin": serialize_admin(db.users.find_one({"_id": target_oid}))})

@app.route('/api/admins/<admin_id>/resend-invite', methods=['POST'])
@require_permission('can_manage_members')
@limiter.limit("5 per minute")
def resend_admin_invite(admin_id):
    admin_oid = oid(admin_id)
    if not admin_oid:
        return jsonify({"error": "Invalid admin id"}), 400

    db = get_db()
    admin = db.users.find_one({"_id": admin_oid, "role": {"$in": ["lgu_admin", "lgu_member"]}})
    if not admin:
        return jsonify({"error": "Admin account not found"}), 404
    if admin.get("password_set", True):
        return jsonify({"error": "This admin has already set their password"}), 400

    create_and_send_otp(admin["email"], 'admin_setup', admin['full_name'])
    return jsonify({"message": "Invite resent"})

# Public (no auth) - the invited person isn't logged in yet. Only usable against
# an account that's still password_set=False, so it can't be used to reset an
# already-active admin's password (that's what forgot-password is for).
@app.route('/api/admins/verify-setup-otp', methods=['POST'])
@limiter.limit("10 per minute")
def verify_admin_setup_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = data.get('code') or ''
    new_password = data.get('new_password') or ''
    if not email or not code or not new_password:
        return jsonify({"error": "Email, code, and new password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    ok, error = verify_otp(email, 'admin_setup', code)
    if not ok:
        return jsonify({"error": error}), 400

    db = get_db()
    user = db.users.find_one({"email": email, "role": {"$in": ["lgu_admin", "lgu_member"]}, "password_set": False})
    if not user:
        return jsonify({"error": "Account not found"}), 404

    db.users.update_one({"_id": user["_id"]}, {"$set": {
        "password": generate_password_hash(new_password),
        "password_set": True,
    }})
    user_payload = {"id": str(user['_id']), "full_name": user['full_name'], "email": user['email'], "role": user['role']}
    if user['role'] == 'lgu_member':
        user_payload["permissions"] = {p: bool(user.get('permissions', {}).get(p)) for p in ADMIN_PERMISSIONS}
    return jsonify({
        "message": "Password set. Your account is ready.",
        "user": user_payload,
        "token": issue_token(user_payload)
    })

@app.route('/api/admins/resend-setup-otp', methods=['POST'])
@limiter.limit("5 per minute")
def resend_admin_setup_otp():
    """Public self-service resend for an invited team member who didn't get (or
    lost) their code - same anti-enumeration shape as the other resend endpoints."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    generic = {"message": "If that email has a pending invite, a new code has been sent."}
    if not email:
        return jsonify({"error": "Email is required"}), 400

    db = get_db()
    user = db.users.find_one({"email": email, "role": {"$in": ["lgu_admin", "lgu_member"]}, "password_set": False})
    if user:
        create_and_send_otp(email, 'admin_setup', user['full_name'])
    return jsonify(generic)

@app.route('/api/admins/<admin_id>', methods=['DELETE'])
@require_permission('can_manage_members')
def delete_admin_account(admin_id):
    admin_oid = oid(admin_id)
    if not admin_oid:
        return jsonify({"error": "Invalid admin id"}), 400

    if str(admin_oid) == g.current_user['id']:
        return jsonify({"error": "You can't remove your own account"}), 400

    db = get_db()
    target = db.users.find_one({"_id": admin_oid, "role": {"$in": ["lgu_admin", "lgu_member"]}})
    if not target:
        return jsonify({"error": "Admin account not found"}), 404
    if target.get('role') == 'lgu_admin':
        return jsonify({"error": "Can't remove the account currently holding the Admin seat - pass the Admin role to someone else first"}), 400

    db.users.delete_one({"_id": admin_oid})
    return jsonify({"message": "Admin account removed"})

def create_admin_with_setup_email(full_name, email, office='', municipality='', role='lgu_member', permissions=None):
    """Inserts a new admin/LGU-member user with no usable starting password and emails
    them a one-time code to set one - used when an existing admin adds a colleague
    directly, so nobody (not even the admin who created the account) ever knows
    another team member's password. (An approved public application is different -
    see create_admin_from_approved_request - the applicant already chose and proved
    their own password before an admin ever reviews it.)"""
    db = get_db()
    placeholder_password = generate_password_hash(secrets.token_urlsafe(32))
    doc = {
        "full_name": full_name,
        "email": email,
        "password": placeholder_password,
        "password_set": False,
        "role": role,
        "status": "active",
        "office": office,
        "municipality": municipality,
        "created_at": datetime.utcnow(),
        "privacy_consent": True,
    }
    if role == 'lgu_member':
        doc["permissions"] = permissions or {p: False for p in ADMIN_PERMISSIONS}
    result = db.users.insert_one(doc)

    create_and_send_otp(email, 'admin_setup', full_name)
    return db.users.find_one({"_id": result.inserted_id})

def create_admin_from_approved_request(req, role, permissions):
    """Inserts a new admin/LGU-member user using the password the applicant already
    chose (and proved their email for) when submitting their request - unlike
    create_admin_with_setup_email, no placeholder password or set-password email is
    needed here since they picked a real one upfront."""
    db = get_db()
    doc = {
        "full_name": req["full_name"],
        "email": req["email"],
        "password": req["password_hash"],
        "password_set": True,
        "role": role,
        "status": "active",
        "office": req.get("office", ""),
        "municipality": req.get("municipality", ""),
        "created_at": datetime.utcnow(),
        "privacy_consent": True,
    }
    if role == 'lgu_member':
        doc["permissions"] = permissions or {p: False for p in ADMIN_PERMISSIONS}
    result = db.users.insert_one(doc)

    office_line = req.get('office') or ''
    if req.get('municipality'):
        office_line = f"{office_line} &middot; {req['municipality']}" if office_line else req['municipality']
    login_link = f"{FRONTEND_URL}/login"
    html = f"""
        <div style="background:#EAF0F7;padding:32px 16px;font-family:Arial,Helvetica,sans-serif;">
          <div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08);">
            <div style="background:linear-gradient(135deg,#16233d,#2c5580);padding:28px 32px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">EcoScholar</h1>
            </div>
            <div style="padding:32px;">
              <h2 style="margin:0 0 12px;color:#1A1A2E;font-size:19px;">You're approved, {req['full_name']}!</h2>
              <p style="margin:0 0 8px;color:#374151;font-size:15px;line-height:1.6;">
                Your admin account request{f" ({office_line})" if office_line else ""} has been approved.
                You can sign in now with the password you set when applying.
              </p>
              <div style="text-align:center;margin:28px 0;">
                <a href="{login_link}" style="display:inline-block;background:#2c5580;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:13px 32px;border-radius:12px;">Sign In</a>
              </div>
              <p style="margin:16px 0 0;color:#6B7280;font-size:13px;">
                If you didn't request admin access, please contact your system administrator.
              </p>
            </div>
          </div>
          <p style="text-align:center;color:#9CA3AF;font-size:12px;margin-top:20px;">
            EcoScholar &middot; Centralized Scholarship Allocation System
          </p>
        </div>
    """
    send_email_async(req["email"], "You're approved as an EcoScholar admin", html)
    return db.users.find_one({"_id": result.inserted_id})

def serialize_admin_request(r):
    return {
        "id": str(r["_id"]),
        "full_name": r.get("full_name", ""),
        "email": r.get("email", ""),
        "office": r.get("office", ""),
        "municipality": r.get("municipality", ""),
        "contact_number": r.get("contact_number", ""),
        "message": r.get("message", ""),
        "status": r.get("status", "pending"),
        "created_at": iso(r.get("created_at")),
        "reviewed_at": iso(r.get("reviewed_at")),
    }

# ── ADMIN ACCOUNT REQUESTS (LGU officials applying for admin access) ──
# Two-step so nobody can submit a request impersonating someone else's inbox:
# 1) POST /start with just an email - emails a one-time code, never confirms
#    whether that email already has an account or a pending request either way.
# 2) POST /verify-start-otp with that code exchanges it for a short-lived token
#    proving the email was actually reachable; only then does the full form
#    (password, office, municipality, etc.) become fillable, and the request is
#    stored under the token's email, not a client-supplied one.
# The applicant's password is collected upfront here (unlike an admin added
# directly by an existing admin, who still gets an emailed set-password link,
# since in that case the adder doesn't know the new member's password) - a
# submission still never creates the account directly, it only queues a
# request that an existing admin must approve, since admin accounts can see
# every applicant's PII and control disbursement decisions.
@app.route('/api/admin-requests/start', methods=['POST'])
@limiter.limit("5 per minute")
def start_admin_request():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()

    generic = {"message": "If that address can apply for admin access, a verification code has been sent to it."}
    if not email or not re.match(r'^\S+@\S+\.\S+$', email):
        return jsonify({"error": "Enter a valid email address"}), 400

    try:
        create_and_send_otp(email, 'admin_apply')
    except Exception:
        if DEBUG:
            raise
    return jsonify(generic)

@app.route('/api/admin-requests/verify-start-otp', methods=['POST'])
@limiter.limit("10 per minute")
def verify_admin_apply_start_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = data.get('code') or ''
    if not email or not code:
        return jsonify({"error": "Email and code are required"}), 400

    ok, error = verify_otp(email, 'admin_apply', code)
    if not ok:
        return jsonify({"error": error}), 400

    token = _admin_apply_serializer.dumps({"email": email})
    return jsonify({"token": token})

@app.route('/api/admin-requests/verify-token', methods=['GET'])
@limiter.limit("20 per minute")
def verify_admin_apply_token():
    token = request.args.get('token') or ''
    try:
        payload = _admin_apply_serializer.loads(token, max_age=ADMIN_APPLY_TOKEN_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This link has expired. Please verify your email again."}), 400
    except BadSignature:
        return jsonify({"error": "This session is invalid."}), 400
    return jsonify({"email": payload.get('email', '')})

@app.route('/api/admin-requests', methods=['POST'])
@limiter.limit("5 per minute")
def submit_admin_request():
    data = request.get_json() or {}
    token = data.get('token') or ''
    full_name = (data.get('full_name') or '').strip()
    password = data.get('password') or ''
    office = (data.get('office') or '').strip()
    municipality = (data.get('municipality') or '').strip()
    contact_number = (data.get('contact_number') or '').strip()
    message = (data.get('message') or '').strip()

    try:
        payload = _admin_apply_serializer.loads(token, max_age=ADMIN_APPLY_TOKEN_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This session has expired. Please verify your email again."}), 400
    except BadSignature:
        return jsonify({"error": "This session is invalid."}), 400
    email = (payload.get('email') or '').strip().lower()

    if not full_name or not email or not office or not municipality or not contact_number or not password:
        return jsonify({"error": "Full name, password, office, municipality, and contact number are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    db = get_db()
    if db.users.find_one({"email": email}):
        return jsonify({"error": "An account with this email already exists"}), 409
    if db.admin_requests.find_one({"email": email, "status": "pending"}):
        return jsonify({"error": "A request for this email is already pending review"}), 409

    db.admin_requests.insert_one({
        "full_name": full_name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "office": office,
        "municipality": municipality,
        "contact_number": contact_number,
        "message": message,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
        "reviewed_by": None,
    })
    return jsonify({"message": "Your request has been submitted for review. An existing admin will verify your details."}), 201

@app.route('/api/admin-requests', methods=['GET'])
@require_permission('can_manage_members')
def list_admin_requests():
    db = get_db()
    status = request.args.get('status')
    query = {"status": status} if status in ('pending', 'approved', 'rejected') else {}
    requests_ = list(db.admin_requests.find(query).sort("created_at", -1))
    return jsonify({"requests": [serialize_admin_request(r) for r in requests_]})

@app.route('/api/admin-requests/<request_id>/approve', methods=['POST'])
@require_permission('can_manage_members')
def approve_admin_request(request_id):
    request_oid = oid(request_id)
    if not request_oid:
        return jsonify({"error": "Invalid request id"}), 400

    db = get_db()
    req = db.admin_requests.find_one({"_id": request_oid})
    if not req:
        return jsonify({"error": "Request not found"}), 404
    if req.get("status") != "pending":
        return jsonify({"error": "This request has already been reviewed"}), 400
    if db.users.find_one({"email": req["email"]}):
        return jsonify({"error": "An account with this email already exists"}), 409

    # Always approved as a plain LGU Member - same as create_admin_account(), the
    # Admin seat only changes hands via POST /api/admins/<id>/transfer-admin.
    data = request.get_json(silent=True) or {}
    raw = data.get('permissions') or {}
    permissions = {p: bool(raw.get(p)) for p in ADMIN_PERMISSIONS}

    admin_doc = create_admin_from_approved_request(req, 'lgu_member', permissions)

    db.admin_requests.update_one({"_id": request_oid}, {"$set": {
        "status": "approved",
        "reviewed_at": datetime.utcnow(),
        "reviewed_by": g.current_user['id'],
    }})

    return jsonify({"message": "Admin request approved", "admin": serialize_admin(admin_doc)}), 201

@app.route('/api/admin-requests/<request_id>/reject', methods=['POST'])
@require_permission('can_manage_members')
def reject_admin_request(request_id):
    request_oid = oid(request_id)
    if not request_oid:
        return jsonify({"error": "Invalid request id"}), 400

    db = get_db()
    result = db.admin_requests.update_one(
        {"_id": request_oid, "status": "pending"},
        {"$set": {"status": "rejected", "reviewed_at": datetime.utcnow(), "reviewed_by": g.current_user['id']}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Request not found or already reviewed"}), 404
    return jsonify({"message": "Admin request rejected"})

# ── GET DASHBOARD STATS ──
@app.route('/api/stats', methods=['GET'])
@require_permission('can_review_applicants')
def get_stats():
    try:
        db = get_db()
        base = {"cycle_id": get_current_cycle_id(db)} if request.args.get('cycle') == 'current' else {}
        total = db.applicants.count_documents(base)
        approved = db.applicants.count_documents({**base, "application.status": "Approved"})
        rejected = db.applicants.count_documents({**base, "application.status": "Rejected"})
        withdrawn = db.applicants.count_documents({**base, "application.status": "Withdrawn"})
        under_review = total - approved - rejected - withdrawn

        return jsonify({
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "withdrawn": withdrawn,
            "under_review": under_review
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCHOLARS APPROVED PER ACADEMIC YEAR ──
@app.route('/api/stats/scholars-per-year', methods=['GET'])
@require_permission('can_review_applicants')
def scholars_per_year():
    try:
        db = get_db()
        pipeline = [
            {"$match": {"application.status": "Approved", "academic.academic_year": {"$ne": None}}},
            {"$group": {"_id": "$academic.academic_year", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        results = list(db.applicants.aggregate(pipeline))
        return jsonify({"scholars_per_year": [{"year": r["_id"], "count": r["count"]} for r in results]})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SYSTEM-WIDE DECISION HISTORY LOG (for the admin dashboard) ──
@app.route('/api/history-log', methods=['GET'])
@require_permission('can_review_applicants')
def get_history_log():
    try:
        limit = min(max(int(request.args.get('limit', 20)), 1), 100)
        db = get_db()
        pipeline = [
            {"$unwind": "$audit_trail"},
            {"$match": {"audit_trail.new_status": {"$in": ["Approved", "Rejected"]}}},
            {"$sort": {"audit_trail.performed_at": -1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "applicant_id": {"$toString": "$_id"},
                "full_name": "$full_name",
                "address": "$address",
                "course": "$academic.course",
                "old_status": "$audit_trail.old_status",
                "new_status": "$audit_trail.new_status",
                "remarks": "$audit_trail.remarks",
                "performed_by": "$audit_trail.performed_by",
                "performed_by_role": "$audit_trail.performed_by_role",
                "performed_at": "$audit_trail.performed_at",
            }},
        ]
        results = list(db.applicants.aggregate(pipeline))
        history = []
        for r in results:
            new_status = r.get("new_status")
            # A "Rejected" entry from the automatic limit re-rank means this applicant
            # was actually eligible, just bumped by a higher-ranked one - "Waitlisted"
            # is a more accurate label for the admin than "Rejected" in that case.
            display_status = (
                'Waitlisted' if new_status == 'Rejected' and r.get('performed_by_role') == 'system'
                else new_status
            )
            history.append({
                "applicant_id": r["applicant_id"],
                "full_name": r.get("full_name"),
                "city": derive_city(r.get("address")),
                "course": r.get("course"),
                "old_status": r.get("old_status"),
                "new_status": new_status,
                "display_status": display_status,
                "remarks": r.get("remarks"),
                "performed_by": r.get("performed_by"),
                "performed_at": iso(r.get("performed_at")),
            })
        return jsonify({"history": history})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCORE SINGLE APPLICANT ──
@app.route('/api/score-applicant/<applicant_id>', methods=['GET'])
@require_permission('can_review_applicants')
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
            "breakdown": build_score_breakdown(applicant)
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCORE AND RANK ALL APPLICANTS ──
@app.route('/api/rank-applicants', methods=['GET'])
@require_permission('can_review_applicants')
def rank_applicants():
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    try:
        db = get_db()
        query = {"application.status": {"$nin": ["Rejected", "Newly Submitted"]}}
        if request.args.get('cycle') == 'current':
            query["cycle_id"] = get_current_cycle_id(db)
        applicants = list(db.applicants.find(query))

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
                    'city': derive_city(applicant.get('address')),
                    'course': academic.get('course'),
                    'gpa': academic.get('gpa'),
                    'monthly_income': applicant.get('monthly_income'),
                    'family_size': applicant.get('family_size'),
                    'housing_situation': applicant.get('housing_situation'),
                    'has_other_scholarship': bool(applicant.get('has_other_scholarship')),
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