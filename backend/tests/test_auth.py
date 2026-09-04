# -*- coding: utf-8 -*-
"""Register / login / forgot-password / reset-password / change-password."""
from werkzeug.security import check_password_hash

VALID_PROFILE = {
    'dob': '2003-05-14', 'gender': 'Male', 'religion': 'Roman Catholic',
    'citizenship': 'Filipino', 'contactNumber': '09171234567',
    'address': '123 Mabini St',
    'fatherName': 'Pedro Cruz', 'fatherOccupation': 'Laborer/Driver', 'fatherEducation': 'High School',
    'motherName': 'Maria Cruz', 'motherOccupation': 'Unemployed', 'motherEducation': 'Elementary',
    'monthlyIncome': '8000', 'familySize': '5', 'numSiblings': '3', 'numSiblingsStudying': '2',
    'housingSituation': 'Rented', 'hasOtherScholarship': 'no', 'otherScholarshipDetails': '',
}


def register_payload(email='juan@test.com', **overrides):
    payload = {'full_name': 'Juan Dela Cruz', 'email': email, 'password': 'ValidPass123', **VALID_PROFILE}
    payload.update(overrides)
    return payload


class TestRegister:
    def test_register_success(self, client):
        res = client.post('/api/register', json=register_payload())
        assert res.status_code == 201
        body = res.get_json()
        assert body['user']['role'] == 'student'
        assert body['user']['email'] == 'juan@test.com'
        assert 'token' in body

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


class TestLogin:
    def test_login_success(self, client):
        client.post('/api/register', json=register_payload())
        res = client.post('/api/login', json={'email': 'juan@test.com', 'password': 'ValidPass123'})
        assert res.status_code == 200
        assert 'token' in res.get_json()

    def test_login_wrong_password(self, client):
        client.post('/api/register', json=register_payload())
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
        assert res.status_code == 401

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
