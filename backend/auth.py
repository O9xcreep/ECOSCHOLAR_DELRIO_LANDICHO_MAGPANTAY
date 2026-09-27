# -*- coding: utf-8 -*-
"""Session tokens, OTP verification, permission decorators, and auth routes
(login/register/profile/password)."""
import secrets
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_transport

from extensions import app, limiter, get_db, DEBUG, SECRET_KEY, FRONTEND_URL, GOOGLE_CLIENT_ID, _mongo_db
from helpers import oid, send_email_async, get_organization_name, find_active_organization_by_code
from activity import log_activity
from field_crypto import encrypt_fields, decrypt_fields, ENCRYPTED_PROFILE_FIELDS

TOKEN_MAX_AGE = 60 * 60 * 12  # 12 hours
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-auth')

RESET_TOKEN_MAX_AGE = 30 * 60  # 30 minutes
_reset_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-reset')

# Proves email ownership for the admin-request flow.
ADMIN_APPLY_TOKEN_MAX_AGE = 30 * 60  # 30 minutes
_admin_apply_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='ecoscholar-admin-apply')

# Registration OTP: short numeric code, single-use, expires quickly, attempts capped.
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
    """(Re)issues a code for the given purpose (an OTP_COPY key), discarding
    any previous unused one."""
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

_google_auth_transport_request = google_auth_transport.Request()

def verify_google_credential(credential):
    """Verifies a Google Identity Services ID token and returns
    {email, name, sub}. Raises ValueError with a safe, user-facing message
    on any failure (bad signature/audience, or an unverified email)."""
    if not GOOGLE_CLIENT_ID:
        raise ValueError("Google sign-in isn't configured on this server.")
    try:
        claims = google_id_token.verify_oauth2_token(
            credential, _google_auth_transport_request, GOOGLE_CLIENT_ID)
    except Exception:
        raise ValueError("Your Google sign-in couldn't be verified. Please try again.")
    if not claims.get('email_verified'):
        raise ValueError("Your Google account's email address isn't verified.")
    return {
        "email": claims['email'].strip().lower(),
        "name": claims.get('name') or claims['email'],
        "sub": claims['sub'],
    }

def verify_otp(email, purpose, code):
    """Returns (ok, error_message). Consumes the code on success only."""
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
        # Identity claim only - org-scoped routes must re-verify from db.users.
        "organization_id": user.get("organization_id"),
    })

def verify_token(token):
    return _serializer.loads(token, max_age=TOKEN_MAX_AGE)

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def revoke_token(token):
    """Blacklists a token until its own natural expiry."""
    try:
        _, issued_at = _serializer.loads(token, max_age=TOKEN_MAX_AGE, return_timestamp=True)
    except (SignatureExpired, BadSignature):
        return
    expires_at = issued_at + timedelta(seconds=TOKEN_MAX_AGE)
    _mongo_db.revoked_tokens.insert_one({"token_hash": hash_token(token), "expires_at": expires_at})

def build_session(db, user):
    """Builds the (user_payload, token) pair every successful sign-in
    returns - shared by password login and Google sign-in so both stay in
    sync (membership backfill, organization_name, lgu_member permissions)."""
    # An account created before the memberships feature has no membership
    # row for its own org yet - backfill it here on login instead of
    # requiring a one-time migration script to run first. Mirrors
    # migrate_phase_b_memberships.py's logic; harmless to also run that
    # script separately, this just makes it unnecessary for any account
    # that logs in at least once.
    if user['role'] != 'admin' and user.get('organization_id'):
        if not db.memberships.find_one({"user_id": user['_id'], "organization_id": user['organization_id']}):
            db.memberships.insert_one({
                "user_id": user['_id'], "organization_id": user['organization_id'], "role": user['role'],
                "permissions": user.get('permissions') if user['role'] == 'lgu_member' else None,
                "municipality": user.get('municipality') if user['role'] in ('lgu_admin', 'lgu_member') else None,
                "joined_at": user.get('created_at') or datetime.utcnow(),
            })

    user_payload = {
        "id": str(user['_id']),
        "full_name": user['full_name'],
        "email": user['email'],
        "role": user['role'],
        "organization_id": str(user['organization_id']) if user.get('organization_id') else None,
        "organization_name": get_organization_name(db, user.get('organization_id')),
    }
    # Informational only - every endpoint re-checks permissions fresh.
    if user['role'] == 'lgu_member':
        user_payload["permissions"] = {p: bool(user.get('permissions', {}).get(p)) for p in ADMIN_PERMISSIONS}
    return user_payload, issue_token(user_payload)

def find_or_link_google_user(db, google_user):
    """Looks up a user by Google sub, falling back to their (Google-verified)
    email - and in that fallback case, attaches the Google id to the account
    so next time it's found directly. Returns None if no account matches
    either way."""
    user = db.users.find_one({"google_id": google_user['sub']})
    if user:
        return user
    user = db.users.find_one({"email": google_user['email']})
    if user and not user.get('google_id'):
        db.users.update_one({"_id": user['_id']}, {"$set": {"google_id": google_user['sub'], "email_verified": True}})
        user['google_id'] = google_user['sub']
        user['email_verified'] = True
    return user

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

# Role tiers: "admin" (Super Admin, platform-level), "lgu_admin" (one per LGU,
# full access, seat held via transfer-admin), "lgu_member" (scoped via
# `permissions`). Permissions are read fresh from the database on every
# request so revocation takes effect immediately.
ADMIN_PERMISSIONS = ('can_review_applicants', 'can_manage_members', 'can_reset_program')

def is_full_access_role(role):
    """True for Super Admin and the LGU's Admin - both get unconditional access."""
    return role in ('admin', 'lgu_admin')

def current_organization_oid():
    """The requesting user's own organization as an ObjectId, or None for
    Super Admin / a legacy account."""
    return oid(g.current_user.get('organization_id'))

def has_permission(permission):
    """Plain-function form of require_permission, for OR-ing with another condition."""
    role = g.current_user.get('role')
    if is_full_access_role(role):
        return True
    if role != 'lgu_member':
        return False
    db = get_db()
    user_oid = oid(g.current_user.get('id'))
    # A member's permissions can now differ per organization (see memberships.py),
    # so look them up for the token's own org, not just the user - falling back
    # to the flat field only for accounts predating the memberships backfill.
    membership = db.memberships.find_one({"user_id": user_oid, "organization_id": current_organization_oid()})
    if membership is not None:
        return bool(membership.get('permissions', {}).get(permission))
    user = db.users.find_one({"_id": user_oid})
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

def require_any_permission(*permissions):
    """Passes if the caller has at least one of the given permissions."""
    def decorator(f):
        @wraps(f)
        @require_auth
        def wrapper(*args, **kwargs):
            if not any(has_permission(p) for p in permissions):
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
            log_activity('auth', 'Failed login - no account with this email',
                         actor={"email": email}, outcome='failure')
            return jsonify({"error": "Invalid email or password"}), 401

        user_actor = {"id": user['_id'], "email": user['email'], "role": user['role'],
                      "full_name": user.get('full_name'), "organization_id": user.get('organization_id')}
        stored = user['password']
        is_hashed = stored.startswith(('pbkdf2:', 'scrypt:'))
        # Legacy plaintext password - compare directly, upgrade below.
        valid = check_password_hash(stored, password) if is_hashed else stored == password

        if not valid:
            log_activity('auth', 'Failed login - wrong password', actor=user_actor, outcome='failure')
            return jsonify({"error": "Invalid email or password"}), 401

        if not is_hashed:
            db.users.update_one({"_id": user['_id']}, {"$set": {"password": generate_password_hash(password)}})

        if not user.get('email_verified', True):
            log_activity('auth', 'Login blocked - email not verified', actor=user_actor, outcome='failure')
            return jsonify({
                "error": "Please verify your email before signing in.",
                "needs_verification": True,
                "email": user['email'],
            }), 403

        user_payload, token = build_session(db, user)
        log_activity('auth', 'Logged in', actor=user_actor)
        return jsonify({"message": "Login successful", "user": user_payload, "token": token})

    except Exception:
        if DEBUG:
            raise
        return jsonify({"error": "Login failed"}), 500

# ── AUTH: LOGIN WITH GOOGLE ──
# Google already proves the email is real, so this never sends/checks an
# OTP. It only ever signs in an EXISTING account - a Google sign-in with no
# matching account is pointed at registration instead (see register_google
# below), same as a plain login never auto-creates one.
@app.route('/api/login/google', methods=['POST'])
@limiter.limit("8 per minute")
def login_google():
    data = request.get_json() or {}
    credential = data.get('credential') or ''
    if not credential:
        return jsonify({"error": "Missing Google credential"}), 400

    try:
        google_user = verify_google_credential(credential)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        db = get_db()
        user = find_or_link_google_user(db, google_user)

        if not user:
            log_activity('auth', 'Failed Google sign-in - no account with this email',
                         actor={"email": google_user['email']}, outcome='failure')
            return jsonify({
                "error": "No account found for this Google account. Create one first.",
                "needs_registration": True,
            }), 404

        user_actor = {"id": user['_id'], "email": user['email'], "role": user['role'],
                      "full_name": user.get('full_name'), "organization_id": user.get('organization_id')}
        user_payload, token = build_session(db, user)
        log_activity('auth', 'Logged in with Google', actor=user_actor)
        return jsonify({"message": "Login successful", "user": user_payload, "token": token})

    except Exception:
        if DEBUG:
            raise
        return jsonify({"error": "Login failed"}), 500

# ── AUTH: LOGOUT ──
@app.route('/api/logout', methods=['POST'])
@require_auth
def logout():
    revoke_token(g.current_token)
    log_activity('auth', 'Logged out')
    return jsonify({"message": "Logged out"})


# Personal-info fields once collected at registration, reused to prefill the
# application form. Registration no longer collects these - they're now
# filled in once, directly on the application form itself (or later via
# Settings' PUT /api/profile) - but GET /api/profile below still reports
# them, so a student who filled these in some other way still gets prefilled.
PROFILE_FIELDS = [
    'dob', 'gender', 'religion', 'citizenship', 'contactNumber', 'address',
    'fatherName', 'fatherOccupation', 'fatherEducation',
    'motherName', 'motherOccupation', 'motherEducation',
    'monthlyIncome', 'familySize', 'numSiblings', 'numSiblingsStudying',
    'housingSituation', 'hasOtherScholarship', 'otherScholarshipDetails',
]

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

    try:
        db = get_db()

        if db.users.find_one({"email": email}):
            return jsonify({"error": "An account with this email already exists"}), 409

        result = db.users.insert_one({
            "full_name": full_name,
            "email": email,
            "password": generate_password_hash(password),
            "password_set": True,
            "role": "student",
            "status": "active",
            "email_verified": False,
            "created_at": datetime.utcnow(),
            "privacy_consent": True,
            "organization_id": organization["_id"],
        })
        db.memberships.insert_one({
            "user_id": result.inserted_id,
            "organization_id": organization["_id"],
            "role": "student",
            "permissions": None,
            "municipality": None,
            "joined_at": datetime.utcnow(),
        })
        create_and_send_otp(email, 'register', full_name)
        log_activity('account', 'Registered a student account',
                     actor={"id": result.inserted_id, "email": email, "role": "student",
                            "full_name": full_name, "organization_id": organization["_id"]})

        return jsonify({
            "message": "Enter the verification code sent to your email to finish creating your account.",
            "email": email,
        }), 201

    except Exception:
        if DEBUG:
            raise
        return jsonify({"error": "Registration failed"}), 500

# ── AUTH: REGISTER WITH GOOGLE ──
# Google already proves the email is real, so this skips the OTP step
# entirely - the account is ready to use immediately. If the email already
# belongs to an account in the SAME organization, this signs them in instead
# of erroring (Google verified they own the address either way); a match in
# a different organization is rejected since a join code decides which LGU a
# student belongs to and we won't silently move them.
@app.route('/api/register/google', methods=['POST'])
@limiter.limit("8 per minute")
def register_google():
    data = request.get_json() or {}
    credential = data.get('credential') or ''
    join_code = (data.get('join_code') or '').strip().upper()

    if not credential:
        return jsonify({"error": "Missing Google credential"}), 400
    if not join_code:
        return jsonify({"error": "An LGU join code is required"}), 400

    try:
        google_user = verify_google_credential(credential)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    organization = find_active_organization_by_code(get_db(), join_code)
    if not organization:
        return jsonify({"error": "That join code isn't valid. Check it with your LGU and try again."}), 400

    try:
        db = get_db()
        email = google_user['email']
        existing = db.users.find_one({"email": email})

        if existing:
            if str(existing.get('organization_id')) != str(organization['_id']):
                return jsonify({
                    "error": "An account with this email already exists under a different LGU. Sign in instead.",
                }), 409
            user = find_or_link_google_user(db, google_user)
            user_actor = {"id": user['_id'], "email": user['email'], "role": user['role'],
                          "full_name": user.get('full_name'), "organization_id": user.get('organization_id')}
            user_payload, token = build_session(db, user)
            log_activity('auth', 'Logged in with Google', actor=user_actor)
            return jsonify({"message": "Login successful", "user": user_payload, "token": token})

        result = db.users.insert_one({
            "full_name": google_user['name'],
            "email": email,
            "password": generate_password_hash(secrets.token_urlsafe(32)),
            "password_set": False,
            "google_id": google_user['sub'],
            "role": "student",
            "status": "active",
            "email_verified": True,
            "created_at": datetime.utcnow(),
            "privacy_consent": True,
            "organization_id": organization["_id"],
        })
        db.memberships.insert_one({
            "user_id": result.inserted_id,
            "organization_id": organization["_id"],
            "role": "student",
            "permissions": None,
            "municipality": None,
            "joined_at": datetime.utcnow(),
        })
        log_activity('account', 'Registered a student account with Google',
                     actor={"id": result.inserted_id, "email": email, "role": "student",
                            "full_name": google_user['name'], "organization_id": organization["_id"]})

        user_payload = {
            "id": str(result.inserted_id), "full_name": google_user['name'], "email": email, "role": "student",
            "organization_id": str(organization["_id"]),
        }
        return jsonify({
            "message": "Your account is ready.",
            "user": user_payload,
            "token": issue_token(user_payload),
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
        log_activity('account', 'Failed email verification code', actor={"email": email}, outcome='failure')
        return jsonify({"error": error}), 400

    db = get_db()
    db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
    user = db.users.find_one({"email": email})
    if not user:
        return jsonify({"error": "Account not found"}), 404
    log_activity('account', 'Verified email address',
                 actor={"id": user['_id'], "email": user['email'], "role": user['role'],
                        "full_name": user.get('full_name'), "organization_id": user.get('organization_id')})

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
    user = decrypt_fields(user, ENCRYPTED_PROFILE_FIELDS)

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

# Email is excluded - it's the login credential and matches applicant records.
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
    db.users.update_one({"_id": user_oid}, {"$set": encrypt_fields(set_fields, ENCRYPTED_PROFILE_FIELDS)})
    log_activity('account', 'Updated profile', details='Changed: ' + ', '.join(sorted(set_fields)))
    user = decrypt_fields(db.users.find_one({"_id": user_oid}), ENCRYPTED_PROFILE_FIELDS)
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
    # 403, not 401: the frontend treats any 401 as an expired session and signs
    # the user out, which a mistyped current password shouldn't do.
    if not valid:
        log_activity('account', 'Failed password change - wrong current password', outcome='failure')
        return jsonify({"error": "Current password is incorrect"}), 403

    db.users.update_one({"_id": user_oid}, {"$set": {"password": generate_password_hash(new_password)}})
    log_activity('account', 'Changed password')
    return jsonify({"message": "Password changed successfully"})

# ── AUTH: FORGOT PASSWORD ──
@app.route('/api/forgot-password', methods=['POST'])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Same message regardless of outcome - avoids account enumeration.
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
            log_activity('account', 'Requested a password reset email',
                         actor={"id": user['_id'], "email": user['email'], "role": user['role'],
                                "full_name": user.get('full_name'), "organization_id": user.get('organization_id')})
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

    # The link was only ever emailed to this address, so using it also proves
    # the inbox is theirs - an account stuck unverified can finish here.
    result = db.users.update_one(
        {"_id": user_oid},
        {"$set": {"password": generate_password_hash(new_password), "password_set": True, "email_verified": True}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "This reset link is invalid."}), 400

    user = db.users.find_one({"_id": user_oid}, {"email": 1, "role": 1, "full_name": 1, "organization_id": 1}) or {}
    log_activity('account', 'Reset password using the emailed link',
                 actor={"id": user_oid, "email": user.get('email'), "role": user.get('role'),
                        "full_name": user.get('full_name'), "organization_id": user.get('organization_id')})
    return jsonify({"message": "Password reset successfully. You can now log in with your new password."})
