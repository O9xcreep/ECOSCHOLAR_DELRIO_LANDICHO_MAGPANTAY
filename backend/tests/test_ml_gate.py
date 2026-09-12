# -*- coding: utf-8 -*-
"""OCR and duplicate/metadata checks (documents.collect_verification_warnings,
documents.run_ocr_check) only ever surface warnings, never block
GET /api/score-applicant/<id> or PUT /api/applications/<id>/verify. POST
.../check-documents runs the same OCR pass standalone, before a decision."""
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
    """One 'Uploaded' entry per required label; ocr_status omitted when None,
    matching a document uploaded but never OCR-checked."""
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
    """GET /api/score-applicant/<id> must always return a score and surface
    concerns as warnings, never a hard block, regardless of document/fraud state."""

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
    """PUT /api/applications/<id>/verify must always proceed to a decision;
    missing docs, un-OCR'd docs, and fraud flags become warnings, never a 409."""

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
        """An uploaded but never OCR-checked document runs through OCR
        automatically; with no gridfs_id here, it fails gracefully into a
        warning rather than raising or blocking the decision."""
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs(ocr_status=None))
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert 'error' not in body
        assert any('could not be OCR-checked' in w for w in body['warnings'])


class TestCheckDocumentsRoute:
    """POST /api/applications/<id>/check-documents runs the same OCR pass
    _verify_and_decide_one runs automatically, standalone, so a reviewer
    can see results before deciding."""

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
        # Form A + Form B are checked concurrently; each result must stay
        # attributed to its own document (regression: a shared temp filename
        # once let concurrent checks corrupt each other).
        assert {r['document_name'] for r in body['results']} == {'Form A', 'Form B'}

    def test_no_warnings_when_already_verified(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        res = client.post(f'/api/applications/{applicant_id}/check-documents', headers=auth_headers('admin'))
        body = res.get_json()
        assert res.status_code == 200
        assert body['results'] == []  # nothing left to check
        assert body['warnings'] == []
