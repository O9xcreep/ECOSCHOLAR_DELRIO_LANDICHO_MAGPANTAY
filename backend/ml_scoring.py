# -*- coding: utf-8 -*-
"""ML model loading, feature building/scoring, the eligibility decision
routes, and recompute_approvals (also used by admin_settings.py and
helpers.py's do_program_reset)."""
from datetime import datetime
from flask import request, jsonify, g

from extensions import app, get_db, DEBUG
from helpers import oid, EDUCATION_LABEL_FIX, income_to_bracket, STATUS_MESSAGES, \
    STATUS_NOTIF_TYPE, GENERIC_REVIEWED_MESSAGE, get_applicant_limit, are_results_visible, \
    get_current_cycle_id, resolve_notify_user_id, create_notification, ml_education_map, derive_city, \
    get_eligibility_top_percent
from auth import require_permission, current_organization_oid
from documents import get_required_doc_labels, collect_verification_warnings, \
    run_ocr_checks_concurrently, documents_needing_ocr

# ── LOAD ML MODEL (EcoScholar classifier + regressor) ──
# ecoscholar_predict.py loads its .joblib/.json files at import time; a missing
# or corrupt model file is caught here so scoring degrades gracefully instead
# of blocking application submission.
try:
    from ecoscholar_predict import score_applicant as _ml_predict, eligibility_cutoff as _eligibility_cutoff, \
        explain_priority_score as _ml_explain
    ml_classifier = True   # sentinel only - the real model objects live inside ecoscholar_predict
    ml_regressor = True
    print("ML model loaded successfully! (EcoScholar classifier + regressor)")
except Exception as e:
    _ml_predict = None
    _eligibility_cutoff = None
    _ml_explain = None
    ml_classifier = None
    ml_regressor = None
    print(f"ML model not loaded: {e}")


def eligibility_cutoff_for(db, org_id):
    """The Total Score an applicant must reach under this LGU's eligibility bar (shown to admins
    for reference)."""
    return round(_eligibility_cutoff(get_eligibility_top_percent(db, org_id)), 2)

# Fields required for the model to score an applicant. Applicants who
# registered before this model was added won't have these and are excluded
# from scoring rather than guessed at.
ML_REQUIRED_FIELDS = [
    'monthly_income', 'housing_situation', 'num_siblings',
    'num_siblings_studying', 'father_education', 'mother_education'
]

def build_feature_row(applicant):
    """Build the flat {field: value} dict ecoscholar_predict.score_applicant()
    expects, mapped from our MongoDB applicant schema. Returns (row, True) or
    (None, False) if this applicant predates the fields the model needs."""
    if any(applicant.get(f) is None for f in ML_REQUIRED_FIELDS):
        return None, False

    academic = applicant.get('academic') or {}
    father_edu = applicant.get('father_education')
    mother_edu = applicant.get('mother_education')
    row = {
        'sex': applicant.get('gender'),
        'household_size': applicant.get('family_size'),
        'siblings': applicant.get('num_siblings'),
        'siblings_studying': applicant.get('num_siblings_studying'),
        'father_education': EDUCATION_LABEL_FIX.get(father_edu, father_edu),
        'mother_education': EDUCATION_LABEL_FIX.get(mother_edu, mother_edu),
        'father_occupation': applicant.get('father_occupation'),
        'mother_occupation': applicant.get('mother_occupation'),
        'monthly_income_bracket': income_to_bracket(applicant.get('monthly_income')),
        'housing_situation': applicant.get('housing_situation'),
        'gwa': academic.get('gpa'),
        'holds_other_scholarship': bool(applicant.get('has_other_scholarship')),
    }
    return row, True

def score_with_model(row, top_percent=None):
    """Run the trained EcoScholar classifier (eligibility, at the given eligibility bar -
    default: the trained default) and regressor (ranking score) on a feature row built by
    build_feature_row(). Returns (ml_score, ml_status)."""
    ml_score, ml_status, _ = score_with_model_detailed(row, top_percent)
    return ml_score, ml_status

def score_with_model_detailed(row, top_percent=None):
    """score_with_model() plus the classifier's eligibility probability, as a
    0-100 percentage, for the admin score card. Returns (ml_score, ml_status,
    eligibility_probability)."""
    result = _ml_predict(row, top_percent)
    ml_status = 'Eligible' if result['eligible'] else 'Not Eligible'
    return result['priority_score'], ml_status, round(result['eligibility_probability'] * 100, 1)

# Groups the model's input columns into the factors shown to admins and
# students; paired columns (both parents, household size + siblings in school)
# are summed since students answer about them together.
BREAKDOWN_FACTORS = [
    ("Household income", ["Income_Num"]),
    ("Other scholarships held", ["Holds_Other_Scholarship"]),
    ("Academic standing (GWA)", ["GWA Numeric"]),
    ("Family size & siblings in school", ["Household_Size_Num", "Siblings_Studying_Num"]),
    ("Housing situation", ["HousingPrecarity"]),
    ("Parents' occupation", ["FatherOccNeed", "MotherOccNeed"]),
    ("Parents' education", ["Father_Edu_Ord", "Mother_Edu_Ord"]),
    ("Sex", ["Sex_Bin"]),
]

def build_score_breakdown(applicant):
    """How far each factor moved this applicant's ML score above or below the
    average (training-set) applicant, taken straight from the regressor's
    trees, so baseline + sum(points) equals ml_score. None if the applicant
    can't be scored (pre-model record, or the model failed to load)."""
    row, ok = build_feature_row(applicant)
    if not ok or _ml_explain is None:
        return None
    explained = _ml_explain(row)
    contributions = explained['contributions']
    factors = [
        {"label": label, "points": round(sum(contributions.get(c, 0.0) for c in cols), 2)}
        for label, cols in BREAKDOWN_FACTORS
    ]
    factors.sort(key=lambda f: abs(f['points']), reverse=True)
    return {"baseline": round(explained['baseline'], 2), "factors": factors}

# Plain-language reason for each factor when it pulled the score down.
REJECTION_REASON_TEXT = {
    "Household income": "household income was higher than typical for approved applicants",
    "Other scholarships held": "the applicant already holds another scholarship",
    "Academic standing (GWA)": "academic performance (GWA) was below the typical level for approved applicants",
    "Family size & siblings in school": "household size and number of siblings in school showed less financial burden than typical for approved applicants",
    "Housing situation": "housing situation showed less financial need than typical for approved applicants",
    "Parents' occupation": "parents' occupations showed less financial need than typical for approved applicants",
    "Parents' education": "parents' education level indicated comparatively lower financial need",
    "Sex": "applicant profile",
}

def generate_rejection_reason(breakdown):
    """Names the (up to two) factors that pulled the ML score down the most."""
    factors = (breakdown or {}).get('factors') or []
    weakest = [f for f in sorted(factors, key=lambda f: f['points']) if f['points'] < 0 and f['label'] != 'Sex'][:2]
    if not weakest:
        return "Primary factors: the overall combination of financial-need indicators was below this cycle's eligibility bar."
    reasons = [REJECTION_REASON_TEXT.get(f['label'], f['label']) for f in weakest]
    return "Primary factors: " + "; and ".join(reasons) + "."

def recompute_approvals(db, org_id, limit, reviewed_by='System'):
    """Keeps 'Approved' as exactly the top-`limit` applicants (by ml_score)
    among everyone the classifier found Eligible in the current cycle. Run
    after every verify decision and whenever the limit changes, since either
    can promote or bump applicants not directly touched by that action.
    Scoped to the current cycle so it never touches an archived cycle."""
    eligible = list(db.applicants.find(
        # Withdrawn applicants can still carry ml_status "Eligible" from a
        # prior verification; excluded so recompute never reinstates them.
        {"ml_status": "Eligible", "application.status": {"$ne": "Withdrawn"},
         "cycle_id": get_current_cycle_id(db, org_id), "organization_id": org_id},
        {"ml_score": 1, "application": 1, "full_name": 1, "email": 1, "user_id": 1}
    ))
    eligible.sort(key=lambda a: a.get('ml_score', 0), reverse=True)

    now = datetime.utcnow()
    results_visible = are_results_visible(db, org_id)
    for i, applicant in enumerate(eligible):
        should_be = 'Approved' if i < limit else 'Rejected'
        current = (applicant.get('application') or {}).get('status')
        if current == should_be:
            continue

        if should_be == 'Approved':
            remarks = f'A scholarship slot became available (applicant limit: {limit}).'
            notif_message = (STATUS_MESSAGES['Approved'] + ' ' + remarks) if results_visible else GENERIC_REVIEWED_MESSAGE
        else:
            remarks = (
                f'This applicant met the eligibility criteria, but the accepted applicant '
                f'limit ({limit}) was reached by higher-ranked applicants.'
            )
            notif_message = (
                f'Your application met the eligibility criteria, but the accepted applicant '
                f'limit ({limit}) has been reached by higher-ranked applicants. You have been '
                f'waitlisted and may be promoted automatically if a slot opens up.'
            ) if results_visible else GENERIC_REVIEWED_MESSAGE

        db.applicants.update_one(
            {"_id": applicant["_id"]},
            {
                "$set": {
                    "application.status": should_be,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                    "application.rejection_reason": remarks if should_be == 'Rejected' else None,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Auto re-ranked due to applicant limit - now {should_be}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "system",
                        "old_status": current,
                        "new_status": should_be,
                        "remarks": remarks,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        create_notification(
            db, notify_user_id, applicant,
            notif_message, STATUS_NOTIF_TYPE[should_be]
        )

def reapply_eligibility_bar(db, org_id, reviewed_by='Admin'):
    """Re-decides eligibility for everyone already decided in the current cycle after the LGU
    changes its eligibility bar, so every applicant in a cycle is judged by the same bar, then
    re-ranks the eligible pool against the applicant limit. Returns how many applicants moved
    each way."""
    top_percent = get_eligibility_top_percent(db, org_id)
    now = datetime.utcnow()
    results_visible = are_results_visible(db, org_id)
    decided = list(db.applicants.find({
        "ml_status": {"$in": ["Eligible", "Not Eligible"]},
        "application.status": {"$ne": "Withdrawn"},
        "cycle_id": get_current_cycle_id(db, org_id), "organization_id": org_id,
    }))

    newly_eligible, newly_ineligible = [], 0
    for applicant in decided:
        row, ok = build_feature_row(applicant)
        if not ok:
            continue
        ml_score, ml_status = score_with_model(row, top_percent)
        if ml_status == applicant.get('ml_status'):
            continue
        old_status = (applicant.get('application') or {}).get('status')

        if ml_status == 'Not Eligible':
            reason = generate_rejection_reason(build_score_breakdown(applicant))
            remarks = f'The eligibility bar changed to the top {top_percent}% of need, which this application no longer meets. {reason}'
            update = {"ml_score": ml_score, "ml_status": ml_status,
                      "application.status": 'Rejected', "application.reviewed_at": now,
                      "application.reviewed_by_name": reviewed_by, "application.rejection_reason": reason}
            # role "admin": a system-role Rejected entry is shown as "Waitlisted" in the history
            entry_role, new_status = 'admin', 'Rejected'
            newly_ineligible += 1
        else:
            remarks = f'The eligibility bar changed to the top {top_percent}% of need, which this application now meets.'
            update = {"ml_score": ml_score, "ml_status": ml_status}
            # still Rejected until recompute_approvals() ranks it: shown as "Waitlisted" meanwhile
            entry_role, new_status = 'system', old_status
            newly_eligible.append(applicant['_id'])

        db.applicants.update_one({"_id": applicant["_id"]}, {
            "$set": update,
            "$push": {"audit_trail": {
                "action": f'Eligibility re-decided after the eligibility bar changed - now {ml_status}',
                "performed_by": reviewed_by, "performed_by_role": entry_role,
                "old_status": old_status, "new_status": new_status,
                "remarks": remarks, "performed_at": now,
            }},
        })
        if ml_status == 'Not Eligible':
            message = (STATUS_MESSAGES['Rejected'] + ' ' + remarks) if results_visible else GENERIC_REVIEWED_MESSAGE
            create_notification(db, resolve_notify_user_id(db, applicant), applicant, message,
                                STATUS_NOTIF_TYPE['Rejected'])

    limit = get_applicant_limit(db, org_id)
    recompute_approvals(db, org_id, limit, reviewed_by=reviewed_by)

    # Newly eligible applicants that recompute_approvals() promoted were notified there; the rest
    # stay waitlisted, which is news to them too.
    for applicant in db.applicants.find({"_id": {"$in": newly_eligible}, "application.status": 'Rejected'}):
        message = (
            f'The program changed its eligibility requirement and your application now meets it, but the '
            f'accepted applicant limit ({limit}) has been reached by higher-ranked applicants. You have been '
            f'waitlisted and may be promoted automatically if a slot opens up.'
        ) if results_visible else GENERIC_REVIEWED_MESSAGE
        create_notification(db, resolve_notify_user_id(db, applicant), applicant, message,
                            STATUS_NOTIF_TYPE['Rejected'])

    return {"now_eligible": len(newly_eligible), "now_not_eligible": newly_ineligible}

def _verify_and_decide_one(db, org_id, applicant_oid, reviewed_by, now):
    """Runs the ML eligibility decision for one applicant; shared by the
    single-applicant and bulk verify routes. Returns (result_dict,
    needs_recompute), where needs_recompute is True when this applicant was
    found Eligible and the accepted-applicant pool must be recomputed.
    Callers processing several applicants should batch that into one
    recompute_approvals() call rather than one per applicant."""
    applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
    if not applicant:
        return {"error": "Applicant not found"}, False

    if (applicant.get('application') or {}).get('status') == 'Withdrawn':
        return {"error": "This application was withdrawn by the applicant and can't be modified."}, False

    # OCR-check every uploaded required document not yet checked (the selfie
    # is compared manually, never OCR'd); results are surfaced as warnings
    # only, since document authenticity is the LGU's call, not an algorithm's.
    required_labels = get_required_doc_labels(db, org_id)
    to_check = documents_needing_ocr(applicant, required_labels)
    run_ocr_checks_concurrently(db, applicant, applicant_oid, to_check, org_id)
    applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
    warnings = collect_verification_warnings(db, applicant, org_id)

    row, ok = build_feature_row(applicant)
    if not ok:
        return {
            "error": "This applicant was submitted before the updated eligibility "
                     "model and can't be auto-decided. Ask them to resubmit using "
                     "the current application form."
        }, False

    ml_score, ml_status, eligibility_probability = score_with_model_detailed(row, get_eligibility_top_percent(db, org_id))
    cutoff = eligibility_cutoff_for(db, org_id)
    old_status = (applicant.get('application') or {}).get('status', '')
    breakdown = build_score_breakdown(applicant)

    if ml_status == 'Not Eligible':
        # Ineligible on the classifier's own terms; rejected outright, the
        # accepted-applicant limit never comes into play here.
        final_status = 'Rejected'
        rejection_reason = generate_rejection_reason(breakdown)
        remarks = f'ML score: {ml_score} ({ml_status}) - {rejection_reason}'

        db.applicants.update_one(
            {"_id": applicant_oid},
            {
                "$set": {
                    "application.status": final_status,
                    "application.reviewed_at": now,
                    "application.reviewed_by_name": reviewed_by,
                    "ml_score": ml_score,
                    "ml_status": ml_status,
                    "application.rejection_reason": rejection_reason,
                },
                "$push": {
                    "audit_trail": {
                        "action": f'Documents verified by admin - model decided: {final_status}',
                        "performed_by": reviewed_by,
                        "performed_by_role": "admin",
                        "old_status": old_status,
                        "new_status": final_status,
                        "remarks": remarks,
                        "performed_at": now,
                    }
                }
            }
        )

        notify_user_id = resolve_notify_user_id(db, applicant)
        notif_message = (STATUS_MESSAGES[final_status] + ' ' + rejection_reason) if are_results_visible(db, org_id) else GENERIC_REVIEWED_MESSAGE
        create_notification(db, notify_user_id, applicant, notif_message, STATUS_NOTIF_TYPE[final_status])
        return {
            "applicant_id": str(applicant_oid), "status": final_status,
            "ml_score": ml_score, "ml_status": ml_status,
            "eligibility_probability": eligibility_probability,
            "regressor_cutoff": cutoff, "breakdown": breakdown,
            "rejection_reason": rejection_reason, "reviewed_by": reviewed_by,
            "warnings": warnings,
        }, False

    # Eligible on its own, but whether it's actually Approved depends on its
    # rank against the accepted applicant limit; left to recompute_approvals().
    db.applicants.update_one(
        {"_id": applicant_oid},
        {"$set": {
            "ml_score": ml_score,
            "ml_status": ml_status,
            "application.reviewed_by_name": reviewed_by,
        }}
    )
    return {
        "applicant_id": str(applicant_oid), "status": None,
        "ml_score": ml_score, "ml_status": ml_status,
        "eligibility_probability": eligibility_probability,
        "regressor_cutoff": cutoff, "breakdown": breakdown,
        "rejection_reason": None, "reviewed_by": reviewed_by,
        "warnings": warnings,
    }, True

# ── VERIFY DOCUMENTS & LET THE MODEL DECIDE ELIGIBILITY ──
@app.route('/api/applications/<applicant_id>/verify', methods=['PUT'])
@require_permission('can_review_applicants')
def verify_and_decide(applicant_id):
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    reviewed_by = g.current_user.get('email', 'Admin')

    try:
        db = get_db()
        org_id = current_organization_oid()
        now = datetime.utcnow()
        result, needs_recompute = _verify_and_decide_one(db, org_id, applicant_oid, reviewed_by, now)
        if "error" in result:
            return jsonify(result), 404 if result["error"] == "Applicant not found" else 409

        if needs_recompute:
            limit = get_applicant_limit(db, org_id)
            recompute_approvals(db, org_id, limit, reviewed_by=reviewed_by)
            applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
            result["status"] = applicant['application']['status']
            result["rejection_reason"] = applicant['application'].get('rejection_reason')

        result["applicant_id"] = applicant_id
        return jsonify(result)

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── BULK VERIFY DOCUMENTS & LET THE MODEL DECIDE ELIGIBILITY ──
@app.route('/api/applications/bulk-verify', methods=['PUT'])
@require_permission('can_review_applicants')
def bulk_verify_and_decide():
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    data = request.get_json() or {}
    ids = data.get('applicant_ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "applicant_ids must be a non-empty list"}), 400
    if len(ids) > 100:
        return jsonify({"error": "Can't process more than 100 applicants at once"}), 400

    reviewed_by = g.current_user.get('email', 'Admin')

    try:
        db = get_db()
        org_id = current_organization_oid()
        now = datetime.utcnow()
        results = []
        any_needs_recompute = False

        for applicant_id in ids:
            applicant_oid = oid(applicant_id)
            if not applicant_oid:
                results.append({"applicant_id": applicant_id, "error": "Invalid applicant id"})
                continue
            result, needs_recompute = _verify_and_decide_one(db, org_id, applicant_oid, reviewed_by, now)
            result["applicant_id"] = applicant_id
            results.append(result)
            any_needs_recompute = any_needs_recompute or needs_recompute

        # Recompute the accepted-applicant pool once at the end rather than
        # per applicant, since it re-evaluates everyone each time it runs.
        if any_needs_recompute:
            limit = get_applicant_limit(db, org_id)
            recompute_approvals(db, org_id, limit, reviewed_by=reviewed_by)
            for r in results:
                if r.get("status") is None and "error" not in r:
                    applicant = db.applicants.find_one({"_id": oid(r["applicant_id"]), "organization_id": org_id})
                    r["status"] = applicant['application']['status']
                    r["rejection_reason"] = applicant['application'].get('rejection_reason')

        succeeded = sum(1 for r in results if "error" not in r)
        return jsonify({"results": results, "succeeded": succeeded, "total": len(ids)})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCORE SINGLE APPLICANT ──
@app.route('/api/score-applicant/<applicant_id>', methods=['GET'])
@require_permission('can_review_applicants')
def score_applicant(applicant_id):
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": current_organization_oid()})

        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        org_id = current_organization_oid()
        # Read-only: never runs OCR (that's "Run OCR Check" / "Start
        # Eligibility") and never saves the score. recompute_approvals() treats
        # any stored ml_status of "Eligible" as officially eligible, so only
        # verify_and_decide may write one.
        warnings = collect_verification_warnings(db, applicant, org_id)

        row, ok = build_feature_row(applicant)
        if not ok:
            return jsonify({
                "error": "This applicant was submitted before the updated eligibility "
                         "model and can't be scored with it. Ask them to resubmit using "
                         "the current application form."
            }), 409

        ml_score, ml_status, eligibility_probability = score_with_model_detailed(row, get_eligibility_top_percent(db, org_id))

        return jsonify({
            "applicant_id": applicant_id,
            "ml_score": ml_score,
            "ml_status": ml_status,
            "eligibility_probability": eligibility_probability,
            "regressor_cutoff": eligibility_cutoff_for(db, org_id),
            "breakdown": build_score_breakdown(applicant),
            "warnings": warnings,
        })

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── SCORE AND RANK ALL APPLICANTS ──
@app.route('/api/rank-applicants', methods=['GET'])
@require_permission('can_review_applicants')
def rank_applicants():
    if not ml_classifier or not ml_regressor:
        return jsonify({"error": "ML model not loaded"}), 500

    try:
        db = get_db()
        org_id = current_organization_oid()
        query = {"application.status": {"$nin": ["Rejected", "Newly Submitted"]}, "organization_id": org_id}
        if request.args.get('cycle') == 'current':
            query["cycle_id"] = get_current_cycle_id(db, org_id)
        applicants = list(db.applicants.find(query))
        top_percent = get_eligibility_top_percent(db, org_id)

        ranked = []
        for applicant in applicants:
            try:
                row, ok = build_feature_row(applicant)
                if not ok:
                    continue  # predates this model

                ml_score, ml_status = score_with_model(row, top_percent)
                academic = applicant.get('academic') or {}

                ranked.append({
                    'id': str(applicant['_id']),
                    'full_name': applicant['full_name'],
                    'city': derive_city(applicant.get('address')),
                    'course': academic.get('course'),
                    'gpa': academic.get('gpa'),
                    'monthly_income': applicant.get('monthly_income'),
                    'family_size': applicant.get('family_size'),
                    'housing_situation': applicant.get('housing_situation'),
                    'has_other_scholarship': bool(applicant.get('has_other_scholarship')),
                    'application_status': (applicant.get('application') or {}).get('status'),
                    'ml_score': ml_score,
                    'ml_status': ml_status
                })
            except Exception:
                continue

        # Sort by ML score descending
        ranked.sort(key=lambda x: x['ml_score'], reverse=True)
        for i, r in enumerate(ranked):
            r['rank'] = i + 1

        return jsonify({"ranked": ranked})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500
