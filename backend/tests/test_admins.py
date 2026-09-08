# -*- coding: utf-8 -*-
"""Admin account management: list/create/delete, self-delete and
last-admin-standing protections."""


class TestListAdmins:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.get('/api/admins', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_excludes_students_and_super_admin(self, client, db, auth_headers, make_user):
        """Super Admin (role='admin') is a dev/platform account, not part of an LGU's
        own team - it's deliberately invisible here, even to itself."""
        make_user(email='student1@test.com', role='student')
        headers = auth_headers()  # creates admin@test.com, role='admin'
        res = client.get('/api/admins', headers=headers)
        emails = [a['email'] for a in res.get_json()['admins']]
        assert 'student1@test.com' not in emails
        assert 'admin@test.com' not in emails

    def test_lists_lgu_admin_and_lgu_member(self, client, db, auth_headers):
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers,
                                  json={'full_name': 'Member', 'email': 'member@test.com'})
        member_id = create_res.get_json()['admin']['id']
        client.post(f'/api/admins/{member_id}/transfer-admin', headers=headers)

        res = client.get('/api/admins', headers=headers)
        emails = [a['email'] for a in res.get_json()['admins']]
        assert 'member@test.com' in emails


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

    def test_role_field_in_body_is_ignored(self, client, auth_headers, db):
        """Always creates a plain lgu_member - the Admin seat can only be reached
        afterward via POST /api/admins/<id>/transfer-admin."""
        res = client.post('/api/admins', headers=auth_headers(),
                           json={'full_name': 'Sneaky', 'email': 'sneaky@test.com', 'role': 'admin'})
        assert res.status_code == 201
        assert res.get_json()['admin']['role'] == 'lgu_member'
        assert db.users.find_one({'email': 'sneaky@test.com'})['role'] == 'lgu_member'

    def test_created_admin_has_no_usable_starting_password(self, client, auth_headers):
        """A manually created admin must not get a caller-chosen password - access is
        only granted by verifying the emailed one-time code and setting a real one."""
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

    def test_lgu_member_cannot_remove_a_super_admin(self, client, auth_headers, db):
        """Super Admin isn't part of the LGU-facing team-management surface at all -
        even with can_manage_members, looking it up by id here 404s rather than
        ever exposing a 403 that would confirm the id belongs to an admin."""
        auth_headers()  # creates the sole super admin, admin@test.com
        lgu_headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        me = db.users.find_one({'email': 'admin@test.com'})

        res = client.delete(f'/api/admins/{me["_id"]}', headers=lgu_headers)
        assert res.status_code == 404

    def test_delete_target_must_be_a_team_member(self, client, auth_headers, make_user):
        headers = auth_headers()
        other_student = make_user(email='notadmin@test.com', role='student')
        res = client.delete(f'/api/admins/{other_student["id"]}', headers=headers)
        assert res.status_code == 404

    def test_can_remove_a_plain_team_member(self, client, auth_headers, db):
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers,
                                  json={'full_name': 'Second', 'email': 'second@test.com'})
        second_id = create_res.get_json()['admin']['id']

        res = client.delete(f'/api/admins/{second_id}', headers=headers)
        assert res.status_code == 200
        assert db.users.find_one({'email': 'second@test.com'}) is None

    def test_cannot_remove_the_admin_seat_holder(self, client, auth_headers, db):
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers,
                                  json={'full_name': 'Seat Holder', 'email': 'seatholder@test.com'})
        member_id = create_res.get_json()['admin']['id']
        client.post(f'/api/admins/{member_id}/transfer-admin', headers=headers)

        res = client.delete(f'/api/admins/{member_id}', headers=headers)
        assert res.status_code == 400
        assert db.users.find_one({'email': 'seatholder@test.com'}) is not None

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

    def test_rejects_already_activated_admin(self, client, auth_headers, make_user):
        headers = auth_headers()
        # make_user() inserts with a real password and no explicit password_set
        # field - serialize_admin() defaults a missing field to True (activated).
        member = make_user(email='activated@test.com', role='lgu_member')
        res = client.post(f'/api/admins/{member["id"]}/resend-invite', headers=headers)
        assert res.status_code == 400

    def test_succeeds_for_pending_admin(self, client, auth_headers):
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers,
                                  json={'full_name': 'Pending Admin', 'email': 'pending@test.com'})
        pending_id = create_res.get_json()['admin']['id']

        res = client.post(f'/api/admins/{pending_id}/resend-invite', headers=headers)
        assert res.status_code == 200


def get_setup_otp_code(db, email):
    return db.otps.find_one({'email': email, 'purpose': 'admin_setup'})['code']


class TestVerifyAdminSetupOtp:
    def test_correct_code_sets_password_and_logs_in(self, client, db, auth_headers):
        client.post('/api/admins', headers=auth_headers(),
                    json={'full_name': 'New Admin', 'email': 'setup@test.com'})
        code = get_setup_otp_code(db, 'setup@test.com')

        res = client.post('/api/admins/verify-setup-otp',
                           json={'email': 'setup@test.com', 'code': code, 'new_password': 'MyChosenPass123'})
        assert res.status_code == 200
        body = res.get_json()
        assert 'token' in body

        assert db.users.find_one({'email': 'setup@test.com'})['password_set'] is True
        relogin = client.post('/api/login', json={'email': 'setup@test.com', 'password': 'MyChosenPass123'})
        assert relogin.status_code == 200

    def test_wrong_code_rejected(self, client, auth_headers):
        client.post('/api/admins', headers=auth_headers(),
                    json={'full_name': 'New Admin', 'email': 'setup2@test.com'})
        res = client.post('/api/admins/verify-setup-otp',
                           json={'email': 'setup2@test.com', 'code': '000000', 'new_password': 'MyChosenPass123'})
        assert res.status_code == 400

    def test_short_password_rejected(self, client, db, auth_headers):
        client.post('/api/admins', headers=auth_headers(),
                    json={'full_name': 'New Admin', 'email': 'setup3@test.com'})
        code = get_setup_otp_code(db, 'setup3@test.com')
        res = client.post('/api/admins/verify-setup-otp',
                           json={'email': 'setup3@test.com', 'code': code, 'new_password': 'short'})
        assert res.status_code == 400

    def test_missing_fields_rejected(self, client):
        res = client.post('/api/admins/verify-setup-otp', json={'email': 'setup4@test.com'})
        assert res.status_code == 400

    def test_cannot_be_used_against_an_already_activated_admin(self, client, db, auth_headers):
        """Otherwise this endpoint would double as an unauthenticated password
        reset for anyone who can guess a valid code window - forgot-password
        (which requires clicking a link mailed to that address) covers that.
        Bypasses resend-invite's own "already activated" guard by inserting the
        OTP directly, to isolate this endpoint's own check."""
        from datetime import datetime, timedelta
        auth_headers()  # admin@test.com, already has password_set True
        db.otps.insert_one({
            'email': 'admin@test.com', 'purpose': 'admin_setup', 'code': '123456', 'attempts': 0,
            'created_at': datetime.utcnow(), 'expires_at': datetime.utcnow() + timedelta(minutes=10),
        })

        res = client.post('/api/admins/verify-setup-otp',
                           json={'email': 'admin@test.com', 'code': '123456', 'new_password': 'NewPass123'})
        assert res.status_code == 404


class TestResendAdminSetupOtp:
    def test_resend_issues_a_new_working_code(self, client, db, auth_headers):
        client.post('/api/admins', headers=auth_headers(),
                    json={'full_name': 'New Admin', 'email': 'resend-setup@test.com'})
        old_code = get_setup_otp_code(db, 'resend-setup@test.com')

        res = client.post('/api/admins/resend-setup-otp', json={'email': 'resend-setup@test.com'})
        assert res.status_code == 200
        new_code = get_setup_otp_code(db, 'resend-setup@test.com')
        assert new_code != old_code

        fresh = client.post('/api/admins/verify-setup-otp',
                             json={'email': 'resend-setup@test.com', 'code': new_code, 'new_password': 'MyChosenPass123'})
        assert fresh.status_code == 200

    def test_same_response_for_activated_or_unknown_email(self, client, auth_headers):
        auth_headers()  # admin@test.com, already activated
        res1 = client.post('/api/admins/resend-setup-otp', json={'email': 'admin@test.com'})
        res2 = client.post('/api/admins/resend-setup-otp', json={'email': 'no-such-account@test.com'})
        assert res1.get_json() == res2.get_json()
