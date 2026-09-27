# -*- coding: utf-8 -*-
"""Register / login / forgot-password / reset-password / change-password."""
from unittest.mock import patch

from werkzeug.security import check_password_hash

import app as app_module


def default_join_code():
    """Reaches app_module's own db handle directly (the same object the `db`
    fixture returns) so register_payload() stays a plain helper any test can
    call without threading a `db` fixture through every signature."""
    db = app_module._mongo_db
    org_id = app_module.get_default_organization_id(db)
    return db.organizations.find_one({"_id": org_id})["join_code"]


def register_payload(email='juan@test.com', **overrides):
    payload = {
        'full_name': 'Juan Dela Cruz', 'email': email, 'password': 'ValidPass123',
        'join_code': default_join_code(),
    }
    payload.update(overrides)
    return payload


def fake_google_user(email='google@test.com', name='Google User', sub='google-sub-123'):
    """Stands in for a verified Google Identity Services credential - tests
    patch auth.verify_google_credential to return this instead of making a
    real call to Google."""
    return {'email': email, 'name': name, 'sub': sub}


def get_otp_code(db, email):
    return db.otps.find_one({'email': email, 'purpose': 'register'})['code']


class TestRegister:
    def test_register_success(self, client, db):
        res = client.post('/api/register', json=register_payload())
        assert res.status_code == 201
        body = res.get_json()
        assert body['email'] == 'juan@test.com'
        assert 'token' not in body

        user = db.users.find_one({'email': 'juan@test.com'})
        assert user['email_verified'] is False

    def test_registered_account_cannot_log_in_before_verifying(self, client):
        client.post('/api/register', json=register_payload())
        res = client.post('/api/login', json={'email': 'juan@test.com', 'password': 'ValidPass123'})
        assert res.status_code == 403
        assert res.get_json()['needs_verification'] is True

    def test_register_duplicate_email(self, client):
        client.post('/api/register', json=register_payload())
        res = client.post('/api/register', json=register_payload())
        assert res.status_code == 409

    def test_register_short_password(self, client):
        res = client.post('/api/register', json=register_payload(password='short'))
        assert res.status_code == 400

    def test_register_missing_fields(self, client):
        res = client.post('/api/register', json={'full_name': 'X', 'email': 'x@test.com', 'password': 'ValidPass123'})
        assert res.status_code == 400


class TestRegisterGoogle:
    """POST /api/register/google - Google already proved the email is real,
    so this skips the OTP step entirely and the account is usable right away."""

    def test_creates_a_new_verified_account_with_no_otp(self, client, db):
        with patch.object(app_module.auth, 'verify_google_credential', return_value=fake_google_user()):
            res = client.post('/api/register/google', json={'credential': 'fake', 'join_code': default_join_code()})
        assert res.status_code == 201, res.get_json()
        body = res.get_json()
        assert body['user']['role'] == 'student'
        assert body['user']['email'] == 'google@test.com'
        assert 'token' in body

        user = db.users.find_one({'email': 'google@test.com'})
        assert user['email_verified'] is True
        assert user['google_id'] == 'google-sub-123'
        assert user['password_set'] is False

    def test_missing_join_code_rejected(self, client):
        with patch.object(app_module.auth, 'verify_google_credential', return_value=fake_google_user()):
            res = client.post('/api/register/google', json={'credential': 'fake'})
        assert res.status_code == 400

    def test_invalid_join_code_rejected(self, client):
        with patch.object(app_module.auth, 'verify_google_credential', return_value=fake_google_user()):
            res = client.post('/api/register/google', json={'credential': 'fake', 'join_code': 'NOPE1234'})
        assert res.status_code == 400

    def test_invalid_credential_rejected(self, client):
        with patch.object(app_module.auth, 'verify_google_credential', side_effect=ValueError('bad token')):
            res = client.post('/api/register/google', json={'credential': 'garbage', 'join_code': default_join_code()})
        assert res.status_code == 400

    def test_existing_email_in_same_org_signs_in_instead_of_erroring(self, client, db, make_user):
        make_user(email='google@test.com', role='student')
        with patch.object(app_module.auth, 'verify_google_credential', return_value=fake_google_user()):
            res = client.post('/api/register/google', json={'credential': 'fake', 'join_code': default_join_code()})
        assert res.status_code == 200
        assert res.get_json()['user']['email'] == 'google@test.com'
        assert db.users.find_one({'email': 'google@test.com'})['google_id'] == 'google-sub-123'

    def test_existing_email_in_a_different_org_is_rejected(self, client, db, make_user):
        make_user(email='google@test.com', role='student')
        other_org_id = db.organizations.insert_one({
            'name': 'Other LGU', 'join_code': 'OTHRORG1', 'status': 'active',
        }).inserted_id
        with patch.object(app_module.auth, 'verify_google_credential', return_value=fake_google_user()):
            res = client.post('/api/register/google', json={'credential': 'fake', 'join_code': 'OTHRORG1'})
        assert res.status_code == 409


class TestLoginGoogle:
    """POST /api/login/google - only ever signs in an EXISTING account;
    no matching account points the caller at registration instead."""

    def test_logs_in_an_existing_account_and_links_it(self, client, db, make_user):
        make_user(email='google-login@test.com', role='student')
        with patch.object(app_module.auth, 'verify_google_credential',
                           return_value=fake_google_user(email='google-login@test.com')):
            res = client.post('/api/login/google', json={'credential': 'fake'})
        assert res.status_code == 200
        assert res.get_json()['user']['email'] == 'google-login@test.com'
        assert db.users.find_one({'email': 'google-login@test.com'})['google_id'] == 'google-sub-123'

    def test_finds_by_linked_google_id_even_if_email_changed_since(self, client, db, make_user):
        user = make_user(email='already-linked@test.com', role='student')
        db.users.update_one({'_id': user['id']}, {'$set': {'google_id': 'sub-999'}})
        with patch.object(app_module.auth, 'verify_google_credential',
                           return_value={'email': 'new-address@test.com', 'name': 'X', 'sub': 'sub-999'}):
            res = client.post('/api/login/google', json={'credential': 'fake'})
        assert res.status_code == 200
        assert res.get_json()['user']['email'] == 'already-linked@test.com'

    def test_no_matching_account_returns_404(self, client):
        with patch.object(app_module.auth, 'verify_google_credential', return_value=fake_google_user()):
            res = client.post('/api/login/google', json={'credential': 'fake'})
        assert res.status_code == 404
        assert res.get_json()['needs_registration'] is True

    def test_invalid_credential_rejected(self, client):
        with patch.object(app_module.auth, 'verify_google_credential', side_effect=ValueError('bad token')):
            res = client.post('/api/login/google', json={'credential': 'garbage'})
        assert res.status_code == 400

    def test_missing_credential_rejected(self, client):
        res = client.post('/api/login/google', json={})
        assert res.status_code == 400


class TestRegisterVerifyOtp:
    def test_correct_code_verifies_and_logs_in(self, client, db):
        client.post('/api/register', json=register_payload())
        code = get_otp_code(db, 'juan@test.com')

        res = client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': code})
        assert res.status_code == 200
        body = res.get_json()
        assert 'token' in body
        assert db.users.find_one({'email': 'juan@test.com'})['email_verified'] is True

    def test_verified_account_can_then_log_in(self, client, db):
        client.post('/api/register', json=register_payload())
        code = get_otp_code(db, 'juan@test.com')
        client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': code})

        res = client.post('/api/login', json={'email': 'juan@test.com', 'password': 'ValidPass123'})
        assert res.status_code == 200

    def test_wrong_code_rejected(self, client, db):
        client.post('/api/register', json=register_payload())
        res = client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': '000000'})
        assert res.status_code == 400
        assert db.users.find_one({'email': 'juan@test.com'})['email_verified'] is False

    def test_wrong_code_does_not_consume_the_real_one(self, client, db):
        """A typo shouldn't burn the user's one shot - the real code must still work after."""
        client.post('/api/register', json=register_payload())
        code = get_otp_code(db, 'juan@test.com')
        client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': '000000'})
        res = client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': code})
        assert res.status_code == 200

    def test_too_many_attempts_locks_out_the_code(self, client, db):
        client.post('/api/register', json=register_payload())
        code = get_otp_code(db, 'juan@test.com')
        for _ in range(5):
            client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': '000000'})
        res = client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': code})
        assert res.status_code == 400
        assert 'Too many' in res.get_json()['error']

    def test_missing_fields_rejected(self, client):
        res = client.post('/api/register/verify-otp', json={'email': 'juan@test.com'})
        assert res.status_code == 400


class TestResendRegisterOtp:
    def test_resend_issues_a_new_working_code(self, client, db):
        client.post('/api/register', json=register_payload())
        old_code = get_otp_code(db, 'juan@test.com')

        res = client.post('/api/register/resend-otp', json={'email': 'juan@test.com'})
        assert res.status_code == 200
        new_code = get_otp_code(db, 'juan@test.com')
        assert new_code != old_code

        # the old code must no longer work
        stale = client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': old_code})
        assert stale.status_code == 400

        fresh = client.post('/api/register/verify-otp', json={'email': 'juan@test.com', 'code': new_code})
        assert fresh.status_code == 200

    def test_same_response_for_already_verified_or_unknown_email(self, client, make_user):
        make_user(email='already-verified@test.com')  # make_user defaults to verified
        res1 = client.post('/api/register/resend-otp', json={'email': 'already-verified@test.com'})
        res2 = client.post('/api/register/resend-otp', json={'email': 'no-such-account@test.com'})
        assert res1.get_json() == res2.get_json()


class TestLogin:
    def test_login_success(self, client, make_user):
        make_user(email='juan@test.com', password='ValidPass123')
        res = client.post('/api/login', json={'email': 'juan@test.com', 'password': 'ValidPass123'})
        assert res.status_code == 200
        assert 'token' in res.get_json()

    def test_login_wrong_password(self, client, make_user):
        make_user(email='juan@test.com', password='ValidPass123')
        res = client.post('/api/login', json={'email': 'juan@test.com', 'password': 'WrongPass123'})
        assert res.status_code == 401

    def test_login_nonexistent_email(self, client):
        res = client.post('/api/login', json={'email': 'nobody@test.com', 'password': 'whatever123'})
        assert res.status_code == 401

    def test_login_missing_fields(self, client):
        res = client.post('/api/login', json={'email': 'juan@test.com'})
        assert res.status_code == 400


class TestForgotAndResetPassword:
    def test_forgot_password_existing_email_returns_generic_message(self, client, make_user):
        make_user(email='exists@test.com')
        res = client.post('/api/forgot-password', json={'email': 'exists@test.com'})
        assert res.status_code == 200
        assert 'message' in res.get_json()

    def test_forgot_password_nonexistent_email_returns_same_generic_message(self, client):
        """Must not leak whether an email is registered - same response either way."""
        res1 = client.post('/api/forgot-password', json={'email': 'nobody@test.com'})
        res2_user_email = 'somebody@test.com'
        res2 = client.post('/api/forgot-password', json={'email': res2_user_email})
        assert res1.get_json() == res2.get_json()

    def test_reset_password_invalid_token(self, client):
        res = client.post('/api/reset-password', json={'token': 'garbage', 'new_password': 'NewPass123'})
        assert res.status_code == 400

    def test_reset_password_missing_fields(self, client):
        res = client.post('/api/reset-password', json={'token': 'x'})
        assert res.status_code == 400

    def test_reset_password_valid_token_changes_password(self, client, db, make_user):
        import app as app_module
        user = make_user(email='reset@test.com', password='OldPass123')
        token = app_module._reset_serializer.dumps({'id': str(user['id'])})

        res = client.post('/api/reset-password', json={'token': token, 'new_password': 'BrandNewPass123'})
        assert res.status_code == 200

        updated = db.users.find_one({'_id': user['id']})
        assert check_password_hash(updated['password'], 'BrandNewPass123')
        assert not check_password_hash(updated['password'], 'OldPass123')

    def test_reset_password_verifies_an_unverified_account(self, client, db):
        """The emailed link proves inbox ownership, so it also unblocks an
        account that registered but never entered its verification code."""
        import app as app_module
        client.post('/api/register', json=register_payload())
        user = db.users.find_one({'email': 'juan@test.com'})
        assert user['email_verified'] is False
        token = app_module._reset_serializer.dumps({'id': str(user['_id'])})

        res = client.post('/api/reset-password', json={'token': token, 'new_password': 'BrandNewPass123'})
        assert res.status_code == 200
        assert db.users.find_one({'_id': user['_id']})['email_verified'] is True

        login = client.post('/api/login', json={'email': 'juan@test.com', 'password': 'BrandNewPass123'})
        assert login.status_code == 200

    def test_reset_password_too_short(self, client, make_user):
        import app as app_module
        user = make_user(email='reset2@test.com')
        token = app_module._reset_serializer.dumps({'id': str(user['id'])})
        res = client.post('/api/reset-password', json={'token': token, 'new_password': 'short'})
        assert res.status_code == 400


class TestChangePassword:
    def test_change_password_wrong_current(self, client, make_user):
        user = make_user(email='cp@test.com', password='CurrentPass123')
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/change-password',
                          headers={'Authorization': f'Bearer {token}'},
                          json={'current_password': 'WrongPass123', 'new_password': 'NewPass123'})
        # Not 401 - the frontend signs the user out on any 401.
        assert res.status_code == 403

    def test_change_password_success(self, client, make_user):
        user = make_user(email='cp2@test.com', password='CurrentPass123')
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/change-password',
                          headers={'Authorization': f'Bearer {token}'},
                          json={'current_password': 'CurrentPass123', 'new_password': 'BrandNewPass123'})
        assert res.status_code == 200

        relogin = client.post('/api/login', json={'email': user['email'], 'password': 'BrandNewPass123'})
        assert relogin.status_code == 200

    def test_change_password_requires_auth(self, client):
        res = client.put('/api/change-password', json={'current_password': 'a', 'new_password': 'BrandNewPass123'})
        assert res.status_code == 401
