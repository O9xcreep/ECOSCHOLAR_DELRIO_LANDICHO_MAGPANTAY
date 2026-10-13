# -*- coding: utf-8 -*-
"""POST /api/documents/precheck: right after upload, tells the student if a
document is unreadable or doesn't show their name, so they can replace it
before review. Only those signals reach the student - value cross-checks and
fraud flags stay admin-only - and each upload is OCR'd at most once."""
from bson import ObjectId

import app as app_module
import documents as documents_module
from documents import student_upload_warning


def ocr_result(status='Verified', name_found=True, readable=True, flags=None):
    return {'document_name': 'Enrollment Form', 'status': status, 'confidence': 0, 'readable': readable,
            'flags': flags or [], 'checks': [{'check': 'Applicant name found', 'passed': name_found}]}


class TestStudentUploadWarning:
    def test_unreadable(self):
        assert "couldn't read" in student_upload_warning(ocr_result(readable=False, name_found=False), 'School ID')

    def test_name_missing(self):
        msg = student_upload_warning(ocr_result(status='Failed Verification', name_found=False), 'School ID')
        assert "couldn't find your name" in msg and 'School ID' in msg

    def test_wrong_document_type(self):
        msg = student_upload_warning(ocr_result(status='Failed Verification'), 'School ID')
        assert "doesn't look like a School ID" in msg

    def test_verified_and_partial_say_nothing(self):
        assert student_upload_warning(ocr_result(), 'School ID') is None
        assert student_upload_warning(ocr_result(status='Partially Verified'), 'School ID') is None

    def test_fraud_flags_are_not_revealed(self):
        """An income/GWA mismatch caps the status at Partially Verified and adds
        a flag - the student must not be told, or they could tune the document."""
        result = ocr_result(status='Partially Verified', flags=["Declared monthly income doesn't match"])
        assert student_upload_warning(result, 'Proof of Income') is None

    def test_ocr_error_says_nothing(self):
        assert student_upload_warning({'document_name': 'x', 'error': 'File not found'}, 'x') is None


class TestPrecheckRoute:
    def _setup(self, client, db, make_user, documents, email='pre@test.com'):
        student = make_user(email=email, role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': 'Maria Santos', 'email': email, 'user_id': student['id'],
            'application': {'status': 'Newly Submitted'}, 'documents': documents,
        }).inserted_id
        login = client.post('/api/login', json={'email': student['email'], 'password': student['password']})
        return applicant_id, {'Authorization': f"Bearer {login.get_json()['token']}"}

    def _post(self, client, headers, applicant_id, document_name='Enrollment Form'):
        return client.post('/api/documents/precheck', headers=headers,
                           json={'applicant_id': str(applicant_id), 'document_name': document_name})

    def _fake_ocr(self, monkeypatch, result):
        calls = []

        def fake(applicant, applicant_oid, document_name):
            calls.append(document_name)
            return {**result, 'document_name': document_name}
        monkeypatch.setattr(documents_module, 'compute_ocr_result', fake)
        return calls

    def test_warns_owner_and_saves_result(self, client, db, make_user, monkeypatch):
        calls = self._fake_ocr(monkeypatch, ocr_result(status='Failed Verification', name_found=False))
        applicant_id, headers = self._setup(client, db, make_user, [
            {'document_name': 'Enrollment Form', 'status': 'Uploaded', 'gridfs_id': ObjectId()}])

        res = self._post(client, headers, applicant_id)
        assert res.status_code == 200
        assert "couldn't find your name" in res.get_json()['warning']
        saved = db.applicants.find_one({'_id': applicant_id})['documents'][0]
        assert saved['ocr_status'] == 'Failed Verification'
        assert saved['upload_warning'] == res.get_json()['warning']

        # Already checked: answered from the saved result, no second OCR run.
        again = self._post(client, headers, applicant_id)
        assert again.get_json()['warning'] == res.get_json()['warning']
        assert calls == ['Enrollment Form']

    def test_response_never_contains_fraud_details(self, client, db, make_user, monkeypatch):
        self._fake_ocr(monkeypatch, ocr_result(status='Partially Verified', flags=['income mismatch']))
        applicant_id, headers = self._setup(client, db, make_user, [
            {'document_name': 'Enrollment Form', 'status': 'Uploaded', 'gridfs_id': ObjectId()}])
        assert self._post(client, headers, applicant_id).get_json() == {'warning': None}

    def test_other_student_forbidden(self, client, db, make_user, monkeypatch):
        calls = self._fake_ocr(monkeypatch, ocr_result())
        applicant_id, _ = self._setup(client, db, make_user, [
            {'document_name': 'Enrollment Form', 'status': 'Uploaded', 'gridfs_id': ObjectId()}])
        _, other_headers = self._setup(client, db, make_user, [], email='other@test.com')
        assert self._post(client, other_headers, applicant_id).status_code == 403
        assert calls == []

    def test_selfie_is_never_ocrd(self, client, db, make_user, monkeypatch):
        calls = self._fake_ocr(monkeypatch, ocr_result())
        applicant_id, headers = self._setup(client, db, make_user, [
            {'document_name': app_module.SELFIE_DOC_LABEL, 'status': 'Uploaded', 'gridfs_id': ObjectId()}])
        res = self._post(client, headers, applicant_id, app_module.SELFIE_DOC_LABEL)
        assert res.get_json() == {'warning': None}
        assert calls == []

    def test_missing_document_404(self, client, db, make_user, monkeypatch):
        self._fake_ocr(monkeypatch, ocr_result())
        applicant_id, headers = self._setup(client, db, make_user, [])
        assert self._post(client, headers, applicant_id).status_code == 404

    def test_invalid_body_400(self, client, auth_headers):
        res = client.post('/api/documents/precheck', headers=auth_headers('student'), json={'applicant_id': None})
        assert res.status_code == 400

    def test_requires_auth(self, client):
        assert client.post('/api/documents/precheck', json={}).status_code == 401

    def test_warning_is_sent_with_the_students_documents(self):
        """serialize_document backs GET /api/student/application's documents."""
        from helpers import serialize_document
        doc = {'document_name': 'Enrollment Form', 'status': 'Uploaded', 'ocr_status': 'Failed Verification',
               'upload_warning': "We couldn't read the text in this file."}
        assert serialize_document(doc)['upload_warning'] == "We couldn't read the text in this file."
