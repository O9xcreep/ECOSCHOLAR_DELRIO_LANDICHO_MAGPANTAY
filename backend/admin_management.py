# -*- coding: utf-8 -*-
"""Admin/LGU-member account management, the admin-request (apply/invite)
flow, and organization lookup/self-view routes."""
import re
import secrets
import hashlib
from datetime import datetime
from flask import request, jsonify, g, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from itsdangerous import BadSignature, SignatureExpired
import gridfs

from extensions import app, limiter, get_db, DEBUG, FRONTEND_URL, _fs
from helpers import oid, iso, send_email_async, get_default_organization_id, \
    generate_unique_join_code, find_active_organization_by_code, serialize_organization, \
    get_organization_municipality
from auth import require_permission, require_auth, current_organization_oid, ADMIN_PERMISSIONS, \
    create_and_send_otp, verify_otp, issue_token, _admin_apply_serializer, ADMIN_APPLY_TOKEN_MAX_AGE
from documents import allowed_file, ALLOWED_EXTENSIONS, safe_mime_for
from memberships import create_membership_from_approved_request, serialize_membership, _activate_membership
from activity import log_activity

PERMISSION_LABELS = {
    'can_review_applicants': 'review applicants',
    'can_manage_members': 'manage members',
    'can_reset_program': 'reset program',
}

def describe_permissions(permissions):
    granted = [PERMISSION_LABELS.get(p, p) for p, on in (permissions or {}).items() if on]
    return 'Permissions: ' + (', '.join(granted) if granted else 'none')

# Lets a logged-in admin/member see their own organization's join code, to
# share it with whoever they want to invite next.
@app.route('/api/organizations/mine', methods=['GET'])
@require_permission('can_manage_members')
def get_my_organization():
    db = get_db()
    org_id = current_organization_oid()
    org = db.organizations.find_one({"_id": org_id}) if org_id else None
    if not org:
        return jsonify({"error": "No organization found for your account"}), 404
    return jsonify({"organization": {**serialize_organization(org), "join_code": org.get("join_code", "")}})

# Public (no auth) - lets registration/admin-apply pages preview which LGU a
# code belongs to. Only ever reveals the organization's display name.
@app.route('/api/organizations/lookup', methods=['GET'])
@limiter.limit("20 per minute")
def lookup_organization():
    code = request.args.get('code') or ''
    org = find_active_organization_by_code(get_db(), code)
    if not org:
        return jsonify({"error": "That join code isn't valid. Check it with your LGU and try again."}), 404
    return jsonify({"organization": serialize_organization(org)})

def serialize_admin(u):
    doc = {
        "id": str(u["_id"]),
        "full_name": u.get("full_name", ""),
        "email": u.get("email", ""),
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
        # Not individually configurable - the Admin seat always has everything.
        # Serialized as all-True so the frontend uses the same checklist UI.
        doc["permissions"] = {p: True for p in ADMIN_PERMISSIONS}
    return doc

def serialize_admin_membership(u, membership):
    """Like serialize_admin(), but reads role/permissions/municipality/joined
    date from a specific MEMBERSHIP rather than the user's flat/active-org
    fields - a user's flat fields only reflect whichever org they last
    switched into, not necessarily this one."""
    role = membership.get("role", "lgu_member")
    doc = {
        "id": str(u["_id"]),
        "full_name": u.get("full_name", ""),
        "email": u.get("email", ""),
        "municipality": membership.get("municipality", ""),
        "role": role,
        "password_set": u.get("password_set", True),
        "created_at": iso(membership.get("joined_at") or u.get("created_at")),
    }
    if role == "lgu_member":
        doc["permissions"] = {p: bool((membership.get("permissions") or {}).get(p)) for p in ADMIN_PERMISSIONS}
    elif role == "lgu_admin":
        doc["permissions"] = {p: True for p in ADMIN_PERMISSIONS}
    return doc

# ── ADMIN ACCOUNT MANAGEMENT ──
# Super Admin (role="admin") is deliberately unreachable here - it's a
# dev/platform account, not part of an LGU's own team. This surface only
# manages "lgu_admin" (the one Admin seat) and "lgu_member" (team members).
@app.route('/api/admins', methods=['GET'])
@require_permission('can_manage_members')
def list_admins():
    db = get_db()
    org_id = current_organization_oid()
    # Query memberships, not users.organization_id directly - a member's flat
    # fields only reflect whichever org they last switched their active
    # session into, which may not be this one anymore.
    memberships_by_user = {
        m["user_id"]: m for m in
        db.memberships.find({"organization_id": org_id, "role": {"$in": ["lgu_admin", "lgu_member"]}})
    }
    if not memberships_by_user:
        return jsonify({"admins": []})
    users_by_id = {u["_id"]: u for u in db.users.find({"_id": {"$in": list(memberships_by_user.keys())}})}
    admins = [
        serialize_admin_membership(users_by_id[uid], m)
        for uid, m in memberships_by_user.items() if uid in users_by_id
    ]
    admins.sort(key=lambda a: a["created_at"] or "")
    return jsonify({"admins": admins})

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

    org_id = current_organization_oid()
    admin_doc = create_admin_with_setup_email(
        full_name=full_name,
        email=email,
        role='lgu_member',
        permissions=permissions,
        municipality=get_organization_municipality(db, org_id),
        organization_id=org_id,
    )
    log_activity('staff', 'Added a team member', organization_id=org_id,
                 target={"type": "user", "id": admin_doc.get('_id'), "label": f"{full_name} ({email})"},
                 details=describe_permissions(permissions))
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
    org_id = current_organization_oid()
    membership = db.memberships.find_one({"user_id": admin_oid, "organization_id": org_id, "role": "lgu_member"})
    if not membership:
        return jsonify({"error": "LGU member not found (use Pass Admin Role to change who holds the Admin seat)"}), 404

    data = request.get_json() or {}
    raw = data.get('permissions') or {}
    permissions = {p: bool(raw.get(p)) for p in ADMIN_PERMISSIONS}

    db.memberships.update_one({"_id": membership["_id"]}, {"$set": {"permissions": permissions}})
    # Keep the flat cache honest if (and only if) this happens to be that
    # member's currently-active org - a no-op match otherwise.
    db.users.update_one({"_id": admin_oid, "organization_id": org_id}, {"$set": {"permissions": permissions}})

    target = db.users.find_one({"_id": admin_oid})
    log_activity('staff', "Changed a team member's permissions", organization_id=org_id,
                 target={"type": "user", "id": admin_oid,
                         "label": f"{(target or {}).get('full_name')} ({(target or {}).get('email')})"},
                 details=describe_permissions(permissions))
    membership["permissions"] = permissions
    return jsonify({"admin": serialize_admin_membership(target, membership)})

# ── TRANSFER THE ADMIN SEAT ──
# Exactly one lgu_admin can exist at a time. Super Admin can assign the first
# one (or reassign in an emergency); once held, only the current holder can
# pass it on. The outgoing Admin is demoted to a bare lgu_member (permissions
# cleared) rather than left with residual elevated access.
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
    org_id = current_organization_oid()
    target_membership = db.memberships.find_one({"user_id": target_oid, "organization_id": org_id, "role": "lgu_member"})
    if not target_membership:
        return jsonify({"error": "Target must be an existing LGU member"}), 404

    requester_role = g.current_user.get('role')
    current_admin_membership = db.memberships.find_one({"role": "lgu_admin", "organization_id": org_id})
    if requester_role == 'lgu_member':
        return jsonify({"error": "Only the current Admin (or Super Admin) can pass on the Admin seat"}), 403
    if requester_role == 'lgu_admin' and (not current_admin_membership or str(current_admin_membership['user_id']) != g.current_user['id']):
        return jsonify({"error": "Only the current Admin can pass on the Admin seat"}), 403

    if current_admin_membership:
        demoted = {"role": "lgu_member", "permissions": {p: False for p in ADMIN_PERMISSIONS}}
        db.memberships.update_one({"_id": current_admin_membership["_id"]}, {"$set": demoted})
        # Mirrors onto the flat cache only if this org happens to be that
        # user's currently-active one - a no-op match otherwise.
        db.users.update_one({"_id": current_admin_membership["user_id"], "organization_id": org_id}, {"$set": demoted})

    db.memberships.update_one({"_id": target_membership["_id"]}, {"$set": {"role": "lgu_admin"}, "$unset": {"permissions": ""}})
    db.users.update_one(
        {"_id": target_oid, "organization_id": org_id},
        {"$set": {"role": "lgu_admin"}, "$unset": {"permissions": ""}}
    )

    target_membership["role"] = "lgu_admin"
    new_admin = db.users.find_one({"_id": target_oid})
    log_activity('staff', 'Passed the Admin role', organization_id=org_id,
                 target={"type": "user", "id": target_oid,
                         "label": f"{(new_admin or {}).get('full_name')} ({(new_admin or {}).get('email')})"})
    return jsonify({"admin": serialize_admin_membership(new_admin, target_membership)})

@app.route('/api/admins/<admin_id>/resend-invite', methods=['POST'])
@require_permission('can_manage_members')
@limiter.limit("5 per minute")
def resend_admin_invite(admin_id):
    admin_oid = oid(admin_id)
    if not admin_oid:
        return jsonify({"error": "Invalid admin id"}), 400

    db = get_db()
    admin = db.users.find_one({"_id": admin_oid, "role": {"$in": ["lgu_admin", "lgu_member"]}, "organization_id": current_organization_oid()})
    if not admin:
        return jsonify({"error": "Admin account not found"}), 404
    if admin.get("password_set", True):
        return jsonify({"error": "This admin has already set their password"}), 400

    create_and_send_otp(admin["email"], 'admin_setup', admin['full_name'])
    return jsonify({"message": "Invite resent"})

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
    """Removes someone from THIS organization's team only - their account (and
    any other org memberships it holds) isn't touched, since a login can now
    belong to more than one org. Full account deletion is self-service only
    (see memberships.py's DELETE /api/account)."""
    admin_oid = oid(admin_id)
    if not admin_oid:
        return jsonify({"error": "Invalid admin id"}), 400

    if str(admin_oid) == g.current_user['id']:
        return jsonify({"error": "You can't remove your own account"}), 400

    db = get_db()
    org_id = current_organization_oid()
    membership = db.memberships.find_one({"user_id": admin_oid, "organization_id": org_id, "role": {"$in": ["lgu_admin", "lgu_member"]}})
    if not membership:
        return jsonify({"error": "Admin account not found"}), 404
    if membership.get('role') == 'lgu_admin':
        return jsonify({"error": "Can't remove the account currently holding the Admin seat - pass the Admin role to someone else first"}), 400

    db.memberships.delete_one({"_id": membership["_id"]})
    removed = db.users.find_one({"_id": admin_oid}, {"full_name": 1, "email": 1}) or {}
    log_activity('staff', 'Removed a team member', organization_id=org_id,
                 target={"type": "user", "id": admin_oid,
                         "label": f"{removed.get('full_name')} ({removed.get('email')})"})

    # If this org happened to be that user's currently-active one, the flat
    # cache would otherwise dangle, pointing at an org they're no longer
    # part of - re-point it to another remaining membership, or to an
    # explicit "no org" state if none remain.
    user = db.users.find_one({"_id": admin_oid})
    if user and user.get('organization_id') == org_id:
        remaining = db.memberships.find_one({"user_id": admin_oid}, sort=[("joined_at", 1)])
        if remaining:
            _activate_membership(db, admin_oid, remaining)
        else:
            db.users.update_one(
                {"_id": admin_oid},
                {"$set": {"organization_id": None, "role": "lgu_member", "permissions": {p: False for p in ADMIN_PERMISSIONS}, "municipality": ""}}
            )

    return jsonify({"message": "Removed from this organization's team"})

def create_admin_with_setup_email(full_name, email, municipality='', role='lgu_member', permissions=None, organization_id=None):
    """Inserts a new admin/LGU-member user with no usable starting password and
    emails them a one-time code to set one, so nobody (not even the creating
    admin) ever knows another team member's password. An approved public
    application is different - see create_admin_from_approved_request."""
    db = get_db()
    placeholder_password = generate_password_hash(secrets.token_urlsafe(32))
    doc = {
        "full_name": full_name,
        "email": email,
        "password": placeholder_password,
        "password_set": False,
        "role": role,
        "status": "active",
        "municipality": municipality,
        "created_at": datetime.utcnow(),
        "privacy_consent": True,
    }
    if role == 'lgu_member':
        doc["permissions"] = permissions or {p: False for p in ADMIN_PERMISSIONS}
    doc["organization_id"] = organization_id or get_default_organization_id(db)
    result = db.users.insert_one(doc)
    db.memberships.insert_one({
        "user_id": result.inserted_id, "organization_id": doc["organization_id"], "role": role,
        "permissions": doc.get("permissions"), "municipality": municipality, "joined_at": doc["created_at"],
    })

    create_and_send_otp(email, 'admin_setup', full_name)
    return db.users.find_one({"_id": result.inserted_id})

def create_admin_from_approved_request(req, role, permissions):
    """Inserts a new admin/LGU-member user using the password the applicant
    already chose and proved their email for. Unlike
    create_admin_with_setup_email, no placeholder password or set-password
    email is needed since they picked a real one upfront."""
    db = get_db()
    doc = {
        "full_name": req["full_name"],
        "email": req["email"],
        "password": req["password_hash"],
        "password_set": True,
        "role": role,
        "status": "active",
        "municipality": req.get("municipality", ""),
        "created_at": datetime.utcnow(),
        "privacy_consent": True,
    }
    if role == 'lgu_member':
        doc["permissions"] = permissions or {p: False for p in ADMIN_PERMISSIONS}
    doc["organization_id"] = req.get("organization_id") or get_default_organization_id(db)
    result = db.users.insert_one(doc)
    db.memberships.insert_one({
        "user_id": result.inserted_id, "organization_id": doc["organization_id"], "role": role,
        "permissions": doc.get("permissions"), "municipality": doc["municipality"], "joined_at": doc["created_at"],
    })

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
                Your admin account request{f" ({req['municipality']})" if req.get('municipality') else ""} has been approved.
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

def serialize_admin_request(r, db=None):
    first_approval = r.get("first_approval")
    org_name = None
    if db is not None and r.get("organization_id"):
        org = db.organizations.find_one({"_id": r["organization_id"]})
        org_name = org.get("name") if org else None
    return {
        "id": str(r["_id"]),
        "full_name": r.get("full_name", ""),
        "email": r.get("email", ""),
        "municipality": r.get("municipality", ""),
        "contact_number": r.get("contact_number", ""),
        "message": r.get("message", ""),
        "status": r.get("status", "pending"),
        "created_at": iso(r.get("created_at")),
        "reviewed_at": iso(r.get("reviewed_at")),
        "proof_of_employment_filename": (r.get("proof_of_employment") or {}).get("filename"),
        "first_approval": {
            "admin_id": first_approval["admin_id"],
            "admin_name": first_approval["admin_name"],
        } if first_approval else None,
        # "Founding" requests bootstrap a new organization and are only ever
        # reviewed by the platform Super Admin, not by an LGU's own admins.
        "is_founding": bool(r.get("is_founding")),
        "organization_name": org_name,
        # "new_account" (default, for requests predating this field) creates a
        # brand-new login on approval; "add_membership" instead adds a
        # membership to an EXISTING account (see join_existing_org below).
        "request_kind": r.get("request_kind", "new_account"),
    }

# ── ADMIN ACCOUNT REQUESTS (LGU officials applying for admin access) ──
# Two-step so nobody can submit a request impersonating someone else's inbox:
# 1) POST /start with just an email - emails a one-time code, never confirms
#    whether that email already has an account or a pending request.
# 2) POST /verify-start-otp exchanges the code for a short-lived token proving
#    the email was reachable; only then does the full form become fillable,
#    stored under the token's email, not a client-supplied one.
# A submission never creates the account directly - it queues a request that
# an existing admin must approve, since admin accounts can see every
# applicant's PII and control disbursement decisions.
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

    token = _admin_apply_serializer.dumps({"email": email, "purpose": "admin_apply"})
    return jsonify({"token": token})

# Shared by both ways of becoming an admin: a public applicant proving their
# email (mode "apply", creates a pending admin_requests row) and someone
# already invited by an admin (mode "invite", password_set=False). Same token
# shape and downstream /apply-admin page; `purpose` picks which form to render.
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

    email = payload.get('email', '')
    purpose = payload.get('purpose', 'admin_apply')

    if purpose == 'admin_setup':
        db = get_db()
        user = db.users.find_one({"email": email, "role": {"$in": ["lgu_admin", "lgu_member"]}, "password_set": False})
        if not user:
            return jsonify({"error": "This invite is no longer valid."}), 400
        return jsonify({
            "email": email,
            "mode": "invite",
            "full_name": user.get("full_name", ""),
            "municipality": user.get("municipality", ""),
            "role": user.get("role"),
        })

    return jsonify({"email": email, "mode": "apply"})

@app.route('/api/admins/verify-setup-code', methods=['POST'])
@limiter.limit("10 per minute")
def verify_admin_setup_code():
    """First step of the invite-activation flow - proves the OTP is correct,
    same shape as verify-start-otp. The invitee lands on /apply-admin (via
    the returned token) to set their password."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    code = data.get('code') or ''
    if not email or not code:
        return jsonify({"error": "Email and code are required"}), 400

    ok, error = verify_otp(email, 'admin_setup', code)
    if not ok:
        return jsonify({"error": error}), 400

    token = _admin_apply_serializer.dumps({"email": email, "purpose": "admin_setup"})
    return jsonify({"token": token})

@app.route('/api/admins/complete-invite-setup', methods=['POST'])
@limiter.limit("10 per minute")
def complete_admin_invite_setup():
    """Final step for an invited admin/LGU member - sets the password chosen
    on the shared /apply-admin page. Mirrors submit_admin_request's token
    handling but activates an existing account instead of creating a request."""
    data = request.get_json() or {}
    token = data.get('token') or ''
    new_password = data.get('new_password') or ''

    try:
        payload = _admin_apply_serializer.loads(token, max_age=ADMIN_APPLY_TOKEN_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This session has expired. Please verify your email again."}), 400
    except BadSignature:
        return jsonify({"error": "This session is invalid."}), 400

    if payload.get('purpose') != 'admin_setup':
        return jsonify({"error": "This session is invalid."}), 400
    email = (payload.get('email') or '').strip().lower()

    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    db = get_db()
    user = db.users.find_one({"email": email, "role": {"$in": ["lgu_admin", "lgu_member"]}, "password_set": False})
    if not user:
        return jsonify({"error": "This invite is no longer valid."}), 400

    db.users.update_one({"_id": user["_id"]}, {"$set": {
        "password": generate_password_hash(new_password),
        "password_set": True,
    }})
    log_activity('account', 'Set password and activated invited staff account',
                 actor={"id": user['_id'], "email": user['email'], "role": user['role'],
                        "full_name": user.get('full_name'), "organization_id": user.get('organization_id')})
    user_payload = {
        "id": str(user['_id']), "full_name": user['full_name'], "email": user['email'], "role": user['role'],
        "organization_id": str(user['organization_id']) if user.get('organization_id') else None,
    }
    if user['role'] == 'lgu_member':
        user_payload["permissions"] = {p: bool(user.get('permissions', {}).get(p)) for p in ADMIN_PERMISSIONS}
    return jsonify({
        "message": "Password set. Your account is ready.",
        "user": user_payload,
        "token": issue_token(user_payload)
    })

@app.route('/api/admin-requests', methods=['POST'])
@limiter.limit("5 per minute")
def submit_admin_request():
    # multipart/form-data, not JSON, since a document upload is required.
    token = request.form.get('token') or ''
    full_name = (request.form.get('full_name') or '').strip()
    password = request.form.get('password') or ''
    municipality = (request.form.get('municipality') or '').strip()
    contact_number = (request.form.get('contact_number') or '').strip()
    message = (request.form.get('message') or '').strip()

    try:
        payload = _admin_apply_serializer.loads(token, max_age=ADMIN_APPLY_TOKEN_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This session has expired. Please verify your email again."}), 400
    except BadSignature:
        return jsonify({"error": "This session is invalid."}), 400
    email = (payload.get('email') or '').strip().lower()

    if not full_name or not email or not contact_number or not password:
        return jsonify({"error": "Full name, password, and contact number are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    # A valid ID or proof-of-employment document is required, raising the bar
    # above "just fill in a form claiming to work for the LGU". Same
    # file-type rules as the student document pipeline (upload_document).
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"error": "A valid ID or proof-of-employment document is required"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"File must be one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}), 400

    # "Create" bootstraps a brand-new LGU (reviewed by the platform Super
    # Admin, since no peer admins exist yet); "join" attaches to an LGU that
    # already exists, via its own admins' shared join code.
    org_mode = (request.form.get('org_mode') or 'join').strip().lower()
    if org_mode not in ('join', 'create'):
        return jsonify({"error": "org_mode must be 'join' or 'create'"}), 400

    db = get_db()
    if db.users.find_one({"email": email}):
        return jsonify({"error": "An account with this email already exists"}), 409
    if db.admin_requests.find_one({"email": email, "status": {"$in": ["pending", "pending_second_approval"]}}):
        return jsonify({"error": "A request for this email is already pending review"}), 409

    is_founding = org_mode == 'create'
    if is_founding:
        org_name = (request.form.get('org_name') or '').strip()
        if not org_name:
            return jsonify({"error": "Organization name is required"}), 400
        if not municipality:
            return jsonify({"error": "Municipality is required"}), 400
        organization_id = db.organizations.insert_one({
            "name": org_name,
            "join_code": generate_unique_join_code(db),
            "status": "pending",
            "created_at": datetime.utcnow(),
            "founding_admin_request_id": None,
            "municipality": municipality,
        }).inserted_id
    else:
        join_code = (request.form.get('join_code') or '').strip().upper()
        organization = find_active_organization_by_code(db, join_code)
        if not organization:
            return jsonify({"error": "That join code isn't valid. Check it with your LGU and try again."}), 400
        organization_id = organization["_id"]
        # Everyone joining an existing org shares its municipality already -
        # inherit it instead of asking each applicant to redundantly pick one.
        municipality = organization.get("municipality", "")

    filename = secure_filename(file.filename)
    unique_filename = f"admin-request_{email}_{filename}"
    file_bytes = file.read()
    gridfs_id = _fs.put(file_bytes, filename=unique_filename, content_type=safe_mime_for(unique_filename))

    result = db.admin_requests.insert_one({
        "full_name": full_name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "municipality": municipality,
        "contact_number": contact_number,
        "message": message,
        "proof_of_employment": {
            "gridfs_id": gridfs_id,
            "filename": filename,
            "content_type": safe_mime_for(unique_filename),
            "file_hash": hashlib.sha256(file_bytes).hexdigest(),
            "uploaded_at": datetime.utcnow(),
        },
        "status": "pending",
        "first_approval": None,
        "second_approval": None,
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
        "reviewed_by": None,
        "organization_id": organization_id,
        "is_founding": is_founding,
    })

    if is_founding:
        db.organizations.update_one({"_id": organization_id}, {"$set": {"founding_admin_request_id": result.inserted_id}})

    return jsonify({"message": "Your request has been submitted for review. An existing admin will verify your details."}), 201

# ── ADMIN/STAFF REQUESTS TO JOIN A DIFFERENT ORG ──
# Unlike submit_admin_request (a brand-new applicant, not yet authenticated,
# hence the OTP/email-proof dance), the caller here is already a logged-in
# admin/LGU member - skip straight to the proof-of-employment upload. Always
# approval-gated (see approve_admin_request's request_kind branch), never
# instant, since a join code isn't a secret credential - anyone who has one
# could otherwise place themselves on another LGU's team unvetted.
@app.route('/api/admin-requests/join-org', methods=['POST'])
@require_auth
@limiter.limit("5 per minute")
def request_join_org():
    if g.current_user.get('role') not in ('lgu_admin', 'lgu_member'):
        return jsonify({"error": "Only admin/LGU staff accounts can request to join another organization"}), 403

    join_code = (request.form.get('join_code') or '').strip().upper()
    contact_number = (request.form.get('contact_number') or '').strip()
    message = (request.form.get('message') or '').strip()

    if not join_code or not contact_number:
        return jsonify({"error": "Join code and contact number are required"}), 400

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"error": "A valid ID or proof-of-employment document is required"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"File must be one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}), 400

    db = get_db()
    organization = find_active_organization_by_code(db, join_code)
    if not organization:
        return jsonify({"error": "That join code isn't valid. Check it with your LGU and try again."}), 400
    # Already a member of that org's municipality, whatever it is - inherit
    # it rather than asking again.
    municipality = organization.get('municipality', '')

    user_oid = oid(g.current_user['id'])
    if organization["_id"] == current_organization_oid():
        return jsonify({"error": "That's already your current organization"}), 400
    if db.memberships.find_one({"user_id": user_oid, "organization_id": organization["_id"]}):
        return jsonify({"error": "You're already a member of that organization"}), 409
    if db.admin_requests.find_one({
        "user_id": user_oid, "organization_id": organization["_id"],
        "request_kind": "add_membership", "status": {"$in": ["pending", "pending_second_approval"]},
    }):
        return jsonify({"error": "A request to join this organization is already pending review"}), 409

    filename = secure_filename(file.filename)
    unique_filename = f"admin-request_{g.current_user['email']}_{filename}"
    file_bytes = file.read()
    gridfs_id = _fs.put(file_bytes, filename=unique_filename, content_type=safe_mime_for(unique_filename))

    db.admin_requests.insert_one({
        "request_kind": "add_membership",
        "user_id": user_oid,
        "full_name": g.current_user.get('full_name', ''),
        "email": g.current_user['email'],
        "password_hash": None,
        "municipality": municipality,
        "contact_number": contact_number,
        "message": message,
        "proof_of_employment": {
            "gridfs_id": gridfs_id,
            "filename": filename,
            "content_type": safe_mime_for(unique_filename),
            "file_hash": hashlib.sha256(file_bytes).hexdigest(),
            "uploaded_at": datetime.utcnow(),
        },
        "status": "pending",
        "first_approval": None,
        "second_approval": None,
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
        "reviewed_by": None,
        "organization_id": organization["_id"],
        "is_founding": False,
    })

    return jsonify({"message": "Your request has been submitted for review. An admin at that organization will verify your details."}), 201

# Admin-only - lets a reviewer see the applicant's uploaded ID/proof of
# employment before approving/rejecting. Mirrors view_document_file(), but
# targets admin_requests; no "owner self-view" case exists here.
@app.route('/api/admin-requests/<request_id>/proof-of-employment', methods=['GET'])
@require_permission('can_manage_members')
def view_admin_request_proof(request_id):
    request_oid = oid(request_id)
    if not request_oid:
        return jsonify({"error": "Invalid request id"}), 400

    db = get_db()
    req = db.admin_requests.find_one({"_id": request_oid})
    if not req:
        return jsonify({"error": "Request not found"}), 404

    proof = req.get('proof_of_employment')
    if not proof or not proof.get('gridfs_id'):
        return jsonify({"error": "No document on file for this request"}), 404

    try:
        grid_out = _fs.get(proof['gridfs_id'])
    except gridfs.errors.NoFile:
        return jsonify({"error": "File not found on server"}), 404

    return send_file(
        grid_out,
        mimetype=safe_mime_for(grid_out.filename),
        download_name=grid_out.filename,
        as_attachment=False
    )

@app.route('/api/admin-requests', methods=['GET'])
@require_permission('can_manage_members')
def list_admin_requests():
    db = get_db()
    status = request.args.get('status')
    # "pending" covers both an untouched request and one sitting on a single
    # approval waiting on a second admin - both belong in the actionable list.
    if status == 'pending':
        query = {"status": {"$in": ["pending", "pending_second_approval"]}}
    elif status in ('pending_second_approval', 'approved', 'rejected'):
        query = {"status": status}
    else:
        query = {}

    # An LGU's own admins only see their own organization's regular requests,
    # never a founding request. The platform Super Admin additionally sees
    # every founding request, on top of its own organization's regular ones.
    org_id = current_organization_oid()
    if g.current_user.get('role') == 'admin':
        query["$or"] = [
            {"is_founding": True},
            {"is_founding": {"$ne": True}, "organization_id": org_id},
        ]
    else:
        query["is_founding"] = {"$ne": True}
        query["organization_id"] = org_id

    requests_ = list(db.admin_requests.find(query).sort("created_at", -1))
    return jsonify({"requests": [serialize_admin_request(r, db) for r in requests_]})

# Granting can_manage_members is the one privilege-escalation risk in this
# flow, since it lets the new account approve/add further admins, so it alone
# requires two DIFFERENT existing admins to sign off. Any other permission
# combination still finalizes on one approval.
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

    is_founding = bool(req.get("is_founding"))
    if is_founding:
        if g.current_user.get('role') != 'admin':
            return jsonify({"error": "Only the platform Super Admin can approve a new organization"}), 403
    elif req.get("organization_id") != current_organization_oid():
        return jsonify({"error": "This request belongs to a different organization"}), 403

    if req.get("status") not in ("pending", "pending_second_approval"):
        return jsonify({"error": "This request has already been reviewed"}), 400

    is_add_membership = req.get("request_kind") == "add_membership"
    if is_add_membership:
        # The account is SUPPOSED to already exist here - the 409 guard below
        # is inverted: it's an error if a membership already exists, not if
        # the account does.
        if db.memberships.find_one({"user_id": req["user_id"], "organization_id": req["organization_id"]}):
            return jsonify({"error": "This account is already a member of that organization"}), 409
    else:
        if db.users.find_one({"email": req["email"]}):
            return jsonify({"error": "An account with this email already exists"}), 409

    now = datetime.utcnow()
    current_admin_id = g.current_user['id']

    if is_founding:
        # No peer review is possible for a brand-new organization - the Super
        # Admin's review already served as the vetting step, so the founding
        # account is created directly as the org's lgu_admin (full access).
        admin_doc = create_admin_from_approved_request(req, 'lgu_admin', None)
        db.organizations.update_one({"_id": req["organization_id"]}, {"$set": {"status": "active"}})
        db.admin_requests.update_one({"_id": request_oid}, {"$set": {
            "status": "approved", "reviewed_at": now, "reviewed_by": current_admin_id,
        }})
        log_activity('staff', 'Approved a new organization and its first Admin',
                     organization_id=req.get("organization_id"), target={"type": "admin_request", "id": request_oid, "label": f"{req.get('full_name')} ({req.get('email')})"})
        return jsonify({"message": "Organization approved", "admin": serialize_admin(admin_doc)}), 201

    # Always approved as a plain LGU Member on a single approval, whatever
    # permissions are granted (including can_manage_members) - the Admin seat
    # only changes hands via POST /api/admins/<id>/transfer-admin.
    data = request.get_json(silent=True) or {}
    raw = data.get('permissions') or {}
    permissions = {p: bool(raw.get(p)) for p in ADMIN_PERMISSIONS}

    db.admin_requests.update_one({"_id": request_oid}, {"$set": {
        "status": "approved",
        "reviewed_at": now,
        "reviewed_by": current_admin_id,
    }})
    log_activity('staff', 'Approved a request to join the team', organization_id=req.get("organization_id"),
                 target={"type": "admin_request", "id": request_oid, "label": f"{req.get('full_name')} ({req.get('email')})"}, details=describe_permissions(permissions))
    if is_add_membership:
        membership_doc = create_membership_from_approved_request(req, permissions)
        return jsonify({"message": "Admin request approved", "membership": serialize_membership(membership_doc, db)}), 201
    admin_doc = create_admin_from_approved_request(req, 'lgu_member', permissions)

    return jsonify({"message": "Admin request approved", "admin": serialize_admin(admin_doc)}), 201

@app.route('/api/admin-requests/<request_id>/reject', methods=['POST'])
@require_permission('can_manage_members')
def reject_admin_request(request_id):
    request_oid = oid(request_id)
    if not request_oid:
        return jsonify({"error": "Invalid request id"}), 400

    db = get_db()
    req = db.admin_requests.find_one({"_id": request_oid})
    if not req:
        return jsonify({"error": "Request not found or already reviewed"}), 404

    is_founding = bool(req.get("is_founding"))
    if is_founding:
        if g.current_user.get('role') != 'admin':
            return jsonify({"error": "Only the platform Super Admin can reject a new organization"}), 403
    elif req.get("organization_id") != current_organization_oid():
        return jsonify({"error": "This request belongs to a different organization"}), 403

    result = db.admin_requests.update_one(
        {"_id": request_oid, "status": {"$in": ["pending", "pending_second_approval"]}},
        {"$set": {"status": "rejected", "reviewed_at": datetime.utcnow(), "reviewed_by": g.current_user['id']}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Request not found or already reviewed"}), 404
    log_activity('staff', 'Rejected a request to join the team', organization_id=req.get("organization_id"),
                 target={"type": "admin_request", "id": request_oid, "label": f"{req.get('full_name')} ({req.get('email')})"})
    return jsonify({"message": "Admin request rejected"})
