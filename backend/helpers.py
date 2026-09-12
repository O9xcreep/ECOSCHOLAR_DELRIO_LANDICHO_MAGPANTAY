# -*- coding: utf-8 -*-
"""Generic, cross-cutting utilities used by nearly every domain module: id/date
helpers, serializers shared between the applicant and student-facing routes,
organization/program-cycle helpers, notification/email helpers, and the ML
config constants shared by registration and application submission. Imports
only from extensions.py - never from a domain module (auth/documents/
applicants/etc.), to keep the dependency graph one-directional."""
import secrets
import threading
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
import requests

from extensions import app, EMAIL_PROVIDER, RESEND_API_KEY, \
    MAILJET_API_KEY, MAILJET_API_SECRET, SMTP_FROM_NAME, SMTP_FROM_EMAIL

def oid(id_str):
    """Parse a string into an ObjectId, or None if it isn't a valid one."""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None

def iso(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None

def derive_city(address):
    """Addresses are stored as "street, city, province" (see the registration/
    application address field) - pull out just the city for display in listings."""
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
    """Best-effort email send via whichever provider EMAIL_PROVIDER selects.
    Returns True/False and never raises - callers must not let a failed send
    change what's shown to the requester, since that would leak whether an
    email address exists in the system."""
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
    """Fires the SMTP send on a background thread so the request that triggered it
    (approve, add-admin, forgot-password...) never waits on a mail server round-trip.
    Fire-and-forget: nothing here can report success/failure back to the caller,
    which matches how every existing caller already treats send_email's result."""
    threading.Thread(target=send_email, args=(to_email, subject, html_body), daemon=True).start()

# ── ML CONFIG (shared by registration and application submission) ──
# Fixed dropdown options the application form offers - independent of whichever ML
# model is deployed behind it, since these define what an applicant can select, not
# how a particular model encodes them internally. Keep in sync with schema/ml_model.md.
DEFAULT_EDUCATION_MAP = {'None': 0, 'Elementary': 1, 'High School': 2, 'Vocational': 3, 'College': 4, 'Postgraduate': 5}
DEFAULT_OCCUPATION_CATEGORIES = ['Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade', 'Office/Clerical', 'Professional', 'Deceased/Not Applicable']
DEFAULT_HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives', 'Informal settler']
ml_education_map = DEFAULT_EDUCATION_MAP
ml_occupation_categories = DEFAULT_OCCUPATION_CATEGORIES
ml_housing_situations = DEFAULT_HOUSING_SITUATIONS

# The form's "Postgraduate" (no space) doesn't match the trained model's own
# survey-derived label "Post Graduate" (with a space) - translated here rather than
# changing the form's wording, which is a UI decision independent of the training data.
EDUCATION_LABEL_FIX = {'Postgraduate': 'Post Graduate'}

def income_to_bracket(income):
    """Buckets a raw monthly income number into the label the model's
    income_bracket_map expects. The model was trained on bracketed survey data,
    but our form collects an exact number, so this converts one to the other.
    Boundaries/labels must match ecoscholar_encoding_maps.json's income_bracket_map
    exactly."""
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

STATUS_MESSAGES = {
    'Approved': 'Your scholarship application has been approved.',
    'Rejected': 'Your scholarship application was not approved this time.',
}
STATUS_NOTIF_TYPE = {'Approved': 'approved', 'Rejected': 'rejected'}

# ── ACCEPTED APPLICANT LIMIT ──
DEFAULT_APPLICANT_LIMIT = 20

def get_applicant_limit(db, org_id):
    doc = db.settings.find_one({"organization_id": org_id})
    return (doc or {}).get("max_accepted", DEFAULT_APPLICANT_LIMIT)

# ── RESULT VISIBILITY (Approved/Rejected status + eligibility details) ──
# An LGU can hold back students seeing they've been decided until a chosen date/time
# (results_visible_after), with a manual override that always wins when set: True
# forces results visible early, False force-hides them past their own release date.
# Not configuring either means "always visible" - the same behavior as before this
# setting existed, so a deployment that never touches it sees no change.
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
# A "cycle" is a scholarship program run. Applicants carry a cycle_id; the current
# (live) cycle is whichever program_cycles document has closed_at: None - at most one
# at a time. Before the very first reset, no program_cycles documents exist at all and
# get_current_cycle_id() returns None, which every "current cycle" query below matches
# against applicants with no cycle_id field - i.e. every applicant that predates this
# feature is implicitly "the current cycle" until the first reset closes it out. This
# is exactly the "implicit Cycle 0" backward-compatibility the feature spec calls for,
# with no need to backfill millions of old documents with an explicit id.
def get_current_cycle(db, org_id):
    return db.program_cycles.find_one({"closed_at": None, "organization_id": org_id})

def get_current_cycle_id(db, org_id):
    cycle = get_current_cycle(db, org_id)
    return cycle["_id"] if cycle else None

def is_cycle_open(cycle):
    """A cycle accepts new applications while it's live (closed_at unset) and, if it
    has a deadline, only until that deadline passes - the deadline is a hard cutoff,
    not just a displayed target, so no separate admin action is needed to stop new
    submissions once it's reached."""
    if not cycle or cycle.get('closed_at') is not None:
        return False
    deadline = cycle.get('deadline')
    return deadline is None or datetime.utcnow() <= deadline

def form_is_locked(db, org_id):
    """The application form (custom fields, document requirements, which built-in
    fields are hidden) can only be edited before a program starts or after it ends -
    changing what's expected of applicants mid-program would silently invalidate
    submissions already in flight."""
    return is_cycle_open(get_current_cycle(db, org_id))

FORM_LOCKED_ERROR = "The form is locked while a program is open. It can be edited again once this program ends."

def do_program_reset(db, org_id, performed_by, new_label=None, deadline=None):
    """Archives the current cycle (or, on a deployment's very first reset, retroactively
    records the implicit pre-tracking cycle as 'Cycle 0') and opens a new one. Nothing is
    deleted - applicants/documents/audit trails all stay exactly where they are; they
    just stop matching get_current_cycle_id() once their cycle's closed_at is set, which
    is what every "current cycle only" query in this file filters on."""
    now = datetime.utcnow()
    current = get_current_cycle(db, org_id)
    if current:
        db.program_cycles.update_one(
            {"_id": current["_id"]},
            {"$set": {"closed_at": now, "closed_by": performed_by}}
        )
    elif db.applicants.count_documents({"cycle_id": None, "organization_id": org_id}) > 0:
        # First-ever reset with pre-existing data: give that data a real (now-closed)
        # cycle record, and backfill it onto every cycle_id: None applicant so the
        # data model stays consistent going forward - without this, those applicants
        # would show up as an orphaned "0 applicants" Cycle 0 record *and* a separate
        # legacy bucket in list_program_cycles(), both pointing at the same data.
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
        "started_by": performed_by,
        "closed_by": None,
        "organization_id": org_id,
    }
    new_cycle_id = db.program_cycles.insert_one(new_cycle).inserted_id

    # A fresh cycle starts with results hidden by default rather than silently
    # inheriting whatever visibility state the outgoing cycle was left in - an LGU
    # that forgets to re-hide results for the new batch would otherwise leak new
    # decisions the moment the first one is verified.
    db.settings.update_one(
        {"organization_id": org_id},
        {"$set": {"results_visible_override": False}, "$unset": {"results_visible_after": ""}},
        upsert=True
    )

    return new_cycle_id

# ── ORGANIZATIONS (multi-tenancy, Phase A) ──
# Every per-tenant collection is being tagged with organization_id as it's
# written, ahead of any query actually filtering on it (that's Phase C) - so
# that once Phase B's join-code flow and Phase C's read-side scoping land,
# there's no second backfill pass needed for data created in between. Exactly
# one organization exists until Phase B ships; this bootstraps it the first
# time anything asks, rather than requiring a separate provisioning step.
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
    """8 chars from a 33-symbol alphabet is ~1.6x10^11 possibilities - a
    collision on any single attempt is vanishingly unlikely, but check anyway
    since join_code is uniquely indexed and a founding request must not fail
    the whole submission on a fluke collision."""
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
    """Best-effort org name for display (e.g. the authenticated app's header/
    sidebar) - never lets a missing/None organization_id or a lookup miss
    turn into an error, since a legacy account predating Phase A just falls
    back to no name shown at all."""
    if not organization_id:
        return None
    org = db.organizations.find_one({"_id": organization_id})
    return org.get("name") if org else None

def serialize_organization(org):
    return {
        "id": str(org["_id"]),
        "name": org.get("name", ""),
        "status": org.get("status", "pending"),
    }

# ── SERIALIZATION HELPERS (shared between admin and student-facing routes) ──
def serialize_applicant(doc):
    """Flatten an applicant document (with embedded academic/application) into
    the same flat shape the frontend has always received from the SQL JOINs."""
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
    }

# ── NOTIFICATION HELPERS ──
def resolve_notify_user_id(db, applicant_doc):
    """Find the account to notify for an applicant: prefer the linked user_id,
    fall back to matching the applicant's email against users (legacy rows)."""
    if applicant_doc.get('user_id'):
        return applicant_doc['user_id']
    email = applicant_doc.get('email')
    if email:
        match = db.users.find_one({"email": email})
        if match:
            return match['_id']
    return None

def create_notification(db, user_id, applicant, message, notif_type='status_update'):
    """Records the in-app notification and, best-effort, emails the applicant
    the same message - since an applicant who doesn't log back in would
    otherwise never learn their status changed. `applicant` is the applicant
    document (or a projection of it including at least _id/full_name/email)."""
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
