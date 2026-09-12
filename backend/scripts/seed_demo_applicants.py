"""Replaces all applicant data with a fresh set of demo applicants built on
the current schema, so Reports/Ranking have realistic, fully-scoreable data.

Clears: applicants, duplicate_flags, notifications
Leaves untouched: users (login accounts stay valid)

Most seeded applicants get auto-decided (Approved/Rejected) by running them
through the real model via build_feature_row/score_with_model, so the
decision logic matches the live app. A few are left at "Newly Submitted" for
the admin to exercise the verify-documents workflow on.

Usage (from backend/): ./venv/Scripts/python.exe scripts/seed_demo_applicants.py"""
import os
import sys
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as flask_app  # noqa: E402  (reuses build_feature_row/score_with_model/db config)

random.seed(42)

SCHOOLS = [
    ("Laguna State Polytechnic University", "Siniloan Campus, Siniloan, Laguna"),
    ("University of the Philippines Los Baños", "Los Baños, Laguna"),
    ("Pamantasan ng Lungsod ng Maynila", "Intramuros, Manila"),
    ("Batangas State University", "Batangas City, Batangas"),
    ("Cavite State University", "Indang, Cavite"),
]

COURSES = [
    "BS Computer Science", "BS Information Technology", "BS Nursing",
    "BS Business Administration", "BS Accountancy", "BS Civil Engineering",
    "BS Education (Elementary)", "BS Criminology", "BS Psychology",
    "BS Hotel and Restaurant Management",
]

FIRST_NAMES_M = ["Juan", "Mark", "Carlo", "Rodel", "John Paul", "Michael", "Christian", "Jerome", "Paolo", "Ronnel"]
FIRST_NAMES_F = ["Ana", "Maria Liza", "Precious Joy", "Kristine Mae", "Lovely Grace", "Angel", "Camille", "Divine", "Erika", "Faith"]
LAST_NAMES = ["Santos", "Dela Cruz", "Reyes", "Bautista", "Flores", "Magbanua", "Villanueva", "Castillo", "Tolentino", "Mendoza",
              "Ramos", "Garcia", "Torres", "Aquino", "Salazar"]

EDUCATION_LEVELS = list(flask_app.ml_education_map.keys())
OCCUPATIONS = flask_app.ml_occupation_categories
HOUSING = flask_app.ml_housing_situations
YEAR_LEVELS = ['1st Year', '2nd Year', '3rd Year', '4th Year']
SEMESTERS = ['1st Semester', '2nd Semester']


def make_applicant(i):
    is_male = i % 2 == 0
    first = random.choice(FIRST_NAMES_M if is_male else FIRST_NAMES_F)
    last = random.choice(LAST_NAMES)
    full_name = f"{first} {last}"
    school, school_address = random.choice(SCHOOLS)
    num_siblings = random.randint(0, 5)
    submitted_days_ago = random.randint(1, 90)
    now = datetime.utcnow()
    submitted_at = now - timedelta(days=submitted_days_ago)

    return {
        "user_id": None,
        "full_name": full_name,
        "email": f"{first.lower().replace(' ', '')}.{last.lower()}{i}@demo.ph",
        "contact_number": f"09{random.randint(100000000, 999999999)}",
        "address": f"{random.randint(1, 999)} {random.choice(['Rizal St', 'Mabini St', 'Bonifacio Ave', 'Luna St'])}, "
                   f"{random.choice(['Siniloan', 'Pangil', 'Famy', 'Mabitac'])}, Laguna",
        "gender": "Male" if is_male else "Female",
        "date_of_birth": f"{random.randint(2003, 2007)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
        "religion": random.choice(["Roman Catholic", "Iglesia ni Cristo", "Born Again Christian"]),
        "citizenship": "Filipino",
        "father_name": f"{random.choice(FIRST_NAMES_M)} {last}",
        "father_occupation": random.choice(OCCUPATIONS),
        "father_education": random.choice(EDUCATION_LEVELS),
        "mother_name": f"{random.choice(FIRST_NAMES_F)} {last}",
        "mother_occupation": random.choice(OCCUPATIONS),
        "mother_education": random.choice(EDUCATION_LEVELS),
        "monthly_income": random.randint(3000, 40000),
        "family_size": random.randint(3, 9),
        "num_siblings": num_siblings,
        "num_siblings_studying": random.randint(0, num_siblings),
        "housing_situation": random.choice(HOUSING),
        "barangay": None,
        "ml_score": 0,
        "ml_status": "Pending",
        "created_at": submitted_at,
        "privacy_consent": True,
        "has_other_scholarship": random.random() < 0.15,
        "other_scholarship_details": "Barangay Scholarship" if random.random() < 0.15 else "",
        "academic": {
            "school": school,
            "school_address": school_address,
            "course": random.choice(COURSES),
            "year_level": random.choice(YEAR_LEVELS),
            "gpa": round(random.uniform(75, 99), 2),
            "academic_year": "2025-2026",
            "semester": random.choice(SEMESTERS),
        },
        "application": {
            "application_type": "General Application",
            "status": "Newly Submitted",
            "submitted_at": submitted_at,
            "reviewed_at": None,
            "reviewed_by_name": None,
            "remarks": None,
        },
        "documents": [],
        "audit_trail": [{
            "action": "Application submitted",
            "performed_by": full_name,
            "performed_by_role": "student",
            "old_status": None,
            "new_status": "Newly Submitted",
            "remarks": None,
            "performed_at": submitted_at,
        }],
    }


def main():
    db = flask_app.get_db()

    applicants_count = db.applicants.count_documents({})
    print(f"Clearing {applicants_count} existing applicants, plus duplicate_flags and notifications...")
    db.applicants.delete_many({})
    db.duplicate_flags.delete_many({})
    db.notifications.delete_many({})

    N = 20
    docs = [make_applicant(i) for i in range(N)]
    result = db.applicants.insert_many(docs)
    print(f"Inserted {len(result.inserted_ids)} demo applicants.")

    # Auto-decide most of them through the real model, leave a few pending
    # so there's something for the admin to actually verify.
    decided = 0
    left_pending = 0
    for applicant_id in result.inserted_ids:
        if random.random() < 0.3:
            left_pending += 1
            continue

        applicant = db.applicants.find_one({"_id": applicant_id})
        row, ok = flask_app.build_feature_row(applicant)
        if not ok:
            continue

        ml_score, ml_status = flask_app.score_with_model(row)
        final_status = 'Approved' if ml_status == 'Eligible' else 'Rejected'
        now = datetime.utcnow()

        db.applicants.update_one(
            {"_id": applicant_id},
            {
                "$set": {
                    "application.status": final_status,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": "Admin",
                    "ml_score": ml_score,
                    "ml_status": ml_status,
                },
                "$push": {
                    "audit_trail": {
                        "action": f"Documents verified by admin - model decided: {final_status}",
                        "performed_by": "Admin",
                        "performed_by_role": "admin",
                        "old_status": "Newly Submitted",
                        "new_status": final_status,
                        "remarks": f"ML score: {ml_score} ({ml_status})",
                        "performed_at": now,
                    }
                }
            }
        )
        decided += 1

    print(f"Auto-decided {decided} applicants via the real model, left {left_pending} as 'Newly Submitted' for manual testing.")
    print("\nSeed complete.")


if __name__ == '__main__':
    main()
