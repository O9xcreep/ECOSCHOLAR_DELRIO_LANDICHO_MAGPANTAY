"""
One-time migration, multi-tenancy Phase A: create a single "Default
Organization" (this deployment's own LGU) and backfill organization_id onto
every existing document in every per-tenant collection. Purely additive - no
existing _id, field, or query is touched, so nothing in the running app
behaves any differently before or after this runs. Safe to re-run: documents
that already have organization_id are left alone.

Going forward, every new document in these collections is already tagged at
write time by app.py's get_default_organization_id() helper - this script
only needs to run once, to catch up data that existed before that shipped.

Usage (from backend/):
    ./venv/Scripts/python.exe scripts/migrate_phase_a_organizations.py
"""
import os
import sys
import secrets
from datetime import datetime

from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

# otps and revoked_tokens are deliberately excluded - genuinely tenant-agnostic
# auth infrastructure, keyed by email/token hash, not LGU data.
TENANT_COLLECTIONS = [
    'users', 'applicants', 'settings', 'program_cycles', 'form_fields',
    'document_requirements', 'admin_requests', 'duplicate_flags', 'notifications',
]


def generate_join_code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))


def main():
    client = MongoClient(os.getenv('MONGO_URI'))
    db = client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]

    db.organizations.create_index('join_code', unique=True)

    org = db.organizations.find_one({})
    if org:
        org_id = org['_id']
        print(f"Using existing organization: {org.get('name')} ({org_id})")
    else:
        result = db.organizations.insert_one({
            "name": "Default Organization",
            "join_code": generate_join_code(),
            "status": "active",
            "created_at": datetime.utcnow(),
            "founding_admin_request_id": None,
        })
        org_id = result.inserted_id
        print(f"Created default organization {org_id}")

    for name in TENANT_COLLECTIONS:
        coll = db[name]
        result = coll.update_many(
            {"organization_id": {"$exists": False}},
            {"$set": {"organization_id": org_id}}
        )
        print(f"{name}: tagged {result.modified_count} document(s)")

    print("Done.")


if __name__ == '__main__':
    main()
