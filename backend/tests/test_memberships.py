# -*- coding: utf-8 -*-
"""Multi-org membership: student self-service join/switch (memberships.py),
self-service account deletion, and the approval-gated "request to join
another org" flow for admin/staff accounts (admin_management.py)."""
import io
import app as app_module


def make_second_org(db, name='Second Org', code='SECOND01'):
    return db.organizations.insert_one({
        "name": name, "join_code": code, "status": "active",
        "created_at": None, "founding_admin_request_id": None,
    }).inserted_id


class TestLoginBackfillsMembership:
    """Accounts created before the memberships feature shipped have no
    membership row yet - login() creates one lazily so nobody needs a manual
    migration script to run first (see migrate_phase_b_memberships.py, which
    does the same thing in bulk for accounts that never log in again)."""

    def test_login_creates_missing_membership_for_legacy_account(self, client, db):
        from werkzeug.security import generate_password_hash
        org_id = app_module.get_default_organization_id(db)
        user_id = db.users.insert_one({
            'full_name': 'Legacy Member', 'email': 'legacy@test.com',
            'password': generate_password_hash('TestPass123'), 'role': 'lgu_member',
            'status': 'active', 'privacy_consent': True, 'organization_id': org_id,
            'permissions': {'can_review_applicants': True, 'can_manage_members': False, 'can_reset_program': False},
        }).inserted_id
        assert db.memberships.find_one({'user_id': user_id}) is None

        res = client.post('/api/login', json={'email': 'legacy@test.com', 'password': 'TestPass123'})
        assert res.status_code == 200

        membership = db.memberships.find_one({'user_id': user_id, 'organization_id': org_id})
        assert membership is not None
        assert membership['role'] == 'lgu_member'
        assert membership['permissions']['can_review_applicants'] is True

    def test_login_does_not_duplicate_existing_membership(self, client, db, make_user):
        user = make_user(email='notlegacy@test.com', password='TestPass123', role='student')
        client.post('/api/login', json={'email': 'notlegacy@test.com', 'password': 'TestPass123'})
        assert db.memberships.count_documents({'user_id': user['id']}) == 1

    def test_super_admin_login_creates_no_membership(self, client, auth_headers, db):
        auth_headers()
        assert db.memberships.count_documents({}) == 0


class TestStudentSelfServiceJoin:
    def test_join_creates_membership_and_switches(self, client, db, make_user):
        user = make_user(email='stu@test.com', password='TestPass123', role='student')
        second_org_id = make_second_org(db)
        res = client.post('/api/login', json={'email': 'stu@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] == str(second_org_id)

        membership = db.memberships.find_one({'user_id': user['id'], 'organization_id': second_org_id})
        assert membership is not None
        assert membership['role'] == 'student'
        assert db.users.find_one({'_id': user['id']})['organization_id'] == second_org_id

    def test_invalid_join_code_rejected(self, client, make_user):
        make_user(email='stu2@test.com', password='TestPass123', role='student')
        res = client.post('/api/login', json={'email': 'stu2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post('/api/organizations/join', headers=headers, json={'join_code': 'NOTREAL'})
        assert res.status_code == 400

    def test_admin_staff_cannot_use_self_service_join(self, client, auth_headers, db):
        headers = auth_headers('lgu_member')
        make_second_org(db)
        res = client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})
        assert res.status_code == 403

    def test_rejoining_same_org_is_idempotent(self, client, db, make_user):
        user = make_user(email='stu3@test.com', password='TestPass123', role='student')
        org_id = user['organization_id']
        join_code = db.organizations.find_one({'_id': org_id})['join_code']
        res = client.post('/api/login', json={'email': 'stu3@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.post('/api/organizations/join', headers=headers, json={'join_code': join_code})
        assert res.status_code == 200
        assert db.memberships.count_documents({'user_id': user['id'], 'organization_id': org_id}) == 1


class TestSwitchOrganization:
    def test_switch_between_two_memberships(self, client, db, make_user):
        user = make_user(email='switcher@test.com', password='TestPass123', role='student')
        first_org_id = user['organization_id']
        make_second_org(db)
        res = client.post('/api/login', json={'email': 'switcher@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})

        res = client.post('/api/organizations/switch', headers=headers, json={'organization_id': str(first_org_id)})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] == str(first_org_id)

    def test_switch_to_non_member_org_rejected(self, client, db, make_user):
        make_user(email='switcher2@test.com', password='TestPass123', role='student')
        other_org_id = make_second_org(db, name='Other', code='OTHER01')
        res = client.post('/api/login', json={'email': 'switcher2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post('/api/organizations/switch', headers=headers, json={'organization_id': str(other_org_id)})
        assert res.status_code == 404

    def test_super_admin_cannot_switch(self, client, auth_headers):
        res = client.post('/api/organizations/switch', headers=auth_headers(),
                           json={'organization_id': '000000000000000000000000'})
        assert res.status_code == 400


class TestListMemberships:
    def test_lists_all_orgs_with_active_flag(self, client, db, make_user):
        make_user(email='lister@test.com', password='TestPass123', role='student')
        make_second_org(db)
        res = client.post('/api/login', json={'email': 'lister@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})

        # Re-login for a fresh token reflecting the switch, same as the real
        # frontend does via setSession() with the join response's token.
        res = client.post('/api/login', json={'email': 'lister@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/memberships', headers=headers)
        assert res.status_code == 200
        memberships = res.get_json()['memberships']
        assert len(memberships) == 2
        assert sum(1 for m in memberships if m['is_active']) == 1

    def test_super_admin_has_no_memberships(self, client, auth_headers):
        res = client.get('/api/memberships', headers=auth_headers())
        assert res.get_json()['memberships'] == []


class TestDeleteOwnAccount:
    def test_wrong_password_rejected(self, client, make_user):
        make_user(email='del1@test.com', password='TestPass123', role='student')
        res = client.post('/api/login', json={'email': 'del1@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.delete('/api/account', headers=headers, json={'password': 'WrongPass1'})
        assert res.status_code == 401

    def test_success_deletes_user_and_memberships_and_revokes_token(self, client, db, make_user):
        user = make_user(email='del2@test.com', password='TestPass123', role='student')
        res = client.post('/api/login', json={'email': 'del2@test.com', 'password': 'TestPass123'})
        token = res.get_json()['token']
        headers = {'Authorization': f"Bearer {token}"}

        res = client.delete('/api/account', headers=headers, json={'password': 'TestPass123'})
        assert res.status_code == 200
        assert db.users.find_one({'_id': user['id']}) is None
        assert db.memberships.count_documents({'user_id': user['id']}) == 0

        # Token revoked - a follow-up request with the same token 401s.
        res = client.get('/api/profile', headers=headers)
        assert res.status_code == 401

    def test_lgu_admin_seat_holder_blocked(self, client, auth_headers, db):
        from werkzeug.security import generate_password_hash
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers, json={'full_name': 'Seat', 'email': 'seat@test.com'})
        seat_id = create_res.get_json()['admin']['id']
        client.post(f'/api/admins/{seat_id}/transfer-admin', headers=headers)
        db.users.update_one({'email': 'seat@test.com'},
                             {'$set': {'password': generate_password_hash('TestPass123'), 'password_set': True}})

        res = client.post('/api/login', json={'email': 'seat@test.com', 'password': 'TestPass123'})
        seat_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.delete('/api/account', headers=seat_headers, json={'password': 'TestPass123'})
        assert res.status_code == 400
        assert db.users.find_one({'email': 'seat@test.com'}) is not None

    def test_super_admin_cannot_self_delete(self, client, auth_headers):
        res = client.delete('/api/account', headers=auth_headers(), json={'password': 'TestPass123'})
        assert res.status_code == 403


class TestRequestJoinOrg:
    def test_lgu_member_can_submit_request(self, client, auth_headers, db):
        # auth_headers (via make_user -> get_default_organization_id) must run
        # BEFORE a second org is inserted - get_default_organization_id()
        # returns whichever org happens to be first in the collection with no
        # other filter, so creating "Second Org" first would make IT the
        # "default" org the fixture user lands in.
        headers = auth_headers('lgu_member')
        make_second_org(db)
        data = {
            'join_code': 'SECOND01', 'municipality': 'Testville', 'contact_number': '09171234567',
            'message': 'please', 'file': (io.BytesIO(b'fake pdf content'), 'proof.pdf'),
        }
        res = client.post('/api/admin-requests/join-org', headers=headers,
                           data=data, content_type='multipart/form-data')
        assert res.status_code == 201
        req = db.admin_requests.find_one({'request_kind': 'add_membership'})
        assert req is not None
        assert req['status'] == 'pending'

    def test_student_cannot_submit_request(self, client, auth_headers, db):
        headers = auth_headers('student')
        make_second_org(db)
        data = {
            'join_code': 'SECOND01', 'municipality': 'X', 'contact_number': '123',
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        }
        res = client.post('/api/admin-requests/join-org', headers=headers,
                           data=data, content_type='multipart/form-data')
        assert res.status_code == 403

    def test_already_current_org_rejected(self, client, auth_headers, db):
        own_org_id = app_module.get_default_organization_id(db)
        own_code = db.organizations.find_one({'_id': own_org_id})['join_code']
        data = {
            'join_code': own_code, 'municipality': 'X', 'contact_number': '123',
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        }
        res = client.post('/api/admin-requests/join-org', headers=auth_headers('lgu_member'),
                           data=data, content_type='multipart/form-data')
        assert res.status_code == 400


class TestApproveJoinOrgRequest:
    def test_approval_creates_membership_not_new_user(self, client, db, make_user):
        requester = make_user(email='req@test.com', password='TestPass123', role='lgu_member',
                               permissions={'can_review_applicants': False})
        second_org_id = make_second_org(db)
        make_user(email='secondadmin@test.com', password='TestPass123', role='lgu_admin',
                  organization_id=second_org_id)

        res = client.post('/api/login', json={'email': 'req@test.com', 'password': 'TestPass123'})
        requester_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        data = {
            'join_code': 'SECOND01', 'municipality': 'X', 'contact_number': '123',
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        }
        client.post('/api/admin-requests/join-org', headers=requester_headers, data=data, content_type='multipart/form-data')
        req = db.admin_requests.find_one({'request_kind': 'add_membership'})

        res = client.post('/api/login', json={'email': 'secondadmin@test.com', 'password': 'TestPass123'})
        second_admin_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=second_admin_headers,
                           json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 201
        assert 'membership' in res.get_json()

        # No new login was created - same email, same account.
        assert db.users.count_documents({'email': 'req@test.com'}) == 1
        membership = db.memberships.find_one({'user_id': requester['id'], 'organization_id': second_org_id})
        assert membership is not None
        assert membership['role'] == 'lgu_member'
        assert membership['permissions']['can_review_applicants'] is True

    def test_already_member_rejected_on_approve(self, client, db, make_user):
        requester = make_user(email='req2@test.com', password='TestPass123', role='lgu_member')
        second_org_id = make_second_org(db)
        db.admin_requests.insert_one({
            'request_kind': 'add_membership', 'user_id': requester['id'], 'full_name': 'Req2',
            'email': 'req2@test.com', 'password_hash': None, 'municipality': 'X', 'contact_number': '123',
            'message': '', 'proof_of_employment': None, 'status': 'pending', 'first_approval': None,
            'second_approval': None, 'created_at': None, 'reviewed_at': None, 'reviewed_by': None,
            'organization_id': second_org_id, 'is_founding': False,
        })
        db.memberships.insert_one({
            'user_id': requester['id'], 'organization_id': second_org_id, 'role': 'lgu_member',
            'permissions': {'can_review_applicants': False, 'can_manage_members': False, 'can_reset_program': False},
            'municipality': 'X', 'joined_at': None,
        })
        req = db.admin_requests.find_one({'request_kind': 'add_membership'})

        second_admin = make_user(email='secondadmin2@test.com', password='TestPass123', role='lgu_admin',
                                  organization_id=second_org_id)
        res = client.post('/api/login', json={'email': 'secondadmin2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers, json={})
        assert res.status_code == 409
