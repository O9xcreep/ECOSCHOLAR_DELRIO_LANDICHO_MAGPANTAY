# -*- coding: utf-8 -*-
"""Documents must be OCR-verified (and any fraud flag resolved) before the ML
scoring/decision endpoints (GET /api/score-applicant/<id>, PUT
/api/applications/<id>/verify) will run - see check_ready_for_ml_decision()."""
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
    when None, matching a document that was uploaded but never OCR-checked."""
    docs = []
    for label in REQUIRED_LABELS:
        d = {'document_name': label, 'status': 'Uploaded'}
        if ocr_status is not None:
            d['ocr_status'] = ocr_status
            d['ocr_confidence'] = 80
            d['ocr_flags'] = []
        docs.append(d)
    return docs


class TestScoreApplicantGate:
    def test_blocked_when_required_docs_missing(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=[])
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert body['blocked'] is True
        assert 'Form A' in body['reason']

    def test_blocked_when_uploaded_but_not_ocr_verified(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs(ocr_status=None))
        res = client.get(f'/api/score-applicant/{applicant_id}', headers=auth_headers())
        body = res.get_json()
        assert body['blocked'] is True
        assert 'OCR verification' in body['reason']

    def test_blocked_when_unresolved_fraud_flag(self, client, db, auth_headers):
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
        assert body['blocked'] is True
        assert 'fraud' in body['reason'].lower()

    def test_selfie_does_not_need_ocr_verification(self, client, db, auth_headers):
        """The selfie is required but is never run through OCR (it's a face photo,
        manually compared against the ID in the UI - see ApplicantModal.jsx) - the
        gate must not demand ocr_status on it, or every applicant would be
        permanently blocked with no way to satisfy the gate through the UI."""
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
        assert not body.get('blocked')

    def test_not_blocked_once_verified_and_flags_resolved(self, client, db, auth_headers):
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
        assert not body.get('blocked')
        assert isinstance(body.get('ml_score'), (int, float))


class TestVerifyAndDecideGate:
    def test_error_when_required_docs_missing(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=[])
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        assert res.status_code == 409
        assert 'Missing required documents' in res.get_json()['error']

    def test_error_when_not_ocr_verified(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs(ocr_status=None))
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        assert res.status_code == 409
        assert 'OCR verification' in res.get_json()['error']

    def test_error_when_unresolved_fraud_flag(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        db.duplicate_flags.insert_one({
            'applicant_id': applicant_id, 'duplicate_of_id': None,
            'reason': 'suspicious_metadata', 'document_name': 'Form A',
            'details': [], 'resolved': False,
            'organization_id': app_module.get_default_organization_id(db),
        })
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        assert res.status_code == 409
        assert 'fraud' in res.get_json()['error'].lower()

    def test_decides_once_verified_and_flags_resolved(self, client, db, auth_headers):
        seed_required_docs(db)
        applicant_id = make_ml_ready_applicant(db, documents=uploaded_docs())
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert 'error' not in body
        assert body['ml_status'] in ('Eligible', 'Not Eligible')
