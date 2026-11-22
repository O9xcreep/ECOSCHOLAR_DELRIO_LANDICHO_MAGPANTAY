# -*- coding: utf-8 -*-
"""Designate an existing LGU Admin as System Owner (optionally transfer it).

Usage: python assign_system_owner.py
"""
import os

from dotenv import load_dotenv
from pymongo import MongoClient

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))


def main():
    mongo_uri = os.getenv("MONGO_URI")
    database_name = os.getenv("MONGO_DB_NAME")
    if not mongo_uri or not database_name:
        print("MONGO_URI and MONGO_DB_NAME must be set in backend/.env.")
        return 1

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    try:
        db = client[database_name]
        db.command("ping")
        db.users.create_index(
            "is_system_owner",
            unique=True,
            partialFilterExpression={"is_system_owner": True},
        )

        email = input("Email of the existing LGU Admin: ").strip().lower()
        target = db.users.find_one({"email": email, "role": "lgu_admin", "status": "active"})
        if not target or not target.get("organization_id"):
            print("No active LGU Admin account with an organization was found.")
            return 1

        organization_id = target["organization_id"]
        membership = db.memberships.find_one({
            "user_id": target["_id"],
            "organization_id": organization_id,
            "role": "lgu_admin",
        })
        if not membership:
            print("The account has no matching LGU Admin membership. No changes were made.")
            return 1

        current_owner = db.users.find_one({"is_system_owner": True})
        if current_owner and current_owner["_id"] == target["_id"] and \
                current_owner.get("system_owner_organization_id") == organization_id:
            print(f"{email} is already the System Owner.")
            return 0

        confirmation = "TRANSFER SYSTEM OWNER" if current_owner else email
        print(f"Target organization: {db.organizations.find_one({'_id': organization_id}, {'name': 1}) or 'Unknown'}")
        if input(f"Type {confirmation} to confirm: ").strip() != confirmation:
            print("Confirmation did not match. No changes were made.")
            return 1

        old_fields = None
        if current_owner:
            old_fields = {
                "is_system_owner": current_owner.get("is_system_owner"),
                "system_owner_organization_id": current_owner.get("system_owner_organization_id"),
            }
            db.users.update_one({"_id": current_owner["_id"]}, {
                "$unset": {"is_system_owner": "", "system_owner_organization_id": ""},
            })

        try:
            result = db.users.update_one({"_id": target["_id"], "role": "lgu_admin"}, {
                "$set": {
                    "is_system_owner": True,
                    "system_owner_organization_id": organization_id,
                },
            })
            if result.matched_count != 1:
                raise RuntimeError("The target account changed during setup; no System Owner was assigned.")
        except Exception:
            if current_owner and old_fields:
                db.users.update_one({"_id": current_owner["_id"]}, {"$set": old_fields})
            raise

        print(f"System Owner assigned to {email}.")
        return 0
    except Exception as error:
        print(f"System Owner assignment failed: {error}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
