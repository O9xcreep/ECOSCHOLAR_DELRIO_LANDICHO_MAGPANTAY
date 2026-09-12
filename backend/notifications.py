# -*- coding: utf-8 -*-
"""In-app notification list/read routes."""
from flask import jsonify, g

from extensions import app, get_db, DEBUG
from helpers import oid, iso
from auth import require_auth

def serialize_notification(n):
    return {
        "id": str(n['_id']),
        "applicant_id": str(n['applicant_id']) if n.get('applicant_id') else None,
        "message": n.get('message'),
        "type": n.get('type', 'status_update'),
        "is_read": bool(n.get('is_read', False)),
        "created_at": iso(n.get('created_at')),
    }

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
