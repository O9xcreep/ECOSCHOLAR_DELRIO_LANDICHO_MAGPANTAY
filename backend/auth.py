# -*- coding: utf-8 -*-
"""Session tokens, OTP verification, permission decorators, and the auth-facing
routes (login/register/profile/password). Every other domain module imports
its decorators (require_auth, require_role, require_permission) and
current_organization_oid from here."""
import secrets
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from extensions import app, limiter, get_db, DEBUG, SECRET_KEY, FRONTEND_URL, _mongo_db
from helpers import oid, send_email_async, get_organization_name, find_active_organization_by_code, \
    ml_education_map, ml_occupation_categories, ml_housing_situations

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
        "intro": f'Enter this code on the <a href="{FRONTEND_URL}/admin-setup">admin setup page</a> to activate your account.',
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

# ── AUTH HELPERS ──
def issue_token(user):
    return _serializer.dumps({
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        # Multi-tenancy, Phase A: carried as a plain identity claim (like id/
        # email/role above), not trusted for anything security-sensitive on
        # its own - Phase C's org-scoped routes should re-verify it fresh
        # from db.users per request, the same way has_permission() already
        # re-reads permissions fresh so revocation takes effect immediately.
        "organization_id": user.get("organization_id"),
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

def current_organization_oid():
    """The requesting user's own organization as a real ObjectId, ready to
    drop straight into a query filter - None for a Super Admin (platform-
    level, not tied to any one LGU) or a legacy account predating Phase A's
    backfill. Multi-tenancy, Phase B: the /api/admins/* team-management
    surface all needs this now that a second organization can actually exist
    - without it, one LGU's admins could list/edit/demote another LGU's."""
    return oid(g.current_user.get('organization_id'))

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
            "role": user['role'],
            "organization_id": str(user['organization_id']) if user.get('organization_id') else None,
            "organization_name": get_organization_name(db, user.get('organization_id')),
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
    join_code = (data.get("join_code") or "").strip().upper()

    if not full_name or not email or not password:
        return jsonify({"error": "All fields are required"}), 400

    if not join_code:
        return jsonify({"error": "An LGU join code is required"}), 400
    organization = find_active_organization_by_code(get_db(), join_code)
    if not organization:
        return jsonify({"error": "That join code isn't valid. Check it with your LGU and try again."}), 400

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
            "organization_id": organization["_id"],
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

    user_payload = {
        "id": str(user['_id']), "full_name": user['full_name'], "email": user['email'], "role": user['role'],
        "organization_id": str(user['organization_id']) if user.get('organization_id') else None,
    }
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
