# -*- coding: utf-8 -*-
"""Restores collections from a backup made by backup_database.py. For each
collection found in the chosen backup folder, the LIVE collection is
replaced entirely (dropped, then reloaded from the backup) - this is a
point-in-time restore, not a merge. Anything written to the database after
that backup was taken is lost for the collections being restored.

Usage: python restore_database.py [backup_folder_name]
If no folder is given, lists available backups under backend/backups/ and
prompts for one."""
import os
import sys
import json
from pymongo import MongoClient
from bson import json_util
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))
BACKUPS_DIR = os.path.join(HERE, "..", "backups")


def choose_backup():
    if not os.path.isdir(BACKUPS_DIR):
        print(f"No backups directory found at {BACKUPS_DIR}.")
        return None
    folders = sorted(
        d for d in os.listdir(BACKUPS_DIR)
        if os.path.isdir(os.path.join(BACKUPS_DIR, d))
    )
    if not folders:
        print("No backups found.")
        return None
    print("Available backups:")
    for f in folders:
        print(f"  {f}")
    choice = input("Backup folder to restore: ").strip()
    return choice if choice in folders else None


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else choose_backup()
    if not folder:
        print("No backup selected - aborting.")
        return

    backup_path = os.path.join(BACKUPS_DIR, folder)
    if not os.path.isdir(backup_path):
        print(f"Backup folder not found: {backup_path}")
        return

    files = sorted(f for f in os.listdir(backup_path) if f.endswith(".json"))
    if not files:
        print(f"No .json files found in {backup_path}.")
        return

    client = MongoClient(os.getenv("MONGO_URI"))
    db = client[os.getenv("MONGO_DB_NAME")]
    collection_names = [f[:-5] for f in files]  # strip ".json"

    print(f"Database: {os.getenv('MONGO_DB_NAME')}")
    print(f"Restoring from: {backup_path}")
    print(f"This will REPLACE these {len(collection_names)} live collection(s) entirely, "
          f"discarding anything written since the backup:")
    for name in collection_names:
        print(f"  - {name}")
    confirm = input("\nType RESTORE to proceed: ").strip()
    if confirm != "RESTORE":
        print("Aborted - nothing was changed.")
        return

    for filename in files:
        name = filename[:-5]
        with open(os.path.join(backup_path, filename), "r", encoding="utf-8") as f:
            docs = json.load(f, object_hook=json_util.object_hook)
        db.drop_collection(name)
        if docs:
            db[name].insert_many(docs)
        print(f"  Restored {name}: {len(docs)} document(s)")

    print("\nDone.")


if __name__ == "__main__":
    main()
