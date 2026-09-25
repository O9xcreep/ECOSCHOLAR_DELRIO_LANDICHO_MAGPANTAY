# -*- coding: utf-8 -*-
"""Read side of the activity log (see activity.py for the writer).

Only the LGU's Admin and the platform Super Admin can read it: it records who
signed in from where and who viewed which applicant's documents, which
ordinary team members shouldn't be able to browse. The role is re-checked
against the database, not taken from the session token, so passing on the
Admin seat revokes access immediately."""
import re
from datetime import datetime, timedelta
from flask import request, jsonify, g

from extensions import app, get_db, DEBUG
from helpers import oid, iso
from auth import require_auth, current_organization_oid
from activity import CATEGORIES


def _is_activity_log_reader(db):
    user_oid = oid(g.current_user.get('id'))
    if g.current_user.get('role') == 'admin':
        user = db.users.find_one({"_id": user_oid}, {"role": 1})
        return bool(user and user.get('role') == 'admin')
    if g.current_user.get('role') == 'lgu_admin':
        return db.memberships.find_one({"user_id": user_oid, "organization_id": current_organization_oid(),
                                        "role": "lgu_admin"}) is not None
    return False


def serialize_activity(a):
    actor = a.get('actor') or {}
    target = a.get('target') or {}
    return {
        "id": str(a['_id']),
        "created_at": iso(a.get('created_at')),
        "category": a.get('category'),
        "action": a.get('action'),
        "outcome": a.get('outcome', 'success'),
        "actor_name": actor.get('full_name'),
        "actor_email": actor.get('email'),
        "actor_role": actor.get('role'),
        "target_type": target.get('type'),
        "target_label": target.get('label'),
        "details": a.get('details'),
        "ip_address": a.get('ip_address'),
        "user_agent": a.get('user_agent'),
    }


def _parse_date(raw, end_of_day=False):
    if not raw:
        return None
    try:
        d = datetime.strptime(raw, '%Y-%m-%d')
    except ValueError:
        return None
    return d + timedelta(days=1) if end_of_day else d


@app.route('/api/activity-logs', methods=['GET'])
@require_auth
def list_activity_logs():
    db = get_db()
    if not _is_activity_log_reader(db):
        return jsonify({"error": "Only the LGU Admin can view the activity log"}), 403

    try:
        page = max(int(request.args.get('page', 1)), 1)
        page_size = min(max(int(request.args.get('page_size', 25)), 1), 100)
    except ValueError:
        return jsonify({"error": "page and page_size must be numbers"}), 400

    query = {}
    # Super Admin sees every organization's log (and platform-level events);
    # an LGU Admin only ever sees their own organization's.
    if g.current_user.get('role') != 'admin':
        query["organization_id"] = current_organization_oid()

    category = request.args.get('category')
    if category:
        if category not in CATEGORIES:
            return jsonify({"error": f"category must be one of {list(CATEGORIES)}"}), 400
        query["category"] = category

    outcome = request.args.get('outcome')
    if outcome in ('success', 'failure'):
        query["outcome"] = outcome

    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'), end_of_day=True)
    if date_from or date_to:
        query["created_at"] = {}
        if date_from:
            query["created_at"]["$gte"] = date_from
        if date_to:
            query["created_at"]["$lt"] = date_to

    search = (request.args.get('q') or '').strip()
    if search:
        pattern = {"$regex": re.escape(search[:100]), "$options": "i"}
        query["$or"] = [
            {"actor.email": pattern}, {"actor.full_name": pattern},
            {"action": pattern}, {"target.label": pattern}, {"details": pattern},
        ]

    try:
        total = db.activity_logs.count_documents(query)
        docs = (db.activity_logs.find(query).sort("created_at", -1)
                .skip((page - 1) * page_size).limit(page_size))
        return jsonify({
            "logs": [serialize_activity(a) for a in docs],
            "total": total,
            "page": page,
            "page_size": page_size,
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500
