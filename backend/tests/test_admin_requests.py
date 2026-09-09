# -*- coding: utf-8 -*-
"""Admin account requests: OTP-verified start step, token-gated submission
(with a password and a valid ID/proof-of-employment document chosen upfront),
and admin approve/reject review - including two-person approval for grants
that include can_manage_members. Most tests here default to "join" mode
against the auto-created default organization (multi-tenancy Phase A/B) -
see test_organizations.py for the create-a-new-org ("founding") flow itself
and the org-scoped review behavior."""
import io

import app as app_module

APPLICANT_EMAIL = 'juan@lgu.gov.ph'

FORM_FIELDS = {
    'full_name': 'Juan Dela Cruz',
    'password': 'ApplicantPass123',
    'office': 'Municipal Social Welfare and Development Office',
    'municipality': 'Liliw',
    'contact_number': '09123456789',
    'message': 'Requesting access to review scholarship applications.',
}


def make_apply_token(email=APPLICANT_EMAIL):
    """Test shortcut for endpoints that need an already-verified session token,
    without going through the real start -> OTP -> verify-start-otp round trip
    (that round trip itself is covered by TestStartAdminRequest below)."""
    return app_module._admin_apply_serializer.dumps({'email': email})


def get_otp_code(db, email):
    return db.otps.find_one({'email': email, 'purpose': 'admin_apply'})['code']


def submit_request(client, db, token=None, include_file=True, filename='proof.pdf', join_code=None, **overrides):
    """multipart/form-data submission - the real shape the endpoint expects
    now that a document upload and an org join code are both required
    alongside the plain form fields. Defaults to "join" mode against the
    auto-created default organization, unless the caller passes org_mode
    explicitly (e.g. org_mode='create')."""
    if token is None:
        token = make_apply_token()
    if join_code is None and overrides.get('org_mode') != 'create':
        default_org = db.organizations.find_one({"_id": app_module.get_default_organization_id(db)})
        join_code = default_org['join_code']
    fields = {**FORM_FIELDS, 'token': token, 'join_code': join_code or '', **overrides}
    data = {k: str(v) for k, v in fields.items()}
    if include_file:
        data['file'] = (io.BytesIO(b'%PDF-1.4 fake proof of employment'), filename)
    return client.post('/api/admin-requests', data=data)


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


class TestVerifyStartOtp:
    def test_correct_code_returns_a_session_token(self, client, db):
        client.post('/api/admin-requests/start', json={'email': APPLICANT_EMAIL})
        code = get_otp_code(db, APPLICANT_EMAIL)

        res = client.post('/api/admin-requests/verify-start-otp', json={'email': APPLICANT_EMAIL, 'code': code})
        assert res.status_code == 200
        assert 'token' in res.get_json()

    def test_token_from_otp_verifies_to_the_right_email(self, client, db):
        client.post('/api/admin-requests/start', json={'email': APPLICANT_EMAIL})
        code = get_otp_code(db, APPLICANT_EMAIL)
        token = client.post('/api/admin-requests/verify-start-otp', json={'email': APPLICANT_EMAIL, 'code': code}).get_json()['token']

        res = client.get(f'/api/admin-requests/verify-token?token={token}')
        assert res.status_code == 200
        assert res.get_json()['email'] == APPLICANT_EMAIL

    def test_wrong_code_rejected(self, client):
        client.post('/api/admin-requests/start', json={'email': APPLICANT_EMAIL})
        res = client.post('/api/admin-requests/verify-start-otp', json={'email': APPLICANT_EMAIL, 'code': '000000'})
        assert res.status_code == 400

    def test_missing_fields_rejected(self, client):
        res = client.post('/api/admin-requests/verify-start-otp', json={'email': APPLICANT_EMAIL})
        assert res.status_code == 400


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
        res = submit_request(client, db)
        assert res.status_code == 201
        stored = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        assert stored is not None
        assert stored['status'] == 'pending'
        assert 'password_hash' in stored
        assert stored['password_hash'] != FORM_FIELDS['password']  # never stored in plaintext

    def test_missing_token_rejected(self, client):
        res = client.post('/api/admin-requests', data={
            **{k: str(v) for k, v in FORM_FIELDS.items()},
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        })
        assert res.status_code == 400

    def test_invalid_token_rejected(self, client, db):
        res = submit_request(client, db, token='garbage')
        assert res.status_code == 400

    def test_missing_fields_rejected(self, client):
        token = make_apply_token()
        res = client.post('/api/admin-requests', data={'token': token, 'file': (io.BytesIO(b'fake'), 'proof.pdf')})
        assert res.status_code == 400

    def test_short_password_rejected(self, client, db):
        res = submit_request(client, db, password='short')
        assert res.status_code == 400

    def test_email_comes_from_token_not_client(self, client, db):
        """A client-supplied email field must never override the verified one
        baked into the token - otherwise the whole point of the token is moot."""
        token = make_apply_token(email=APPLICANT_EMAIL)
        res = submit_request(client, db, token=token, email='attacker@test.com')
        assert res.status_code == 201
        assert db.admin_requests.find_one({'email': 'attacker@test.com'}) is None
        assert db.admin_requests.find_one({'email': APPLICANT_EMAIL}) is not None

    def test_duplicate_pending_request_rejected(self, client, db):
        submit_request(client, db)
        res = submit_request(client, db, token=make_apply_token())
        assert res.status_code == 409

    def test_existing_user_email_rejected(self, client, db, make_user):
        make_user(email=APPLICANT_EMAIL, role='admin')
        res = submit_request(client, db)
        assert res.status_code == 409

    def test_does_not_create_a_user_account(self, client, db):
        submit_request(client, db)
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None

    def test_missing_file_rejected(self, client, db):
        res = submit_request(client, db, include_file=False)
        assert res.status_code == 400
        assert db.admin_requests.find_one({'email': APPLICANT_EMAIL}) is None

    def test_disallowed_file_extension_rejected(self, client, db):
        res = submit_request(client, db, filename='proof.exe')
        assert res.status_code == 400
        assert db.admin_requests.find_one({'email': APPLICANT_EMAIL}) is None

    def test_stores_proof_of_employment_in_gridfs(self, client, db):
        res = submit_request(client, db, filename='id-card.png')
        assert res.status_code == 201
        stored = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        assert stored['proof_of_employment']['gridfs_id'] is not None
        assert stored['proof_of_employment']['filename'] == 'id-card.png'


class TestListAdminRequests:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.get('/api/admin-requests', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_lists_submitted_requests(self, client, db, auth_headers):
        submit_request(client, db)
        res = client.get('/api/admin-requests', headers=auth_headers())
        assert res.status_code == 200
        emails = [r['email'] for r in res.get_json()['requests']]
        assert APPLICANT_EMAIL in emails

    def test_lists_include_proof_of_employment_filename(self, client, db, auth_headers):
        submit_request(client, db, filename='appointment-letter.pdf')
        res = client.get('/api/admin-requests?status=pending', headers=auth_headers())
        req = next(r for r in res.get_json()['requests'] if r['email'] == APPLICANT_EMAIL)
        assert req['proof_of_employment_filename'] == 'appointment-letter.pdf'

    def test_filters_by_status(self, client, db, auth_headers):
        submit_request(client, db)
        res = client.get('/api/admin-requests?status=rejected', headers=auth_headers())
        assert res.get_json()['requests'] == []


class TestViewProofOfEmployment:
    def test_requires_can_manage_members(self, client, db, auth_headers):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        res = client.get(f'/api/admin-requests/{req["_id"]}/proof-of-employment', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_admin_can_reach_the_view_endpoint(self, client, db, auth_headers):
        """Fake GridFS (see conftest.py) never actually stores/serves bytes, so
        success here means "past the permission check, 404 on the file itself
        from _fs.get()" - not 403 or a request-not-found 404."""
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        res = client.get(f'/api/admin-requests/{req["_id"]}/proof-of-employment', headers=auth_headers())
        assert res.status_code == 404
        assert res.get_json()['error'] == 'File not found on server'

    def test_invalid_id_rejected(self, client, auth_headers):
        res = client.get('/api/admin-requests/not-a-valid-id/proof-of-employment', headers=auth_headers())
        assert res.status_code == 400

    def test_unknown_request_404s(self, client, auth_headers):
        res = client.get('/api/admin-requests/000000000000000000000000/proof-of-employment', headers=auth_headers())
        assert res.status_code == 404


class TestApproveAdminRequest:
    def test_approve_creates_admin_account(self, client, db, auth_headers):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())
        assert res.status_code == 201

        created = db.users.find_one({'email': APPLICANT_EMAIL})
        # Defaults to the least-privileged role - the approving admin has to
        # explicitly opt in to granting super-admin access (see TestApproveAsAdmin).
        assert created['role'] == 'lgu_member'
        assert created['permissions'] == {'can_review_applicants': False, 'can_manage_members': False, 'can_reset_program': False}
        assert created['municipality'] == 'Liliw'

        updated_req = db.admin_requests.find_one({'_id': req['_id']})
        assert updated_req['status'] == 'approved'

    def test_can_approve_with_specific_permissions(self, client, db, auth_headers):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers(),
                           json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 201
        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created['permissions'] == {'can_review_applicants': True, 'can_manage_members': False, 'can_reset_program': False}

    def test_a_role_field_in_the_body_is_ignored(self, client, db, auth_headers):
        """Approving always creates a plain lgu_member - the Admin seat can only be
        reached afterward via POST /api/admins/<id>/transfer-admin."""
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        lgu_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=lgu_headers, json={'role': 'admin'})
        assert res.status_code == 201
        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created['role'] == 'lgu_member'

    def test_approved_admin_can_log_in_with_the_password_they_chose(self, client, db, auth_headers):
        """Unlike a directly-added admin (who gets a random placeholder password and
        an emailed set-password link), an approved applicant already proved their
        email and chose their own password when submitting - it should just work."""
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())

        res = client.post('/api/login', json={'email': APPLICANT_EMAIL, 'password': FORM_FIELDS['password']})
        assert res.status_code == 200

        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created['password_set'] is True

    def test_wrong_password_still_rejected(self, client, db, auth_headers):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())

        res = client.post('/api/login', json={'email': APPLICANT_EMAIL, 'password': 'guessed-password'})
        assert res.status_code == 401

    def test_requires_admin_role(self, client, auth_headers, db):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_cannot_approve_twice(self, client, db, auth_headers):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        headers = auth_headers()
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)
        assert res.status_code == 400

    def test_invalid_id(self, client, auth_headers):
        res = client.post('/api/admin-requests/not-a-valid-id/approve', headers=auth_headers())
        assert res.status_code == 400


class TestTwoPersonApprovalForManageMembers:
    """Granting can_manage_members is the one privilege-escalation risk in this
    flow - it lets the new account approve/add further admins - so it alone
    needs two DIFFERENT existing admins to sign off before the account exists."""

    def _peer_headers(self, client, make_user, email='peeradmin@test.com', role='lgu_admin', permissions=None):
        """A non-Super-Admin approver - an org's own lgu_admin or a lgu_member
        granted can_manage_members - the actual peer-review case this whole
        class is testing. (Super Admin's own single-approval bypass is
        covered separately below.)"""
        user = make_user(email=email, role=role, permissions=permissions)
        token = client.post('/api/login', json={'email': user['email'], 'password': user['password']}).get_json()['token']
        return {'Authorization': f'Bearer {token}'}, user

    def test_granting_can_manage_members_does_not_create_account_on_first_approval(self, client, db, make_user):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        headers, _ = self._peer_headers(client, make_user)

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers,
                           json={'permissions': {'can_manage_members': True}})
        assert res.status_code == 200
        assert 'admin' not in res.get_json()
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None

        updated = db.admin_requests.find_one({'_id': req['_id']})
        assert updated['status'] == 'pending_second_approval'
        assert updated['first_approval']['permissions_granted']['can_manage_members'] is True

    def test_second_different_admin_finalizes_it(self, client, db, make_user):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        headers1, admin1 = self._peer_headers(client, make_user, email='admin1@test.com', role='lgu_admin')
        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers1,
                    json={'permissions': {'can_manage_members': True}})

        headers2, admin2 = self._peer_headers(client, make_user, email='admin2@test.com', role='lgu_member',
                                               permissions={'can_manage_members': True})
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers2)

        assert res.status_code == 201
        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created is not None
        assert created['permissions']['can_manage_members'] is True

        updated = db.admin_requests.find_one({'_id': req['_id']})
        assert updated['status'] == 'approved'
        assert updated['second_approval']['admin_id'] == str(admin2['id'])

    def test_same_admin_cannot_give_both_approvals(self, client, db, make_user):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        headers, _ = self._peer_headers(client, make_user)

        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers,
                    json={'permissions': {'can_manage_members': True}})
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers)

        assert res.status_code == 400
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None

    def test_rejecting_a_pending_second_approval_request_works(self, client, db, make_user):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        headers, _ = self._peer_headers(client, make_user)

        client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers,
                    json={'permissions': {'can_manage_members': True}})
        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=headers)

        assert res.status_code == 200
        assert db.admin_requests.find_one({'_id': req['_id']})['status'] == 'rejected'
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None

    def test_super_admin_single_approval_finalizes_can_manage_members_grant(self, client, db, auth_headers):
        """The platform Super Admin is a higher trust tier that already
        bypasses every other permission check (including granting
        can_manage_members directly via PUT /api/admins/<id>/permissions,
        with no second approval there either) - so unlike a peer LGU admin,
        Super Admin's own approval finalizes the account immediately, same
        as the founding-org path."""
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers(),
                           json={'permissions': {'can_manage_members': True}})
        assert res.status_code == 201
        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created is not None
        assert created['permissions']['can_manage_members'] is True
        assert db.admin_requests.find_one({'_id': req['_id']})['status'] == 'approved'

    def test_permissions_without_can_manage_members_still_need_only_one_approval(self, client, db, auth_headers):
        """Regression check: the common case (review-only access) must not be
        slowed down by the two-person rule."""
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers(),
                           json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 201
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is not None


class TestRejectAdminRequest:
    def test_reject_marks_status_without_creating_account(self, client, db, auth_headers):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=auth_headers())
        assert res.status_code == 200
        assert db.admin_requests.find_one({'_id': req['_id']})['status'] == 'rejected'
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is None

    def test_requires_admin_role(self, client, auth_headers, db):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        res = client.post(f'/api/admin-requests/{req["_id"]}/reject', headers=auth_headers('student'))
        assert res.status_code == 403
