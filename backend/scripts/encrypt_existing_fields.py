"""One-time migration: encrypts the sensitive personal fields of records
created before field-level encryption was added (see field_crypto.py), and
adds the date-of-birth blind index used for duplicate detection.

New records are encrypted as they are written; this only catches the old
ones. Safe to re-run: values that are already encrypted are left alone.

It requires FIELD_ENCRYPTION_KEY to be set, and it MUST be the same value
the deployed backend uses (set it on Render first). Without one, the key
would be derived from this machine's SECRET_KEY, which differs from the
server's, and the live site could not decrypt what this script wrote.

Generate a key once with:
  python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

Usage (from backend/):
  python scripts/encrypt_existing_fields.py --dry-run   # count only
  python scripts/encrypt_existing_fields.py             # apply
"""
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

if not os.getenv('FIELD_ENCRYPTION_KEY', '').strip():
    sys.exit('FIELD_ENCRYPTION_KEY is not set. Set the same key here and on the server, then re-run.')

from pymongo import MongoClient  # noqa: E402
from field_crypto import (encrypt_field, decrypt_field, is_encrypted, blind_index,  # noqa: E402
                          ENCRYPTED_APPLICANT_FIELDS, ENCRYPTED_PROFILE_FIELDS)


def migrate(collection, fields, dry_run, dob_field=None):
    changed = 0
    for doc in collection.find({}, {f: 1 for f in fields}):
        update = {}
        for f in fields:
            value = doc.get(f)
            if value not in (None, '') and not is_encrypted(value):
                update[f] = encrypt_field(value)
        if dob_field and doc.get(dob_field) not in (None, ''):
            update[f'{dob_field}_index'] = blind_index(decrypt_field(doc[dob_field]))
        if update:
            changed += 1
            if not dry_run:
                collection.update_one({"_id": doc["_id"]}, {"$set": update})
    return changed


def main():
    dry_run = '--dry-run' in sys.argv
    client = MongoClient(os.getenv('MONGO_URI'))
    db = client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]

    applicants = migrate(db.applicants, ENCRYPTED_APPLICANT_FIELDS, dry_run, dob_field='date_of_birth')
    users = migrate(db.users, ENCRYPTED_PROFILE_FIELDS, dry_run)

    verb = 'Would update' if dry_run else 'Updated'
    print(f'{verb} {applicants} applicant record(s) and {users} user profile(s).')


if __name__ == '__main__':
    main()
