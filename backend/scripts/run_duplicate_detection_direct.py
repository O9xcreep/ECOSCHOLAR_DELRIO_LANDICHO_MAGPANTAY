# -*- coding: utf-8 -*-
"""Runs the duplicate-detection dataset (test_data/duplicate_detection/dataset.json)
against the exact matching rules submit_application() uses in applicants.py -
email exact match, then full-name + date-of-birth exact match - reimplemented
here as a pure in-memory function so no Flask server or database is needed.

Two phases, mirroring a real submission sequence:
1. Each of the 30 legitimate applicants "submits" in turn, checked against
   everyone submitted so far (should never match - false-flag-rate check).
2. Each of the 15 seeded duplicate attempts is then checked against the full
   pool of 30 legitimate applicants (should always match - detection-rate check).

Usage (from backend/): python scripts/run_duplicate_detection_direct.py
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "..", "test_data", "duplicate_detection", "dataset.json")


def check_duplicate(existing, email, full_name, dob):
    """Mirrors applicants.py's submit_application: exact (case-insensitive)
    email match first, then exact full-name + date-of-birth match."""
    email = email.strip().lower()
    for a in existing:
        if a["email"] == email:
            return "email"
    full_name = full_name.strip().lower()
    for a in existing:
        if a["full_name"].strip().lower() == full_name and a["dob"] == dob:
            return "name_and_birthdate"
    return None


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    legit = dataset["legitimate_applicants"]
    pairs = dataset["duplicate_pairs"]

    pool = []
    legit_results = []
    for p in legit:
        reason = check_duplicate(pool, p["email"], p["full_name"], p["dob"])
        legit_results.append({"id": p["id"], "blocked": reason is not None, "reason": reason})
        pool.append({"email": p["email"].strip().lower(), "full_name": p["full_name"], "dob": p["dob"]})

    dup_results = []
    for pair in pairs:
        attempt = pair["attempt"]
        reason = check_duplicate(pool, attempt["application_email"], attempt["full_name"], attempt["dob"])
        dup_results.append({
            "pair_id": pair["pair_id"], "match_type": pair["match_type"],
            "blocked": reason is not None, "reason": reason,
        })

    total_legit = len(legit_results)
    incorrectly_flagged = sum(1 for r in legit_results if r["blocked"])
    total_seeded = len(dup_results)
    correctly_flagged = sum(1 for r in dup_results if r["blocked"])
    by_email = sum(1 for r in dup_results if r["blocked"] and r["reason"] == "email")
    by_namedob = sum(1 for r in dup_results if r["blocked"] and r["reason"] == "name_and_birthdate")

    summary = {
        "total_applications_tested": total_legit + total_seeded,
        "known_seeded_duplicate_pairs": total_seeded,
        "correctly_flagged_duplicates": correctly_flagged,
        "detection_rate_pct": round(100 * correctly_flagged / total_seeded, 1),
        "legitimate_incorrectly_flagged": incorrectly_flagged,
        "false_flag_rate_pct": round(100 * incorrectly_flagged / total_legit, 1),
        "flagged_by_email_match": by_email,
        "flagged_by_name_dob_match": by_namedob,
    }
    print(json.dumps(summary, indent=2))

    mismatches = [r for r in dup_results if not r["blocked"]] + [r for r in legit_results if r["blocked"]]
    if mismatches:
        print("\nMismatches:")
        for m in mismatches:
            print(" ", m)

    out_path = os.path.join(HERE, "..", "test_data", "duplicate_detection", "duplicate_dataset_run_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "legitimate": legit_results, "duplicate_attempts": dup_results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    main()
