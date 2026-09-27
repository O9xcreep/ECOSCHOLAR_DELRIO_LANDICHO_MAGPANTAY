# -*- coding: utf-8 -*-
"""Dumps every collection in the database to timestamped JSON files under
backend/backups/ - a pure-Python stand-in for `mongodump` (not installed on
this machine), using bson's Extended JSON so ObjectId/datetime/Binary values
round-trip correctly through restore_database.py.

Run this before any risky/destructive operation (org resets, migrations,
manual deletes) - see restore_database.py to reload a backup.

Usage: python backup_database.py"""
import os
import json
from datetime import datetime
from pymongo import MongoClient
from bson import json_util
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))
BACKUPS_DIR = os.path.join(HERE, "..", "backups")


def main():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME")]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BACKUPS_DIR, stamp)
    os.makedirs(out_dir, exist_ok=True)

    collections = db.list_collection_names()
    if not collections:
        print("Database has no collections - nothing to back up.")
        return

    print(f"Database: {os.getenv('MONGO_DB_NAME')}")
    print(f"Backing up {len(collections)} collection(s) to {out_dir}\n")

    total_docs = 0
    for name in sorted(collections):
        docs = list(db[name].find({}))
        with open(os.path.join(out_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(docs, f, default=json_util.default, indent=2)
        print(f"  {name}: {len(docs)} document(s)")
        total_docs += len(docs)

    print(f"\nDone. {total_docs} total document(s) backed up to:\n  {out_dir}")


if __name__ == "__main__":
    main()
