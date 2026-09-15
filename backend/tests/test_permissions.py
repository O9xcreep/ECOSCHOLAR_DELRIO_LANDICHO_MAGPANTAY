# -*- coding: utf-8 -*-
"""LGU-member roles/permissions model: require_permission gating, and the
PUT /api/admins/<id>/permissions endpoint that edits an existing member's
role/permissions."""
import app as app_module


class TestRequirePermissionGating:
    def test_super_admin_bypasses_every_permission_check(self, client, auth_headers):
        """role='admin' always passes require_permission, regardless of which
        permission is being checked - matches pre-existing full-access behavior."""
        headers = auth_headers()
        assert client.get('/api/admins', headers=headers).status_code == 200
        assert client.get('/api/applicants', headers=headers).status_code == 200

    def test_lgu_admin_bypasses_every_permission_check_too(self, client, auth_headers):
        """The one-per-LGU Admin seat gets the same unconditional full access as
        Super Admin - it just isn't visible/reachable through the Team UI."""
        headers = auth_headers('lgu_admin')
        assert client.get('/api/admins', headers=headers).status_code == 200
        assert client.get('/api/applicants', headers=headers).status_code == 200
        assert client.get('/api/settings', headers=headers).status_code == 200

    def test_lgu_member_without_permission_is_forbidden(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_manage_members': False, 'can_review_applicants': False})
        assert client.get('/api/admins', headers=headers).status_code == 403
        assert client.get('/api/applicants', headers=headers).status_code == 403

    def test_lgu_member_with_permission_is_allowed(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        assert client.get('/api/applicants', headers=headers).status_code == 200
        # can_review_applicants doesn't grant can_manage_members's surface
        assert client.get('/api/admins', headers=headers).status_code == 403

    def test_permission_change_takes_effect_without_relogin(self, client, auth_headers, db):
        """Permissions are read fresh from the DB on every request, not trusted from
        the token - revoking access must work immediately on an already-issued session."""
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        assert client.get('/api/applicants', headers=headers).status_code == 200

        # Permissions now live on the membership row (a member's permissions
        # can differ per org) - the flat users.permissions field is just a
        # cache of whichever org is currently active, so has_permission()
        # reads memberships first.
        user = db.users.find_one({'email': 'lgu_member@test.com'})
        db.memberships.update_one(
            {'user_id': user['_id'], 'organization_id': user['organization_id']},
            {'$set': {'permissions.can_review_applicants': False}}
        )
        assert client.get('/api/applicants', headers=headers).status_code == 403

    def test_student_role_is_forbidden(self, client, auth_headers):
        headers = auth_headers('student')
        assert client.get('/api/admins', headers=headers).status_code == 403


class TestUpdateAdminPermissions:
    """Role is no longer settable through this endpoint at all - creating an account
    always makes an lgu_member, and the one Admin seat can only change hands via
    POST /api/admins/<id>/transfer-admin (see TestAdminSeatTransfer)."""

    def test_super_admin_can_grant_permissions_to_lgu_member(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com', 'permissions': {}})
        member_id = create_res.get_json()['admin']['id']

        res = client.put(f'/api/admins/{member_id}/permissions', headers=admin_headers,
                          json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 200
        assert res.get_json()['admin']['permissions'] == {
            'can_review_applicants': True, 'can_manage_members': False, 'can_reset_program': False
        }

    def test_lgu_member_with_can_manage_members_can_edit_another_lgu_member(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com'})
        member_id = create_res.get_json()['admin']['id']

        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        res = client.put(f'/api/admins/{member_id}/permissions', headers=manager_headers,
                          json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 200

    def test_sending_a_role_field_has_no_effect(self, client, auth_headers, db):
        """The endpoint only ever edits permissions - a role field in the body is
        silently ignored, it can never be used to mint or touch the Admin seat."""
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com'})
        member_id = create_res.get_json()['admin']['id']

        res = client.put(f'/api/admins/{member_id}/permissions', headers=admin_headers,
                          json={'role': 'lgu_admin', 'permissions': {'can_review_applicants': True}})
        assert res.status_code == 200
        assert res.get_json()['admin']['role'] == 'lgu_member'
        assert db.users.count_documents({'role': 'lgu_admin'}) == 0

    def test_cannot_target_super_admin(self, client, auth_headers, make_user):
        """Super Admin isn't reachable through this LGU-facing endpoint at all -
        looking it up by id 404s, same as any other id that isn't an lgu_member."""
        admin_headers = auth_headers()
        other_super_admin = make_user(email='othersuperadmin@test.com', role='admin')

        res = client.put(f'/api/admins/{other_super_admin["id"]}/permissions', headers=admin_headers,
                          json={'permissions': {}})
        assert res.status_code == 404

    def test_cannot_target_the_admin_seat_holder(self, client, auth_headers, db):
        lgu_admin_headers = auth_headers('lgu_admin')
        admin_user = db.users.find_one({'email': 'lgu_admin@test.com'})
        super_admin_headers = auth_headers()

        res = client.put(f'/api/admins/{admin_user["_id"]}/permissions', headers=super_admin_headers,
                          json={'permissions': {}})
        assert res.status_code == 404

    def test_cannot_edit_own_permissions(self, client, auth_headers, db):
        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        me = db.users.find_one({'email': 'lgu_member@test.com'})

        res = client.put(f'/api/admins/{me["_id"]}/permissions', headers=manager_headers,
                          json={'permissions': {'can_manage_members': False}})
        assert res.status_code == 400

    def test_invalid_id(self, client, auth_headers):
        res = client.put('/api/admins/not-a-valid-id/permissions', headers=auth_headers(), json={})
        assert res.status_code == 400

    def test_not_found(self, client, auth_headers):
        res = client.put('/api/admins/000000000000000000000000/permissions', headers=auth_headers(), json={})
        assert res.status_code == 404


class TestAdminSeatTransfer:
    """POST /api/admins/<id>/transfer-admin - exactly one lgu_admin can exist. Super
    Admin can assign or reassign it at any time; once held, only the current holder
    can pass it on; a plain lgu_member never can, no matter what else they're granted."""

    def test_super_admin_assigns_the_first_admin(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com'})
        member_id = create_res.get_json()['admin']['id']

        res = client.post(f'/api/admins/{member_id}/transfer-admin', headers=admin_headers)
        assert res.status_code == 200
        assert res.get_json()['admin']['role'] == 'lgu_admin'
        assert db.users.count_documents({'role': 'lgu_admin'}) == 1

    def test_current_admin_can_pass_it_on(self, client, auth_headers, db):
        from werkzeug.security import generate_password_hash
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'First', 'email': 'first@test.com'})
        first_id = create_res.get_json()['admin']['id']
        client.post(f'/api/admins/{first_id}/transfer-admin', headers=admin_headers)
        # create_admin_account() sends a set-password invite, not a usable password;
        # set one directly since this test only needs a working login.
        db.users.update_one({'email': 'first@test.com'},
                             {'$set': {'password': generate_password_hash('TestPass123'), 'password_set': True}})

        first_res = client.post('/api/login', json={'email': 'first@test.com', 'password': 'TestPass123'})
        first_headers = {'Authorization': f"Bearer {first_res.get_json()['token']}"}

        create_res2 = client.post('/api/admins', headers=first_headers,
                                   json={'full_name': 'Second', 'email': 'second@test.com'})
        second_id = create_res2.get_json()['admin']['id']

        res = client.post(f'/api/admins/{second_id}/transfer-admin', headers=first_headers)
        assert res.status_code == 200
        assert res.get_json()['admin']['role'] == 'lgu_admin'

        first_user = db.users.find_one({'email': 'first@test.com'})
        assert first_user['role'] == 'lgu_member'
        assert first_user['permissions'] == {'can_review_applicants': False, 'can_manage_members': False, 'can_reset_program': False}
        assert db.users.count_documents({'role': 'lgu_admin'}) == 1

    def test_lgu_member_cannot_transfer_even_with_manage_members(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Target', 'email': 'target@test.com'})
        target_id = create_res.get_json()['admin']['id']

        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        res = client.post(f'/api/admins/{target_id}/transfer-admin', headers=manager_headers)
        assert res.status_code == 403

    def test_non_holder_lgu_admin_cannot_transfer(self, client, db):
        """Defensive: if somehow two lgu_admin memberships existed for the same
        org, only the actual current holder (found via role='lgu_admin' lookup)
        can transfer - a stale/duplicate one can't. (Normal flows never create
        a second one.)"""
        from werkzeug.security import generate_password_hash
        org_id = app_module.get_default_organization_id(db)
        real_admin_id = db.users.insert_one({'full_name': 'Real Admin', 'email': 'realadmin@test.com',
                              'password': generate_password_hash('TestPass123'), 'role': 'lgu_admin',
                              'status': 'active', 'privacy_consent': True, 'organization_id': org_id}).inserted_id
        stale_admin_id = db.users.insert_one({'full_name': 'Stale Admin', 'email': 'staleadmin@test.com',
                              'password': generate_password_hash('TestPass123'), 'role': 'lgu_admin',
                              'status': 'active', 'privacy_consent': True, 'organization_id': org_id}).inserted_id
        target = db.users.insert_one({'full_name': 'Target', 'email': 'target2@test.com',
                                       'password': generate_password_hash('TestPass123'), 'role': 'lgu_member',
                                       'status': 'active', 'privacy_consent': True, 'organization_id': org_id,
                                       'permissions': {'can_manage_members': True, 'can_review_applicants': False, 'can_reset_program': False}}).inserted_id
        # Transfer/membership lookups now go through `memberships`, not raw
        # users.organization_id - mirror that for these hand-crafted fixtures.
        db.memberships.insert_one({'user_id': real_admin_id, 'organization_id': org_id, 'role': 'lgu_admin', 'permissions': None, 'municipality': None})
        db.memberships.insert_one({'user_id': stale_admin_id, 'organization_id': org_id, 'role': 'lgu_admin', 'permissions': None, 'municipality': None})
        db.memberships.insert_one({'user_id': target, 'organization_id': org_id, 'role': 'lgu_member',
                                    'permissions': {'can_manage_members': True, 'can_review_applicants': False, 'can_reset_program': False},
                                    'municipality': None})

        res = client.post('/api/login', json={'email': 'staleadmin@test.com', 'password': 'TestPass123'})
        stale_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post(f'/api/admins/{target}/transfer-admin', headers=stale_headers)
        assert res.status_code == 403

    def test_target_must_be_an_existing_lgu_member(self, client, auth_headers, db):
        admin_headers = auth_headers()
        res = client.post('/api/admins/000000000000000000000000/transfer-admin', headers=admin_headers)
        assert res.status_code == 404

    def test_cannot_transfer_to_self(self, client, auth_headers, db):
        admin_headers = auth_headers()
        me = db.users.find_one({'email': 'admin@test.com'})
        res = client.post(f'/api/admins/{me["_id"]}/transfer-admin', headers=admin_headers)
        assert res.status_code == 400


class TestDocumentAccess:
    """GET /api/documents/<id> and /api/documents/<id>/view accept a super
    admin, an lgu_member with can_review_applicants, or the applicant's own
    account."""

    def login(self, client, make_user, **kwargs):
        user = make_user(**kwargs)
        res = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = res.get_json()['token']
        return user, {'Authorization': f'Bearer {token}'}

    def test_lgu_member_with_permission_can_list_documents(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({'full_name': 'A', 'email': 'a@test.com', 'documents': []}).inserted_id
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        res = client.get(f'/api/documents/{applicant_id}', headers=headers)
        assert res.status_code == 200

    def test_lgu_member_without_permission_cannot_list_documents(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({'full_name': 'A', 'email': 'a@test.com', 'documents': []}).inserted_id
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': False})
        res = client.get(f'/api/documents/{applicant_id}', headers=headers)
        assert res.status_code == 403

    def test_owning_student_can_list_their_own_documents(self, client, db, make_user):
        user, headers = self.login(client, make_user, email='owner@test.com', role='student')
        applicant_id = db.applicants.insert_one(
            {'full_name': 'A', 'email': 'owner@test.com', 'documents': [], 'user_id': user['id']}
        ).inserted_id
        res = client.get(f'/api/documents/{applicant_id}', headers=headers)
        assert res.status_code == 200

    def test_other_student_cannot_list_someone_elses_documents(self, client, db, make_user):
        owner, _ = self.login(client, make_user, email='owner2@test.com', role='student')
        _, other_headers = self.login(client, make_user, email='other@test.com', role='student')
        applicant_id = db.applicants.insert_one(
            {'full_name': 'A', 'email': 'owner2@test.com', 'documents': [], 'user_id': owner['id']}
        ).inserted_id
        res = client.get(f'/api/documents/{applicant_id}', headers=other_headers)
        assert res.status_code == 403

    def test_lgu_member_with_permission_can_reach_view_endpoint(self, client, db, auth_headers):
        """Fake GridFS (see conftest.py) has no file to serve, so success here
        means "past the permission check, 404 on the file itself" - not 403."""
        applicant_id = db.applicants.insert_one({'full_name': 'A', 'email': 'a@test.com', 'documents': []}).inserted_id
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        res = client.get(f'/api/documents/{applicant_id}/view?document_name=School+ID', headers=headers)
        assert res.status_code == 404
        assert res.get_json()['error'] != 'Forbidden'

    def test_lgu_member_without_permission_forbidden_from_view_endpoint(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({'full_name': 'A', 'email': 'a@test.com', 'documents': []}).inserted_id
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': False})
        res = client.get(f'/api/documents/{applicant_id}/view?document_name=School+ID', headers=headers)
        assert res.status_code == 403
