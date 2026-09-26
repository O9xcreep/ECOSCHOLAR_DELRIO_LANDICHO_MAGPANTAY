# -*- coding: utf-8 -*-
"""Register / login / forgot-password / reset-password / change-password."""
from werkzeug.security import check_password_hash

import app as app_module

VALID_PROFILE = {
    'dob': '2003-05-14', 'gender': 'Male', 'religion': 'Roman Catholic',
    'citizenship': 'Filipino', 'contactNumber': '09171234567',
    'address': '123 Mabini St',
    'fatherName': 'Pedro Cruz', 'fatherOccupation': 'Laborer/Driver', 'fatherEducation': 'High School',
    'motherName': 'Maria Cruz', 'motherOccupation': 'Unemployed', 'motherEducation': 'Elementary',
    'monthlyIncome': '8000', 'familySize': '5', 'numSiblings': '3', 'numSiblingsStudying': '2',
    'housingSituation': 'Rented', 'hasOtherScholarship': 'no', 'otherScholarshipDetails': '',
}


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
        **VALID_PROFILE,
    }
    payload.update(overrides)
    return payload


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

    def test_register_invalid_gender(self, client):
        res = client.post('/api/register', json=register_payload(gender='Other'))
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
