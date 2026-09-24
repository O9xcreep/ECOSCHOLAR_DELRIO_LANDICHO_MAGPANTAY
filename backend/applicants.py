# -*- coding: utf-8 -*-
"""Applicant CRUD/list, application submission, status updates, student-facing
application view/withdraw, and the reporting routes (stats/history-log/audit-
trail)."""
import re
from datetime import datetime
from flask import request, jsonify, g

from extensions import app, limiter, get_db, DEBUG
from helpers import oid, iso, derive_city, serialize_applicant, serialize_document, \
    resolve_notify_user_id, create_notification, STATUS_MESSAGES, STATUS_NOTIF_TYPE, \
    get_current_cycle, get_current_cycle_id, is_cycle_open, are_results_visible, \
    ml_education_map, ml_occupation_categories, ml_housing_situations
from auth import require_auth, require_permission, current_organization_oid, is_full_access_role
from documents import get_required_doc_labels, compute_display_status, \
    compute_admin_status, build_status_query_fragment, COMPUTED_STATUSES
from admin_settings import get_hidden_builtin_fields
from ml_scoring import build_score_breakdown

def serialize_audit_entry(a):
    return {
        "action": a.get('action'),
        "performed_by": a.get('performed_by'),
        "performed_by_role": a.get('performed_by_role'),
        "old_status": a.get('old_status'),
        "new_status": a.get('new_status'),
        "remarks": a.get('remarks'),
        "performed_at": iso(a.get('performed_at')),
    }

# ── GET ALL APPLICANTS ──
# `page` is opt-in: omitting it returns every applicant, since Dashboard/
# Reports/Ranking need the full set for their own aggregation. Passing `page`
# switches to server-side search/filter/pagination for the Applicants list.
@app.route('/api/applicants', methods=['GET'])
@require_permission('can_review_applicants')
def get_applicants():
    try:
        db = get_db()
        org_id = current_organization_oid()
        page_param = request.args.get('page')
        # Opt-in, not opt-out: defaults to every cycle ever, so callers that don't
        # pass cycle=current (Reports, CSV export) keep seeing the full history.
        # Only the live Applications queue asks for cycle=current.
        base_query = {"organization_id": org_id}
        if request.args.get('cycle') == 'current':
            base_query["cycle_id"] = get_current_cycle_id(db, org_id)
        # A withdrawn-then-resubmitted applicant leaves an old Withdrawn record
        # behind, linked via superseded_by (set in submit_application). Hide it
        # from the live queue by default so it doesn't show up twice; opt-in
        # via include_superseded=true for callers that want the full history.
        if request.args.get('include_superseded') != 'true':
            base_query["application.superseded_by"] = {"$exists": False}

        required_labels = get_required_doc_labels(db, org_id)

        def serialize_with_status(doc):
            flat = serialize_applicant(doc)
            flat['application_status'] = compute_admin_status(doc, required_labels)
            return flat

        if page_param is None:
            applicants = [serialize_with_status(a) for a in db.applicants.find(base_query)]
            return jsonify({"applicants": applicants})

        try:
            page = max(1, int(page_param))
        except ValueError:
            return jsonify({"error": "page must be a number"}), 400
        try:
            limit = min(100, max(1, int(request.args.get('limit', 20))))
        except ValueError:
            return jsonify({"error": "limit must be a number"}), 400

        query = dict(base_query)
        status_param = request.args.get('status')
        statuses = None
        if status_param and status_param != 'All':
            # Comma-separated so a tab can mean "any of these statuses"
            # without matching every status in the system.
            statuses = [s.strip() for s in status_param.split(',') if s.strip()]

        q = (request.args.get('q') or '').strip()
        if q:
            pattern = {"$regex": re.escape(q), "$options": "i"}
            query['$or'] = [{"full_name": pattern}, {"academic.course": pattern}]

        # Whitelisted so `sort` can't be used to inject an arbitrary field path.
        # A leading "-" means descending (e.g. "-submitted_at" = newest first).
        SORT_FIELD_MAP = {
            'submitted_at': 'application.submitted_at',
            'gpa': 'academic.gpa',
            'ml_score': 'ml_score',
            'full_name': 'full_name',
        }
        sort_param = (request.args.get('sort') or '').strip()
        sort_field, sort_dir = 'created_at', -1
        if sort_param:
            direction = -1 if sort_param.startswith('-') else 1
            key = sort_param.lstrip('-')
            if key not in SORT_FIELD_MAP:
                return jsonify({"error": f"sort must be one of {sorted(SORT_FIELD_MAP)} (optionally prefixed with -)"}), 400
            sort_field, sort_dir = SORT_FIELD_MAP[key], direction

        # "Pending Verification"/"Incomplete"/"Newly Submitted" are computed from
        # document completeness, not a stored field, so Mongo can't filter or
        # count them directly. Fall back to fetching raw "Newly Submitted"
        # matches and filter/sort/paginate in Python instead.
        if statuses and (set(statuses) & COMPUTED_STATUSES):
            raw_statuses_needed = sorted({
                'Newly Submitted' if s in COMPUTED_STATUSES else s
                for s in statuses
            })
            py_query = dict(query)
            py_query['application.status'] = raw_statuses_needed[0] if len(raw_statuses_needed) == 1 else {'$in': raw_statuses_needed}

            def sort_key(doc):
                val = doc
                for part in sort_field.split('.'):
                    val = (val or {}).get(part) if isinstance(val, dict) else None
                return (val is None, val)

            matched = [
                (doc, disp) for doc in db.applicants.find(py_query)
                if (disp := compute_admin_status(doc, required_labels)) in statuses
            ]
            matched.sort(key=lambda pair: sort_key(pair[0]), reverse=(sort_dir == -1))

            total = len(matched)
            start = (page - 1) * limit
            page_slice = matched[start:start + limit]
            applicants = []
            for doc, disp in page_slice:
                flat = serialize_applicant(doc)
                flat['application_status'] = disp
                applicants.append(flat)

            return jsonify({
                "applicants": applicants,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": max(1, (total + limit - 1) // limit),
            })

        if statuses:
            status_fragment = build_status_query_fragment(statuses)
            if '$or' in status_fragment and '$or' in query:
                # Both the search box and the status split want the top-level
                # $or slot; combine with $and instead of one clobbering the other.
                query['$and'] = [{'$or': query.pop('$or')}, status_fragment]
            else:
                query.update(status_fragment)

        total = db.applicants.count_documents(query)
        cursor = db.applicants.find(query).sort(sort_field, sort_dir).skip((page - 1) * limit).limit(limit)
        applicants = [serialize_with_status(doc) for doc in cursor]

        return jsonify({
            "applicants": applicants,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": max(1, (total + limit - 1) // limit),
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── EXPORT ALL APPLICANTS ──
# Feeds Settings -> System's Data Export, which anyone who can manage the
# program may use even without can_review_applicants (that permission gates the
# Applications/Ranking pages, not this). Same rows as an unpaginated
# GET /api/applicants: every cycle, minus superseded withdrawn records.
@app.route('/api/applicants/export', methods=['GET'])
@require_permission('can_reset_program')
def export_applicants():
    try:
        db = get_db()
        org_id = current_organization_oid()
        required_labels = get_required_doc_labels(db, org_id)
        applicants = []
        for doc in db.applicants.find({"organization_id": org_id, "application.superseded_by": {"$exists": False}}):
            flat = serialize_applicant(doc)
            flat['application_status'] = compute_admin_status(doc, required_labels)
            applicants.append(flat)
        return jsonify({"applicants": applicants})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── APPLICANT TAB/BADGE COUNTS (ALL AT ONCE) ── returns per-tab counts for the
# Applications page in one query pass, instead of one request per tab (three
# of which would otherwise each re-fetch and recompute the same status pool).
@app.route('/api/applicants/status-counts', methods=['GET'])
@require_permission('can_review_applicants')
def applicant_status_counts():
    try:
        db = get_db()
        org_id = current_organization_oid()
        base_query = {"organization_id": org_id}
        if request.args.get('cycle') == 'current':
            base_query["cycle_id"] = get_current_cycle_id(db, org_id)
        # A withdrawn-then-resubmitted applicant leaves an old Withdrawn record
        # behind, linked via superseded_by (set in submit_application). Hide it
        # from the live queue by default so it doesn't show up twice; opt-in
        # via include_superseded=true for callers that want the full history.
        if request.args.get('include_superseded') != 'true':
            base_query["application.superseded_by"] = {"$exists": False}

        required_labels = get_required_doc_labels(db, org_id)

        counts = {s: 0 for s in COMPUTED_STATUSES}
        newly_submitted_query = dict(base_query, **{"application.status": "Newly Submitted"})
        for doc in db.applicants.find(newly_submitted_query, {"documents": 1, "application": 1}):
            counts[compute_admin_status(doc, required_labels)] += 1

        for status in ("Waitlisted", "Approved", "Rejected", "Withdrawn"):
            status_query = dict(base_query, **build_status_query_fragment([status]))
            counts[status] = db.applicants.count_documents(status_query)

        counts["All"] = sum(counts.values())
        return jsonify(counts)
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET SINGLE APPLICANT ──
@app.route('/api/applicants/<applicant_id>', methods=['GET'])
@require_permission('can_review_applicants')
def get_applicant(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        org_id = current_organization_oid()
        doc = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
        if not doc:
            return jsonify({"applicant": None, "academic": None, "documents": [], "application": None})

        flat = serialize_applicant(doc)
        flat['application_status'] = compute_admin_status(doc, get_required_doc_labels(db, org_id))
        return jsonify({
            "applicant": flat,
            "academic": doc.get('academic'),
            "documents": [serialize_document(d) for d in doc.get('documents', [])],
            "application": doc.get('application')
        })
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SUBMIT APPLICATION ──
@app.route('/api/apply', methods=['POST'])
@require_auth
@limiter.limit("10 per minute")
def submit_application():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data received"}), 400

    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        db = get_db()
        org_id = current_organization_oid()
        current_cycle = get_current_cycle(db, org_id)
        current_cycle_id = current_cycle["_id"] if current_cycle else None

        # An org must explicitly start a scholarship program (Settings -> System)
        # before students can apply; current_cycle is None until that happens, and
        # a brand-new org has nothing open until an admin starts one. A cycle with
        # no deadline stays open indefinitely; a past deadline closes it automatically.
        if not is_cycle_open(current_cycle):
            return jsonify({"error": "No scholarship program is currently open."}), 403

        # ── Check duplicate by EMAIL ──
        # Scoped to the current cycle only, so a program reset lets someone who
        # applied in a past archived cycle apply again. Reused document/photo
        # detection (in upload_document) separately catches reapplication under a
        # new identity, and stays cross-cycle. Withdrawn applications never count
        # as the blocking duplicate, since withdrawing frees the applicant to
        # resubmit in the same cycle.
        existing = db.applicants.find_one({
            "email": email, "cycle_id": current_cycle_id, "application.status": {"$ne": "Withdrawn"},
            "organization_id": org_id,
        })
        duplicate_reason = 'email' if existing else None

        # ── Check duplicate by FULL NAME + DATE OF BIRTH ──
        if not existing:
            full_name = data.get('fullName', '').strip()
            dob = data.get('dob', '').strip()
            if full_name and dob:
                existing = db.applicants.find_one({
                    "full_name": {"$regex": f"^{re.escape(full_name)}$", "$options": "i"},
                    "date_of_birth": dob,
                    "cycle_id": current_cycle_id,
                    "application.status": {"$ne": "Withdrawn"},
                    "organization_id": org_id,
                })
                if existing:
                    duplicate_reason = 'name_and_birthdate'

        if existing:
            existing_app = {
                "id": str(existing['_id']),
                "application_status": (existing.get('application') or {}).get('status'),
                "ml_status": existing.get('ml_status'),
                "submitted_at": iso((existing.get('application') or {}).get('submitted_at')),
                "course": (existing.get('academic') or {}).get('course'),
                "gpa": (existing.get('academic') or {}).get('gpa'),
            }
            try:
                db.duplicate_flags.insert_one({
                    "applicant_id": existing['_id'],
                    "duplicate_of_id": existing['_id'],
                    "reason": duplicate_reason,
                    "flagged_at": datetime.utcnow(),
                    "resolved": False,
                    "organization_id": org_id,
                })
            except Exception:
                pass

            return jsonify({
                "error": "A duplicate application was detected.",
                "duplicate_reason": duplicate_reason,
                "existing_application": existing_app
            }), 409

        # religion/citizenship drop out if this LGU has hidden them
        # (see HIDEABLE_BUILTIN_FIELDS / hidden_builtin_fields).
        hidden_builtin = get_hidden_builtin_fields(db, org_id)
        required_fields = [
            'fullName', 'email', 'contactNumber', 'address',
            'gender', 'dob', 'religion', 'citizenship',
            'fatherName', 'fatherOccupation', 'fatherEducation',
            'motherName', 'motherOccupation', 'motherEducation',
            'monthlyIncome', 'familySize', 'numSiblings', 'numSiblingsStudying',
            'housingSituation',
            'school', 'schoolAddress', 'course',
            'yearLevel', 'gpa', 'academicYear', 'semester'
        ]
        required_fields = [f for f in required_fields if f not in hidden_builtin]
        for field in required_fields:
            if data.get(field) in (None, ''):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Custom (LGU-defined) extra fields; required ones must be present.
        # These never feed build_feature_row/the ML model.
        submitted_extra = data.get('extraFields') or {}
        custom_fields = list(db.form_fields.find({"enabled": True, "organization_id": org_id}))
        extra_fields_to_store = {}
        for cf in custom_fields:
            value = submitted_extra.get(cf['key'], '')
            if cf.get('required') and value in (None, '', []):
                return jsonify({"error": f"Missing required field: {cf['label']}"}), 400
            extra_fields_to_store[cf['key']] = value

        if data['gender'] not in ('Male', 'Female'):
            return jsonify({"error": "Gender must be Male or Female"}), 400
        if data['fatherEducation'] not in ml_education_map or data['motherEducation'] not in ml_education_map:
            return jsonify({"error": "Invalid education level"}), 400
        if data['fatherOccupation'] not in ml_occupation_categories or data['motherOccupation'] not in ml_occupation_categories:
            return jsonify({"error": "Invalid occupation category"}), 400
        if data['housingSituation'] not in ml_housing_situations:
            return jsonify({"error": "Invalid housing situation"}), 400

        has_other = data.get('hasOtherScholarship', 'no') == 'yes'
        other_details = data.get('otherScholarshipDetails', '')
        now = datetime.utcnow()

        applicant_doc = {
            "user_id": oid(g.current_user['id']),
            "cycle_id": current_cycle_id,
            "full_name": data['fullName'],
            "email": email,
            "contact_number": data['contactNumber'],
            "address": data['address'],
            "gender": data['gender'],
            "date_of_birth": data['dob'],
            "religion": data.get('religion', ''),
            "citizenship": data.get('citizenship', ''),
            "father_name": data['fatherName'],
            "father_occupation": data['fatherOccupation'],
            "father_education": data['fatherEducation'],
            "mother_name": data['motherName'],
            "mother_occupation": data['motherOccupation'],
            "mother_education": data['motherEducation'],
            "monthly_income": float(data['monthlyIncome']),
            "family_size": int(data['familySize']),
            "num_siblings": int(data['numSiblings']),
            "num_siblings_studying": int(data['numSiblingsStudying']),
            "housing_situation": data['housingSituation'],
            "barangay": None,
            "ml_score": 0,
            "ml_status": "Pending",
            "created_at": now,
            "privacy_consent": True,
            "has_other_scholarship": has_other,
            "other_scholarship_details": other_details,
            "academic": {
                "school": data['school'],
                "school_address": data['schoolAddress'],
                "course": data['course'],
                "year_level": data['yearLevel'],
                "gpa": float(data['gpa']),
                "academic_year": data['academicYear'],
                "semester": data['semester'],
            },
            "application": {
                "application_type": data.get('applicationType', 'General'),
                "status": "Newly Submitted",
                "submitted_at": now,
                "reviewed_at": None,
                "reviewed_by_name": None,
                "remarks": None,
            },
            "documents": [],
            "audit_trail": [],
            "extra_fields": extra_fields_to_store,
            "organization_id": org_id,
        }

        result = db.applicants.insert_one(applicant_doc)

        # Link any old Withdrawn record(s) for this same person/cycle to the new
        # one, so the live Applications queue (get_applicants/applicant_status_counts)
        # can hide the superseded record instead of showing the same applicant
        # twice - once Withdrawn under Decided, once fresh under Needs Attention.
        # Nothing is deleted; superseded_by is purely a display-time filter.
        db.applicants.update_many(
            {
                "email": email,
                "cycle_id": current_cycle_id,
                "organization_id": org_id,
                "application.status": "Withdrawn",
                "_id": {"$ne": result.inserted_id},
            },
            {"$set": {"application.superseded_by": result.inserted_id}}
        )

        return jsonify({
            "message": "Application submitted successfully!",
            "applicant_id": str(result.inserted_id)
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── UPDATE APPLICATION STATUS ──
@app.route('/api/applications/<applicant_id>/status', methods=['PUT'])
@require_permission('can_review_applicants')
def update_status(applicant_id):
    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    data = request.get_json()
    status = data.get('status')
    reviewed_by = g.current_user.get('email', 'Admin')
    old_status = data.get('old_status', '')
    remarks = data.get('remarks', '')

    if not status:
        return jsonify({"error": "Status is required"}), 400

    if status in ('Approved', 'Rejected'):
        return jsonify({
            "error": "Approval/rejection is decided by the eligibility model, not set manually. "
                     "Use the verify-documents action instead."
        }), 400

    notif_message = STATUS_MESSAGES.get(status, f"Your application status was updated to '{status}'.")
    notif_type = STATUS_NOTIF_TYPE.get(status, 'status_update')

    try:
        db = get_db()
        now = datetime.utcnow()

        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": current_organization_oid()})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        if (applicant.get('application') or {}).get('status') == 'Withdrawn':
            return jsonify({"error": "This application was withdrawn by the applicant and can't be modified."}), 400

        db.applicants.update_one(
            {"_id": applicant_oid},
            {
                "$set": {
                    "application.status": status,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Status changed to {status}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "admin",
                        "old_status": old_status,
                        "new_status": status,
                        "remarks": remarks,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        create_notification(db, notify_user_id, applicant, notif_message, notif_type)

        return jsonify({
            "message": f"Application {status} successfully",
            "applicant_id": applicant_id,
            "status": status,
            "reviewed_by": reviewed_by
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── REQUEST CHANGES (pre-verification: docs missing/unclear) ──
# Distinct from Verify: used when an admin decides documents are NOT ready to
# be scored yet; never touches ml_score/ml_status. Reuses the Withdrawn status
# (same mechanism as a student's own withdraw) to get the same "student can
# freely resubmit, exempt from duplicate-detection" behavior. admin_comment is
# what tells the two apart on display.
@app.route('/api/applications/<applicant_id>/request-changes', methods=['PUT'])
@require_permission('can_review_applicants')
def request_changes(applicant_id):
    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    data = request.get_json() or {}
    comment = (data.get('comment') or '').strip()
    if not comment:
        return jsonify({"error": "A comment is required so the applicant knows what to fix."}), 400

    reviewed_by = g.current_user.get('email', 'Admin')

    try:
        db = get_db()
        now = datetime.utcnow()

        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": current_organization_oid()})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        old_status = (applicant.get('application') or {}).get('status')
        if old_status in ('Approved', 'Rejected', 'Withdrawn'):
            return jsonify({"error": f"Can't request changes on an application that's already {old_status}."}), 400

        db.applicants.update_one(
            {"_id": applicant_oid},
            {
                "$set": {
                    "application.status": "Withdrawn",
                    "application.admin_comment": comment,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                },
                "$push": {
                    "audit_trail": {
                        "action": "Changes requested",
                        "performed_by": reviewed_by,
                        "performed_by_role": "admin",
                        "old_status": old_status,
                        "new_status": "Withdrawn",
                        "remarks": comment,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        create_notification(
            db, notify_user_id, applicant,
            f"An admin has requested changes to your application: {comment} "
            "Please update your documents and resubmit.",
            'changes_requested'
        )

        return jsonify({
            "message": "Changes requested",
            "applicant_id": applicant_id,
            "status": "Withdrawn",
            "admin_comment": comment,
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET AUDIT TRAIL ──
@app.route('/api/audit-trail/<applicant_id>', methods=['GET'])
@require_permission('can_review_applicants')
def get_audit_trail(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": current_organization_oid()}, {"audit_trail": 1})
        trail = (applicant or {}).get('audit_trail', [])
        trail = sorted(trail, key=lambda t: t.get('performed_at') or datetime.min, reverse=True)
        return jsonify({"trail": [serialize_audit_entry(t) for t in trail]})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET STUDENT APPLICATION BY EMAIL ──
@app.route('/api/student/application', methods=['GET'])
@require_auth
def get_student_application():
    email = request.args.get('email')

    if not email:
        return jsonify({"error": "Email is required"}), 400

    if not is_full_access_role(g.current_user.get('role')) and email.strip().lower() != g.current_user.get('email', '').lower():
        return jsonify({"error": "Forbidden"}), 403

    try:
        db = get_db()
        org_id = current_organization_oid()
        query = {"email": email.strip().lower(), "organization_id": org_id}
        # A student only sees their CURRENT cycle's application here; once a
        # reset closes their old cycle this goes back to "No Application Found"
        # so they can start fresh. Admins bypass this since they need to look up
        # a student's latest record regardless of cycle.
        if not is_full_access_role(g.current_user.get('role')):
            query["cycle_id"] = get_current_cycle_id(db, org_id)
        applicant = db.applicants.find_one(query, sort=[("_id", -1)])

        # Lets the student dashboard/application form know whether a program is
        # currently open, even before they have an application of their own.
        current_cycle = get_current_cycle(db, org_id)
        current_cycle_info = {
            "label": current_cycle.get("label") if current_cycle else None,
            "deadline": iso(current_cycle.get("deadline")) if current_cycle else None,
            "is_open": is_cycle_open(current_cycle),
        }

        if not applicant:
            return jsonify({"application": None, "current_cycle": current_cycle_info})

        application = serialize_applicant(applicant)
        # Same document-completeness computation admins see in the Applications
        # queue; only changes a raw "Newly Submitted" display, so it can't
        # collide with the Approved/Rejected masking step below.
        if application['application_status'] == 'Newly Submitted':
            application['application_status'] = compute_display_status(applicant, get_required_doc_labels(db, org_id))
        # Only mask for the applicant viewing their own record; admins always
        # see the real decision, same as every other admin-facing route.
        if not is_full_access_role(g.current_user.get('role')) and application['application_status'] in ('Approved', 'Rejected'):
            if not are_results_visible(db, org_id):
                application['application_status'] = 'Pending Verification'
                application['ml_status'] = 'Pending'
                application['ml_score'] = 0
                application['rejection_reason'] = None
                application['reviewed_at'] = None
                application['reviewed_by_name'] = None

        # Same per-factor bars admins see, but only once a decision is out
        # (the masking above has already hidden undisclosed results).
        application['score_breakdown'] = (
            build_score_breakdown(applicant)
            if application['application_status'] in ('Approved', 'Rejected') else None
        )

        return jsonify({
            "application": application,
            "documents": [serialize_document(d) for d in applicant.get('documents', [])],
            "current_cycle": current_cycle_info,
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── WITHDRAW APPLICATION ──
# Students can't edit submitted fields (income, GWA, etc. feed the eligibility
# model; allowing edits would reopen the tampering fraud-detection guards
# against). Withdrawing sets a status rather than deleting, so the record
# stays visible to admins and in the audit trail; there's no undo. Once the
# eligibility model has scored the application (Approved/Rejected, including
# Waitlisted, stored as Rejected with ml_status Eligible), it can no longer
# be withdrawn either.
@app.route('/api/student/application/withdraw', methods=['PUT'])
@require_auth
def withdraw_application():
    if is_full_access_role(g.current_user.get('role')):
        return jsonify({"error": "Only the applicant can withdraw their own application"}), 403

    email = g.current_user.get('email', '').strip().lower()

    try:
        db = get_db()
        applicant = db.applicants.find_one({"email": email, "organization_id": current_organization_oid()}, sort=[("_id", -1)])
        if not applicant:
            return jsonify({"error": "No application found"}), 404

        current_status = (applicant.get('application') or {}).get('status')
        if current_status == 'Withdrawn':
            return jsonify({"error": "This application has already been withdrawn"}), 400
        if current_status in ('Approved', 'Rejected'):
            return jsonify({"error": "This application has already been scored and can no longer be withdrawn."}), 400

        now = datetime.utcnow()
        db.applicants.update_one(
            {"_id": applicant["_id"]},
            {
                "$set": {
                    "application.status": "Withdrawn",
                    "application.reviewed_at": now,
                },
                "$push": {
                    "audit_trail": {
                        "action": "Application withdrawn by applicant",
                        "performed_by": email,
                        "performed_by_role": "student",
                        "old_status": current_status,
                        "new_status": "Withdrawn",
                        "remarks": "Withdrawn by the applicant.",
                        "performed_at": now,
                    }
                }
            }
        )
        return jsonify({"message": "Application withdrawn"})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET DASHBOARD STATS ──
@app.route('/api/stats', methods=['GET'])
@require_permission('can_review_applicants')
def get_stats():
    try:
        db = get_db()
        org_id = current_organization_oid()
        base = {"organization_id": org_id}
        if request.args.get('cycle') == 'current':
            base["cycle_id"] = get_current_cycle_id(db, org_id)
        total = db.applicants.count_documents(base)
        approved = db.applicants.count_documents({**base, "application.status": "Approved"})
        rejected = db.applicants.count_documents({**base, "application.status": "Rejected"})
        withdrawn = db.applicants.count_documents({**base, "application.status": "Withdrawn"})
        under_review = total - approved - rejected - withdrawn

        return jsonify({
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "withdrawn": withdrawn,
            "under_review": under_review
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SYSTEM-WIDE DECISION HISTORY LOG (for the admin dashboard) ──
@app.route('/api/history-log', methods=['GET'])
@require_permission('can_review_applicants')
def get_history_log():
    try:
        limit = min(max(int(request.args.get('limit', 20)), 1), 100)
        db = get_db()
        pipeline = [
            {"$match": {"organization_id": current_organization_oid()}},
            {"$unwind": "$audit_trail"},
            {"$match": {"audit_trail.new_status": {"$in": ["Approved", "Rejected"]}}},
            {"$sort": {"audit_trail.performed_at": -1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "applicant_id": {"$toString": "$_id"},
                "full_name": "$full_name",
                "address": "$address",
                "course": "$academic.course",
                "old_status": "$audit_trail.old_status",
                "new_status": "$audit_trail.new_status",
                "remarks": "$audit_trail.remarks",
                "performed_by": "$audit_trail.performed_by",
                "performed_by_role": "$audit_trail.performed_by_role",
                "performed_at": "$audit_trail.performed_at",
            }},
        ]
        results = list(db.applicants.aggregate(pipeline))
        history = []
        for r in results:
            new_status = r.get("new_status")
            # A "Rejected" entry from the automatic limit re-rank means this
            # applicant was eligible but bumped by a higher-ranked one, so
            # "Waitlisted" is a more accurate admin-facing label.
            display_status = (
                'Waitlisted' if new_status == 'Rejected' and r.get('performed_by_role') == 'system'
                else new_status
            )
            history.append({
                "applicant_id": r["applicant_id"],
                "full_name": r.get("full_name"),
                "city": derive_city(r.get("address")),
                "course": r.get("course"),
                "old_status": r.get("old_status"),
                "new_status": new_status,
                "display_status": display_status,
                "remarks": r.get("remarks"),
                "performed_by": r.get("performed_by"),
                "performed_at": iso(r.get("performed_at")),
            })
        return jsonify({"history": history})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500
