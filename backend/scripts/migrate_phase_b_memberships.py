"""One-time migration, multi-org membership: backfills a `memberships` row
for every existing user's current organization_id/role/permissions, so
has_permission() (which now reads memberships for lgu_member accounts) and
the Team tab (which now reads memberships, not users.organization_id
directly) keep working for accounts that existed before this feature
shipped. Purely additive; safe to re-run since a (user_id, organization_id)
pair that already has a membership row is skipped.

MUST run before deploying the has_permission()/admin_management.py changes
that read from `memberships` - otherwise every existing lgu_member's
permission checks (and every org's Team tab) break until this has run.

Usage (from backend/): ./venv/Scripts/python.exe scripts/migrate_phase_b_memberships.py"""
import os
import sys

from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


def main():
    client = MongoClient(os.getenv('MONGO_URI'))
    db = client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]

    inserted = 0
    skipped_existing = 0
    skipped_no_org = 0

    for user in db.users.find({"role": {"$ne": "admin"}}):
        org_id = user.get("organization_id")
        if not org_id:
            skipped_no_org += 1
            continue

        if db.memberships.find_one({"user_id": user["_id"], "organization_id": org_id}):
            skipped_existing += 1
            continue

        role = user.get("role", "lgu_member")
        db.memberships.insert_one({
            "user_id": user["_id"],
            "organization_id": org_id,
            "role": role,
            "permissions": user.get("permissions") if role == "lgu_member" else None,
            "municipality": user.get("municipality") if role in ("lgu_admin", "lgu_member") else None,
            "joined_at": user.get("created_at"),
        })
        inserted += 1

    print(f"Inserted {inserted} membership row(s)")
    print(f"Skipped {skipped_existing} (already had a membership row)")
    print(f"Skipped {skipped_no_org} (no organization_id - Super Admin or legacy account)")
    print("Done.")


if __name__ == '__main__':
    main()
