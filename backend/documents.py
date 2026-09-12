# -*- coding: utf-8 -*-
"""Document requirements, document-completeness status computation, upload/
fraud detection, OCR verification, and duplicate-flag routes. Imported by
applicants.py, ml_scoring.py, and admin_settings.py for the status-computation
helpers and document-requirement collection."""
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
from ocr import extract_text, verify_document

# ── UPLOAD CONFIG ──
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
# Serving files back to the browser with a client-supplied Content-Type is a stored-XSS
# vector (e.g. an upload named "photo.png" claiming Content-Type: text/html). Always
# derive the served mimetype from this fixed map instead of trusting the upload metadata.
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
    """Visual fingerprint of a document's first page, used to catch near-identical
    files (re-saved, re-compressed, screenshotted, lightly cropped) that a byte-for-byte
    SHA-256 comparison would miss entirely since re-encoding changes every byte. Returns
    None on any failure (corrupt file, unsupported content) - this is a best-effort
    fraud signal layered on top of the upload, never a reason to reject the upload."""
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

# Hamming distance threshold (out of 64 bits) below which two documents are considered
# a near-duplicate. Chosen conservatively - real re-uploads of the same scanned/photographed
# page (recompressed, lightly cropped, mild lighting shift) typically land under 6-8;
# two different documents of the same type (e.g. two different students' report cards)
# routinely score 20+.
NEAR_DUPLICATE_THRESHOLD = 8

# Substrings of image/PDF editing-tool names that shouldn't legitimately appear in the
# metadata of a scanned/photographed government or school form.
EDITING_TOOL_SIGNATURES = ('photoshop', 'gimp', 'canva', 'illustrator', 'snapseed', 'picsart', 'lightroom')

def extract_metadata_flags(file_bytes, filename):
    """Best-effort forensic check of embedded file metadata (EXIF Software tag for
    images, Producer/Creator for PDFs) for signs the document was produced or edited
    with an image-editing tool rather than scanned/photographed/generated as a form.
    Deliberately does NOT flag missing metadata (messaging apps strip EXIF on send,
    which is extremely common and not itself suspicious) - only an explicit editing-tool
    signature. Returns a list of human-readable flag strings (empty if nothing found or
    on any failure reading the file)."""
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
# Which documents an LGU asks applicants to upload. The "label" here IS the
# document_name stored against every upload (see upload_document()) - one string
# used consistently as the storage key, the OCR verify_document() doc_type, and the
# label shown to students/admins, rather than three drifting variants.
#
# SELFIE_DOC_LABEL is stored/uploaded exactly like any other requirement (same GridFS
# path, same fraud checks) but the frontend pulls it out of the generic checklist and
# gives it its own "Identity Verification" UI - a live-camera capture on the student
# side, and a side-by-side compare against ID_DOC_LABEL's photo on the admin side, for
# manual visual comparison (not automated face-matching, which is a separate, bigger
# feature - see feature spec §1.2).
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
# Matched by label rather than a stored flag - every org's document_requirements
# is seeded from this exact list (get_doc_requirements_collection), so no
# migration is needed for existing data. An LGU can still hide one (disable it
# or uncheck "Required") but can't delete it outright - the eligibility
# model's document-completeness computation and OCR verification both assume
# these exist by label (SELFIE_DOC_LABEL/ID_DOC_LABEL especially).
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

# Admin-facing status flags computed from document-upload completeness, never
# stored on the applicant doc. "Newly Submitted" only ever means "hasn't shown
# up in the admin queue yet" in the DB - these three labels are what the admin
# actually sees for that same raw value, based on how far the student has
# gotten through uploading their required documents:
#   - no required docs uploaded yet      -> "Newly Submitted"
#   - some but not all required docs up  -> "Incomplete"
#   - every required doc uploaded        -> "Pending Verification" (ready to verify)
# Approved/Rejected/Withdrawn are real decisions and pass through unchanged.
COMPUTED_STATUSES = {'Newly Submitted', 'Pending Verification', 'Incomplete'}

def get_doc_requirements_collection(db, org_id):
    """Lazy-seeds the default requirements on first use per organization, so a
    newly-created LGU starts with the same documents the form always had -
    scoped by organization_id since a bare count_documents({}) would only ever
    seed once platform-wide, leaving every LGU after the first with none."""
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
    """Surfaces document/fraud concerns for the LGU to weigh - never blocks the
    ML decision. Whether a document is genuine is the LGU's call, not an
    algorithm's: OCR and the duplicate/metadata checks only inform that call
    (see run_ocr_check, extract_metadata_flags) by showing what they found;
    an admin who has looked at the actual file can always go ahead (or undo a
    decision afterward via Reconsider/Revoke Approval). Returns a list of
    human-readable warning strings, empty when there's nothing to flag."""
    warnings = []
    required_labels = get_required_doc_labels(db, org_id)
    uploaded = {d.get('document_name'): d for d in applicant.get('documents', []) if d.get('status') == 'Uploaded'}

    missing = required_labels - uploaded.keys()
    if missing:
        warnings.append(f"Not uploaded: {', '.join(sorted(missing))}")

    # The selfie is deliberately never OCR-checked (it's a face photo, shown
    # side-by-side with the ID for the admin to manually compare - see
    # ApplicantModal.jsx).
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
    """Admin-only layer on top of compute_display_status(): additionally
    relabels a Rejected-but-model-Eligible applicant as "Waitlisted" - they
    met the eligibility bar but the accepted-applicant limit was full, and
    can still be auto-promoted later (see recompute_approvals). Deliberately
    NOT used by the student-facing endpoint (get_student_application), which
    must see the raw "Rejected" value to decide whether to mask it before
    results are revealed - relabeling it here first would let that check
    slip past undetected and leak the decision early."""
    status = compute_display_status(doc, required_labels)
    if status == 'Rejected' and doc.get('ml_status') == 'Eligible':
        return 'Waitlisted'
    return status

def build_status_query_fragment(statuses):
    """Translate requested display-statuses into the Mongo filter that
    actually matches them. "Waitlisted" isn't a stored value - it's Rejected
    further split by ml_status (see compute_admin_status) - so from here on
    "Rejected" always means true rejects only; a caller wanting the old
    undifferentiated set requests both. Both directions are ordinary,
    directly-queryable fields, unlike the document-completeness statuses
    above, so this needs no fetch-everything-then-filter fallback."""
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
    """Runs OCR + the content/fraud cross-checks on one already-uploaded document.
    Read-only w.r.t. the database (only reads the GridFS file bytes) - safe to
    call from multiple threads at once, see run_ocr_checks_concurrently below.
    Returns the result dict (extended with 'document_name'), or
    {'document_name', 'error': ...} if the file couldn't be read (missing from
    storage, corrupt, etc.) - never raises."""
    doc = next((d for d in applicant.get('documents', []) if d.get('document_name') == document_name), None)
    if not doc or not doc.get('gridfs_id'):
        return {"document_name": document_name, "error": "Document not found"}

    try:
        grid_out = _fs.get(doc['gridfs_id'])
    except gridfs.errors.NoFile:
        return {"document_name": document_name, "error": "File not found on server"}

    # OCR needs a real file path, so write GridFS bytes to a scratch temp
    # file for the duration of processing only - nothing is kept on disk.
    # Unique per (applicant, document, call) - several documents for the same
    # applicant can be OCR'd concurrently, so a filename shared across them
    # would let two calls stomp on each other's temp file mid-read.
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
            "address": applicant.get('address') or '',
            "monthly_income": applicant.get('monthly_income'),
            "gpa": academic.get('gpa'),
        }

        extracted_text = extract_text(temp_path)
        result = verify_document(document_name, extracted_text, applicant_data)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Surface metadata-forensics flags (from upload time) alongside the OCR
    # content flags, so a reviewer sees both in one place.
    result['flags'] = list(result['flags']) + list(doc.get('metadata_flags') or [])
    result['document_name'] = document_name
    return result

def persist_ocr_result(db, applicant_oid, org_id, result):
    """Saves one compute_ocr_result() outcome. A file-not-found/missing-doc
    error has nothing to persist - it just means this document stays
    unchecked, which collect_verification_warnings already reports."""
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
    """Single-document OCR check (used by POST /api/verify-document): compute,
    then persist. OCR here is advisory, not a gate - it surfaces confidence/
    flags for a human to weigh, it never blocks anything on its own (see
    collect_verification_warnings)."""
    result = compute_ocr_result(applicant, applicant_oid, document_name)
    persist_ocr_result(db, applicant_oid, org_id, result)
    return result

def run_ocr_checks_concurrently(db, applicant, applicant_oid, document_names, org_id):
    """Runs OCR for several of one applicant's documents at once instead of one
    after another - each check mostly waits on the Tesseract subprocess (the
    GIL is released for that wait), so a small thread pool cuts the total wait
    roughly in proportion to how many documents need checking. All the actual
    database writes happen afterward, sequentially on the calling thread -
    compute_ocr_result never touches the database, so there's nothing to race."""
    if not document_names:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(document_names))) as pool:
        results = list(pool.map(
            lambda name: compute_ocr_result(applicant, applicant_oid, name),
            document_names
        ))
    for result in results:
        persist_ocr_result(db, applicant_oid, org_id, result)
    return results

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

            # Once an application has been reviewed (Approved/Rejected) or
            # withdrawn, its documents are frozen - same reasoning as blocking
            # withdraw after scoring: allowing a swap after the decision was
            # made would let a student silently change what the model/admin
            # actually reviewed. A Withdrawn applicant submits a fresh
            # application instead of editing the old one's documents.
            status_doc = db.applicants.find_one(
                {"_id": applicant_oid, "organization_id": org_id}, {"application.status": 1}
            )
            if not status_doc:
                return jsonify({"error": "Applicant not found"}), 404
            current_status = (status_doc.get('application') or {}).get('status')
            if current_status in ('Approved', 'Rejected', 'Withdrawn'):
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

            # Clean up the previous file now that the new one is safely stored
            if old_gridfs_id:
                try:
                    _fs.delete(old_gridfs_id)
                except Exception:
                    pass

            # ── Fraud signal: has this exact file already been uploaded by a
            # DIFFERENT applicant? A byte-for-byte match is a strong indicator of
            # document reuse (shared/borrowed paperwork, or the same fake document
            # submitted under multiple identities). Reuses the existing
            # duplicate_flags mechanism the Dashboard already surfaces. Scoped to
            # this LGU only - a cross-tenant match would otherwise leak another
            # LGU's applicant's name into this one's fraud queue.
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
                # ── Fraud signal: near-duplicate detection via perceptual hashing.
                # Catches the same document re-uploaded after being re-saved,
                # screenshotted, or lightly cropped - all of which change the file's
                # bytes (so the exact-hash check above misses it) but leave the
                # visual content essentially unchanged. Only runs when there was no
                # exact-hash match, since that's already the stronger signal.
                # Scoped to this LGU only, same reasoning as the exact-hash check.
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
                            # imagehash's ImageHash.__sub__ returns numpy.int64, which
                            # bson/pymongo cannot encode - cast to a native int up front
                            # so the flag document below is actually insertable.
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

            # ── Fraud signal: document metadata (EXIF Software tag / PDF Producer)
            # names an image-editing tool, suggesting the file was edited rather than
            # scanned/photographed/generated as a form. Reuses the same duplicate_flags
            # mechanism as the checks above so it plugs into the existing alert/resolve
            # workflow; duplicate_of_id is None since there's no other applicant involved.
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

# ── OCR VERIFY DOCUMENT ── admin-only: OCR only ever runs on the admin verification
# side, never during a student's own application (see the removed /api/ocr-autofill).
# Kept as a standalone endpoint for re-checking one document on demand - the
# dedicated "Run OCR Check" button (check_documents_route, below) and "Start
# Eligibility" (via _verify_and_decide_one) both run this per-document helper too.
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

# ── OCR-CHECK ALL DOCUMENTS FOR ONE APPLICANT ── the dedicated "run OCR" action:
# checks every uploaded required document that hasn't been OCR-checked yet, in one
# tap, so the admin can review the results before separately deciding eligibility
# (see /api/applications/<id>/verify, which also runs this as a fallback for
# anything still unchecked when eligibility is decided).
@app.route('/api/applications/<applicant_id>/check-documents', methods=['POST'])
@require_permission('can_review_applicants')
@limiter.limit("10 per minute")
def check_documents_route(applicant_id):
    try:
        applicant_oid = oid(applicant_id)
        if not applicant_oid:
            return jsonify({"error": "Invalid applicant id"}), 400

        db = get_db()
        org_id = current_organization_oid()
        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
        if not applicant:
            return jsonify({"error": "Applicant not found"}), 404

        required_labels = get_required_doc_labels(db, org_id)
        to_check = [
            d['document_name'] for d in applicant.get('documents', [])
            if d.get('document_name') in required_labels and d.get('status') == 'Uploaded'
            and d.get('document_name') != SELFIE_DOC_LABEL and not d.get('ocr_status')
        ]
        results = run_ocr_checks_concurrently(db, applicant, applicant_oid, to_check, org_id)

        applicant = db.applicants.find_one({"_id": applicant_oid, "organization_id": org_id})
        warnings = collect_verification_warnings(db, applicant, org_id)
        return jsonify({"results": results, "warnings": warnings})

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
                "applicant_dob": a1.get('date_of_birth'),
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
        return jsonify({"message": "Flag resolved"})
    except Exception as e:
        app.logger.error(str(e))
        if DEBUG:
            raise
        return jsonify({"error": "Something went wrong. Please try again."}), 500
