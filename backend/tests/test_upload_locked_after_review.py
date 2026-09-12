# -*- coding: utf-8 -*-
"""POST /api/upload: once an application is reviewed (Approved/Rejected) or
withdrawn, its documents are frozen - swapping a file after the decision
would change what was actually reviewed."""
import io


def make_file():
    return (io.BytesIO(b'fake image bytes'), 'test.jpg')


class TestUploadBlockedAfterReview:
    def _upload(self, client, headers, applicant_id, document_name='School ID'):
        return client.post('/api/upload', headers=headers, content_type='multipart/form-data', data={
            'file': make_file(),
            'applicant_id': str(applicant_id),
            'document_name': document_name,
        })

    def test_blocked_when_approved(self, client, db, make_user, auth_headers):
        student = make_user(email='upload-approved@test.com', role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'email': 'upload-approved@test.com', 'user_id': student['id'],
            'application': {'status': 'Approved'}, 'documents': [],
        }).inserted_id
        login = client.post('/api/login', json={'email': student['email'], 'password': student['password']})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = self._upload(client, headers, applicant_id)
        assert res.status_code == 400
        updated = db.applicants.find_one({'_id': applicant_id})
        assert updated['documents'] == []

    def test_blocked_when_rejected(self, client, db, make_user):
        student = make_user(email='upload-rejected@test.com', role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'email': 'upload-rejected@test.com', 'user_id': student['id'],
            'application': {'status': 'Rejected'}, 'documents': [],
        }).inserted_id
        login = client.post('/api/login', json={'email': student['email'], 'password': student['password']})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = self._upload(client, headers, applicant_id)
        assert res.status_code == 400

    def test_blocked_when_withdrawn(self, client, db, make_user):
        student = make_user(email='upload-withdrawn@test.com', role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'email': 'upload-withdrawn@test.com', 'user_id': student['id'],
            'application': {'status': 'Withdrawn'}, 'documents': [],
        }).inserted_id
        login = client.post('/api/login', json={'email': student['email'], 'password': student['password']})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = self._upload(client, headers, applicant_id)
        assert res.status_code == 400

    def test_allowed_when_newly_submitted(self, client, db, make_user):
        """Sanity check the fix is scoped to reviewed/withdrawn only - a normal
        in-progress application must keep accepting uploads."""
        student = make_user(email='upload-pending@test.com', role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'email': 'upload-pending@test.com', 'user_id': student['id'],
            'application': {'status': 'Newly Submitted'}, 'documents': [],
        }).inserted_id
        login = client.post('/api/login', json={'email': student['email'], 'password': student['password']})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = self._upload(client, headers, applicant_id)
        assert res.status_code == 200, res.get_json()
        updated = db.applicants.find_one({'_id': applicant_id})
        assert updated['documents'][0]['status'] == 'Uploaded'
