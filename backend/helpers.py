# -*- coding: utf-8 -*-
"""Cross-cutting utilities: id/date helpers, shared serializers, organization/
program-cycle helpers, notification/email helpers, and ML config constants.
Imports only from extensions.py (and field_crypto.py, which itself only
imports extensions), never from a domain module."""
import secrets
import threading
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
import requests

from extensions import app, EMAIL_PROVIDER, RESEND_API_KEY, \
    MAILJET_API_KEY, MAILJET_API_SECRET, SMTP_FROM_NAME, SMTP_FROM_EMAIL
from field_crypto import decrypt_fields, ENCRYPTED_APPLICANT_FIELDS

def oid(id_str):
    """Parse a string into an ObjectId, or None if it isn't a valid one."""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None

def iso(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None

def derive_city(address):
    """Addresses are stored as "street, city, province" - extracts the city."""
    if not address:
        return None
    parts = [p.strip() for p in address.split(',') if p.strip()]
    return parts[-2] if len(parts) >= 2 else None

# ── EMAIL ──
def _send_email_via_resend(to_email, subject, html_body):
    resp = requests.post(
        'https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {RESEND_API_KEY}'},
        json={
            'from': f'{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>',
            'to': [to_email],
            'subject': subject,
            'html': html_body,
        },
        timeout=10,
    )
    resp.raise_for_status()

def _send_email_via_mailjet(to_email, subject, html_body):
    resp = requests.post(
        'https://api.mailjet.com/v3.1/send',
        auth=(MAILJET_API_KEY, MAILJET_API_SECRET),
        json={
            'Messages': [{
                'From': {'Email': SMTP_FROM_EMAIL, 'Name': SMTP_FROM_NAME},
                'To': [{'Email': to_email}],
                'Subject': subject,
                'HTMLPart': html_body,
            }]
        },
        timeout=10,
    )
    resp.raise_for_status()

def send_email(to_email, subject, html_body):
    """Best-effort send via whichever provider EMAIL_PROVIDER selects. Returns
    True/False, never raises."""
    if EMAIL_PROVIDER == 'mailjet':
        if not MAILJET_API_KEY or not MAILJET_API_SECRET or not SMTP_FROM_EMAIL:
            app.logger.warning('Email not sent (MAILJET_API_KEY/MAILJET_API_SECRET/SMTP_FROM_EMAIL not configured): %s', subject)
            return False
        sender = _send_email_via_mailjet
    else:
        if not RESEND_API_KEY or not SMTP_FROM_EMAIL:
            app.logger.warning('Email not sent (RESEND_API_KEY/SMTP_FROM_EMAIL not configured): %s', subject)
            return False
        sender = _send_email_via_resend

    try:
        sender(to_email, subject, html_body)
        return True
    except Exception as e:
        app.logger.error('Email send failed (%s): %s', EMAIL_PROVIDER, str(e))
        return False

def send_email_async(to_email, subject, html_body):
    """Sends on a background thread; fire-and-forget."""
    threading.Thread(target=send_email, args=(to_email, subject, html_body), daemon=True).start()

# ── ML CONFIG (shared by registration and application submission) ──
# Form dropdown options. Keep in sync with schema/ml_model.md.
DEFAULT_EDUCATION_MAP = {'None': 0, 'Elementary': 1, 'High School': 2, 'Vocational': 3, 'College': 4, 'Postgraduate': 5}
DEFAULT_OCCUPATION_CATEGORIES = ['Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade', 'Office/Clerical', 'Professional', 'OFW', 'Deceased/Not Applicable']
DEFAULT_HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives', 'Informal settler']
ml_education_map = DEFAULT_EDUCATION_MAP
ml_occupation_categories = DEFAULT_OCCUPATION_CATEGORIES
ml_housing_situations = DEFAULT_HOUSING_SITUATIONS

# Form label "Postgraduate" vs. the model's trained label "Post Graduate".
EDUCATION_LABEL_FIX = {'Postgraduate': 'Post Graduate'}

def income_to_bracket(income):
    """Maps a raw monthly income to the model's income_bracket_map label.
    Must match ecoscholar_encoding_maps.json exactly."""
    if income is None:
        return None
    income = float(income)
    if income < 5000:
        return "Below ₱ 5,000"
    if income <= 10000:
        return "₱ 5,001 - ₱ 10,000"
    if income <= 15000:
        return "₱ 10,000 - ₱ 15,000"
    if income <= 20000:
        return "₱ 15,000 - ₱ 20,000"
    return "₱ 20,000 Above"

# The bracket labels the application form offers (ApplicationForm.jsx's
# INCOME_RANGES). The form stores a stand-in figure inside the chosen bracket
# as monthly_income, so screens show this label rather than that number.
def income_bracket_label(income):
    if income is None:
        return None
    return {
        "Below ₱ 5,000": "Below ₱5,000",
        "₱ 5,001 - ₱ 10,000": "₱5,001 - ₱10,000",
        "₱ 10,000 - ₱ 15,000": "₱10,000 - ₱15,000",
        "₱ 15,000 - ₱ 20,000": "₱15,000 - ₱20,000",
        "₱ 20,000 Above": "₱20,000 and above",
    }[income_to_bracket(income)]

STATUS_MESSAGES = {
    'Approved': ('Your scholarship application has been approved. Next step: disbursement - '
                 "your LGU's scholarship office will announce when and where to claim your grant."),
    'Rejected': 'Your scholarship application was not approved this time.',
}
STATUS_NOTIF_TYPE = {'Approved': 'approved', 'Rejected': 'rejected'}

# ── ACCEPTED APPLICANT LIMIT ──
DEFAULT_APPLICANT_LIMIT = 20

def get_applicant_limit(db, org_id):
    doc = db.settings.find_one({"organization_id": org_id})
    return (doc or {}).get("max_accepted", DEFAULT_APPLICANT_LIMIT)

# ── ELIGIBILITY BAR ──
# Who qualifies at all ("top X% of need"), before the applicant limit decides who is funded.
# The choices must stay inside the range the eligibility classifier was trained on
# (eligibility_bar.selectable_top_percents in ecoscholar_encoding_maps.json).
DEFAULT_ELIGIBILITY_TOP_PERCENT = 30
ELIGIBILITY_TOP_PERCENT_CHOICES = list(range(10, 61, 10))

def get_eligibility_top_percent(db, org_id):
    """The bar the current program was started with. Before any program (or for a program
    started before bars were stored per program), the LGU's saved choice."""
    cycle = get_current_cycle(db, org_id)
    if cycle and cycle.get("eligibility_top_percent") is not None:
        return cycle["eligibility_top_percent"]
    doc = db.settings.find_one({"organization_id": org_id})
    return (doc or {}).get("eligibility_top_percent", DEFAULT_ELIGIBILITY_TOP_PERCENT)

def eligibility_bar_locked(db, org_id):
    """The bar is chosen when a program starts and stays fixed until the next one, so every
    applicant in a program is judged by the same standard. Only changeable before the first program."""
    return get_current_cycle(db, org_id) is not None

ELIGIBILITY_BAR_LOCKED_ERROR = ("The eligibility bar is fixed once a program has started. "
                                "Choose a different bar when you start the next program.")

# ── RESULT VISIBILITY (Approved/Rejected status + eligibility details) ──
# An LGU can hold results until a chosen date/time (results_visible_after),
# with a manual override that always wins when set. Default is visible.
GENERIC_REVIEWED_MESSAGE = (
    "Your application has finished review. Results will be available once released "
    "by the program - check back or sign in again later."
)

def are_results_visible(db, org_id):
    settings = db.settings.find_one({"organization_id": org_id}) or {}
    override = settings.get('results_visible_override')
    if override is not None:
        return bool(override)
    visible_after = settings.get('results_visible_after')
    if not visible_after:
        return True
    return datetime.utcnow() >= visible_after

# ── PROGRAM CYCLES (archive-then-clear reset) ──
# A "cycle" is a scholarship program run. The current cycle is the
# program_cycles document with closed_at: None. Applicants with no cycle_id
# predate this feature and are implicitly "current" until the first reset.
def get_current_cycle(db, org_id):
    return db.program_cycles.find_one({"closed_at": None, "organization_id": org_id})

def get_current_cycle_id(db, org_id):
    cycle = get_current_cycle(db, org_id)
    return cycle["_id"] if cycle else None

def is_cycle_open(cycle):
    """A cycle is open while live and, if it has a deadline, before it passes."""
    if not cycle or cycle.get('closed_at') is not None:
        return False
    deadline = cycle.get('deadline')
    return deadline is None or datetime.utcnow() <= deadline

def form_is_locked(db, org_id):
    """Form fields/document requirements can only be edited outside an open program."""
    return is_cycle_open(get_current_cycle(db, org_id))

FORM_LOCKED_ERROR = "The form is locked while a program is open. It can be edited again once this program ends."

def do_program_reset(db, org_id, performed_by, new_label=None, deadline=None, eligibility_top_percent=None):
    """Archives the current cycle and opens a new one. Nothing is deleted;
    existing data just stops matching get_current_cycle_id(). The new program keeps the
    outgoing program's eligibility bar unless a different one is given."""
    now = datetime.utcnow()
    if eligibility_top_percent is None:
        eligibility_top_percent = get_eligibility_top_percent(db, org_id)
    current = get_current_cycle(db, org_id)
    if current:
        db.program_cycles.update_one(
            {"_id": current["_id"]},
            {"$set": {"closed_at": now, "closed_by": performed_by}}
        )
    elif db.applicants.count_documents({"cycle_id": None, "organization_id": org_id}) > 0:
        # First-ever reset: backfill pre-existing applicants onto a real, closed cycle.
        cycle0_id = db.program_cycles.insert_one({
            "label": "Program 0 (before program tracking)",
            "started_at": None,
            "closed_at": now,
            "started_by": None,
            "closed_by": performed_by,
            "organization_id": org_id,
        }).inserted_id
        db.applicants.update_many({"cycle_id": None, "organization_id": org_id}, {"$set": {"cycle_id": cycle0_id}})

    cycle_count = db.program_cycles.count_documents({"organization_id": org_id})
    new_cycle = {
        "label": (new_label or '').strip() or f"Program {cycle_count + 1}",
        "started_at": now,
        "closed_at": None,
        "deadline": deadline,
        "eligibility_top_percent": eligibility_top_percent,
        "started_by": performed_by,
        "closed_by": None,
        "organization_id": org_id,
    }
    new_cycle_id = db.program_cycles.insert_one(new_cycle).inserted_id

    # A fresh cycle starts with results hidden by default. The bar is also remembered as the
    # LGU's choice, so it is the starting value when the next program is set up.
    db.settings.update_one(
        {"organization_id": org_id},
        {"$set": {"results_visible_override": False, "eligibility_top_percent": eligibility_top_percent},
         "$unset": {"results_visible_after": ""}},
        upsert=True
    )

    return new_cycle_id

# ── ORGANIZATIONS (multi-tenancy) ──
def generate_join_code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))

def get_default_organization_id(db):
    org = db.organizations.find_one({})
    if org:
        return org["_id"]
    result = db.organizations.insert_one({
        "name": "Default Organization",
        "join_code": generate_join_code(),
        "status": "active",
        "created_at": datetime.utcnow(),
        "founding_admin_request_id": None,
    })
    return result.inserted_id

def generate_unique_join_code(db):
    """Retries on the rare collision - join_code is uniquely indexed."""
    for _ in range(10):
        code = generate_join_code()
        if not db.organizations.find_one({"join_code": code}):
            return code
    raise RuntimeError("Could not generate a unique join code")

def find_active_organization_by_code(db, code):
    code = (code or '').strip().upper()
    if not code:
        return None
    return db.organizations.find_one({"join_code": code, "status": "active"})

def get_organization_name(db, organization_id):
    """Best-effort org name for display. Returns None if missing or not found."""
    if not organization_id:
        return None
    org = db.organizations.find_one({"_id": organization_id})
    return org.get("name") if org else None

def get_organization_municipality(db, organization_id):
    """The org's own municipality, set once by whoever founded it. Anyone
    joining an existing org (invite, join code, or approved request) inherits
    this instead of being asked to redundantly pick their own - one
    organization is one LGU, so everyone under it already serves it."""
    if not organization_id:
        return ''
    org = db.organizations.find_one({"_id": organization_id})
    return (org or {}).get("municipality", "") or ''

def serialize_organization(org):
    return {
        "id": str(org["_id"]),
        "name": org.get("name", ""),
        "status": org.get("status", "pending"),
    }

# ── SERIALIZATION HELPERS (shared between admin and student-facing routes) ──
def serialize_applicant(doc):
    """Flattens an applicant document (embedded academic/application) for the API."""
    doc = decrypt_fields(doc, ENCRYPTED_APPLICANT_FIELDS)
    academic = doc.get('academic') or {}
    application = doc.get('application') or {}
    return {
        "id": str(doc['_id']),
        "user_id": str(doc['user_id']) if doc.get('user_id') else None,
        "full_name": doc.get('full_name'),
        "email": doc.get('email'),
        "contact_number": doc.get('contact_number'),
        "address": doc.get('address'),
        "gender": doc.get('gender'),
        "date_of_birth": doc.get('date_of_birth'),
        "religion": doc.get('religion'),
        "citizenship": doc.get('citizenship'),
        "father_name": doc.get('father_name'),
        "father_occupation": doc.get('father_occupation'),
        "father_education": doc.get('father_education'),
        "mother_name": doc.get('mother_name'),
        "mother_occupation": doc.get('mother_occupation'),
        "mother_education": doc.get('mother_education'),
        "household_income": doc.get('monthly_income'),
        "household_income_bracket": income_bracket_label(doc.get('monthly_income')),
        "family_size": doc.get('family_size'),
        "num_siblings": doc.get('num_siblings'),
        "num_siblings_studying": doc.get('num_siblings_studying'),
        "housing_situation": doc.get('housing_situation'),
        "barangay": doc.get('barangay'),
        "ml_score": doc.get('ml_score', 0),
        "ml_status": doc.get('ml_status', 'Pending'),
        "created_at": iso(doc.get('created_at')),
        "privacy_consent": doc.get('privacy_consent', False),
        "has_other_scholarship": doc.get('has_other_scholarship', False),
        "other_scholarship_details": doc.get('other_scholarship_details'),
        "course": academic.get('course'),
        "year_level": academic.get('year_level'),
        "gpa": academic.get('gpa'),
        "school": academic.get('school'),
        "school_address": academic.get('school_address'),
        "academic_year": academic.get('academic_year'),
        "semester": academic.get('semester'),
        "application_status": application.get('status'),
        "application_id": str(doc['_id']),
        "submitted_at": iso(application.get('submitted_at')),
        "reviewed_at": iso(application.get('reviewed_at')),
        "reviewed_by_name": application.get('reviewed_by_name'),
        "application_type": application.get('application_type'),
        "rejection_reason": application.get('rejection_reason'),
        "admin_comment": application.get('admin_comment'),
        "city": derive_city(doc.get('address')),
        "extra_fields": doc.get('extra_fields', {}),
        "cycle_id": str(doc['cycle_id']) if doc.get('cycle_id') else None,
    }

def serialize_document(d):
    return {
        "document_name": d.get('document_name'),
        "status": d.get('status', 'Missing'),
        "uploaded_at": iso(d.get('uploaded_at')),
        "ocr_status": d.get('ocr_status'),
        "upload_warning": d.get('upload_warning'),
    }

# ── NOTIFICATION HELPERS ──
def resolve_notify_user_id(db, applicant_doc):
    """Prefers the linked user_id, falls back to matching by email."""
    if applicant_doc.get('user_id'):
        return applicant_doc['user_id']
    email = applicant_doc.get('email')
    if email:
        match = db.users.find_one({"email": email})
        if match:
            return match['_id']
    return None

def create_notification(db, user_id, applicant, message, notif_type='status_update'):
    """Records an in-app notification and best-effort emails the applicant."""
    if not user_id:
        return
    db.notifications.insert_one({
        "user_id": user_id,
        "applicant_id": applicant["_id"],
        "message": message,
        "type": notif_type,
        "is_read": False,
        "organization_id": applicant.get("organization_id") or get_default_organization_id(db),
        "created_at": datetime.utcnow(),
    })

    email = applicant.get('email')
    if email:
        html = f"""
            <p>Hi {applicant.get('full_name', '')},</p>
            <p>{message}</p>
            <p>Log in to EcoScholar to see the full details of your application.</p>
        """
        send_email_async(email, 'EcoScholar application update', html)
