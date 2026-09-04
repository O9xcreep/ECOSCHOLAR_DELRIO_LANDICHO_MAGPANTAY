# -*- coding: utf-8 -*-
"""
Creates a real admin user account in the users collection. Password is
entered interactively (hidden, never echoed or logged) and stored only as
a salted hash - the same hashing function backend/app.py's /api/register
uses.

Usage:
    python create_admin.py
"""
import os
import getpass
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))


def main():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME")]

    full_name = input("Full name: ").strip()
    email = input("Email: ").strip().lower()
    if not full_name or not email:
        print("Full name and email are required.")
        return

    if db.users.find_one({"email": email}):
        print(f"An account with email '{email}' already exists.")
        return

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.")
        return
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    db.users.insert_one({
        "full_name": full_name,
        "email": email,
        "password": generate_password_hash(password),
        "role": "admin",
        "status": "active",
        "created_at": datetime.utcnow(),
        "privacy_consent": True,
    })
    print(f"Admin account created: {email}")


if __name__ == "__main__":
    main()
