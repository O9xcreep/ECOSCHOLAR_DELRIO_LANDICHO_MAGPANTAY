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

from extensions import app, limiter, get_db, _fs
from helpers import oid, iso, get_organization_name, find_active_organization_by_code, send_email_async
from auth import require_auth, current_organization_oid, issue_token, revoke_token, ADMIN_PERMISSIONS, PROFILE_FIELDS


def _activate_membership(db, user_oid, membership):
    """Copies a membership's role/permissions/municipality onto the flat
    `users` fields and mints a fresh token, mirroring login()'s user_payload
    shape (auth.py) so the frontend can setSession() with it directly."""
    role = membership["role"]
    set_fields = {"organization_id": membership["organization_id"], "role": role}
    # Being in an org again ends the "your organization was disbanded" notice
    # (see delete_organization below).
    update = {"$set": set_fields, "$unset": {"disbanded_organization_name": ""}}
    if role == "lgu_member":
        set_fields["permissions"] = membership.get("permissions") or {p: False for p in ADMIN_PERMISSIONS}
        set_fields["municipality"] = membership.get("municipality") or ""
    elif role == "lgu_admin":
        set_fields["municipality"] = membership.get("municipality") or ""
        update["$unset"]["permissions"] = ""

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
    user = db.users.find_one({"_id": user_oid}, {"disbanded_organization_name": 1})
    return jsonify({
        "memberships": [serialize_membership(m, db, active_org_id) for m in rows],
        # Set when the org this account belonged to was deleted and it hasn't
        # joined another yet - the student and admin portals use it to show a prompt.
        "disbanded_organization_name": (user or {}).get("disbanded_organization_name"),
    })


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


def _password_matches(user, password):
    stored = user['password']
    is_hashed = stored.startswith(('pbkdf2:', 'scrypt:'))
    return check_password_hash(stored, password) if is_hashed else stored == password


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

    # 403, not 401: the frontend treats any 401 as an expired session and signs
    # the user out, which a mistyped password shouldn't do.
    if not _password_matches(user, password):
        return jsonify({"error": "Incorrect password"}), 403

    if db.memberships.find_one({"user_id": user_oid, "role": "lgu_admin"}):
        return jsonify({"error": "You currently hold the Admin seat in at least one organization. Transfer it to someone else, or delete the organization, before deleting your account."}), 400

    # Memberships are pure relationship data (unlike applicants/notifications/
    # audit_trail, which stay untouched as historical records) - cascade them.
    db.memberships.delete_many({"user_id": user_oid})
    db.users.delete_one({"_id": user_oid})
    revoke_token(g.current_token)

    return jsonify({"message": "Your account has been permanently deleted"})


# ── DELETE AN ORGANIZATION ──
# Only whoever holds that organization's Admin seat can do this. Unlike a
# program reset (which archives), this is a permanent hard delete of
# everything the organization owns - its applicants and their uploaded
# documents included - since it's an LGU choosing to leave the platform.
# Students left with no organization keep their login but have their saved
# personal info wiped, and are told to join another org with a join code.
# Not transactional (nothing in this codebase is); the org document itself is
# removed last, so a failure partway leaves an org that can be deleted again.
_ORG_SCOPED_COLLECTIONS = (
    "applicants", "duplicate_flags", "notifications", "document_requirements",
    "form_fields", "program_cycles", "settings", "admin_requests",
)


def _delete_org_uploads(db, org_oid):
    """Best-effort GridFS cleanup - a file that's already gone shouldn't abort the delete."""
    file_ids = []
    for applicant in db.applicants.find({"organization_id": org_oid}, {"documents.gridfs_id": 1}):
        file_ids += [d["gridfs_id"] for d in applicant.get("documents", []) if d.get("gridfs_id")]
    for req in db.admin_requests.find({"organization_id": org_oid}, {"proof_of_employment.gridfs_id": 1}):
        proof_id = (req.get("proof_of_employment") or {}).get("gridfs_id")
        if proof_id:
            file_ids.append(proof_id)
    for file_id in file_ids:
        try:
            _fs.delete(file_id)
        except Exception:
            pass


def _leave_deleted_org(db, user_oid, org_oid, org_name):
    """Repairs one user's cached org fields after org_oid (and their membership
    in it) is gone. Without this, login()'s legacy backfill would see a user
    pointing at an org with no membership row and quietly recreate one.
    Returns (payload, token) if they were moved into another org they belong
    to, else None."""
    user = db.users.find_one({"_id": user_oid})
    if not user or user.get("organization_id") != org_oid:
        return None  # this wasn't their active org, so nothing cached to fix

    remaining = db.memberships.find_one({"user_id": user_oid}, sort=[("joined_at", 1)])
    if remaining:
        return _activate_membership(db, user_oid, remaining)

    if user.get("role") == "student":
        # Keeps the login (name, email, password) so they can join another LGU,
        # but wipes what they told this one: the registration profile that
        # would otherwise prefill their next application. Their applications
        # and documents went with the org. The name is kept so the student
        # portal can tell them what happened (see list_my_memberships).
        db.users.update_one(
            {"_id": user_oid},
            {"$set": {"organization_id": None, "disbanded_organization_name": org_name},
             "$unset": {field: "" for field in PROFILE_FIELDS}}
        )
    else:
        # Same "no org" state DELETE /api/admins/<id> leaves a removed teammate
        # in, plus the same notice students get so the admin portal can tell
        # them what happened (see list_my_memberships).
        db.users.update_one(
            {"_id": user_oid},
            {"$set": {"organization_id": None, "role": "lgu_member", "permissions": {p: False for p in ADMIN_PERMISSIONS},
                      "municipality": "", "disbanded_organization_name": org_name}}
        )
    return None


@app.route('/api/organizations/<organization_id>', methods=['DELETE'])
@require_auth
@limiter.limit("5 per minute")
def delete_organization(organization_id):
    if g.current_user.get('role') == 'admin':
        return jsonify({"error": "The Super Admin account isn't tied to an organization"}), 400

    org_oid = oid(organization_id)
    if not org_oid:
        return jsonify({"error": "Invalid organization id"}), 400

    data = request.get_json() or {}
    db = get_db()
    caller_oid = oid(g.current_user['id'])
    caller = db.users.find_one({"_id": caller_oid})
    if not caller:
        return jsonify({"error": "User not found"}), 404

    # Checked against the memberships row, not the token's role claim: a token
    # can be days old, and this route is destructive.
    if not db.memberships.find_one({"user_id": caller_oid, "organization_id": org_oid, "role": "lgu_admin"}):
        return jsonify({"error": "Only the Admin of an organization can delete it"}), 403
    organization = db.organizations.find_one({"_id": org_oid})
    if not organization:
        return jsonify({"error": "Organization not found"}), 404

    # 403 rather than 401: the frontend treats any 401 as an expired session
    # and signs the user out, which a mistyped password shouldn't do.
    if not _password_matches(caller, data.get('password') or ''):
        return jsonify({"error": "Incorrect password"}), 403
    if (data.get('confirm_name') or '').strip() != (organization.get('name') or ''):
        return jsonify({"error": "Type the organization's name exactly to confirm"}), 400

    caller_was_active = caller.get("organization_id") == org_oid

    # Everyone attached to the org: its memberships, plus any account whose
    # cached org still points here without a membership row (pre-memberships
    # legacy accounts). The caller goes last so a failure partway still leaves
    # them able to retry.
    affected = {m["user_id"] for m in db.memberships.find({"organization_id": org_oid}, {"user_id": 1})}
    affected |= {u["_id"] for u in db.users.find({"organization_id": org_oid}, {"_id": 1})}
    affected.discard(caller_oid)

    _delete_org_uploads(db, org_oid)
    for collection in _ORG_SCOPED_COLLECTIONS:
        db[collection].delete_many({"organization_id": org_oid})
    db.memberships.delete_many({"organization_id": org_oid})
    db.organizations.delete_one({"_id": org_oid})

    org_name = organization.get('name') or ''
    for user_oid in affected:
        _leave_deleted_org(db, user_oid, org_oid, org_name)
    caller_session = _leave_deleted_org(db, caller_oid, org_oid, org_name)

    response = {"message": f"{organization.get('name') or 'The organization'} has been permanently deleted"}
    if caller_session:
        response["user"], response["token"] = caller_session
    elif caller_was_active:
        # Nowhere left to put them, and their token still names the deleted org.
        revoke_token(g.current_token)
        response["signed_out"] = True
    return jsonify(response)
