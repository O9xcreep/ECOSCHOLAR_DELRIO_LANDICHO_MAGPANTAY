# -*- coding: utf-8 -*-
"""LGU-member roles/permissions model: require_permission gating, and the
PUT /api/admins/<id>/permissions endpoint that edits an existing member's
role/permissions."""


class TestRequirePermissionGating:
    def test_super_admin_bypasses_every_permission_check(self, client, auth_headers):
        """role='admin' always passes require_permission, regardless of which
        permission is being checked - matches pre-existing full-access behavior."""
        headers = auth_headers()
        assert client.get('/api/admins', headers=headers).status_code == 200
        assert client.get('/api/applicants', headers=headers).status_code == 200

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

        db.users.update_one({'email': 'lgu_member@test.com'}, {'$set': {'permissions.can_review_applicants': False}})
        assert client.get('/api/applicants', headers=headers).status_code == 403

    def test_student_role_is_forbidden(self, client, auth_headers):
        headers = auth_headers('student')
        assert client.get('/api/admins', headers=headers).status_code == 403


class TestUpdateAdminPermissions:
    def test_super_admin_can_grant_permissions_to_lgu_member(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com',
                                        'role': 'lgu_member', 'permissions': {}})
        member_id = create_res.get_json()['admin']['id']

        res = client.put(f'/api/admins/{member_id}/permissions', headers=admin_headers,
                          json={'role': 'lgu_member', 'permissions': {'can_review_applicants': True}})
        assert res.status_code == 200
        assert res.get_json()['admin']['permissions'] == {'can_review_applicants': True, 'can_manage_members': False}

    def test_lgu_member_with_can_manage_members_can_edit_another_lgu_member(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com', 'role': 'lgu_member'})
        member_id = create_res.get_json()['admin']['id']

        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        res = client.put(f'/api/admins/{member_id}/permissions', headers=manager_headers,
                          json={'role': 'lgu_member', 'permissions': {'can_review_applicants': True}})
        assert res.status_code == 200

    def test_lgu_member_cannot_promote_to_super_admin(self, client, auth_headers, db):
        admin_headers = auth_headers()
        create_res = client.post('/api/admins', headers=admin_headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com', 'role': 'lgu_member'})
        member_id = create_res.get_json()['admin']['id']

        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        res = client.put(f'/api/admins/{member_id}/permissions', headers=manager_headers,
                          json={'role': 'admin'})
        assert res.status_code == 403

    def test_lgu_member_cannot_edit_a_super_admin(self, client, auth_headers, db):
        admin_headers = auth_headers()
        me = db.users.find_one({'email': 'admin@test.com'})
        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})

        res = client.put(f'/api/admins/{me["_id"]}/permissions', headers=manager_headers,
                          json={'role': 'lgu_member', 'permissions': {}})
        assert res.status_code == 403

    def test_cannot_edit_own_permissions(self, client, auth_headers, db):
        manager_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        me = db.users.find_one({'email': 'lgu_member@test.com'})

        res = client.put(f'/api/admins/{me["_id"]}/permissions', headers=manager_headers,
                          json={'role': 'lgu_member', 'permissions': {'can_manage_members': False}})
        assert res.status_code == 400

    def test_invalid_id(self, client, auth_headers):
        res = client.put('/api/admins/not-a-valid-id/permissions', headers=auth_headers(),
                          json={'role': 'lgu_member'})
        assert res.status_code == 400

    def test_not_found(self, client, auth_headers):
        res = client.put('/api/admins/000000000000000000000000/permissions', headers=auth_headers(),
                          json={'role': 'lgu_member'})
        assert res.status_code == 404
