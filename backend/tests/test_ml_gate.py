# -*- coding: utf-8 -*-
"""Whether a document is genuine is the LGU's call, not an algorithm's - OCR and
the duplicate/metadata checks (see collect_verification_warnings, run_ocr_check
in backend/app.py) only ever surface warnings for a human to weigh, never block
the ML scoring/decision endpoints (GET /api/score-applicant/<id>, PUT
/api/applications/<id>/verify). "Start Eligibility" is one tap: it also runs OCR
automatically on any required document that hasn't been checked yet - the
dedicated "Run OCR Check" button (POST .../check-documents) does the same OCR
pass on its own, for a reviewer who wants to see the results before deciding."""
import app as app_module

REQUIRED_LABELS = ['Form A', 'Form B', app_module.SELFIE_DOC_LABEL]


def seed_required_docs(db):
    db.document_requirements.insert_many([
        {'label': label, 'required': True, 'enabled': True} for label in REQUIRED_LABELS
    ])


def make_ml_ready_applicant(db, email='ready@test.com', documents=None):
    doc = {
        'full_name': 'Test Applicant', 'email': email,
        'application': {'status': 'Newly Submitted'},
        'academic': {'gpa': 1.5, 'course': 'BSCS'},
        'monthly_income': 10000, 'housing_situation': 'Rented',
        'num_siblings': 1, 'num_siblings_studying': 1,
        'father_education': 'College', 'mother_education': 'College',
        'father_occupation': 'Laborer/Driver', 'mother_occupation': 'Laborer/Driver',
        'family_size': 4, 'gender': 'Male', 'has_other_scholarship': False,
        'documents': documents if documents is not None else [],
        'audit_trail': [],
    }
    return db.applicants.insert_one(doc).inserted_id


def uploaded_docs(ocr_status='Verified'):
    """One 'Uploaded' entry per required label; ocr_status omitted entirely
    when None, matching a document that was uploaded but never OCR-checked
    (and has no gridfs_id, so run_ocr_check can't actually OCR it either)."""
    docs = []
    for label in REQUIRED_LABELS:
        d = {'document_name': label, 'status': 'Uploaded'}
        if ocr_status is not None:
            d['ocr_status'] = ocr_status
            d['ocr_confidence'] = 80
            d['ocr_flags'] = []
        docs.append(d)
    return docs


class TestScoreApplicantNeverBlocks:
    """GET /api/score-applicant/<id> is just a preview fetched automatically on
    modal open - it must always return a score (when the applicant has the
    required ML fields) and surface any concerns as 'warnings', never a hard
    block, regardless of document/fraud state."""

    def test_scores_with_missing_required_documents(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=[])
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert isinstance(body.get('ml_score'), (int, float))
        assert any('Form A' in w for w in body['warnings'])

    def test_scores_with_unverified_documents(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs(ocr_status=None))
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert isinstance(body.get('ml_score'), (int, float))
        assert any('could not be OCR-checked' in w for w in body['warnings'])

    def test_scores_with_unresolved_fraud_flag(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        db.duplicate_flags.insert_one({
            'applicant_id': applicant_id, 'duplicate_of_id': None,
            'reason': 'suspicious_metadata', 'document_name': 'Form A',
            'details': ['Image metadata shows editing'], 'resolved': False,
            'organization_id': app_module.get_default_organization_id(db),
        })
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert isinstance(body.get('ml_score'), (int, float))
        assert any('fraud' in w.lower() for w in body['warnings'])

    def test_no_warnings_once_verified_and_flags_resolved(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        db.duplicate_flags.insert_one({
            'applicant_id': applicant_id, 'duplicate_of_id': None,
            'reason': 'suspicious_metadata', 'document_name': 'Form A',
            'details': ['Image metadata shows editing'], 'resolved': True,
            'organization_id': app_module.get_default_organization_id(db),
        })
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert body['warnings'] == []

    def test_selfie_never_produces_an_ocr_warning(self, client, db, auth_headers):
        """The selfie is required but is never run through OCR (it's a face
        photo, manually compared against the ID in the UI) - it must not be
        reported as 'could not be OCR-checked'."""
        seed_required_docs(db)
        docs = uploaded_docs()
        for d in docs:
            if d['document_name'] == app_module.SELFIE_DOC_LABEL:
                d.pop('ocr_status', None)
                d.pop('ocr_confidence', None)
                d.pop('ocr_flags', None)
        applicant_id = make_ml_ready_applicant(db, documents=docs)
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert body['warnings'] == []


class TestVerifyAndDecideNeverBlocks:
    """PUT /api/applications/<id>/verify is the one-tap action: it must always
    proceed to a decision (missing docs, un-OCR'd docs, and unresolved fraud
    flags become 'warnings' in the response, never a 409) - the LGU decides
    whether to accept the model's call after seeing them, using the existing
    Reconsider/Revoke Approval actions if they disagree."""

    def test_decides_with_missing_required_documents(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=[])
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert 'error' not in body
        assert any('Form A' in w for w in body['warnings'])

    def test_decides_with_unresolved_fraud_flag(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        db.duplicate_flags.insert_one({
            'applicant_id': applicant_id, 'duplicate_of_id': None,
            'reason': 'suspicious_metadata', 'document_name': 'Form A',
            'details': [], 'resolved': False,
            'organization_id': app_module.get_default_organization_id(db),
        })
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert any('fraud' in w.lower() for w in body['warnings'])

    def test_decides_cleanly_once_verified_and_flags_resolved(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert 'error' not in body
        assert body['ml_status'] in ('Eligible', 'Not Eligible')
        assert body['warnings'] == []

    def test_attempts_ocr_on_uploaded_but_unchecked_documents(self, client, db, auth_headers):
        """A document that was uploaded but never OCR-checked (no ocr_status)
        should get run through OCR automatically as part of this one tap - since
        it has no gridfs_id in this test, the attempt fails gracefully and shows
        up as a warning rather than raising or blocking the decision."""
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs(ocr_status=None))
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert 'error' not in body
        assert any('could not be OCR-checked' in w for w in body['warnings'])


class TestCheckDocumentsRoute:
    """POST /api/applications/<id>/check-documents is the dedicated "Run OCR
    Check" button - a standalone way to run the same OCR pass _verify_and_decide_one
    runs automatically, so a reviewer can see the results before deciding at all."""

    def test_requires_auth(self, client):
        res = client.post('/api/applications/x/check-documents')
        assert res.status_code == 401

    def test_student_forbidden(self, client, auth_headers):
        res = client.post('/api/applications/x/check-documents', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_invalid_applicant_id(self, client, auth_headers):
        res = client.post('/api/applications/not-a-valid-id/check-documents', headers=auth_headers('admin'))
        assert res.status_code == 400

    def test_reports_documents_that_cannot_be_checked(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs(ocr_status=None))
        res = client.post(f'/api/applications/{applicant_id}/check-documents', headers=auth_headers('admin'))
        body = res.get_json()
        assert res.status_code == 200
        assert any('could not be OCR-checked' in w for w in body['warnings'])
        # Form A + Form B are checked concurrently (not the selfie) - each result
        # must still be correctly attributed to its own document, regression check
        # for a temp-file collision that once let concurrent checks corrupt each
        # other when they shared one filename.
        assert {r['document_name'] for r in body['results']} == {'Form A', 'Form B'}

    def test_no_warnings_when_already_verified(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        res = client.post(f'/api/applications/{applicant_id}/check-documents', headers=auth_headers('admin'))
        body = res.get_json()
        assert res.status_code == 200
        assert body['results'] == []  # nothing left to check
        assert body['warnings'] == []
