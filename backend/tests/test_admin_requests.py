# -*- coding: utf-8 -*-
"""Admin account requests: email-verification start step, token-gated
submission, and admin approve/reject review."""

APPLICANT_EMAIL = 'juan@lgu.gov.ph'

FORM_FIELDS = {
    'full_name': 'Juan Dela Cruz',
    'office': 'Municipal Social Welfare and Development Office',
    'municipality': 'Liliw',
    'contact_number': '09123456789',
    'message': 'Requesting access to review scholarship applications.',
}


def make_apply_token(email=APPLICANT_EMAIL):
    import app as app_module
    return app_module._admin_apply_serializer.dumps({'email': email})


class TestStartAdminRequest:
    def test_start_success(self, client):
        res = client.post('/api/admin-requests/start', json={'email': APPLICANT_EMAIL})
        assert res.status_code == 200

    def test_invalid_email_rejected(self, client):
        res = client.post('/api/admin-requests/start', json={'email': 'not-an-email'})
        assert res.status_code == 400

    def test_missing_email_rejected(self, client):
        res = client.post('/api/admin-requests/start', json={})
        assert res.status_code == 400

    def test_same_generic_response_regardless_of_existing_account(self, client, make_user):
        """Must not reveal whether the email already has an account or a pending
        request - same shape as the forgot-password endpoint's anti-enumeration behavior."""
        make_user(email='existing-admin@test.com', role='admin')
        res1 = client.post('/api/admin-requests/start', json={'email': 'existing-admin@test.com'})
        res2 = client.post('/api/admin-requests/start', json={'email': 'brand-new@test.com'})
        assert res1.status_code == res2.status_code == 200
        assert res1.get_json() == res2.get_json()


class TestVerifyAdminApplyToken:
    def test_valid_token_returns_email(self, client):
        token = make_apply_token()
        res = client.get(f'/api/admin-requests/verify-token?token={token}')
        assert res.status_code == 200
        assert res.get_json()['email'] == APPLICANT_EMAIL

    def test_invalid_token_rejected(self, client):
        res = client.get('/api/admin-requests/verify-token?token=garbage')
        assert res.status_code == 400

    def test_missing_token_rejected(self, client):
        res = client.get('/api/admin-requests/verify-token')
        assert res.status_code == 400


class TestSubmitAdminRequest:
    def test_submit_success(self, client, db):
        token = make_apply_token()
        res = client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': token})
        assert res.status_code == 201
        stored = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        assert stored is not None
        assert stored['status'] == 'pending'

    def test_missing_token_rejected(self, client):
        res = client.post('/api/admin-requests', json=FORM_FIELDS)
        assert res.status_code == 400

    def test_invalid_token_rejected(self, client):
        res = client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': 'garbage'})
        assert res.status_code == 400

    def test_missing_fields_rejected(self, client):
        token = make_apply_token()
        res = client.post('/api/admin-requests', json={'token': token})
        assert res.status_code == 400

    def test_email_comes_from_token_not_client(self, client, db):
        """A client-supplied email field must never override the verified one
        baked into the token - otherwise the whole point of the token is moot."""
        token = make_apply_token(email=APPLICANT_EMAIL)
        res = client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': token, 'email': 'attacker@test.com'})
        assert res.status_code == 201
        assert db.admin_requests.find_one({'email': 'attacker@test.com'}) is None
        assert db.admin_requests.find_one({'email': APPLICANT_EMAIL}) is not None

    def test_duplicate_pending_request_rejected(self, client):
        token = make_apply_token()
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': token})
        res = client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        assert res.status_code == 409

    def test_existing_user_email_rejected(self, client, make_user):
        make_user(email=APPLICANT_EMAIL, role='admin')
        token = make_apply_token()
        res = client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': token})
        assert res.status_code == 409

    def test_does_not_create_a_user_account(self, client, db):
        token = make_apply_token()
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': token})
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None


class TestListAdminRequests:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.get('/api/admin-requests', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_lists_submitted_requests(self, client, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        res = client.get('/api/admin-requests', headers=auth_headers())
        assert res.status_code == 200
        emails = [r['email'] for r in res.get_json()['requests']]
        assert APPLICANT_EMAIL in emails

    def test_filters_by_status(self, client, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        res = client.get('/api/admin-requests?status=rejected', headers=auth_headers())
        assert res.get_json()['requests'] == []


class TestApproveAdminRequest:
    def test_approve_creates_admin_account(self, client, db, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())
        assert res.status_code == 201

        created = db.users.find_one({'email': APPLICANT_EMAIL})
        # Defaults to the least-privileged role - the approving admin has to
        # explicitly opt in to granting super-admin access (see TestApproveAsAdmin).
        assert created['role'] == 'lgu_member'
        assert created['permissions'] == {'can_review_applicants': False, 'can_manage_members': False}
        assert created['municipality'] == 'Liliw'

        updated_req = db.admin_requests.find_one({'_id': req['_id']})
        assert updated_req['status'] == 'approved'

    def test_can_approve_with_specific_role_and_permissions(self, client, db, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers(),
                           json={'role': 'lgu_member', 'permissions': {'can_review_applicants': True}})
        assert res.status_code == 201
        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created['permissions'] == {'can_review_applicants': True, 'can_manage_members': False}

    def test_approving_as_super_admin_requires_super_admin_requester(self, client, db, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        # Has can_manage_members (so it gets past the endpoint's permission gate at
        # all) but must still be refused the specific act of minting a super admin.
        lgu_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=lgu_headers, json={'role': 'admin'})
        assert res.status_code == 403

    def test_approved_admin_has_no_usable_starting_password(self, client, db, auth_headers):
        """Approval must never leave a guessable/known password on the account -
        access is only granted through the emailed set-password link."""
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())

        res = client.post('/api/login', json={'email': APPLICANT_EMAIL, 'password': 'guessed-password'})
        assert res.status_code == 401

    def test_requires_admin_role(self, client, auth_headers, db):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_cannot_approve_twice(self, client, db, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        headers = auth_headers()
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)
        assert res.status_code == 400

    def test_invalid_id(self, client, auth_headers):
        res = client.post('/api/admin-requests/not-a-valid-id/approve', headers=auth_headers())
        assert res.status_code == 400


class TestRejectAdminRequest:
    def test_reject_marks_status_without_creating_account(self, client, db, auth_headers):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=auth_headers())
        assert res.status_code == 200
        assert db.admin_requests.find_one({'_id': req['_id']})['status'] == 'rejected'
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None

    def test_requires_admin_role(self, client, auth_headers, db):
        client.post('/api/admin-requests', json={**FORM_FIELDS, 'token': make_apply_token()})
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=auth_headers('student'))
        assert res.status_code == 403
