# -*- coding: utf-8 -*-
"""Resets an existing user's password directly in the database. Password is
entered interactively (hidden, never echoed) and stored as a salted hash,
using the same hashing function as /api/register. Use this when a password
is forgotten and there's no working forgot-password flow to fall back on.

Usage: python reset_password.py"""
import os
import getpass
from pymongo import MongoClient
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))


def main():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME")]

    email = input("Email of the account to reset: ").strip().lower()
    user = db.users.find_one({"email": email})
    if not user:
        print(f"No account found with email '{email}'.")
        return

    print(f"Found account: {user.get('full_name')} ({user.get('role')})")
    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        print("Passwords did not match.")
        return
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    db.users.update_one({"_id": user["_id"]}, {"$set": {"password": generate_password_hash(password)}})
    print(f"Password reset for {email}.")


if __name__ == "__main__":
    main()
