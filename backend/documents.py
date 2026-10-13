# -*- coding: utf-8 -*-
"""Document requirements, status computation, upload/fraud detection, OCR
verification, and duplicate-flag routes."""
import os
import re
import io
import hashlib
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import imagehash
import pdf2image
import pypdf
import gridfs
from PIL import Image
from flask import request, jsonify, g, send_file
from werkzeug.utils import secure_filename

from extensions import app, limiter, get_db, DEBUG, UPLOAD_FOLDER, _fs
from helpers import oid, iso, serialize_document
from auth import require_auth, require_permission, current_organization_oid, has_permission
from ocr import extract_and_verify
from activity import log_activity
from field_crypto import decrypt_field

# ── UPLOAD CONFIG ──
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
# Served Content-Type is always derived from this map, never from client-supplied
# upload metadata (avoids a stored-XSS vector).
SAFE_MIME_TYPES = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_mime_for(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return SAFE_MIME_TYPES.get(ext, 'application/octet-stream')

def compute_perceptual_hash(file_bytes, filename):
    """Visual fingerprint of a document's first page - catches near-identical
    files a byte-for-byte hash would miss. Returns None on any failure."""
    try:
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext == 'pdf':
            pages = pdf2image.convert_from_bytes(file_bytes, dpi=150, first_page=1, last_page=1)
            if not pages:
                return None
            image = pages[0]
        else:
            image = Image.open(io.BytesIO(file_bytes))
        return str(imagehash.phash(image))
    except Exception:
        return None

# Hamming distance (of 64 bits) below which two documents count as a near-duplicate.
NEAR_DUPLICATE_THRESHOLD = 8

# Editing-tool names that shouldn't appear in a scanned form's metadata.
EDITING_TOOL_SIGNATURES = ('photoshop', 'gimp', 'canva', 'illustrator', 'snapseed', 'picsart', 'lightroom')

def extract_metadata_flags(file_bytes, filename):
    """Checks EXIF (images) / Producer-Creator (PDFs) for editing-tool
    signatures. Does not flag missing metadata. Returns a list of flag
    strings, empty if none found."""
    flags = []
    try:
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext == 'pdf':
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            meta = reader.metadata or {}
            producer = f"{meta.get('/Producer') or ''} {meta.get('/Creator') or ''}".strip()
            if producer and any(tool in producer.lower() for tool in EDITING_TOOL_SIGNATURES):
                flags.append(
                    f"PDF metadata shows it was produced/edited with '{producer}', "
                    f"not a scan or form generator - worth a manual check."
                )
        else:
            image = Image.open(io.BytesIO(file_bytes))
            software = image.getexif().get(0x0131, '')  # Software tag
            if software and any(tool in software.lower() for tool in EDITING_TOOL_SIGNATURES):
                flags.append(
                    f"Image metadata shows it was processed with '{software}', "
                    f"suggesting possible editing - worth a manual check."
                )
    except Exception:
        pass
    return flags

# ── DOCUMENT REQUIREMENTS ──
# `label` is the document_name used consistently as storage key, OCR doc_type,
# and display label. SELFIE_DOC_LABEL is uploaded like any other requirement,
# but the frontend shows it separately for manual comparison against the ID
# photo (no automated face-matching).
SELFIE_DOC_LABEL = "Selfie / Face Photo"
ID_DOC_LABEL = "School ID"

DEFAULT_DOC_REQUIREMENTS = [
    {"label": "Enrollment Form", "required": True},
    {"label": "Barangay Endorsement", "required": True},
    {"label": ID_DOC_LABEL, "required": True},
    {"label": "Grade 12 Grades", "required": True},
    {"label": "4Ps Certificate", "required": False},
    {"label": "Proof of Income", "required": True},
    {"label": SELFIE_DOC_LABEL, "required": True},
]
# Defaults can be disabled/un-required per org, but not deleted.
DEFAULT_DOC_LABELS = {d["label"] for d in DEFAULT_DOC_REQUIREMENTS}

def serialize_doc_requirement(d):
    return {
        "id": str(d["_id"]),
        "label": d.get("label"),
        "required": d.get("required", False),
        "enabled": d.get("enabled", True),
        "order": d.get("order", 0),
        "is_default": d.get("label") in DEFAULT_DOC_LABELS,
    }

# Computed from document-upload completeness, never stored on the applicant
# doc: no docs uploaded -> "Newly Submitted"; some -> "Incomplete"; all ->
# "Pending Verification". Approved/Rejected/Withdrawn pass through unchanged.
COMPUTED_STATUSES = {'Newly Submitted', 'Pending Verification', 'Incomplete'}

def get_doc_requirements_collection(db, org_id):
    """Lazy-seeds the default requirements on first use, per organization."""
    if db.document_requirements.count_documents({"organization_id": org_id}) == 0:
        now = datetime.utcnow()
        db.document_requirements.insert_many([
            {**d, "enabled": True, "order": i, "created_at": now, "organization_id": org_id}
            for i, d in enumerate(DEFAULT_DOC_REQUIREMENTS)
        ])
    elif db.document_requirements.count_documents({"label": SELFIE_DOC_LABEL, "organization_id": org_id}) == 0:
        # Backfill for deployments seeded before the selfie step existed.
        db.document_requirements.insert_one({
            "label": SELFIE_DOC_LABEL,
            "required": True,
            "enabled": True,
            "order": db.document_requirements.count_documents({"organization_id": org_id}),
            "created_at": datetime.utcnow(),
            "organization_id": org_id,
        })
    return db.document_requirements

def get_required_doc_labels(db, org_id):
    return {r['label'] for r in get_doc_requirements_collection(db, org_id).find({"required": True, "enabled": True, "organization_id": org_id})}

def collect_verification_warnings(db, applicant, org_id):
    """Surfaces document/fraud concerns for the LGU to weigh - never blocks
    the ML decision. Returns a list of warning strings, empty if none."""
    warnings = []
    required_labels = get_required_doc_labels(db, org_id)
    uploaded = {d.get('document_name'): d for d in applicant.get('documents', []) if d.get('status') == 'Uploaded'}

    missing = required_labels - uploaded.keys()
    if missing:
        warnings.append(f"Not uploaded: {', '.join(sorted(missing))}")

    # The selfie is never OCR-checked - manually compared against the ID instead.
    for label in sorted(required_labels & uploaded.keys()):
        if label == SELFIE_DOC_LABEL:
            continue
        doc = uploaded[label]
        ocr_status = doc.get('ocr_status')
        if not ocr_status:
            warnings.append(f"'{label}' could not be OCR-checked.")
        elif ocr_status != 'Verified':
            warnings.append(f"'{label}' OCR check came back {ocr_status.lower()}.")
        for flag in doc.get('ocr_flags') or []:
            warnings.append(f"'{label}': {flag}")

    for flag in db.duplicate_flags.find({"applicant_id": applicant['_id'], "resolved": False, "organization_id": org_id}):
        warnings.append(f"Unresolved fraud flag ({flag.get('reason')}) on '{flag.get('document_name', 'this applicant')}'.")

    return warnings

def compute_display_status(doc, required_labels):
    raw = (doc.get('application') or {}).get('status')
    if raw != 'Newly Submitted':
        return raw
    if not required_labels:
        return 'Pending Verification'
    uploaded = {d.get('document_name') for d in doc.get('documents', []) if d.get('status') == 'Uploaded'}
    if not uploaded & required_labels:
        return 'Newly Submitted'
    if required_labels.issubset(uploaded):
        return 'Pending Verification'
    return 'Incomplete'

def compute_admin_status(doc, required_labels):
    """Admin-only layer over compute_display_status(): relabels a
    Rejected-but-Eligible applicant as "Waitlisted". Not used by the
    student-facing endpoint, which must see the raw "Rejected" value."""
    status = compute_display_status(doc, required_labels)
    if status == 'Rejected' and doc.get('ml_status') == 'Eligible':
        return 'Waitlisted'
    return status

def build_status_query_fragment(statuses):
    """Translates display-statuses into a Mongo filter. "Waitlisted" isn't a
    stored value - it's Rejected split by ml_status."""
    other = [s for s in statuses if s not in ('Rejected', 'Waitlisted')]
    clauses = []
    if 'Waitlisted' in statuses:
        clauses.append({"application.status": "Rejected", "ml_status": "Eligible"})
    if 'Rejected' in statuses:
        clauses.append({"application.status": "Rejected", "ml_status": {"$ne": "Eligible"}})
    if other:
        clauses.append({"application.status": other[0] if len(other) == 1 else {"$in": other}})
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}

# ── OCR ──
def compute_ocr_result(applicant, applicant_oid, document_name):
    """Runs OCR + content/fraud checks on one uploaded document. Read-only
    (safe to call from multiple threads). Returns the result dict, or
    {'document_name', 'error': ...} if the file couldn't be read."""
    doc = next((d for d in applicant.get('documents', []) if d.get('document_name') == document_name), None)
    if not doc or not doc.get('gridfs_id'):
        return {"document_name": document_name, "error": "Document not found"}

    try:
        grid_out = _fs.get(doc['gridfs_id'])
    except gridfs.errors.NoFile:
        return {"document_name": document_name, "error": "File not found on server"}

    # OCR needs a real file path - write to a scratch temp file, unique per
    # call so concurrent OCR of the same applicant's documents can't collide.
    ext = os.path.splitext(grid_out.filename)[1] or '.bin'
    safe_doc_name = re.sub(r'[^A-Za-z0-9_-]', '_', document_name)
    temp_path = os.path.join(
        UPLOAD_FOLDER,
        f"temp_verify_{applicant_oid}_{safe_doc_name}_{uuid.uuid4().hex}{ext}"
    )
    with open(temp_path, 'wb') as f:
        f.write(grid_out.read())

    try:
        academic = applicant.get('academic') or {}
        applicant_data = {
            "full_name": applicant.get('full_name', ''),
            "school": academic.get('school', ''),
            "course": academic.get('course', ''),
            "address": decrypt_field(applicant.get('address')) or '',
            "monthly_income": applicant.get('monthly_income'),
            "gpa": academic.get('gpa'),
        }

        _, result = extract_and_verify(temp_path, document_name, applicant_data)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Merge in metadata-forensics flags from upload time.
    result['flags'] = list(result['flags']) + list(doc.get('metadata_flags') or [])
    result['document_name'] = document_name
    return result

def persist_ocr_result(db, applicant_oid, org_id, result):
    """Saves one compute_ocr_result() outcome. No-ops on error."""
    if 'error' in result:
        return
    db.applicants.update_one(
        {"_id": applicant_oid, "documents.document_name": result['document_name'], "organization_id": org_id},
        {"$set": {
            "documents.$.status": "Uploaded",
            "documents.$.ocr_status": result['status'],
            "documents.$.ocr_confidence": result['confidence'],
            "documents.$.ocr_flags": result['flags'],
            "documents.$.ocr_checked_at": datetime.utcnow(),
        }}
    )

def run_ocr_check(db, applicant, applicant_oid, document_name, org_id):
    """Single-document OCR check: compute, then persist. Advisory only,
    never blocks anything."""
    result = compute_ocr_result(applicant, applicant_oid, document_name)
    persist_ocr_result(db, applicant_oid, org_id, result)
    return result

def documents_needing_ocr(applicant, required_labels):
    """Names of uploaded required documents that haven't been OCR-checked
    yet. The selfie is never OCR'd - it's compared manually against the ID."""
    return [
        d['document_name'] for d in applicant.get('documents', [])
        if d.get('document_name') in required_labels and d.get('status') == 'Uploaded'
        and d.get('document_name') != SELFIE_DOC_LABEL and not d.get('ocr_status')
    ]

def run_ocr_checks_concurrently(db, applicant, applicant_oid, document_names, org_id):
    """Runs OCR for several documents in parallel via a thread pool. Each
    result is saved the moment its document finishes, not after the whole
    batch - if the request is killed partway (gunicorn --timeout), the
    documents already done aren't lost and re-OCR'd from scratch."""
    if not document_names:
        return []

    def check_and_save(name):
        result = compute_ocr_result(applicant, applicant_oid, name)
        persist_ocr_result(db, applicant_oid, org_id, result)
        return result

    # Capped at 2 (not 4) - each doc can render up to MAX_PDF_PAGES pages at
    # 200dpi through Tesseract, and 4-way concurrency was exceeding available
    # RAM on a small instance, getting the process OOM-killed mid-request.
    # This is a memory-pressure fix, not a correctness one - don't raise it
    # back without addressing that first.
    with ThreadPoolExecutor(max_workers=min(2, len(document_names))) as pool:
        return list(pool.map(check_and_save, document_names))

# ── UPLOAD DOCUMENT ──
@app.route('/api/upload', methods=['POST'])
@require_auth
@limiter.limit("20 per minute")
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    applicant_id = request.form.get('applicant_id', '')
    document_name = request.form.get('document_name', '')

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant_id"}), 400

    safe_document_name = secure_filename(document_name)
    if not safe_document_name:
        return jsonify({"error": "Invalid document_name"}), 400

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{applicant_id}_{safe_document_name}_{filename}"

        try:
            db = get_db()
            org_id = current_organization_oid()
            now = datetime.utcnow()

            # Documents are frozen once the application is reviewed or withdrawn -
            # except when an admin has requested changes (Withdrawn + admin_comment
            # set), which puts it back in the student's hands. Mirrors the frontend's
            # adminRequestedChanges unlock logic in ApplicantDetails.jsx.
            status_doc = db.applicants.find_one(
                {"_id": applicant_oid, "organization_id": org_id},
                {"application.status": 1, "application.admin_comment": 1, "user_id": 1, "email": 1, "full_name": 1}
            )
            if not status_doc:
                return jsonify({"error": "Applicant not found"}), 404
            # Only the applicant themselves (or reviewing staff) may change an
            # application's documents - same rule as viewing them. Records from
            # before user_id was stored fall back to the email on the record.
            if status_doc.get('user_id'):
                is_owner = str(status_doc['user_id']) == g.current_user['id']
            else:
                is_owner = (status_doc.get('email') or '').lower() == (g.current_user.get('email') or '').lower()
            if not is_owner and not has_permission('can_review_applicants'):
                log_activity('document', "Blocked upload to another applicant's application", outcome='failure',
                             target={"type": "applicant", "id": applicant_oid, "label": status_doc.get('full_name')},
                             details=document_name)
                return jsonify({"error": "Forbidden"}), 403
            application_info = status_doc.get('application') or {}
            current_status = application_info.get('status')
            admin_requested_changes = current_status == 'Withdrawn' and bool(application_info.get('admin_comment'))
            if current_status in ('Approved', 'Rejected') or (current_status == 'Withdrawn' and not admin_requested_changes):
                return jsonify({"error": "This application has already been reviewed and its documents can no longer be changed."}), 400

            applicant = db.applicants.find_one(
                {"_id": applicant_oid, "documents.document_name": document_name, "organization_id": org_id},
                {"documents.$": 1}
            )
            old_gridfs_id = None
            if applicant and applicant.get('documents'):
                old_gridfs_id = applicant['documents'][0].get('gridfs_id')

            file_bytes = file.read()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            phash = compute_perceptual_hash(file_bytes, filename)
            metadata_flags = extract_metadata_flags(file_bytes, filename)

            new_gridfs_id = _fs.put(
                file_bytes, filename=unique_filename,
                content_type=safe_mime_for(unique_filename)
            )

            result = db.applicants.update_one(
                {"_id": applicant_oid, "documents.document_name": document_name, "organization_id": org_id},
                {"$set": {
                    "documents.$.gridfs_id": new_gridfs_id,
                    "documents.$.status": "Uploaded",
                    "documents.$.uploaded_at": now,
                    "documents.$.file_hash": file_hash,
                    "documents.$.phash": phash,
                    "documents.$.metadata_flags": metadata_flags,
                }}
            )

            if result.matched_count == 0:
                db.applicants.update_one(
                    {"_id": applicant_oid, "organization_id": org_id},
                    {"$push": {"documents": {
                        "document_name": document_name,
                        "gridfs_id": new_gridfs_id,
                        "status": "Uploaded",
                        "uploaded_at": now,
                        "file_hash": file_hash,
                        "phash": phash,
                        "metadata_flags": metadata_flags,
                    }}}
                )

            replaced = bool(old_gridfs_id)
            db.applicants.update_one({"_id": applicant_oid, "organization_id": org_id}, {"$push": {"audit_trail": {
                "action": f"Document {'replaced' if replaced else 'uploaded'}: {document_name}",
                "performed_by": g.current_user.get('email'),
                "performed_by_role": g.current_user.get('role'),
                "old_status": current_status,
                "new_status": current_status,
                "remarks": f"File: {filename}",
                "performed_at": now,
            }}})
            log_activity('document', 'Replaced a document' if replaced else 'Uploaded a document',
                         target={"type": "applicant", "id": applicant_oid, "label": status_doc.get('full_name')},
                         details=f"{document_name} ({filename})")

            # Clean up the previous file now that the new one is safely stored
            if old_gridfs_id:
                try:
                    _fs.delete(old_gridfs_id)
                except Exception:
                    pass

            # Fraud signal: exact file already uploaded by a different applicant.
            reused = db.applicants.find_one(
                {"_id": {"$ne": applicant_oid}, "documents.file_hash": file_hash, "organization_id": org_id},
                {"full_name": 1}
            )
            if reused:
                try:
                    db.duplicate_flags.insert_one({
                        "applicant_id": applicant_oid,
                        "duplicate_of_id": reused["_id"],
                        "reason": "duplicate_document",
                        "document_name": document_name,
                        "flagged_at": now,
                        "resolved": False,
                        "organization_id": org_id,
                    })
                except Exception:
                    pass
            elif phash:
                # Fraud signal: near-duplicate via perceptual hash (re-saved/cropped copy).
                try:
                    this_hash = imagehash.hex_to_hash(phash)
                    best_match_doc, best_match_applicant, best_distance = None, None, None
                    for other in db.applicants.find(
                        {"_id": {"$ne": applicant_oid}, "documents.phash": {"$exists": True, "$ne": None}, "organization_id": org_id},
                        {"full_name": 1, "documents.document_name": 1, "documents.phash": 1}
                    ):
                        for d in other.get('documents', []):
                            if not d.get('phash'):
                                continue
                            # Cast to native int - numpy.int64 isn't bson-encodable.
                            distance = int(this_hash - imagehash.hex_to_hash(d['phash']))
                            if best_distance is None or distance < best_distance:
                                best_distance, best_match_doc, best_match_applicant = distance, d, other

                    if best_match_applicant and best_distance <= NEAR_DUPLICATE_THRESHOLD:
                        db.duplicate_flags.insert_one({
                            "applicant_id": applicant_oid,
                            "duplicate_of_id": best_match_applicant["_id"],
                            "reason": "near_duplicate_document",
                            "document_name": document_name,
                            "duplicate_of_document_name": best_match_doc.get("document_name"),
                            "similarity_distance": best_distance,
                            "flagged_at": now,
                            "resolved": False,
                            "organization_id": org_id,
                        })
                except Exception:
                    pass

            # Fraud signal: metadata names an editing tool. No other applicant involved.
            if metadata_flags:
                try:
                    db.duplicate_flags.insert_one({
                        "applicant_id": applicant_oid,
                        "duplicate_of_id": None,
                        "reason": "suspicious_metadata",
                        "document_name": document_name,
                        "details": metadata_flags,
                        "flagged_at": now,
                        "resolved": False,
                        "organization_id": org_id,
                    })
                except Exception:
                    pass

            return jsonify({
                "message": "File uploaded successfully",
                "filename": unique_filename
            })

        except Exception as e:
            app.logger.error(str(e))
            if DEBUG:
                raise
            return jsonify({"error": "Something went wrong. Please try again."}), 500

    return jsonify({"error": "File type not allowed"}), 400

# ── OCR VERIFY DOCUMENT ── admin-only; re-checks one document on demand.
@app.route('/api/verify-document', methods=['POST'])
@require_permission('can_review_applicants')
@limiter.limit("20 per minute")
def verify_document_route():
    data = request.get_json()
    applicant_id = data.get('applicant_id')
    document_name = data.get('document_name')

    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant_id"}), 400

        db = get_db()
        org_id = current_organization_oid()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
        if not applicant:
            return jsonify({"error": "Document not found"}), 404

        result = run_ocr_check(db, applicant, applicant_oid, document_name, org_id)
        if 'error' in result:
            return jsonify(result), 404
        return jsonify(result)

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── OCR-CHECK ONE APPLICANT'S DOCUMENTS, ONE DOCUMENT PER REQUEST ──
# On a small instance a single document takes ~20s+ of OCR, so checking them
# all in one request can pass gunicorn's --timeout, which kills the worker and
# leaves the browser with a dropped connection. The caller loops until
# `remaining` is 0, sending back the names it has already attempted as
# `exclude` so a document that errors can't be picked again and stall the loop.
OCR_DOCS_PER_REQUEST = 1

@app.route('/api/applications/<applicant_id>/check-documents', methods=['POST'])
@require_permission('can_review_applicants')
@limiter.limit("60 per minute")
def check_documents_route(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        body = request.get_json(silent=True)
        raw_exclude = body.get('exclude') if isinstance(body, dict) else None
        exclude = {n for n in raw_exclude if isinstance(n, str)} if isinstance(raw_exclude, list) else set()

        db = get_db()
        org_id = current_organization_oid()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        required_labels = get_required_doc_labels(db, org_id)
        pending = [n for n in documents_needing_ocr(applicant, required_labels) if n not in exclude]
        batch = pending[:OCR_DOCS_PER_REQUEST]
        results = run_ocr_checks_concurrently(db, applicant, applicant_oid, batch, org_id)

        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
        warnings = collect_verification_warnings(db, applicant, org_id)
        return jsonify({"results": results, "warnings": warnings, "remaining": len(pending) - len(batch)})

    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET APPLICANT DOCUMENTS ──
@app.route('/api/documents/<applicant_id>', methods=['GET'])
@require_auth
def get_documents(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": current_organization_oid()}, {"documents": 1, "user_id": 1})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        is_owner = applicant.get('user_id') and str(applicant['user_id']) == g.current_user['id']
        if not has_permission('can_review_applicants') and not is_owner:
            return jsonify({"error": "Forbidden"}), 403

        documents = applicant.get('documents', [])
        return jsonify({"documents": [serialize_document(d) for d in documents]})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── VIEW A SPECIFIC UPLOADED DOCUMENT FILE ──
@app.route('/api/documents/<applicant_id>/view', methods=['GET'])
@require_auth
def view_document_file(applicant_id):
    document_name = request.args.get('document_name')
    if not document_name:
        return jsonify({"error": "document_name is required"}), 400

    applicant_oid = oid(applicant_id)
    if not applicant_oid:
        return jsonify({"error": "Invalid applicant id"}), 400

    try:
        db = get_db()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": current_organization_oid()})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        is_owner = applicant.get('user_id') and str(applicant['user_id']) == g.current_user['id']
        if not has_permission('can_review_applicants') and not is_owner:
            return jsonify({"error": "Forbidden"}), 403

        doc = next((d for d in applicant.get('documents', []) if d.get('document_name') == document_name), None)
        if not doc or not doc.get('gridfs_id'):
            return jsonify({"error": "Document not found"}), 404

        try:
            grid_out = _fs.get(doc['gridfs_id'])
        except gridfs.errors.NoFile:
            return jsonify({"error": "File not found on server"}), 404

        log_activity('document', 'Viewed a document',
                     target={"type": "applicant", "id": applicant_oid, "label": applicant.get('full_name')},
                     details=document_name)
        return send_file(
            grid_out,
            mimetype=safe_mime_for(grid_out.filename),
            download_name=grid_out.filename,
            as_attachment=False
        )
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── GET DUPLICATE FLAGS ──
@app.route('/api/duplicate-flags', methods=['GET'])
@require_permission('can_review_applicants')
def get_duplicate_flags():
    try:
        db = get_db()
        org_id = current_organization_oid()
        flag_docs = list(db.duplicate_flags.find({"resolved": False, "organization_id": org_id}).sort("flagged_at", -1))

        applicant_ids = {f.get('applicant_id') for f in flag_docs if f.get('applicant_id')}
        applicant_ids |= {f.get('duplicate_of_id') for f in flag_docs if f.get('duplicate_of_id')}
        applicants_by_id = {
            a['_id']: a for a in db.applicants.find({"_id": {"$in": list(applicant_ids)}, "organization_id": org_id})
        }

        flags = []
        for f in flag_docs:
            a1 = applicants_by_id.get(f.get('applicant_id'), {})
            a2 = applicants_by_id.get(f.get('duplicate_of_id'), {})
            flags.append({
                "id": str(f['_id']),
                "applicant_id": str(f['applicant_id']) if f.get('applicant_id') else None,
                "duplicate_of_id": str(f['duplicate_of_id']) if f.get('duplicate_of_id') else None,
                "reason": f.get('reason'),
                "flagged_at": iso(f.get('flagged_at')),
                "resolved": bool(f.get('resolved', False)),
                "applicant_name": a1.get('full_name'),
                "applicant_email": a1.get('email'),
                "applicant_dob": decrypt_field(a1.get('date_of_birth')),
                "document_name": f.get('document_name'),
                "duplicate_of_document_name": f.get('duplicate_of_document_name'),
                "similarity_distance": f.get('similarity_distance'),
                "duplicate_of_name": a2.get('full_name'),
                "duplicate_of_email": a2.get('email'),
                "details": f.get('details'),
            })
        return jsonify({"flags": flags})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500

# ── RESOLVE DUPLICATE FLAG ──
@app.route('/api/duplicate-flags/<flag_id>/resolve', methods=['PUT'])
@require_permission('can_review_applicants')
def resolve_flag(flag_id):
    try:
        flag_oid = oid(flag_id)
        if not flag_oid:
            return jsonify({"error": "Invalid flag id"}), 400

        db = get_db()
        result = db.duplicate_flags.update_one(
            {"_id": flag_oid, "organization_id": current_organization_oid()},
            {"$set": {"resolved": True}}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Flag not found"}), 404
        flag = db.duplicate_flags.find_one({"_id": flag_oid}, {"reason": 1, "document_name": 1, "applicant_id": 1}) or {}
        log_activity('document', 'Resolved a duplicate/fraud flag',
                     target={"type": "applicant", "id": flag.get('applicant_id')},
                     details=' - '.join(x for x in (flag.get('reason'), flag.get('document_name')) if x))
        return jsonify({"message": "Flag resolved"})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500
