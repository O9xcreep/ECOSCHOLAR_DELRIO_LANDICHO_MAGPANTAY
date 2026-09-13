# -*- coding: utf-8 -*-
"""
Runs the duplicate-detection test dataset (test_data/duplicate_detection/dataset.json)
against the real /api/register + /api/apply endpoints and reports detection
rate / false-flag rate.

Registrations are paced to stay under the production rate limit
(8 per minute on /api/register) - with 45 profiles (30 legitimate + 15
duplicate attempts) this run takes roughly 6-7 minutes.

Requires: the Flask backend running locally (python app.py).

Usage:
    python run_duplicate_dataset_test.py
"""
import os
import time
import json
import requests
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(HERE, "..")
DATA_DIR = os.path.join(BACKEND_DIR, "test_data", "duplicate_detection")

load_dotenv(os.path.join(BACKEND_DIR, ".env"))
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME")]

BASE_URL = "http://localhost:5000"
created_user_emails = []


def register(email, full_name, dob, profile_template):
    payload = {"full_name": full_name, "email": email, "password": "TestPass123!", "dob": dob, **profile_template}
    r = requests.post(f"{BASE_URL}/api/register", json=payload)
    created_user_emails.append(email)
    time.sleep(8)  # stay under the 8/minute rate limit on /api/register
    body = r.json()
    if "token" not in body:
        print(f"  [register failed] {email}: {r.status_code} {body}")
    return body.get("token")


def apply(token, full_name, email, dob, profile_template):
    payload = {"fullName": full_name, "email": email, "dob": dob, **profile_template}
    r = requests.post(f"{BASE_URL}/api/apply", headers={"Authorization": f"Bearer {token}"}, json=payload)
    return r.status_code, r.json()


def main():
    with open(os.path.join(DATA_DIR, "dataset.json"), encoding="utf-8") as f:
        dataset = json.load(f)
    profile_template = dataset["profile_template"]

    legit_results = []
    print(f"Submitting {len(dataset['legitimate_applicants'])} legitimate applicants...")
    for p in dataset["legitimate_applicants"]:
        token = register(p["email"], p["full_name"], p["dob"], profile_template)
        status, resp = apply(token, p["full_name"], p["email"], p["dob"], profile_template)
        legit_results.append({"id": p["id"], "status": status, "blocked": status == 409,
                               "reason": resp.get("duplicate_reason")})
        print(f"  {p['id']}: status={status} blocked={status == 409}")

    dup_results = []
    print(f"\nSubmitting {len(dataset['duplicate_pairs'])} seeded duplicate attempts...")
    for pair in dataset["duplicate_pairs"]:
        attempt = pair["attempt"]
        # register_email creates the attacker's own account (must be unique);
        # application_email is what's declared on the application form itself -
        # that's the field the applicant-level duplicate check actually reads.
        token = register(attempt["register_email"], attempt["full_name"], attempt["dob"], profile_template)
        status, resp = apply(token, attempt["full_name"], attempt["application_email"], attempt["dob"], profile_template)
        dup_results.append({"pair_id": pair["pair_id"], "match_type": pair["match_type"],
                             "status": status, "blocked": status == 409, "reason": resp.get("duplicate_reason")})
        print(f"  {pair['pair_id']} ({pair['match_type']}): status={status} blocked={status == 409}")

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
    print("\n" + json.dumps(summary, indent=2))
    with open(os.path.join(DATA_DIR, "duplicate_dataset_run_results.json"), "w") as f:
        json.dump({"summary": summary, "legitimate": legit_results, "duplicate_attempts": dup_results}, f, indent=2)

    # Cleanup: remove every user + applicant this run created
    test_applicant_ids = [a["_id"] for a in db.applicants.find({"email": {"$regex": "dataset.ecoscholar.test$"}}, {"_id": 1})]
    db.duplicate_flags.delete_many({"applicant_id": {"$in": test_applicant_ids}})
    db.applicants.delete_many({"_id": {"$in": test_applicant_ids}})
    db.users.delete_many({"email": {"$in": created_user_emails}})
    print("\nCleanup complete.")


if __name__ == "__main__":
    main()
