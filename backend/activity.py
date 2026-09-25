# -*- coding: utf-8 -*-
"""System-wide activity log: logins (including failed ones), logouts, account
and password changes, staff and permission changes, settings changes, and
document uploads/views. Separate from each applicant's audit_trail, which
records that one application's status history.

log_activity() never raises - a logging failure must not break the action
being logged."""
from datetime import datetime
from bson import ObjectId
from flask import request, g, has_request_context

from extensions import app, get_db

CATEGORIES = ('auth', 'account', 'staff', 'settings', 'application', 'document')


def _oid(value):
    if isinstance(value, ObjectId) or value is None:
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _client_ip():
    # Behind Render's proxy, remote_addr is the proxy; the client is the first
    # X-Forwarded-For entry. Informational only (the header can be forged).
    forwarded = request.headers.get('X-Forwarded-For', '')
    return (forwarded.split(',')[0].strip() or request.remote_addr or '')[:64]


def log_activity(category, action, *, actor=None, organization_id=None, target=None,
                 details=None, outcome='success'):
    """Record one event.

    category: one of CATEGORIES.
    action: short past-tense description, e.g. "Logged in".
    actor: {"id", "email", "role", "full_name"}; defaults to the signed-in user.
    organization_id: defaults to the actor's organization.
    target: optional {"type", "id", "label"} - what the action was done to.
    details: optional short free-text detail.
    outcome: "success" or "failure".
    """
    try:
        db = get_db()
        if actor is None and has_request_context():
            actor = getattr(g, 'current_user', None)
        actor = dict(actor or {})
        actor_id = _oid(actor.get('id'))
        if actor_id and not actor.get('full_name'):
            user = db.users.find_one({"_id": actor_id}, {"full_name": 1})
            actor['full_name'] = (user or {}).get('full_name')
        if organization_id is None:
            organization_id = actor.get('organization_id')

        entry = {
            "created_at": datetime.utcnow(),
            "category": category,
            "action": action,
            "outcome": outcome,
            "actor": {
                "id": actor_id,
                "email": actor.get('email'),
                "full_name": actor.get('full_name'),
                "role": actor.get('role'),
            },
            "organization_id": _oid(organization_id),
            "target": {
                "type": target.get('type'),
                "id": str(target['id']) if target.get('id') is not None else None,
                "label": target.get('label'),
            } if target else None,
            "details": (details or None) and str(details)[:500],
        }
        if has_request_context():
            entry["ip_address"] = _client_ip()
            entry["user_agent"] = request.headers.get('User-Agent', '')[:300]
        db.activity_logs.insert_one(entry)
    except Exception as e:
        app.logger.warning(f'activity log write failed: {e}')
