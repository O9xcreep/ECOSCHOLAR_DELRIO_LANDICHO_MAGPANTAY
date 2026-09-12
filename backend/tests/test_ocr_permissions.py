# -*- coding: utf-8 -*-
"""OCR only ever runs on the admin verification side (POST /api/verify-document),
never during a student's own application - the old /api/ocr-autofill route (student-
facing, auto-triggered on document upload) has been removed entirely."""


class TestVerifyDocumentIsAdminOnly:
    def test_requires_auth(self, client):
        res = client.post('/api/verify-document', json={'applicant_id': 'x', 'document_name': 'y'})
        assert res.status_code == 401

    def test_student_forbidden(self, client, auth_headers):
        res = client.post('/api/verify-document', headers=auth_headers('student'),
                           json={'applicant_id': 'x', 'document_name': 'y'})
        assert res.status_code == 403

    def test_lgu_member_without_can_review_applicants_forbidden(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        res = client.post('/api/verify-document', headers=headers,
                           json={'applicant_id': 'x', 'document_name': 'y'})
        assert res.status_code == 403

    def test_admin_passes_the_permission_gate(self, client, auth_headers):
        # 400 here means the permission check passed - a full OCR run needs a
        # real file, which this suite's fake GridFS can't provide.
        res = client.post('/api/verify-document', headers=auth_headers('admin'),
                           json={'applicant_id': 'not-a-valid-id', 'document_name': 'y'})
        assert res.status_code == 400


class TestOcrAutofillRemoved:
    def test_route_no_longer_exists(self, client, auth_headers):
        res = client.post('/api/ocr-autofill', headers=auth_headers('student'), data={})
        assert res.status_code == 404
