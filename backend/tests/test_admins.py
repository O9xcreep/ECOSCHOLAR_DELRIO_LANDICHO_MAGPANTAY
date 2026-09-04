# -*- coding: utf-8 -*-
"""Admin account management: list/create/delete, self-delete and
last-admin-standing protections."""


class TestListAdmins:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.get('/api/admins', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_lists_only_admins(self, client, db, auth_headers, make_user):
        make_user(email='student1@test.com', role='student')
        res = client.get('/api/admins', headers=auth_headers())
        emails = [a['email'] for a in res.get_json()['admins']]
        assert 'student1@test.com' not in emails
        assert 'admin@test.com' in emails  # the one auth_headers() itself created


class TestCreateAdmin:
    def test_create_success(self, client, auth_headers):
        res = client.post('/api/admins', headers=auth_headers(),
                           json={'full_name': 'New Admin', 'email': 'newadmin@test.com'})
        assert res.status_code == 201
        admin = res.get_json()['admin']
        assert admin['email'] == 'newadmin@test.com'
        assert admin['password_set'] is False

    def test_duplicate_email_rejected(self, client, auth_headers):
        headers = auth_headers()
        client.post('/api/admins', headers=headers, json={'full_name': 'A', 'email': 'dup@test.com'})
        res = client.post('/api/admins', headers=headers, json={'full_name': 'B', 'email': 'dup@test.com'})
        assert res.status_code == 409

    def test_missing_fields_rejected(self, client, auth_headers):
        res = client.post('/api/admins', headers=auth_headers(), json={'email': 'x@test.com'})
        assert res.status_code == 400

    def test_created_admin_has_no_usable_starting_password(self, client, auth_headers):
        """A manually created admin must not get a caller-chosen password - access is
        only granted through the emailed set-password link, same as approved requests."""
        client.post('/api/admins', headers=auth_headers(),
                    json={'full_name': 'New Admin', 'email': 'nopassword@test.com'})
        res = client.post('/api/login', json={'email': 'nopassword@test.com', 'password': 'guessed-password'})
        assert res.status_code == 401


class TestDeleteAdmin:
    def test_cannot_remove_self(self, client, auth_headers, db):
        headers = auth_headers()
        me = db.users.find_one({'email': 'admin@test.com'})
        res = client.delete(f'/api/admins/{me["_id"]}', headers=headers)
        assert res.status_code == 400

    def test_cannot_remove_last_admin(self, client, auth_headers, db, make_user):
        headers = auth_headers()
        # Only one admin exists (the one auth_headers created) - even trying
        # to remove a *different* nonexistent id should hit the last-admin
        # guard before ever reaching the "not found" case.
        other_student = make_user(email='notadmin@test.com', role='student')
        res = client.delete(f'/api/admins/{other_student["id"]}', headers=headers)
        assert res.status_code == 400
        assert 'last remaining admin' in res.get_json()['error']

    def test_can_remove_other_admin_when_multiple_exist(self, client, auth_headers, db):
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers,
                                  json={'full_name': 'Second', 'email': 'second@test.com'})
        second_id = create_res.get_json()['admin']['id']

        res = client.delete(f'/api/admins/{second_id}', headers=headers)
        assert res.status_code == 200
        assert db.users.find_one({'email': 'second@test.com'}) is None

    def test_invalid_id(self, client, auth_headers):
        res = client.delete('/api/admins/not-a-valid-id', headers=auth_headers())
        assert res.status_code == 400


class TestResendInvite:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.post('/api/admins/000000000000000000000000/resend-invite', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_invalid_id(self, client, auth_headers):
        res = client.post('/api/admins/not-a-valid-id/resend-invite', headers=auth_headers())
        assert res.status_code == 400

    def test_not_found(self, client, auth_headers):
        res = client.post('/api/admins/000000000000000000000000/resend-invite', headers=auth_headers())
        assert res.status_code == 404

    def test_rejects_already_activated_admin(self, client, auth_headers, db):
        headers = auth_headers()
        me = db.users.find_one({'email': 'admin@test.com'})
        res = client.post(f'/api/admins/{me["_id"]}/resend-invite', headers=headers)
        assert res.status_code == 400

    def test_succeeds_for_pending_admin(self, client, auth_headers):
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers,
                                  json={'full_name': 'Pending Admin', 'email': 'pending@test.com'})
        pending_id = create_res.get_json()['admin']['id']

        res = client.post(f'/api/admins/{pending_id}/resend-invite', headers=headers)
        assert res.status_code == 200
