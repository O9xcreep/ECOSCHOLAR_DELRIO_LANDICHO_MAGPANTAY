# -*- coding: utf-8 -*-
"""LGU-configurable settings: accepted-applicant limit / result visibility,
program cycles (reset), custom form fields, document requirements (thin
routes over documents.py's model), and student-facing guidelines."""
import re
from datetime import datetime
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import app, limiter, get_db, DEBUG
from helpers import oid, iso, get_applicant_limit, are_results_visible, get_current_cycle, \
    get_current_cycle_id, is_cycle_open, form_is_locked, FORM_LOCKED_ERROR, do_program_reset
from auth import require_auth, require_permission, current_organization_oid, \
    is_full_access_role, has_permission, PROFILE_FIELDS
from documents import get_doc_requirements_collection, serialize_doc_requirement, DEFAULT_DOC_LABELS
from ml_scoring import recompute_approvals

def serialize_cycle(c, applicant_count=None):
    return {
        "id": str(c["_id"]),
        "label": c.get("label"),
        "started_at": iso(c.get("started_at")),
        "closed_at": iso(c.get("closed_at")),
        "deadline": iso(c.get("deadline")),
        "started_by": c.get("started_by"),
        "closed_by": c.get("closed_by"),
        "is_current": c.get("closed_at") is None,
        "is_open": is_cycle_open(c),
        "applicant_count": applicant_count,
    }

def get_hidden_builtin_fields(db, org_id):
    doc = db.settings.find_one({"organization_id": org_id})
    return (doc or {}).get("hidden_builtin_fields", [])

# ── ACCEPTED APPLICANT LIMIT SETTING ──
def serialize_settings(db, org_id):
    doc = db.settings.find_one({"organization_id": org_id}) or {}
    current_cycle = get_current_cycle(db, org_id)
    return {
        "max_accepted": get_applicant_limit(db, org_id),
        "approved_count": db.applicants.count_documents({
            "application.status": "Approved", "cycle_id": get_current_cycle_id(db, org_id), "organization_id": org_id
        }),
        "hidden_builtin_fields": get_hidden_builtin_fields(db, org_id),
        "results_visible_after": iso(doc.get('results_visible_after')),
        "results_visible_override": doc.get('results_visible_override'),
        "results_visible_now": are_results_visible(db, org_id),
        "reset_password_set": bool(doc.get('reset_password_hash')),
        "current_cycle": serialize_cycle(current_cycle) if current_cycle else None,
    }

@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    # Read access is wider than write access: an lgu_member granted only
    # can_reset_program still needs to see reset_password_set/current_cycle to
    # use the Reset Program action.
    if not (is_full_access_role(g.current_user.get('role')) or has_permission('can_reset_program')):
        return jsonify({"error": "Forbidden"}), 403
    db = get_db()
    return jsonify(serialize_settings(db, current_organization_oid()))

@app.route('/api/settings', methods=['PUT'])
@require_auth
def update_settings():
    data = request.get_json() or {}

    # hidden_builtin_fields is part of "the form" itself (see form_is_locked
    # below) - anyone trusted to reset the program can configure it, same as
    # custom fields/document requirements/guidelines. Every other setting
    # here (accepted-applicant limit, result visibility, the reset
    # confirmation password) stays full-access-only.
    is_full_access = is_full_access_role(g.current_user.get('role'))
    FULL_ACCESS_ONLY_KEYS = {'max_accepted', 'results_visible_after', 'results_visible_override', 'reset_password'}
    if any(k in data for k in FULL_ACCESS_ONLY_KEYS) and not is_full_access:
        return jsonify({"error": "Forbidden"}), 403
    if 'hidden_builtin_fields' in data and not (is_full_access or has_permission('can_reset_program')):
        return jsonify({"error": "Forbidden"}), 403

    set_fields = {}
    unset_fields = {}
    db = get_db()
    org_id = current_organization_oid()

    if 'max_accepted' in data:
        max_accepted = data.get('max_accepted')
        if not isinstance(max_accepted, int) or isinstance(max_accepted, bool) or max_accepted < 1:
            return jsonify({"error": "max_accepted must be a positive integer"}), 400
        set_fields['max_accepted'] = max_accepted

    if 'hidden_builtin_fields' in data:
        # Part of "the form" itself, locked the same as custom fields/document
        # requirements while a program is open (see form_is_locked()).
        if form_is_locked(db, org_id):
            return jsonify({"error": FORM_LOCKED_ERROR}), 409
        hidden = data.get('hidden_builtin_fields')
        if not isinstance(hidden, list) or any(f not in HIDEABLE_BUILTIN_FIELDS for f in hidden):
            return jsonify({"error": f"hidden_builtin_fields must be a list from {list(HIDEABLE_BUILTIN_FIELDS)}"}), 400
        set_fields['hidden_builtin_fields'] = hidden

    if 'results_visible_after' in data:
        raw = data.get('results_visible_after')
        if raw in (None, ''):
            unset_fields['results_visible_after'] = ''
        else:
            try:
                set_fields['results_visible_after'] = datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
            except (ValueError, AttributeError):
                return jsonify({"error": "results_visible_after must be an ISO date/time string, or null"}), 400

    if 'results_visible_override' in data:
        override = data.get('results_visible_override')
        if override is None:
            unset_fields['results_visible_override'] = ''
        elif isinstance(override, bool):
            set_fields['results_visible_override'] = override
        else:
            return jsonify({"error": "results_visible_override must be true, false, or null"}), 400

    # Reset confirmation password (see POST /api/program-reset), separate from
    # the admin's login password. Never read back; GET /api/settings only
    # reports whether one is set (reset_password_set), never the hash.
    if 'reset_password' in data:
        reset_password = data.get('reset_password')
        if reset_password in (None, ''):
            unset_fields['reset_password_hash'] = ''
        elif isinstance(reset_password, str) and len(reset_password) >= 6:
            set_fields['reset_password_hash'] = generate_password_hash(reset_password)
        else:
            return jsonify({"error": "reset_password must be at least 6 characters, or null to remove it"}), 400

    if not set_fields and not unset_fields:
        return jsonify({"error": "No valid settings provided"}), 400

    try:
        update = {}
        if set_fields:
            update['$set'] = set_fields
        if unset_fields:
            update['$unset'] = unset_fields
        db.settings.update_one({"organization_id": org_id}, update, upsert=True)
        if 'max_accepted' in set_fields:
            recompute_approvals(db, org_id, set_fields['max_accepted'], reviewed_by=g.current_user.get('email', 'Admin'))
        return jsonify({"message": "Settings updated", **serialize_settings(db, org_id)})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── LIST PROGRAM CYCLES ──
@app.route('/api/program-cycles', methods=['GET'])
@require_permission('can_review_applicants')
def list_program_cycles():
    db = get_db()
    org_id = current_organization_oid()
    cycles = list(db.program_cycles.find({"organization_id": org_id}).sort('started_at', -1))
    result = []
    for c in cycles:
        count = db.applicants.count_documents({"cycle_id": c["_id"], "organization_id": org_id})
        result.append(serialize_cycle(c, applicant_count=count))

    legacy_count = db.applicants.count_documents({"cycle_id": None, "organization_id": org_id})
    if legacy_count > 0:
        result.append({
            "id": None, "label": "Before program tracking (legacy data)",
            "started_at": None, "closed_at": None,
            "started_by": None, "closed_by": None,
            "is_current": len(cycles) == 0,
            "applicant_count": legacy_count,
        })

    return jsonify({"cycles": result})

# ── PROGRAM RESET (archive current cycle, start a new one) ──
# Super Admin and the LGU's Admin always have this; an lgu_member only gets it
# if explicitly granted can_reset_program, since it changes what's "live"
# everywhere in the app at once. Nothing is destructive: see
# do_program_reset()'s docstring.
@app.route('/api/program-reset', methods=['POST'])
@require_permission('can_reset_program')
@limiter.limit("5 per minute")
def program_reset():
    data = request.get_json() or {}
    password = data.get('password') or ''
    label = data.get('label')

    raw_deadline = data.get('deadline')
    if not raw_deadline:
        return jsonify({"error": "An application deadline is required to start a program."}), 400
    try:
        deadline = datetime.fromisoformat(raw_deadline.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return jsonify({"error": "deadline must be an ISO date/time string"}), 400
    if deadline <= datetime.utcnow():
        return jsonify({"error": "deadline must be in the future"}), 400

    try:
        db = get_db()
        org_id = current_organization_oid()
        settings_doc = db.settings.find_one({"organization_id": org_id}) or {}
        reset_hash = settings_doc.get('reset_password_hash')
        if not reset_hash:
            return jsonify({"error": "Set a reset confirmation password in Settings before resetting."}), 400
        if not check_password_hash(reset_hash, password):
            return jsonify({"error": "Incorrect reset confirmation password."}), 403

        outgoing_cycle = get_current_cycle(db, org_id)
        outgoing_count = db.applicants.count_documents(
            {"cycle_id": outgoing_cycle["_id"], "organization_id": org_id} if outgoing_cycle
            else {"cycle_id": None, "organization_id": org_id}
        )

        performed_by = g.current_user.get('email', 'Admin')
        new_cycle_id = do_program_reset(db, org_id, performed_by, new_label=label, deadline=deadline)

        return jsonify({
            "message": "Program reset complete. A new cycle has started.",
            "archived_applicant_count": outgoing_count,
            **serialize_settings(db, org_id),
            "new_cycle_id": str(new_cycle_id),
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── UPDATE CURRENT CYCLE'S DEADLINE ──
# Lets an admin extend or tighten the deadline of the program that's already
# running, without going through the destructive archive-and-start-new flow
# that POST /api/program-reset requires. Gated by can_review_applicants (not
# can_reset_program) since nothing here is destructive.
@app.route('/api/program-cycles/current/deadline', methods=['PUT'])
@require_permission('can_review_applicants')
def update_current_cycle_deadline():
    data = request.get_json() or {}
    raw_deadline = data.get('deadline')
    if not raw_deadline:
        return jsonify({"error": "An application deadline is required."}), 400
    try:
        deadline = datetime.fromisoformat(raw_deadline.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return jsonify({"error": "deadline must be an ISO date/time string"}), 400
    if deadline <= datetime.utcnow():
        return jsonify({"error": "deadline must be in the future"}), 400

    try:
        db = get_db()
        org_id = current_organization_oid()
        cycle = get_current_cycle(db, org_id)
        if not cycle:
            return jsonify({"error": "No program is currently running."}), 400
        db.program_cycles.update_one({"_id": cycle["_id"]}, {"$set": {"deadline": deadline}})
        updated_cycle = db.program_cycles.find_one({"_id": cycle["_id"]})
        return jsonify(serialize_cycle(updated_cycle))
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── CUSTOM APPLICATION FORM FIELDS ──
# LGUs collect extra information beyond the core fields the eligibility model
# needs (see build_feature_row); these are admin-defined, informational-only
# fields, stored under applicant.extra_fields and never read by
# build_feature_row, so no custom field can influence the ML score.
FIELD_TYPES = {'text', 'textarea', 'number', 'date', 'select', 'checkbox'}
FORM_SECTIONS = {'personal', 'school'}

# Existing built-in fields that are genuinely optional (never read by
# build_feature_row) and safe to let an LGU hide entirely.
HIDEABLE_BUILTIN_FIELDS = {
    'religion': 'Religion',
    'citizenship': 'Citizenship',
}

def serialize_form_field(f):
    return {
        "id": str(f["_id"]),
        "key": f.get("key"),
        "label": f.get("label"),
        "type": f.get("type"),
        "options": f.get("options", []),
        "required": f.get("required", False),
        "enabled": f.get("enabled", True),
        "section": f.get("section"),
        "order": f.get("order", 0),
    }

@app.route('/api/form-fields', methods=['GET'])
@require_auth
def list_form_fields():
    db = get_db()
    org_id = current_organization_oid()
    query = {"organization_id": org_id} if is_full_access_role(g.current_user.get('role')) else {"enabled": True, "organization_id": org_id}
    fields = list(db.form_fields.find(query).sort([("section", 1), ("order", 1)]))
    return jsonify({
        "fields": [serialize_form_field(f) for f in fields],
        "hidden_builtin_fields": get_hidden_builtin_fields(db, org_id),
        "hideable_builtin_fields": HIDEABLE_BUILTIN_FIELDS,
    })

@app.route('/api/form-fields', methods=['POST'])
@require_permission('can_reset_program')
def create_form_field():
    data = request.get_json() or {}
    key = (data.get('key') or '').strip()
    label = (data.get('label') or '').strip()
    field_type = data.get('type')
    section = data.get('section')

    if not key or not re.match(r'^[a-z][a-z0-9_]*$', key):
        return jsonify({"error": "Key is required and must be lowercase letters, numbers, and underscores only"}), 400
    if not label:
        return jsonify({"error": "Label is required"}), 400
    if field_type not in FIELD_TYPES:
        return jsonify({"error": f"Type must be one of {sorted(FIELD_TYPES)}"}), 400
    if section not in FORM_SECTIONS:
        return jsonify({"error": f"Section must be one of {sorted(FORM_SECTIONS)}"}), 400
    if key in HIDEABLE_BUILTIN_FIELDS or key in PROFILE_FIELDS:
        return jsonify({"error": "This key is already used by a built-in field"}), 400

    options = data.get('options') or []
    if field_type == 'select' and (not isinstance(options, list) or not options):
        return jsonify({"error": "Select fields need at least one option"}), 400
    if field_type == 'checkbox' and options and not isinstance(options, list):
        return jsonify({"error": "Checkbox options must be a list"}), 400

    db = get_db()
    org_id = current_organization_oid()
    if form_is_locked(db, org_id):
        return jsonify({"error": FORM_LOCKED_ERROR}), 409
    if db.form_fields.find_one({"key": key, "organization_id": org_id}):
        return jsonify({"error": "A custom field with this key already exists"}), 409

    doc = {
        "key": key,
        "label": label,
        "type": field_type,
        "options": options if field_type in ('select', 'checkbox') else [],
        "required": bool(data.get('required', False)),
        "enabled": True,
        "section": section,
        "order": db.form_fields.count_documents({"section": section, "organization_id": org_id}),
        "created_at": datetime.utcnow(),
        "organization_id": org_id,
    }
    result = db.form_fields.insert_one(doc)
    doc["_id"] = result.inserted_id
    return jsonify({"field": serialize_form_field(doc)}), 201

@app.route('/api/form-fields/<field_id>', methods=['PUT'])
@require_permission('can_reset_program')
def update_form_field(field_id):
    field_oid = oid(field_id)
    if not field_oid:
        return jsonify({"error": "Invalid field id"}), 400

    data = request.get_json() or {}
    set_fields = {}
    if 'label' in data:
        label = (data.get('label') or '').strip()
        if not label:
            return jsonify({"error": "Label cannot be empty"}), 400
        set_fields['label'] = label
    if 'required' in data:
        set_fields['required'] = bool(data['required'])
    if 'enabled' in data:
        set_fields['enabled'] = bool(data['enabled'])
    if 'options' in data:
        set_fields['options'] = data['options'] or []

    if not set_fields:
        return jsonify({"error": "No valid fields provided"}), 400

    db = get_db()
    org_id = current_organization_oid()
    if form_is_locked(db, org_id):
        return jsonify({"error": FORM_LOCKED_ERROR}), 409
    result = db.form_fields.update_one({"_id": field_oid, "organization_id": org_id}, {"$set": set_fields})
    if result.matched_count == 0:
        return jsonify({"error": "Field not found"}), 404

    updated = db.form_fields.find_one({"_id": field_oid, "organization_id": org_id})
    return jsonify({"field": serialize_form_field(updated)})

@app.route('/api/form-fields/<field_id>', methods=['DELETE'])
@require_permission('can_reset_program')
def delete_form_field(field_id):
    field_oid = oid(field_id)
    if not field_oid:
        return jsonify({"error": "Invalid field id"}), 400

    db = get_db()
    org_id = current_organization_oid()
    if form_is_locked(db, org_id):
        return jsonify({"error": FORM_LOCKED_ERROR}), 409
    result = db.form_fields.delete_one({"_id": field_oid, "organization_id": org_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Field not found"}), 404
    return jsonify({"message": "Field deleted"})

@app.route('/api/document-requirements', methods=['GET'])
@require_auth
def list_doc_requirements():
    db = get_db()
    org_id = current_organization_oid()
    coll = get_doc_requirements_collection(db, org_id)
    query = {"organization_id": org_id} if is_full_access_role(g.current_user.get('role')) else {"enabled": True, "organization_id": org_id}
    docs = list(coll.find(query).sort("order", 1))
    return jsonify({"requirements": [serialize_doc_requirement(d) for d in docs]})

@app.route('/api/document-requirements', methods=['POST'])
@require_permission('can_reset_program')
def create_doc_requirement():
    data = request.get_json() or {}
    label = (data.get('label') or '').strip()
    if not label:
        return jsonify({"error": "Label is required"}), 400

    db = get_db()
    org_id = current_organization_oid()
    if form_is_locked(db, org_id):
        return jsonify({"error": FORM_LOCKED_ERROR}), 409
    coll = get_doc_requirements_collection(db, org_id)
    if coll.find_one({"label": label, "organization_id": org_id}):
        return jsonify({"error": "A document requirement with this label already exists"}), 409

    doc = {
        "label": label,
        "required": bool(data.get('required', False)),
        "enabled": True,
        "order": coll.count_documents({"organization_id": org_id}),
        "created_at": datetime.utcnow(),
        "organization_id": org_id,
    }
    result = coll.insert_one(doc)
    doc["_id"] = result.inserted_id
    return jsonify({"requirement": serialize_doc_requirement(doc)}), 201

@app.route('/api/document-requirements/<req_id>', methods=['PUT'])
@require_permission('can_reset_program')
def update_doc_requirement(req_id):
    req_oid = oid(req_id)
    if not req_oid:
        return jsonify({"error": "Invalid requirement id"}), 400

    data = request.get_json() or {}
    set_fields = {}
    if 'label' in data:
        label = (data.get('label') or '').strip()
        if not label:
            return jsonify({"error": "Label cannot be empty"}), 400
        set_fields['label'] = label
    if 'required' in data:
        set_fields['required'] = bool(data['required'])
    if 'enabled' in data:
        set_fields['enabled'] = bool(data['enabled'])

    if not set_fields:
        return jsonify({"error": "No valid fields provided"}), 400

    db = get_db()
    org_id = current_organization_oid()
    if form_is_locked(db, org_id):
        return jsonify({"error": FORM_LOCKED_ERROR}), 409
    coll = get_doc_requirements_collection(db, org_id)
    result = coll.update_one({"_id": req_oid, "organization_id": org_id}, {"$set": set_fields})
    if result.matched_count == 0:
        return jsonify({"error": "Requirement not found"}), 404

    updated = coll.find_one({"_id": req_oid, "organization_id": org_id})
    return jsonify({"requirement": serialize_doc_requirement(updated)})

@app.route('/api/document-requirements/<req_id>', methods=['DELETE'])
@require_permission('can_reset_program')
def delete_doc_requirement(req_id):
    req_oid = oid(req_id)
    if not req_oid:
        return jsonify({"error": "Invalid requirement id"}), 400

    db = get_db()
    org_id = current_organization_oid()
    if form_is_locked(db, org_id):
        return jsonify({"error": FORM_LOCKED_ERROR}), 409

    existing = db.document_requirements.find_one({"_id": req_oid, "organization_id": org_id})
    if not existing:
        return jsonify({"error": "Requirement not found"}), 404
    if existing.get("label") in DEFAULT_DOC_LABELS:
        return jsonify({"error": "Default document requirements can't be deleted; disable it or uncheck \"Required\" instead."}), 400

    result = db.document_requirements.delete_one({"_id": req_oid, "organization_id": org_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Requirement not found"}), 404
    return jsonify({"message": "Requirement deleted"})

# ── APPLICATION GUIDELINES (student-facing, admin-editable) ──
# A rich-text blob any LGU admin can edit from Settings > System. This default
# is the same content the page always showed, for LGUs that never edit it.
DEFAULT_GUIDELINES_HTML = """
<h2>General Eligibility Criteria</h2>
<ul>
<li>Must be a registered resident of the city with a valid Barangay Certificate.</li>
<li>Must be currently enrolled or an incoming first-year college student in an accredited institution.</li>
<li>Must maintain a minimum general weighted average (GWA) or GPA requirement as specified by your specific scholarship type.</li>
<li>Combined family annual income must not exceed the threshold set for financial assistance (unless applying for pure merit-based slots).</li>
<li>Must not be a recipient of any other government scholarship at the time of application.</li>
<li>Must be a Filipino citizen.</li>
</ul>
<h2>Document Submission Rules</h2>
<ul>
<li><strong>File Format:</strong> All uploaded files must be in clear PDF, PNG, or JPEG format.</li>
<li><strong>File Size:</strong> Individual document file sizes must not exceed 5MB.</li>
<li>Ensure that scanned documents or photos are completely readable &mdash; blurry submissions can cause automatic rejection or delay processing.</li>
<li>The <em>Proof of Income</em> must be an official Certificate of Indigency from your Barangay or an ITR from the BIR.</li>
<li>All documents must be current and valid &mdash; expired documents will not be accepted.</li>
</ul>
<h2>Scholarship Types</h2>
<ul>
<li>Academic Merit</li>
<li>Financial Aid</li>
<li>Full Scholar</li>
<li>Loyalty Grant</li>
</ul>
<h2>Application Process</h2>
<ol>
<li><strong>Fill Personal Information:</strong> Complete all required fields in Step 1 including parental and financial details.</li>
<li><strong>Provide Academic Information:</strong> Enter your school, course, GWA, and semester details in Step 2.</li>
<li><strong>Upload Required Documents:</strong> Upload all required supporting documents in Step 3 before submitting.</li>
<li><strong>Submit Application:</strong> Click Submit Application. Your application will be reviewed by the scholarship committee.</li>
<li><strong>Wait for Results:</strong> You'll be notified once your application is reviewed. Depending on how your LGU has configured result visibility, you may see the decision immediately or only after the program's application period ends.</li>
</ol>
<h2>Important Reminders</h2>
<blockquote><p><strong>Editing After Submission:</strong> You can withdraw your application and submit a corrected one at any time before it's reviewed - for example, if you notice a mistake, or if the LGU asks you to fix something with a specific document. Once your application has been Approved or Rejected, that decision is final: it can no longer be withdrawn, and its documents can no longer be changed.</p></blockquote>
<ul>
<li><strong>Deadline:</strong> Check the deadline shown on your Dashboard or Application page - it's set by your LGU and applications stop being accepted automatically once it passes.</li>
<li><strong>Data Privacy:</strong> All information submitted is protected under the Data Privacy Act of 2012 (RA 10173). Your data will only be used for scholarship evaluation.</li>
<li><strong>Need Help?</strong> Contact your LGU's scholarship office using the details they've provided, or visit their office during business hours.</li>
</ul>
""".strip()

MAX_GUIDELINES_HTML_LENGTH = 200_000

def sanitize_basic_html(html):
    """Not a full sanitizer - guidelines_html is only ever written by an
    admin/lgu_admin, the same trust level already controlling form-field
    labels and email templates. Defense-in-depth against an obviously
    dangerous paste, not a security boundary against the editor's author."""
    html = re.sub(r'(?is)<script.*?</script>', '', html)
    html = re.sub(r'(?is)\son\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', html)
    html = re.sub(r'(?is)(href|src)\s*=\s*(["\'])\s*javascript:.*?\2', r'\1=\2#\2', html)
    return html

@app.route('/api/guidelines', methods=['GET'])
@require_auth
def get_guidelines():
    db = get_db()
    doc = db.settings.find_one({"organization_id": current_organization_oid()}) or {}
    return jsonify({"html": doc.get("guidelines_html", DEFAULT_GUIDELINES_HTML)})

@app.route('/api/guidelines', methods=['PUT'])
@require_permission('can_reset_program')
def update_guidelines():
    data = request.get_json() or {}
    html = data.get('html')
    if not isinstance(html, str) or not html.strip():
        return jsonify({"error": "html is required"}), 400
    if len(html) > MAX_GUIDELINES_HTML_LENGTH:
        return jsonify({"error": "Guidelines content is too long"}), 400

    db = get_db()
    org_id = current_organization_oid()
    db.settings.update_one({"organization_id": org_id}, {"$set": {"guidelines_html": sanitize_basic_html(html)}}, upsert=True)
    return jsonify({"message": "Guidelines updated", "html": db.settings.find_one({"organization_id": org_id})["guidelines_html"]})
