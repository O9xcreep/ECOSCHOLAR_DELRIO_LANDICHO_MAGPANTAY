# -*- coding: utf-8 -*-
"""Applicant withdraw: PUT /api/student/application/withdraw."""


class TestWithdraw:
    def test_requires_auth(self, client):
        res = client.put('/api/student/application/withdraw')
        assert res.status_code == 401

    def test_admin_cannot_withdraw(self, client, auth_headers):
        res = client.put('/api/student/application/withdraw', headers=auth_headers('admin'))
        assert res.status_code == 403

    def test_no_application_found(self, client, auth_headers):
        res = client.put('/api/student/application/withdraw', headers=auth_headers('student'))
        assert res.status_code == 404

    def test_withdraw_success(self, client, db, make_user):
        user = make_user(email='withdraw@test.com', role='student')
        db.applicants.insert_one({
            'full_name': 'Withdraw Test', 'email': 'withdraw@test.com',
            'application': {'status': 'Newly Submitted'}, 'academic': {}, 'user_id': user['id'],
        })
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/student/application/withdraw', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 200

        updated = db.applicants.find_one({'email': 'withdraw@test.com'})
        assert updated['application']['status'] == 'Withdrawn'
        assert updated['audit_trail'][0]['action'] == 'Application withdrawn by applicant'

    def test_cannot_withdraw_twice(self, client, db, make_user):
        user = make_user(email='withdraw2@test.com', role='student')
        db.applicants.insert_one({
            'full_name': 'Withdraw Test', 'email': 'withdraw2@test.com',
            'application': {'status': 'Withdrawn'}, 'academic': {}, 'user_id': user['id'],
        })
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/student/application/withdraw', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 400


class TestWithdrawnCannotBeOverridden:
    def test_status_change_blocked_on_withdrawn(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'application': {'status': 'Withdrawn'}, 'academic': {},
        }).inserted_id
        res = client.put(f'/api/applications/{applicant_id}/status',
                          headers=auth_headers(), json={'status': 'Pending Verification'})
        assert res.status_code == 400
        assert 'withdrawn' in res.get_json()['error'].lower()

    def test_verify_blocked_on_withdrawn(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'application': {'status': 'Withdrawn'}, 'academic': {},
        }).inserted_id
        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        assert res.status_code == 409
        assert 'withdrawn' in res.get_json()['error'].lower()


class TestRecomputeExcludesWithdrawn:
    def test_withdrawn_applicant_not_reinstated(self, db):
        """A withdrawn applicant with a stale ml_status='Eligible' must not get
        flipped back to Approved/Rejected by recompute_approvals()."""
        import app as app_module

        db.applicants.insert_one({
            'full_name': 'Stale Eligible', 'email': 'stale@test.com',
            'ml_status': 'Eligible', 'ml_score': 99,
            'application': {'status': 'Withdrawn'},
        })
        app_module.recompute_approvals(db, limit=10)

        updated = db.applicants.find_one({'email': 'stale@test.com'})
        assert updated['application']['status'] == 'Withdrawn'
