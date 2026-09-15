# -*- coding: utf-8 -*-
"""Multi-org membership: a user's `organization_id`/`role`/`permissions`/
`municipality` fields on `users` are the CURRENTLY ACTIVE membership, cached
there so every existing org-scoped query (current_organization_oid() and its
~200+ call sites) keeps working unmodified. The `memberships` collection is
the source of truth for every org a user actually belongs to; switching or
joining just copies one membership's fields onto the cache and reissues a
token, exactly like login() already snapshots role/org into a token."""
from datetime import datetime
from flask import request, jsonify, g
from werkzeug.security import check_password_hash

from extensions import app, limiter, get_db
from helpers import oid, iso, get_organization_name, find_active_organization_by_code, send_email_async
from auth import require_auth, current_organization_oid, issue_token, revoke_token, ADMIN_PERMISSIONS


def _activate_membership(db, user_oid, membership):
    """Copies a membership's role/permissions/municipality onto the flat
    `users` fields and mints a fresh token, mirroring login()'s user_payload
    shape (auth.py) so the frontend can setSession() with it directly."""
    role = membership["role"]
    set_fields = {"organization_id": membership["organization_id"], "role": role}
    update = {"$set": set_fields}
    if role == "lgu_member":
        set_fields["permissions"] = membership.get("permissions") or {p: False for p in ADMIN_PERMISSIONS}
        set_fields["municipality"] = membership.get("municipality") or ""
    elif role == "lgu_admin":
        set_fields["municipality"] = membership.get("municipality") or ""
        update["$unset"] = {"permissions": ""}

    db.users.update_one({"_id": user_oid}, update)
    user = db.users.find_one({"_id": user_oid})

    user_payload = {
        "id": str(user["_id"]), "full_name": user["full_name"], "email": user["email"], "role": user["role"],
        "organization_id": str(user["organization_id"]) if user.get("organization_id") else None,
        "organization_name": get_organization_name(db, user.get("organization_id")),
    }
    if user["role"] == "lgu_member":
        user_payload["permissions"] = {p: bool(user.get("permissions", {}).get(p)) for p in ADMIN_PERMISSIONS}
    return user_payload, issue_token(user_payload)


def serialize_membership(m, db, active_org_id=None):
    return {
        "organization_id": str(m["organization_id"]),
        "organization_name": get_organization_name(db, m["organization_id"]),
        "role": m["role"],
        "permissions": {p: bool((m.get("permissions") or {}).get(p)) for p in ADMIN_PERMISSIONS} if m["role"] == "lgu_member" else None,
        "municipality": m.get("municipality"),
        "joined_at": iso(m.get("joined_at")),
        "is_active": m["organization_id"] == active_org_id,
    }


def create_membership_from_approved_request(req, permissions):
    """The multi-org-safe counterpart to create_admin_from_approved_request()
    (admin_management.py) for a request from an EXISTING account - inserts
    only a membership row, never a new `users` doc (which would collide with
    the unique email index), and always role lgu_member (never lgu_admin,
    preserving the one-seat-per-org rule)."""
    db = get_db()
    membership_doc = {
        "user_id": req["user_id"],
        "organization_id": req["organization_id"],
        "role": "lgu_member",
        "permissions": permissions or {p: False for p in ADMIN_PERMISSIONS},
        "municipality": req.get("municipality", ""),
        "joined_at": datetime.utcnow(),
    }
    db.memberships.insert_one(membership_doc)

    org_name = get_organization_name(db, req["organization_id"]) or "the organization"
    user = db.users.find_one({"_id": req["user_id"]})
    if user:
        send_email_async(
            user["email"],
            f"You've been added to {org_name} on EcoScholar",
            f"<p>Your request to join {org_name} has been approved. You're now an LGU Member there - "
            f"open Settings &rsaquo; Your Organizations next time you sign in to switch into it.</p>"
        )
    return membership_doc


# ── LIST MY MEMBERSHIPS ──
@app.route('/api/memberships', methods=['GET'])
@require_auth
def list_my_memberships():
    if g.current_user.get('role') == 'admin':
        return jsonify({"memberships": []})
    db = get_db()
    user_oid = oid(g.current_user['id'])
    active_org_id = current_organization_oid()
    rows = list(db.memberships.find({"user_id": user_oid}).sort("joined_at", 1))
    return jsonify({"memberships": [serialize_membership(m, db, active_org_id) for m in rows]})


# ── STUDENT SELF-SERVICE JOIN ──
# Admin/staff joining a DIFFERENT org needs approval (see
# admin_management.py's POST /api/admin-requests/join-org) since a join code
# isn't a secret credential - anyone with one could otherwise place
# themselves on another LGU's team unvetted. A student has no such privilege
# risk (role is always 'student'), so this stays instant self-service, same
# as registration already is.
@app.route('/api/organizations/join', methods=['POST'])
@require_auth
@limiter.limit("8 per minute")
def join_organization():
    if g.current_user.get('role') != 'student':
        return jsonify({"error": "Admin and LGU staff accounts need approval to join another organization - use \"Request to Join\" in Settings instead."}), 403

    data = request.get_json() or {}
    join_code = (data.get('join_code') or '').strip().upper()

    db = get_db()
    organization = find_active_organization_by_code(db, join_code)
    if not organization:
        return jsonify({"error": "That join code isn't valid. Check it with your LGU and try again."}), 400

    user_oid = oid(g.current_user['id'])
    membership = db.memberships.find_one({"user_id": user_oid, "organization_id": organization["_id"]})
    if not membership:
        membership = {
            "user_id": user_oid, "organization_id": organization["_id"], "role": "student",
            "permissions": None, "municipality": None, "joined_at": datetime.utcnow(),
        }
        db.memberships.insert_one(membership)

    user_payload, token = _activate_membership(db, user_oid, membership)
    return jsonify({"message": f"Joined {organization.get('name', 'the organization')}", "user": user_payload, "token": token})


# ── SWITCH ACTIVE ORGANIZATION ──
# Shared by students and admin/staff alike - requires an existing membership,
# never creates one (that's join_organization or an approved admin-request).
@app.route('/api/organizations/switch', methods=['POST'])
@require_auth
def switch_organization():
    if g.current_user.get('role') == 'admin':
        return jsonify({"error": "The Super Admin account isn't tied to an organization"}), 400

    data = request.get_json() or {}
    target_oid = oid(data.get('organization_id'))
    if not target_oid:
        return jsonify({"error": "Invalid organization id"}), 400

    db = get_db()
    user_oid = oid(g.current_user['id'])
    membership = db.memberships.find_one({"user_id": user_oid, "organization_id": target_oid})
    if not membership:
        return jsonify({"error": "You're not a member of that organization"}), 404

    user_payload, token = _activate_membership(db, user_oid, membership)
    return jsonify({"message": "Switched organization", "user": user_payload, "token": token})


# ── DELETE MY ACCOUNT ──
# Permanent hard delete, matching the existing admin-removes-teammate
# precedent (DELETE /api/admins/<id>), but this one revokes the caller's own
# session token - that route doesn't need to (it ends someone ELSE's
# session), this one does since it's ending the caller's own.
@app.route('/api/account', methods=['DELETE'])
@require_auth
@limiter.limit("5 per minute")
def delete_own_account():
    if g.current_user.get('role') == 'admin':
        return jsonify({"error": "Super Admin accounts can't be deleted through self-service - contact your platform operator."}), 403

    data = request.get_json() or {}
    password = data.get('password') or ''

    db = get_db()
    user_oid = oid(g.current_user['id'])
    user = db.users.find_one({"_id": user_oid})
    if not user:
        return jsonify({"error": "User not found"}), 404

    stored = user['password']
    is_hashed = stored.startswith(('pbkdf2:', 'scrypt:'))
    valid = check_password_hash(stored, password) if is_hashed else stored == password
    if not valid:
        return jsonify({"error": "Incorrect password"}), 401

    if db.memberships.find_one({"user_id": user_oid, "role": "lgu_admin"}):
        return jsonify({"error": "You currently hold the Admin seat in at least one organization. Transfer it to someone else before deleting your account."}), 400

    # Memberships are pure relationship data (unlike applicants/notifications/
    # audit_trail, which stay untouched as historical records) - cascade them.
    db.memberships.delete_many({"user_id": user_oid})
    db.users.delete_one({"_id": user_oid})
    revoke_token(g.current_token)

    return jsonify({"message": "Your account has been permanently deleted"})
