# -*- coding: utf-8 -*-
"""Runs the OCR verification test dataset (test_data/ocr_verification/)
against the real /api/upload + /api/verify-document endpoints and reports
how the actual outcome compared to each sample's expected_status label.

Requires: the Flask backend running locally (python app.py), connected to a
real MongoDB instance (disposable applicant records are created and deleted
for the run only). Also requires TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD env
vars set to a real admin account (see create_admin.py).

Usage: python run_ocr_dataset_test.py"""
import os
import json
import requests
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
import gridfs

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(HERE, "..")
DATA_DIR = os.path.join(BACKEND_DIR, "test_data", "ocr_verification")

load_dotenv(os.path.join(BACKEND_DIR, ".env"))
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME")]
fs = gridfs.GridFS(db)

BASE_URL = "http://localhost:5000"
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD")


def admin_token():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise SystemExit("Set TEST_ADMIN_EMAIL and TEST_ADMIN_PASSWORD env vars to a real admin account first.")
    r = requests.post(f"{BASE_URL}/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return r.json()["token"]


def create_test_applicant(applicant_fields):
    doc = {
        "full_name": applicant_fields.get("full_name", ""),
        "email": f"{applicant_fields.get('full_name', 'unknown').lower().replace(' ', '.')}@dataset.ecoscholar.test",
        "documents": [], "application": {"status": "Newly Submitted"},
        "academic": {"gpa": applicant_fields.get("gpa"), "school": applicant_fields.get("school"),
                     "course": applicant_fields.get("course")},
        "monthly_income": applicant_fields.get("monthly_income"),
        "address": applicant_fields.get("address"),
        "created_at": datetime.utcnow(), "_test_fixture": True,
    }
    return db.applicants.insert_one(doc).inserted_id


def upload(token, applicant_id, file_path, document_name):
    with open(file_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/api/upload", headers={"Authorization": f"Bearer {token}"},
                           data={"applicant_id": str(applicant_id), "document_name": document_name},
                           files={"file": (os.path.basename(file_path), f, "image/jpeg")})
    return r.status_code, r.json()


def verify(token, applicant_id, document_name):
    r = requests.post(f"{BASE_URL}/api/verify-document", headers={"Authorization": f"Bearer {token}"},
                       json={"applicant_id": str(applicant_id), "document_name": document_name})
    return r.status_code, r.json()


def main():
    with open(os.path.join(DATA_DIR, "labels.json"), encoding="utf-8") as f:
        dataset = json.load(f)["samples"]

    token = admin_token()
    test_applicant_ids = []
    results = []

    for sample in dataset:
        img_path = os.path.join(DATA_DIR, sample["file"])
        aid = create_test_applicant(sample["applicant"])
        test_applicant_ids.append(aid)
        upload(token, aid, img_path, sample["document_type"])
        status, resp = verify(token, aid, sample["document_type"])
        actual_status = resp.get("status")
        match = actual_status == sample["expected_status"]
        results.append({
            "file": sample["file"], "document_type": sample["document_type"], "scenario": sample["scenario"],
            "expected_status": sample["expected_status"], "actual_status": actual_status,
            "match": match, "confidence": resp.get("confidence"), "flags": resp.get("flags"),
        })
        marker = "OK  " if match else "MISS"
        print(f"[{marker}] {sample['document_type']:22s} {sample['scenario']:16s} "
              f"expected={sample['expected_status']:20s} actual={actual_status}")

    total = len(results)
    matched = sum(1 for r in results if r["match"])
    by_type = {}
    for r in results:
        t = by_type.setdefault(r["document_type"], {"total": 0, "matched": 0})
        t["total"] += 1
        t["matched"] += 1 if r["match"] else 0

    summary = {
        "total_samples": total, "matched_expected": matched,
        "match_rate_pct": round(100 * matched / total, 1),
        "by_document_type": by_type,
        "mismatches": [r for r in results if not r["match"]],
    }
    print("\n" + json.dumps(summary, indent=2))
    with open(os.path.join(HERE, "..", "test_data", "ocr_dataset_run_results.json"), "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    # Cleanup: remove every disposable applicant + uploaded file this run
    # created, plus any duplicate_flags it triggered (synthetic documents
    # share a common template, so the near-duplicate check can flag them
    # against each other).
    db.duplicate_flags.delete_many({"applicant_id": {"$in": test_applicant_ids}})
    for aid in test_applicant_ids:
        a = db.applicants.find_one({"_id": aid})
        if a:
            for d in a.get("documents", []):
                if d.get("gridfs_id"):
                    try:
                        fs.delete(d["gridfs_id"])
                    except Exception:
                        pass
        db.applicants.delete_one({"_id": aid})
    print("\nCleanup complete.")


if __name__ == "__main__":
    main()
