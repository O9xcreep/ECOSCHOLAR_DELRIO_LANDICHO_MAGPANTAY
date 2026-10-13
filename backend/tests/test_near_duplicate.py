# -*- coding: utf-8 -*-
"""Near-duplicate (perceptual hash) detection must not flag two applicants who
each upload their own copy of the same printed form. A pHash fingerprints
layout, so same-template documents hash identically; the upload only records
candidates, and the OCR check flags one only if the other applicant's name is
on the document."""
import io
import os
from bson import ObjectId

import app as app_module
import documents as documents_module
from ocr import names_other_person

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'test_data', 'ocr_verification', 'barangay_endorsement')


def fixture_bytes(name):
    with open(os.path.join(FIXTURES, name), 'rb') as f:
        return f.read()


class TestNamesOtherPerson:
    def test_own_copy_of_template_is_not_the_other_persons(self):
        text = "BARANGAY ENDORSEMENT This is to certify that MARIA SANTOS is a resident"
        assert not names_other_person('Juan Dela Cruz', 'Maria Santos', text)

    def test_other_applicants_copy_is_confirmed(self):
        text = "BARANGAY ENDORSEMENT This is to certify that JUAN DELA CRUZ is a resident"
        assert names_other_person('Juan Dela Cruz', 'Maria Santos', text)

    def test_ocr_misread_of_other_name_still_confirms(self):
        text = "This is to certify that PAULINE PANALLGAN is a resident"
        assert names_other_person('Pauline Panaligan', 'Maria Santos', text)

    def test_sibling_sharing_surnames_is_not_confirmed(self):
        """Siblings' own certificates share the middle and last name - only a
        part the other sibling doesn't share (the first name) counts."""
        text = "This is to certify that MARIA RIVERO ROSALES is a resident"
        assert not names_other_person('Juan Rivero Rosales', 'Maria Rivero Rosales', text)

    def test_one_letter_different_first_name_does_not_match(self):
        text = "This is to certify that MARIO CRUZ is a resident"
        assert not names_other_person('Maria Cruz', 'Mario Cruz', text)


class TestSameTemplateUpload:
    def _student_upload(self, client, db, make_user, email, full_name, file_name):
        student = make_user(email=email, role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': full_name, 'email': email, 'user_id': student['id'],
            'application': {'status': 'Newly Submitted'}, 'documents': [],
        }).inserted_id
        login = client.post('/api/login', json={'email': student['email'], 'password': student['password']})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
        res = client.post('/api/upload', headers=headers, content_type='multipart/form-data', data={
            'file': (io.BytesIO(fixture_bytes(file_name)), file_name),
            'applicant_id': str(applicant_id),
            'document_name': 'Barangay Endorsement',
        })
        assert res.status_code == 200, res.get_json()
        return applicant_id

    def test_same_template_different_person_is_candidate_not_flag(self, client, db, make_user):
        first = self._student_upload(client, db, make_user, 'juan@test.com', 'Juan Dela Cruz', 'clean_01.jpg')
        second = self._student_upload(client, db, make_user, 'maria@test.com', 'Maria Santos', 'clean_02.jpg')

        assert db.duplicate_flags.count_documents({}) == 0
        doc = db.applicants.find_one({'_id': second})['documents'][0]
        assert [c['applicant_id'] for c in doc['near_duplicate_candidates']] == [first]

    def test_exact_same_file_is_still_flagged_immediately(self, client, db, make_user):
        self._student_upload(client, db, make_user, 'juan@test.com', 'Juan Dela Cruz', 'clean_01.jpg')
        self._student_upload(client, db, make_user, 'copy@test.com', 'Maria Santos', 'clean_01.jpg')

        assert db.duplicate_flags.count_documents({'reason': 'duplicate_document'}) == 1


class TestOcrConfirmsNearDuplicate:
    def _applicant_with_candidate(self, db, other_id):
        return db.applicants.insert_one({
            'full_name': 'Maria Santos', 'email': 'maria@test.com',
            'application': {'status': 'Newly Submitted'},
            'documents': [{
                'document_name': 'Barangay Endorsement', 'status': 'Uploaded', 'gridfs_id': ObjectId(),
                'near_duplicate_candidates': [{
                    'applicant_id': other_id, 'full_name': 'Juan Dela Cruz',
                    'document_name': 'Barangay Endorsement', 'distance': 0,
                }],
            }],
        }).inserted_id

    def _run_check(self, db, monkeypatch, applicant_id, ocr_text):
        class FakeFile:
            filename = 'x.jpg'

            def read(self):
                return b''

        class FakeFs:
            def get(self, *a, **kw):
                return FakeFile()

        monkeypatch.setattr(documents_module, '_fs', FakeFs())
        monkeypatch.setattr(documents_module, 'extract_and_verify', lambda path, doc_type, data: (
            ocr_text, {'status': 'Verified', 'confidence': 100, 'flags': [], 'checks': []}))
        applicant = db.applicants.find_one({'_id': applicant_id})
        org_id = applicant['organization_id']
        return documents_module.run_ocr_check(db, applicant, applicant_id, 'Barangay Endorsement', org_id)

    def test_own_template_copy_is_not_flagged(self, db, monkeypatch):
        applicant_id = self._applicant_with_candidate(db, ObjectId())
        self._run_check(db, monkeypatch, applicant_id, 'certify that MARIA SANTOS is a resident')
        assert db.duplicate_flags.count_documents({}) == 0

    def test_other_applicants_name_on_document_is_flagged_once(self, db, monkeypatch):
        other_id = ObjectId()
        applicant_id = self._applicant_with_candidate(db, other_id)
        for _ in range(2):  # re-checks must not stack duplicate flags
            result = self._run_check(db, monkeypatch, applicant_id, 'certify that JUAN DELA CRUZ is a resident')
            assert 'confirmed_near_duplicates' not in result  # holds ObjectIds; result is returned as JSON

        flags = list(db.duplicate_flags.find({}))
        assert len(flags) == 1
        assert flags[0]['reason'] == 'near_duplicate_document'
        assert flags[0]['duplicate_of_id'] == other_id
