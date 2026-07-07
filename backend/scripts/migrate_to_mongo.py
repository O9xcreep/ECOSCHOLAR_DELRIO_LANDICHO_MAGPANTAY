"""
One-time migration: copy data out of the local MySQL database into the
MongoDB Atlas cluster used by the app now.

Requires mysql-connector-python to be installed (it no longer ships in
requirements.txt since the app itself doesn't need it after this migration).

Usage (from backend/):
    ./venv/Scripts/python.exe scripts/migrate_to_mongo.py

Reads MySQL connection info from DB_HOST/DB_USER/DB_PASSWORD/DB_NAME and the
Mongo connection info from MONGO_URI/MONGO_DB_NAME, all via .env.
"""
import os
import sys
from datetime import datetime

import mysql.connector
from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


def get_mysql():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'ecoscholars')
    )


def to_str_date(value):
    return str(value) if value is not None else None


def to_float(value):
    return float(value) if value is not None else None


def main():
    mysql_db = get_mysql()
    cursor = mysql_db.cursor(dictionary=True)

    mongo_client = MongoClient(os.getenv('MONGO_URI'))
    mongo_db = mongo_client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]

    if mongo_db.applicants.count_documents({}) > 0 or mongo_db.users.count_documents({}) > 0:
        print("Mongo database already has data. Aborting to avoid duplicating records.")
        print("Drop the collections first if you want to re-run this migration.")
        return

    # ── USERS ──
    cursor.execute("SELECT * FROM users")
    mysql_users = cursor.fetchall()
    user_id_map = {}  # old int id -> new ObjectId
    for u in mysql_users:
        doc = {
            "full_name": u['full_name'],
            "email": u['email'],
            "password": u['password'],
            "role": u['role'],
            "status": u['status'],
            "created_at": u['created_at'] or datetime.utcnow(),
            "privacy_consent": bool(u['privacy_consent']),
        }
        result = mongo_db.users.insert_one(doc)
        user_id_map[u['id']] = result.inserted_id
    print(f"Migrated {len(user_id_map)} users")

    # ── APPLICANTS (+ embedded academic_info, applications, documents, audit_trail) ──
    cursor.execute("SELECT * FROM applicants")
    mysql_applicants = cursor.fetchall()
    applicant_id_map = {}  # old int id -> new ObjectId

    for a in mysql_applicants:
        old_id = a['id']

        cursor.execute("SELECT * FROM academic_info WHERE applicant_id = %s", (old_id,))
        academic_row = cursor.fetchone()
        academic = {
            "school": academic_row['school'] if academic_row else None,
            "school_address": academic_row['school_address'] if academic_row else None,
            "course": academic_row['course'] if academic_row else None,
            "year_level": academic_row['year_level'] if academic_row else None,
            "gpa": to_float(academic_row['gpa']) if academic_row else None,
            "academic_year": academic_row['academic_year'] if academic_row else None,
            "semester": academic_row['semester'] if academic_row else None,
        }

        cursor.execute("SELECT * FROM applications WHERE applicant_id = %s", (old_id,))
        app_row = cursor.fetchone()
        application = {
            "application_type": app_row['application_type'] if app_row else None,
            "status": app_row['status'] if app_row else 'Newly Submitted',
            "submitted_at": app_row['submitted_at'] if app_row else None,
            "reviewed_at": app_row['reviewed_at'] if app_row else None,
            "reviewed_by_name": app_row['reviewed_by_name'] if app_row else None,
            "remarks": app_row['remarks'] if app_row else None,
        }

        cursor.execute("SELECT * FROM documents WHERE applicant_id = %s", (old_id,))
        documents = [{
            "document_name": d['document_name'],
            "file_path": d['file_path'],
            "status": d['status'],
            "uploaded_at": d['uploaded_at'],
        } for d in cursor.fetchall()]

        cursor.execute("SELECT * FROM audit_trail WHERE applicant_id = %s", (old_id,))
        audit_trail = [{
            "action": t['action'],
            "performed_by": t['performed_by'],
            "performed_by_role": t['performed_by_role'],
            "old_status": t['old_status'],
            "new_status": t['new_status'],
            "remarks": t['remarks'],
            "performed_at": t['performed_at'],
        } for t in cursor.fetchall()]

        doc = {
            "user_id": user_id_map.get(a['user_id']),
            "full_name": a['full_name'],
            "email": a['email'],
            "contact_number": a['contact_number'],
            "address": a['address'],
            "gender": a['gender'],
            "date_of_birth": to_str_date(a['date_of_birth']),
            "religion": a['religion'],
            "citizenship": a['citizenship'],
            "father_name": a['father_name'],
            "father_occupation": a['father_occupation'],
            "mother_name": a['mother_name'],
            "mother_occupation": a['mother_occupation'],
            "household_income": a['household_income'],
            "family_size": a['family_size'],
            "barangay": a['barangay'],
            "ml_score": to_float(a['ml_score']) or 0,
            "ml_status": a['ml_status'] or 'Pending',
            "created_at": a['created_at'] or datetime.utcnow(),
            "privacy_consent": bool(a['privacy_consent']),
            "has_other_scholarship": bool(a['has_other_scholarship']),
            "other_scholarship_details": a['other_scholarship_details'],
            "academic": academic,
            "application": application,
            "documents": documents,
            "audit_trail": audit_trail,
        }
        result = mongo_db.applicants.insert_one(doc)
        applicant_id_map[old_id] = result.inserted_id

    print(f"Migrated {len(applicant_id_map)} applicants (with embedded academic/application/documents/audit_trail)")

    # ── DUPLICATE FLAGS ──
    cursor.execute("SELECT * FROM duplicate_flags")
    flag_count = 0
    for f in cursor.fetchall():
        if f['applicant_id'] not in applicant_id_map:
            continue
        mongo_db.duplicate_flags.insert_one({
            "applicant_id": applicant_id_map.get(f['applicant_id']),
            "duplicate_of_id": applicant_id_map.get(f['duplicate_of_id']),
            "reason": f['reason'],
            "flagged_at": f['flagged_at'] or datetime.utcnow(),
            "resolved": bool(f['resolved']),
        })
        flag_count += 1
    print(f"Migrated {flag_count} duplicate flags")

    # ── NOTIFICATIONS ──
    cursor.execute("SELECT * FROM notifications")
    notif_count = 0
    for n in cursor.fetchall():
        if n['user_id'] not in user_id_map:
            continue
        mongo_db.notifications.insert_one({
            "user_id": user_id_map.get(n['user_id']),
            "applicant_id": applicant_id_map.get(n['applicant_id']),
            "message": n['message'],
            "type": n.get('type', 'status_update'),
            "is_read": bool(n['is_read']),
            "created_at": n['created_at'] or datetime.utcnow(),
        })
        notif_count += 1
    print(f"Migrated {notif_count} notifications")

    cursor.close()
    mysql_db.close()
    print("\nMigration complete.")


if __name__ == '__main__':
    main()
