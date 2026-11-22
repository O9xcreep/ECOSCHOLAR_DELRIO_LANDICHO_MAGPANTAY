# -*- coding: utf-8 -*-
"""Bootstrap an LGU System Owner and the first organization on a fresh install.

Usage: python create_admin.py
"""
import getpass
import os
import secrets
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient
from werkzeug.security import generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))


def _new_join_code(db):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(10):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.organizations.find_one({"join_code": code}):
            return code
    raise RuntimeError("Could not generate a unique organization join code.")


def main():
    mongo_uri = os.getenv("MONGO_URI")
    database_name = os.getenv("MONGO_DB_NAME")
    if not mongo_uri or not database_name:
        print("MONGO_URI and MONGO_DB_NAME must be set in backend/.env.")
        return 1

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    created_org_id = None
    created_user_id = None
    created_membership_id = None
    try:
        db = client[database_name]
        db.command("ping")
        db.users.create_index(
            "is_system_owner",
            unique=True,
            partialFilterExpression={"is_system_owner": True},
        )

        if db.users.find_one({"is_system_owner": True}):
            print("A System Owner is already designated. No changes were made.")
            return 1

        organizations = list(db.organizations.find({"status": "active"}).sort("name", 1))
        if organizations:
            print("Choose an existing active organization, or press Enter to create one:")
            for index, organization in enumerate(organizations, 1):
                print(f"{index}. {organization.get('name', 'Unnamed')} ({organization['_id']})")
            selection = input("Organization number: ").strip()
            if selection:
                try:
                    organization = organizations[int(selection) - 1]
                except (ValueError, IndexError):
                    print("Enter a listed organization number.")
                    return 1
                organization_id = organization["_id"]
                organization_name = organization.get("name", "Organization")
                municipality = organization.get("municipality", "")
                if db.memberships.find_one({"organization_id": organization_id, "role": "lgu_admin"}) or \
                        db.users.find_one({"organization_id": organization_id, "role": "lgu_admin"}):
                    print("That organization already has an LGU Admin. Use assign_system_owner.py instead.")
                    return 1
            else:
                organization_id = None
        else:
            organization_id = None

        if organization_id is None:
            organization_name = input("Organization name: ").strip()
            municipality = input("Municipality: ").strip()
            if not organization_name or not municipality:
                print("Organization name and municipality are required.")
                return 1

        full_name = input("System Owner full name: ").strip()
        email = input("System Owner email: ").strip().lower()
        if not full_name or not email:
            print("Full name and email are required.")
            return 1
        if db.users.find_one({"email": email}):
            print(f"An account with email '{email}' already exists. Use assign_system_owner.py instead.")
            return 1

        password = getpass.getpass("Password (at least 8 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match.")
            return 1
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return 1

        print(f"\nThis will create the first LGU Admin/System Owner for {organization_name}.")
        if input(f"Type {email} to confirm: ").strip().lower() != email:
            print("Confirmation did not match. No changes were made.")
            return 1

        now = datetime.utcnow()
        if organization_id is None:
            org_result = db.organizations.insert_one({
                "name": organization_name,
                "municipality": municipality,
                "join_code": _new_join_code(db),
                "status": "active",
                "created_at": now,
                "founding_admin_request_id": None,
            })
            created_org_id = org_result.inserted_id
            organization_id = created_org_id

        user_result = db.users.insert_one({
            "full_name": full_name,
            "email": email,
            "password": generate_password_hash(password),
            "password_set": True,
            "role": "lgu_admin",
            "status": "active",
            "municipality": municipality,
            "organization_id": organization_id,
            "is_system_owner": True,
            "system_owner_organization_id": organization_id,
            "created_at": now,
            "privacy_consent": True,
        })
        created_user_id = user_result.inserted_id
        membership_result = db.memberships.insert_one({
            "user_id": created_user_id,
            "organization_id": organization_id,
            "role": "lgu_admin",
            "permissions": None,
            "municipality": municipality,
            "joined_at": now,
        })
        created_membership_id = membership_result.inserted_id

        organization = db.organizations.find_one({"_id": organization_id})
        print(f"System Owner account created for {organization_name}.")
        print(f"Organization: {organization.get('name', organization_name)}")
        print(f"Join code: {organization.get('join_code', 'not available')}")
        return 0
    except Exception as error:
        if created_membership_id:
            db.memberships.delete_one({"_id": created_membership_id})
        if created_user_id:
            db.users.delete_one({"_id": created_user_id})
        if created_org_id:
            db.organizations.delete_one({"_id": created_org_id})
        print(f"System Owner setup failed: {error}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
