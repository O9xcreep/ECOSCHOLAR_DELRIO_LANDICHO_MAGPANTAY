# -*- coding: utf-8 -*-
"""Wipes application data and all accounts except the designated System Owner.

The owner's home organization and membership are preserved so the account
remains usable. Destructive and not reversible; only run against a database
that holds no real data you need to keep.

Usage: python reset_all_except_super_admin.py"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

# The owner's organization and membership are preserved; all application and
# uploaded-file collections are cleared.
COLLECTIONS_TO_DROP = [
    "applicants", "admin_requests",
    "activity_logs", "notifications", "document_requirements", "form_fields",
    "program_cycles", "settings", "duplicate_flags", "otps", "revoked_tokens",
    # GridFS-backed uploaded files (proof-of-employment, applicant documents).
    "fs.files", "fs.chunks",
]


def main():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME")]

    owner = db.users.find_one({
        "role": "lgu_admin",
        "status": "active",
        "is_system_owner": True,
        "$expr": {"$eq": ["$organization_id", "$system_owner_organization_id"]},
    })
    if not owner:
        print("No active System Owner account found - refusing to run, "
              "since that would leave the database with zero accounts at all.")
        return

    owner_org_id = owner["system_owner_organization_id"]
    if not db.organizations.find_one({"_id": owner_org_id}):
        print("The System Owner's organization is missing - refusing to run.")
        return
    if not db.memberships.find_one({
        "user_id": owner["_id"], "organization_id": owner_org_id, "role": "lgu_admin",
    }):
        print("The System Owner's LGU Admin membership is missing - refusing to run.")
        return

    other_users = db.users.count_documents({"_id": {"$ne": owner["_id"]}})

    print(f"Database: {os.getenv('MONGO_DB_NAME')}")
    print("Will KEEP the System Owner and home organization:")
    print(f"  - {owner.get('full_name')} <{owner.get('email')}>")
    print(f"  - organization id: {owner_org_id}")
    print(f"Will DELETE {other_users} other user account(s), plus every "
          f"document in: {', '.join(COLLECTIONS_TO_DROP)}")
    print("Other organizations and memberships will also be deleted.")
    print()
    confirm = input("Type RESET to permanently wipe all of the above: ").strip()
    if confirm != "RESET":
        print("Aborted - nothing was deleted.")
        return

    result = db.users.delete_many({"_id": {"$ne": owner["_id"]}})
    print(f"Deleted {result.deleted_count} user account(s).")

    for name in COLLECTIONS_TO_DROP:
        db.drop_collection(name)
        print(f"Dropped collection: {name}")

    db.organizations.delete_many({"_id": {"$ne": owner_org_id}})
    db.memberships.delete_many({
        "$or": [
            {"organization_id": {"$ne": owner_org_id}},
            {"user_id": {"$ne": owner["_id"]}},
        ],
    })
    print("Done. Only the System Owner and its home organization remain.")


if __name__ == "__main__":
    main()
