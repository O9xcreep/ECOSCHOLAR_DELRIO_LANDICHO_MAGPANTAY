# -*- coding: utf-8 -*-
"""Wipes every organization, account, application, and related record from
the database EXCEPT Super Admin (role='admin') users - for resetting a test
environment to a clean slate. Destructive and not reversible; only ever run
this against a database that holds no real data you need to keep.

Usage: python reset_all_except_super_admin.py"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

# Everything here is wiped completely. Super Admin accounts are the only
# users.py document identifiable and worth keeping, so `users` is filtered
# instead of dropped outright.
COLLECTIONS_TO_DROP = [
    "organizations", "memberships", "applicants", "admin_requests",
    "activity_logs", "notifications", "document_requirements", "form_fields",
    "program_cycles", "settings", "duplicate_flags", "otps", "revoked_tokens",
    # GridFS-backed uploaded files (proof-of-employment, applicant documents).
    "fs.files", "fs.chunks",
]


def main():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME")]

    super_admins = list(db.users.find({"role": "admin"}))
    if not super_admins:
        print("No Super Admin (role='admin') account found - refusing to run, "
              "since that would leave the database with zero accounts at all.")
        return

    other_users = db.users.count_documents({"role": {"$ne": "admin"}})

    print(f"Database: {os.getenv('MONGO_DB_NAME')}")
    print(f"Will KEEP {len(super_admins)} Super Admin account(s):")
    for u in super_admins:
        print(f"  - {u.get('full_name')} <{u.get('email')}>")
    print(f"Will DELETE {other_users} other user account(s), plus every "
          f"document in: {', '.join(COLLECTIONS_TO_DROP)}")
    print()
    confirm = input("Type RESET to permanently wipe all of the above: ").strip()
    if confirm != "RESET":
        print("Aborted - nothing was deleted.")
        return

    result = db.users.delete_many({"role": {"$ne": "admin"}})
    print(f"Deleted {result.deleted_count} user account(s).")

    for name in COLLECTIONS_TO_DROP:
        db.drop_collection(name)
        print(f"Dropped collection: {name}")

    print("Done. Only the Super Admin account(s) listed above remain.")


if __name__ == "__main__":
    main()
