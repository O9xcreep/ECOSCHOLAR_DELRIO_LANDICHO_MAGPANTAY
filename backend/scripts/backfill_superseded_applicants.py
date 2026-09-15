"""One-time backfill for the withdraw-then-resubmit duplicate-display bug
(fixed going forward in applicants.py's submit_application(), which now sets
application.superseded_by on the old Withdrawn record at resubmission time).

This only catches NEW resubmissions from the moment that fix shipped. Anyone
who withdrew and resubmitted BEFORE it shipped is left with two live records
-- one Withdrawn, one live -- both still showing up in the Applications
queue (e.g. "Needs Attention" and "Decided" at once) because neither has
superseded_by set. This script finds those pre-existing pairs and links them,
the same way a fresh resubmission would today.

Purely additive and safe to re-run: only touches Withdrawn documents that
don't already have superseded_by set, and only when exactly one clear
"current" (non-Withdrawn) record exists to point at. A group with more than
one non-Withdrawn record for the same email/cycle/org is left untouched and
reported for manual review, since it's ambiguous which one "wins."

Usage (from backend/):
  python scripts/backfill_superseded_applicants.py            # apply
  python scripts/backfill_superseded_applicants.py --dry-run  # preview only
"""
import os
import sys
from collections import defaultdict

from pymongo import MongoClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()


def main():
    dry_run = '--dry-run' in sys.argv

    client = MongoClient(os.getenv('MONGO_URI'))
    db = client[os.getenv('MONGO_DB_NAME', 'ecoscholars')]

    groups = defaultdict(list)
    for doc in db.applicants.find(
        {},
        {"email": 1, "cycle_id": 1, "organization_id": 1, "application.status": 1, "application.superseded_by": 1, "full_name": 1}
    ):
        key = (doc.get('email'), doc.get('cycle_id'), doc.get('organization_id'))
        groups[key].append(doc)

    linked = 0
    skipped_ambiguous = 0
    skipped_no_current = 0

    for (email, cycle_id, org_id), docs in groups.items():
        if len(docs) < 2:
            continue

        withdrawn = [d for d in docs if (d.get('application') or {}).get('status') == 'Withdrawn'
                     and not (d.get('application') or {}).get('superseded_by')]
        current = [d for d in docs if (d.get('application') or {}).get('status') != 'Withdrawn']

        if not withdrawn:
            continue
        if len(current) == 0:
            skipped_no_current += len(withdrawn)
            continue
        if len(current) > 1:
            print(f"AMBIGUOUS - {email} (cycle {cycle_id}, org {org_id}) has {len(current)} "
                  f"non-Withdrawn records; skipping, needs manual review: "
                  f"{[str(d['_id']) for d in current]}")
            skipped_ambiguous += len(withdrawn)
            continue

        winner = current[0]
        for old in withdrawn:
            print(f"{'[DRY RUN] Would link' if dry_run else 'Linking'} "
                  f"{old.get('full_name')} <{email}> Withdrawn {old['_id']} -> superseded by {winner['_id']}")
            if not dry_run:
                db.applicants.update_one(
                    {"_id": old['_id']},
                    {"$set": {"application.superseded_by": winner['_id']}}
                )
            linked += 1

    print(f"\n{'Would link' if dry_run else 'Linked'}: {linked}")
    print(f"Skipped (no current record to link to): {skipped_no_current}")
    print(f"Skipped (ambiguous, multiple current records): {skipped_ambiguous}")


if __name__ == '__main__':
    main()
