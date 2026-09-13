# -*- coding: utf-8 -*-
"""
Generates the OCR verification and duplicate-detection test datasets used in
Chapter IV system testing, and writes them as persistent files under
backend/test_data/ - not just generated in memory and discarded.

Re-running this script regenerates the dataset deterministically (no random
seeds are used; every sample is explicitly enumerated below), so the dataset
can be regenerated from scratch at any time and still match what's documented
in the thesis.

Usage:
    python generate_test_dataset.py

Output:
    test_data/ocr_verification/<document_type_slug>/<scenario>_<n>.jpg
    test_data/ocr_verification/labels.json
    test_data/duplicate_detection/dataset.json
"""
import io
import os
import json
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "test_data")
OCR_DIR = os.path.join(OUT_DIR, "ocr_verification")
DUP_DIR = os.path.join(OUT_DIR, "duplicate_detection")

FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 34)
FONT_BIG = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 42)
FONT_SCRIPT_PATH = r"C:\Windows\Fonts\segoesc.ttf"
FONT_SCRIPT = ImageFont.truetype(FONT_SCRIPT_PATH, 34) if os.path.exists(FONT_SCRIPT_PATH) else FONT

CANVAS = (1400, 900)


def new_canvas():
    return Image.new("RGB", CANVAS, color=(255, 255, 255))


def save_jpeg(img, path, quality=92):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert("RGB").save(path, format="JPEG", quality=quality)


def degrade(img, blur=0, downscale=1.0):
    if downscale < 1.0:
        small = img.resize((int(img.width * downscale), int(img.height * downscale)))
        img = small.resize(img.size)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img


# ═══ Document builders ═══

def enrollment_form(name, school="", course="", extra_lines=True):
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, 880], outline=(0, 0, 0), width=3)
    d.text((60, 60), "ENROLLMENT FORM", fill=(0, 0, 0), font=FONT_BIG)
    d.text((60, 180), f"Name: {name}", fill=(0, 0, 0), font=FONT)
    if school:
        d.text((60, 260), f"School: {school}", fill=(0, 0, 0), font=FONT)
    if course:
        d.text((60, 340), f"Course: {course}", fill=(0, 0, 0), font=FONT)
    if extra_lines:
        d.text((60, 420), "Status: Officially Enrolled, School Year 2025-2026", fill=(0, 0, 0), font=FONT)
        d.text((60, 500), "1st Semester Registration Confirmed", fill=(0, 0, 0), font=FONT)
    return img


def proof_of_income(name, income_text="", extra_lines=True, handwritten=False):
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, 880], outline=(0, 0, 0), width=3)
    d.text((60, 60), "CERTIFICATE OF INDIGENCY", fill=(0, 0, 0), font=FONT_BIG)
    d.text((60, 180), f"Name: {name}", fill=(0, 0, 0), font=FONT)
    if income_text:
        if handwritten:
            d.text((60, 260), "Monthly Household Income:", fill=(0, 0, 0), font=FONT)
            d.text((90, 320), income_text, fill=(0, 0, 0), font=FONT_SCRIPT)
        else:
            d.text((60, 260), f"Monthly Household Income: {income_text}", fill=(0, 0, 0), font=FONT)
    if extra_lines:
        y = 400 if handwritten else 340
        d.text((60, y), "Barangay: San Isidro", fill=(0, 0, 0), font=FONT)
        d.text((60, y + 80), "Issued by the Office of the Barangay Captain", fill=(0, 0, 0), font=FONT)
        d.text((60, y + 160), "This is to certify that the above-named person", fill=(0, 0, 0), font=FONT)
        d.text((60, y + 220), "is a resident and indigent of this barangay.", fill=(0, 0, 0), font=FONT)
    return img


def barangay_endorsement(name, address_word="", extra_lines=True):
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, 880], outline=(0, 0, 0), width=3)
    d.text((60, 60), "BARANGAY ENDORSEMENT", fill=(0, 0, 0), font=FONT_BIG)
    d.text((60, 180), f"Name: {name}", fill=(0, 0, 0), font=FONT)
    if address_word:
        d.text((60, 260), f"Resident of {address_word}", fill=(0, 0, 0), font=FONT)
    if extra_lines:
        d.text((60, 340), "This is to certify that the above-named person", fill=(0, 0, 0), font=FONT)
        d.text((60, 420), "is a bona fide resident of this barangay and is", fill=(0, 0, 0), font=FONT)
        d.text((60, 500), "hereby endorsed for the scholarship program.", fill=(0, 0, 0), font=FONT)
    return img


def school_id(name, school="", extra_lines=True):
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, 880], outline=(0, 0, 0), width=3)
    if school:
        d.text((60, 60), school, fill=(0, 0, 0), font=FONT_BIG)
    d.text((60, 180), "STUDENT IDENTIFICATION CARD", fill=(0, 0, 0), font=FONT)
    d.text((60, 280), f"Name: {name}", fill=(0, 0, 0), font=FONT)
    if extra_lines:
        d.text((60, 360), "Valid Until: School Year 2025-2026", fill=(0, 0, 0), font=FONT)
    return img


def grade_report(name, school="", gwa_text="", extra_lines=True):
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, 880], outline=(0, 0, 0), width=3)
    d.text((60, 60), "GRADE 12 REPORT CARD", fill=(0, 0, 0), font=FONT_BIG)
    d.text((60, 180), f"Name: {name}", fill=(0, 0, 0), font=FONT)
    if school:
        d.text((60, 260), f"School: {school}", fill=(0, 0, 0), font=FONT)
    if gwa_text:
        d.text((60, 340), f"General Weighted Average: {gwa_text}", fill=(0, 0, 0), font=FONT)
    if extra_lines:
        d.text((60, 420), "DepEd Form 138 - Learner's Progress Report Card", fill=(0, 0, 0), font=FONT)
    return img


def certificate_4ps(name, extra_lines=True):
    img = new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, 880], outline=(0, 0, 0), width=3)
    d.text((60, 60), "4Ps CERTIFICATE OF ELIGIBILITY", fill=(0, 0, 0), font=FONT_BIG)
    d.text((60, 180), f"Name: {name}", fill=(0, 0, 0), font=FONT)
    if extra_lines:
        d.text((60, 260), "Pantawid Pamilyang Pilipino Program (4Ps)", fill=(0, 0, 0), font=FONT)
        d.text((60, 340), "DSWD Conditional Cash Transfer Beneficiary Household", fill=(0, 0, 0), font=FONT)
    return img


SCHOOL = "Rizal National High School"

# ═══ Dataset definition: each entry is one labeled sample.
# scenario values: clean | missing_field | blurry | name_mismatch | wrong_document | value_mismatch
# expected_status: Verified | Partially Verified | Failed Verification (per Chapter III thresholds) ═══

def build_ocr_dataset():
    samples = []

    def add(doc_type, slug, scenario, idx, img, applicant, expected_status, note=""):
        filename = f"{scenario}_{idx:02d}.jpg"
        rel_path = f"{slug}/{filename}"
        save_jpeg(img, os.path.join(OCR_DIR, slug, filename))
        samples.append({
            "file": rel_path,
            "document_type": doc_type,
            "scenario": scenario,
            "expected_status": expected_status,
            "note": note,
            "applicant": applicant,
        })

    names = ["Juan Dela Cruz", "Maria Santos", "Pedro Ramos", "Rosa Villa", "Carlos Mendoza",
             "Elena Torres", "Manuel Cruz", "Ana Reyes", "Mark Aquino", "Liza Fernandez"]

    # ═══ Enrollment Form (slug: enrollment_form) ═══
    slug, dtype = "enrollment_form", "Enrollment Form"
    for i, (nm, course) in enumerate([("Juan Dela Cruz", "BS Computer Science"), ("Maria Santos", "BS Nursing"), ("Pedro Ramos", "BS Accountancy")], 1):
        add(dtype, slug, "clean", i, enrollment_form(nm, SCHOOL, course),
            {"full_name": nm, "school": SCHOOL, "course": course}, "Verified")
    for i, nm in enumerate(["Rosa Villa", "Carlos Mendoza"], 1):
        add(dtype, slug, "missing_field", i, enrollment_form(nm, SCHOOL, extra_lines=False),
            {"full_name": nm, "school": SCHOOL, "course": "BSIT"}, "Partially Verified", "course/status lines omitted")
    for i, (nm, blur, scale) in enumerate([("Elena Torres", 2.0, 0.6), ("Manuel Cruz", 3.0, 0.4)], 1):
        add(dtype, slug, "blurry", i, degrade(enrollment_form(nm, SCHOOL, "BSIT"), blur=blur, downscale=scale),
            {"full_name": nm, "school": SCHOOL, "course": "BSIT"}, "Failed Verification", f"blur={blur}, downscale={scale}")
    add(dtype, slug, "name_mismatch", 1, enrollment_form("Frankie Garcia", SCHOOL, "BSCS"),
        {"full_name": "Francisco Garcia Jr.", "school": SCHOOL, "course": "BSCS"}, "Failed Verification",
        "nickname on document vs legal name on file")
    add(dtype, slug, "wrong_document", 1, proof_of_income("Liza Fernandez", "PHP 9,000.00"),
        {"full_name": "Liza Fernandez", "school": SCHOOL, "course": "BSBA"}, "Failed Verification",
        "income certificate uploaded where enrollment form expected")

    # ═══ Proof of Income (slug: proof_of_income) ═══
    slug, dtype = "proof_of_income", "Proof of Income"
    for i, (nm, income) in enumerate([("Pedro Ramos", 8500), ("Ana Reyes", 6000), ("Mark Aquino", 12000)], 1):
        add(dtype, slug, "clean", i, proof_of_income(nm, f"PHP {income:,}.00"),
            {"full_name": nm, "monthly_income": income}, "Verified")
    # Omitting the income figure itself (not the barangay/issuer boilerplate) is what
    # actually degrades the score - "Income document keywords found" passes on the
    # title alone ("CERTIFICATE OF INDIGENCY"), so only the amount check is affected.
    add(dtype, slug, "missing_field", 1, proof_of_income("Carlos Mendoza", income_text=""),
        {"full_name": "Carlos Mendoza", "monthly_income": 6000}, "Partially Verified", "income figure omitted")
    for i, (nm, blur, scale) in enumerate([("Elena Torres", 2.0, 0.6), ("Liza Fernandez", 3.0, 0.4)], 1):
        add(dtype, slug, "blurry", i, degrade(proof_of_income(nm, "PHP 7,200.00"), blur=blur, downscale=scale),
            {"full_name": nm, "monthly_income": 7200}, "Failed Verification", f"blur={blur}, downscale={scale}")
    add(dtype, slug, "value_mismatch", 1, proof_of_income("Rosa Villa", "PHP 8,500.00"),
        {"full_name": "Rosa Villa", "monthly_income": 3000}, "Partially Verified",
        "document states PHP 8,500 vs declared PHP 3,000")
    add(dtype, slug, "handwritten", 1, degrade(proof_of_income("Manuel Cruz", "7,000", handwritten=True), blur=1.2),
        {"full_name": "Manuel Cruz", "monthly_income": 7000}, "Verified", "cursive-style figure, low legibility")

    # ═══ Barangay Endorsement (slug: barangay_endorsement) ═══
    slug, dtype = "barangay_endorsement", "Barangay Endorsement"
    for i, nm in enumerate(["Juan Dela Cruz", "Maria Santos", "Pedro Ramos"], 1):
        add(dtype, slug, "clean", i, barangay_endorsement(nm, "San Isidro"),
            {"full_name": nm, "address": "San Isidro, Quezon"}, "Verified")
    # Omitting the address line (not the certify/endorsed boilerplate) is what actually
    # degrades the score - "Endorsement keywords found" passes on the title alone
    # ("BARANGAY ENDORSEMENT") plus "endorsed" in the closing line.
    add(dtype, slug, "missing_field", 1, barangay_endorsement("Rosa Villa", address_word=""),
        {"full_name": "Rosa Villa", "address": "San Isidro, Quezon"}, "Partially Verified", "resident/address line omitted")
    add(dtype, slug, "blurry", 1, degrade(barangay_endorsement("Carlos Mendoza", "San Isidro"), blur=3.0, downscale=0.4),
        {"full_name": "Carlos Mendoza", "address": "San Isidro, Quezon"}, "Failed Verification", "blur=3.0, downscale=0.4")
    add(dtype, slug, "value_mismatch", 1, barangay_endorsement("Elena Torres", "San Isidro"),
        {"full_name": "Elena Torres", "address": "Poblacion, Laguna"}, "Partially Verified",
        "address on file (Poblacion, Laguna) doesn't match document barangay (San Isidro)")

    # ═══ School ID (slug: school_id) ═══
    slug, dtype = "school_id", "School ID"
    for i, nm in enumerate(["Juan Dela Cruz", "Maria Santos", "Pedro Ramos"], 1):
        add(dtype, slug, "clean", i, school_id(nm, SCHOOL),
            {"full_name": nm, "school": SCHOOL}, "Verified")
    add(dtype, slug, "missing_field", 1, school_id("Rosa Villa", SCHOOL, extra_lines=False),
        {"full_name": "Rosa Villa", "school": SCHOOL}, "Verified", "validity line omitted")
    add(dtype, slug, "blurry", 1, degrade(school_id("Carlos Mendoza", SCHOOL), blur=3.0, downscale=0.4),
        {"full_name": "Carlos Mendoza", "school": SCHOOL}, "Failed Verification", "blur=3.0, downscale=0.4")

    # ═══ Grade 12 Grades (slug: grade_12_grades) ═══
    slug, dtype = "grade_12_grades", "Grade 12 Grades"
    for i, (nm, gwa) in enumerate([("Juan Dela Cruz", 90), ("Maria Santos", 88), ("Pedro Ramos", 92)], 1):
        add(dtype, slug, "clean", i, grade_report(nm, SCHOOL, str(gwa)),
            {"full_name": nm, "school": SCHOOL, "gpa": gwa}, "Verified")
    add(dtype, slug, "missing_field", 1, grade_report("Rosa Villa", extra_lines=False),
        {"full_name": "Rosa Villa", "school": SCHOOL, "gpa": 88}, "Failed Verification", "school name line omitted")
    add(dtype, slug, "blurry", 1, degrade(grade_report("Carlos Mendoza", SCHOOL, "85"), blur=3.0, downscale=0.4),
        {"full_name": "Carlos Mendoza", "school": SCHOOL, "gpa": 85}, "Failed Verification", "blur=3.0, downscale=0.4")
    add(dtype, slug, "value_mismatch", 1, grade_report("Elena Torres", SCHOOL, "78"),
        {"full_name": "Elena Torres", "school": SCHOOL, "gpa": 95}, "Partially Verified",
        "document states GWA 78 vs declared GWA 95")

    # ═══ 4Ps Certificate (slug: 4ps_certificate) ═══
    slug, dtype = "4ps_certificate", "4Ps Certificate"
    for i, nm in enumerate(["Juan Dela Cruz", "Maria Santos", "Pedro Ramos"], 1):
        add(dtype, slug, "clean", i, certificate_4ps(nm),
            {"full_name": nm}, "Verified")
    add(dtype, slug, "missing_field", 1, certificate_4ps("Rosa Villa", extra_lines=False),
        {"full_name": "Rosa Villa"}, "Verified",
        "DSWD/Pantawid keywords omitted - still passes on the '4ps' substring in the title (see Chapter IV discussion)")
    add(dtype, slug, "blurry", 1, degrade(certificate_4ps("Carlos Mendoza"), blur=3.0, downscale=0.4),
        {"full_name": "Carlos Mendoza"}, "Failed Verification",
        "blur=3.0, downscale=0.4 - consistent with every other document type: this degradation defeats the name gate")

    return samples


# ═══ Duplicate detection dataset ═══

PROFILE_TEMPLATE = {
    "gender": "Male", "religion": "Roman Catholic", "citizenship": "Filipino",
    "contactNumber": "09171234567", "address": "123 Mabini St, San Isidro",
    "fatherName": "Pedro Cruz", "fatherOccupation": "Laborer/Driver", "fatherEducation": "High School",
    "motherName": "Maria Cruz", "motherOccupation": "Unemployed", "motherEducation": "Elementary",
    "monthlyIncome": "8000", "familySize": "5", "numSiblings": "3", "numSiblingsStudying": "2",
    "housingSituation": "Rented", "hasOtherScholarship": "no", "otherScholarshipDetails": "",
    "school": "Rizal National High School", "schoolAddress": "San Isidro",
    "course": "BS Computer Science", "yearLevel": "1st Year", "gpa": "88",
    "academicYear": "2025-2026", "semester": "1st Semester",
}

FIRST_NAMES = ["Juan", "Maria", "Pedro", "Ana", "Carlos", "Rosa", "Manuel", "Elena", "Mark", "Liza",
               "Jose", "Carmen", "Ramon", "Teresa", "Antonio", "Isabel", "Fernando", "Grace", "Daniel", "Corazon",
               "Rogelio", "Victor", "Josefina", "Benjamin", "Amelia", "Francisco", "Cristina", "Rafael", "Luz", "Ernesto"]


def build_duplicate_dataset():
    legitimate = []
    for i, first in enumerate(FIRST_NAMES):  # 30 unique legitimate applicants
        legitimate.append({
            "id": f"legit_{i+1:02d}",
            "full_name": f"{first} Bautista{i}",
            "email": f"legit{i+1:02d}@dataset.ecoscholar.test",
            "dob": f"200{i % 6}-0{(i % 9) + 1}-1{i % 9}",
        })

    # Two DISTINCT emails matter for every attempt: `register_email` is used to create
    # the attacker's own (unique) user account via /api/register, which has its own
    # separate unique-email constraint unrelated to the applicant-level duplicate
    # check under test. `application_email` is what the attacker types into the
    # *application form's* email field via /api/apply - that's the field the
    # applicant-level email-match duplicate check actually reads. Conflating the two
    # (reusing the target's email for registration too) makes /api/register reject
    # the attempt outright before the real duplicate check is ever exercised.
    duplicate_pairs = []
    # 8 email-match duplicate pairs: application_email collides with an existing
    # applicant's declared email; register_email is the attacker's own, unique account.
    for i in range(8):
        target = legitimate[i]
        duplicate_pairs.append({
            "pair_id": f"dup_email_{i+1:02d}",
            "match_type": "email",
            "target_id": target["id"],
            "attempt": {
                "full_name": f"Attacker Email {i+1}",
                "register_email": f"attacker.email{i+1:02d}@dataset.ecoscholar.test",
                "application_email": target["email"],  # collides with target's declared email
                "dob": f"2005-0{(i % 9) + 1}-0{(i % 9) + 1}",
            },
        })
    # 7 name+dob-match duplicate pairs: full_name+dob collide with an existing
    # applicant; both emails are the attacker's own, unique to this attempt.
    for i in range(7):
        target = legitimate[8 + i]
        attacker_email = f"attacker.namedob{i+1:02d}@dataset.ecoscholar.test"
        duplicate_pairs.append({
            "pair_id": f"dup_namedob_{i+1:02d}",
            "match_type": "name_dob",
            "target_id": target["id"],
            "attempt": {
                "full_name": target["full_name"],  # collides with target's name
                "register_email": attacker_email,
                "application_email": attacker_email,
                "dob": target["dob"],  # collides with target's dob
            },
        })

    return {"profile_template": PROFILE_TEMPLATE, "legitimate_applicants": legitimate, "duplicate_pairs": duplicate_pairs}


def main():
    ocr_samples = build_ocr_dataset()
    os.makedirs(OCR_DIR, exist_ok=True)
    with open(os.path.join(OCR_DIR, "labels.json"), "w", encoding="utf-8") as f:
        json.dump({"samples": ocr_samples}, f, indent=2)
    print(f"OCR dataset: {len(ocr_samples)} samples written to {OCR_DIR}")

    by_type = {}
    for s in ocr_samples:
        by_type.setdefault(s["document_type"], 0)
        by_type[s["document_type"]] += 1
    for k, v in by_type.items():
        print(f"  {k}: {v}")

    dup_dataset = build_duplicate_dataset()
    os.makedirs(DUP_DIR, exist_ok=True)
    with open(os.path.join(DUP_DIR, "dataset.json"), "w", encoding="utf-8") as f:
        json.dump(dup_dataset, f, indent=2)
    print(f"\nDuplicate-detection dataset: {len(dup_dataset['legitimate_applicants'])} legitimate applicants, "
          f"{len(dup_dataset['duplicate_pairs'])} seeded duplicate pairs written to {DUP_DIR}")


if __name__ == "__main__":
    main()
