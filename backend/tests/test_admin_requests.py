# -*- coding: utf-8 -*-
"""Admin account requests: public submission plus admin approve/reject review."""

VALID_REQUEST = {
    'full_name': 'Juan Dela Cruz',
    'email': 'juan@lgu.gov.ph',
    'office': 'Municipal Social Welfare and Development Office',
    'municipality': 'Liliw',
    'contact_number': '09123456789',
    'message': 'Requesting access to review scholarship applications.',
}


class TestSubmitAdminRequest:
    def test_submit_success(self, client, db):
        res = client.post('/api/admin-requests', json=VALID_REQUEST)
        assert res.status_code == 201
        stored = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})
        assert stored is not None
        assert stored['status'] == 'pending'

    def test_missing_fields_rejected(self, client):
        res = client.post('/api/admin-requests', json={'email': 'x@test.com'})
        assert res.status_code == 400

    def test_invalid_email_rejected(self, client):
        res = client.post('/api/admin-requests', json={**VALID_REQUEST, 'email': 'not-an-email'})
        assert res.status_code == 400

    def test_duplicate_pending_request_rejected(self, client):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        res = client.post('/api/admin-requests', json=VALID_REQUEST)
        assert res.status_code == 409

    def test_existing_user_email_rejected(self, client, make_user):
        make_user(email='juan@lgu.gov.ph', role='admin')
        res = client.post('/api/admin-requests', json=VALID_REQUEST)
        assert res.status_code == 409

    def test_does_not_create_a_user_account(self, client, db):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        assert db.users.find_one({'email': 'juan@lgu.gov.ph'}) is None


class TestListAdminRequests:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.get('/api/admin-requests', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_lists_submitted_requests(self, client, auth_headers):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        res = client.get('/api/admin-requests', headers=auth_headers())
        assert res.status_code == 200
        emails = [r['email'] for r in res.get_json()['requests']]
        assert 'juan@lgu.gov.ph' in emails

    def test_filters_by_status(self, client, auth_headers):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        res = client.get('/api/admin-requests?status=rejected', headers=auth_headers())
        assert res.get_json()['requests'] == []


class TestApproveAdminRequest:
    def test_approve_creates_admin_account(self, client, db, auth_headers):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        req = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())
        assert res.status_code == 201

        created = db.users.find_one({'email': 'juan@lgu.gov.ph'})
        assert created['role'] == 'admin'
        assert created['municipality'] == 'Liliw'

        updated_req = db.admin_requests.find_one({'_id': req['_id']})
        assert updated_req['status'] == 'approved'

    def test_approved_admin_has_no_usable_starting_password(self, client, db, auth_headers):
        """Approval must never leave a guessable/known password on the account -
        access is only granted through the emailed set-password link."""
        client.post('/api/admin-requests', json=VALID_REQUEST)
        req = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())

        res = client.post('/api/login', json={'email': 'juan@lgu.gov.ph', 'password': 'guessed-password'})
        assert res.status_code == 401

    def test_requires_admin_role(self, client, auth_headers, db):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        req = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_cannot_approve_twice(self, client, db, auth_headers):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        req = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})
        headers = auth_headers()
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)
        assert res.status_code == 400

    def test_invalid_id(self, client, auth_headers):
        res = client.post('/api/admin-requests/not-a-valid-id/approve', headers=auth_headers())
        assert res.status_code == 400


class TestRejectAdminRequest:
    def test_reject_marks_status_without_creating_account(self, client, db, auth_headers):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        req = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})

        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=auth_headers())
        assert res.status_code == 200
        assert db.admin_requests.find_one({'_id': req['_id']})['status'] == 'rejected'
        assert db.users.find_one({'email': 'juan@lgu.gov.ph'}) is None

    def test_requires_admin_role(self, client, auth_headers, db):
        client.post('/api/admin-requests', json=VALID_REQUEST)
        req = db.admin_requests.find_one({'email': 'juan@lgu.gov.ph'})
        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=auth_headers('student'))
        assert res.status_code == 403
