# -*- coding: utf-8 -*-
"""Admin account requests: OTP-verified start step, token-gated submission
(password + proof-of-employment document), and admin approve/reject review,
including two-person approval for can_manage_members grants. Tests default
to "join" mode against the default organization; see test_organizations.py
for the "founding" flow and org-scoped review behavior."""
import io

import app as app_module

APPLICANT_EMAIL = 'juan@lgu.gov.ph'

FORM_FIELDS = {
    'full_name': 'Juan Dela Cruz',
    'password': 'ApplicantPass123',
    'municipality': 'Liliw',
    'contact_number': '09123456789',
    'message': 'Requesting access to review scholarship applications.',
}


def make_apply_token(email=APPLICANT_EMAIL):
    """Shortcut for an already-verified session token, skipping the real
    start -> OTP -> verify-start-otp round trip (covered by TestStartAdminRequest)."""
    return app_module._admin_apply_serializer.dumps({'email': email})


def get_otp_code(db, email):
    return db.otps.find_one({'email': email, 'purpose': 'admin_apply'})['code']


def submit_request(client, db, token=None, include_file=True, filename='proof.pdf', join_code=None, **overrides):
    """multipart/form-data submission matching the endpoint's shape (file +
    join code + form fields). Defaults to "join" mode against the default
    organization unless org_mode is overridden (e.g. org_mode='create')."""
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
        """Fake GridFS never stores/serves bytes, so success here means "past
        the permission check, 404 on the file itself" - not 403."""
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
        # Joining an existing org inherits ITS municipality rather than
        # whatever the applicant typed - set on the default org here so the
        # created account's municipality can be asserted below.
        org_id = app_module.get_default_organization_id(db)
        db.organizations.update_one({'_id': org_id}, {'$set': {'municipality': 'Liliw'}})
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers())
        assert res.status_code == 201

        created = db.users.find_one({'email': APPLICANT_EMAIL})
        # Defaults to the least-privileged role; admin access requires explicit opt-in.
        assert created['role'] == 'lgu_member'
        assert created['permissions'] == {'can_review_applicants': False, 'can_manage_members': False, 'can_reset_program': False}
        assert created['municipality'] == 'Liliw'

        updated_req = db.admin_requests.find_one({'_id': req['_id']})
        assert updated_req['status'] == 'approved'

    def test_join_mode_ignores_submitted_municipality_uses_orgs_own(self, client, db):
        """Joining an EXISTING org always inherits its municipality - the
        submitted form value (still sent by older clients) is ignored."""
        org_id = app_module.get_default_organization_id(db)
        db.organizations.update_one({'_id': org_id}, {'$set': {'municipality': 'San Pablo'}})
        submit_request(client, db, municipality='Something Else Entirely')
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        assert req['municipality'] == 'San Pablo'

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
        """Unlike a directly-added admin, an approved applicant already chose
        their own password when submitting, so it should just work."""
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


class TestSingleApprovalAlwaysFinalizes:
    """Every admin request - regardless of which permissions are granted,
    including can_manage_members - finalizes on exactly one approval. A
    two-different-admins requirement for can_manage_members grants used to
    exist here as a privilege-escalation safeguard, but was removed."""

    def _peer_headers(self, client, make_user, email='peeradmin@test.com', role='lgu_admin', permissions=None):
        user = make_user(email=email, role=role, permissions=permissions)
        token = client.post('/api/login', json={'email': user['email'], 'password': user['password']}).get_json()['token']
        return {'Authorization': f'Bearer {token}'}, user

    def test_peer_admin_single_approval_finalizes_can_manage_members_grant(self, client, db, make_user):
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        headers, _ = self._peer_headers(client, make_user)

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers,
                           json={'permissions': {'can_manage_members': True}})
        assert res.status_code == 201
        created = db.users.find_one({'email': APPLICANT_EMAIL})
        assert created is not None
        assert created['permissions']['can_manage_members'] is True
        assert db.admin_requests.find_one({'_id': req['_id']})['status'] == 'approved'

    def test_super_admin_single_approval_finalizes_can_manage_members_grant(self, client, db, auth_headers):
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
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=auth_headers(),
                           json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 201
        assert db.users.find_one({'email': APPLICANT_EMAIL}) is not None

    def test_a_request_already_stuck_pending_second_approval_can_still_be_resolved(self, client, db, make_user):
        """Legacy recovery case: any request that predates this change and is
        still sitting in pending_second_approval status can be finalized by a
        single approval too, rather than being permanently stuck."""
        submit_request(client, db)
        req = db.admin_requests.find_one({'email': APPLICANT_EMAIL})
        db.admin_requests.update_one({'_id': req['_id']}, {'$set': {'status': 'pending_second_approval'}})
        headers, _ = self._peer_headers(client, make_user)

        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers,
                           json={'permissions': {'can_manage_members': True}})
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


class TestFoundingOrgMunicipality:
    """org_mode='create' has no existing org to inherit a municipality from -
    it's asked once here, and becomes that new org's own municipality for
    everyone who joins it afterward (see test_join_mode_ignores_submitted_
    municipality_uses_orgs_own above)."""

    def test_create_mode_requires_municipality(self, client, db):
        res = submit_request(client, db, org_mode='create', org_name='New LGU', municipality='')
        assert res.status_code == 400

    def test_create_mode_stores_municipality_on_new_org(self, client, db):
        res = submit_request(client, db, org_mode='create', org_name='New LGU', municipality='Pila')
        assert res.status_code == 201
        org = db.organizations.find_one({'name': 'New LGU'})
        assert org is not None
        assert org['municipality'] == 'Pila'
