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


class TestCannotWithdrawAfterScoring:
    """Once the eligibility model has decided Approved/Rejected, that's final -
    same as it can no longer be edited, it can no longer be withdrawn either."""

    def test_cannot_withdraw_approved(self, client, db, make_user):
        user = make_user(email='withdraw-approved@test.com', role='student')
        db.applicants.insert_one({
            'full_name': 'X', 'email': 'withdraw-approved@test.com',
            'application': {'status': 'Approved'}, 'academic': {}, 'user_id': user['id'],
        })
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/student/application/withdraw', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 400
        updated = db.applicants.find_one({'email': 'withdraw-approved@test.com'})
        assert updated['application']['status'] == 'Approved'

    def test_cannot_withdraw_rejected(self, client, db, make_user):
        user = make_user(email='withdraw-rejected@test.com', role='student')
        db.applicants.insert_one({
            'full_name': 'X', 'email': 'withdraw-rejected@test.com',
            'application': {'status': 'Rejected'}, 'academic': {}, 'user_id': user['id'],
        })
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/student/application/withdraw', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 400
        updated = db.applicants.find_one({'email': 'withdraw-rejected@test.com'})
        assert updated['application']['status'] == 'Rejected'

    def test_cannot_withdraw_waitlisted(self, client, db, make_user):
        """Waitlisted is a display-only label (stored status is Rejected with
        ml_status Eligible); tested explicitly since it's a distinct
        student-visible state."""
        user = make_user(email='withdraw-waitlisted@test.com', role='student')
        db.applicants.insert_one({
            'full_name': 'X', 'email': 'withdraw-waitlisted@test.com', 'ml_status': 'Eligible',
            'application': {'status': 'Rejected'}, 'academic': {}, 'user_id': user['id'],
        })
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/student/application/withdraw', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 400

    def test_can_still_withdraw_incomplete(self, client, db, make_user):
        """Sanity check the fix is scoped to Approved/Rejected only - every
        pre-scoring status must remain withdrawable."""
        user = make_user(email='withdraw-incomplete@test.com', role='student')
        db.applicants.insert_one({
            'full_name': 'X', 'email': 'withdraw-incomplete@test.com',
            'application': {'status': 'Incomplete'}, 'academic': {}, 'user_id': user['id'],
        })
        login = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
        token = login.get_json()['token']

        res = client.put('/api/student/application/withdraw', headers={'Authorization': f'Bearer {token}'})
        assert res.status_code == 200


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


VALID_APPLY_PAYLOAD = {
    'contactNumber': '09171234567', 'address': 'X', 'gender': 'Male', 'dob': '2003-01-01',
    'religion': 'X', 'citizenship': 'Filipino',
    'fatherName': 'X', 'fatherOccupation': 'Informal/Vendor', 'fatherEducation': 'High School',
    'motherName': 'X', 'motherOccupation': 'Informal/Vendor', 'motherEducation': 'High School',
    'monthlyIncome': '10000', 'familySize': '4', 'numSiblings': '1', 'numSiblingsStudying': '1',
    'housingSituation': 'Owned', 'school': 'X', 'schoolAddress': 'X', 'course': 'BSCS',
    'yearLevel': '2', 'gpa': '90', 'academicYear': '2026', 'semester': '1st',
}


class TestReapplyAfterWithdraw:
    """A withdrawn application must not be treated as a blocking duplicate;
    withdrawing frees the applicant to submit a fresh application, not lock
    them out for the rest of the cycle."""

    def test_student_can_reapply_in_same_cycle_after_withdrawing(self, client, db, make_user, open_cycle):
        student = make_user(email='withdraw-reapply@test.com', password='TestPass123', role='student')
        db.applicants.insert_one({
            'full_name': 'Withdraw Reapply', 'email': 'withdraw-reapply@test.com', 'user_id': student['id'],
            'application': {'status': 'Withdrawn'}, 'cycle_id': open_cycle,
        })
        login = client.post('/api/login', json={'email': 'withdraw-reapply@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = client.post('/api/apply', headers=headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Withdraw Reapply', 'email': 'withdraw-reapply@test.com'})
        assert res.status_code == 200, res.get_json()

        docs = list(db.applicants.find({'email': 'withdraw-reapply@test.com'}))
        assert len(docs) == 2
        assert any(d['application']['status'] == 'Withdrawn' for d in docs)
        assert any(d['application']['status'] == 'Newly Submitted' for d in docs)

    def test_still_active_application_remains_blocked(self, client, db, make_user, open_cycle):
        """The fix only exempts Withdrawn - an application still in the pipeline
        must keep blocking a second submission for the same person."""
        student = make_user(email='still-active@test.com', password='TestPass123', role='student')
        db.applicants.insert_one({
            'full_name': 'Still Active', 'email': 'still-active@test.com', 'user_id': student['id'],
            'application': {'status': 'Newly Submitted'}, 'cycle_id': open_cycle,
        })
        login = client.post('/api/login', json={'email': 'still-active@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = client.post('/api/apply', headers=headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Still Active', 'email': 'still-active@test.com'})
        assert res.status_code == 409

    def test_name_and_birthdate_duplicate_also_exempts_withdrawn(self, client, db, make_user, open_cycle):
        student = make_user(email='withdraw-reapply2@test.com', password='TestPass123', role='student')
        db.applicants.insert_one({
            'full_name': 'Name Dob Withdrawn', 'email': 'old-email@test.com', 'user_id': student['id'],
            'date_of_birth': '2003-01-01',
            'application': {'status': 'Withdrawn'}, 'cycle_id': open_cycle,
        })
        login = client.post('/api/login', json={'email': 'withdraw-reapply2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = client.post('/api/apply', headers=headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Name Dob Withdrawn',
                                 'email': 'withdraw-reapply2@test.com', 'dob': '2003-01-01'})
        assert res.status_code == 200, res.get_json()


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
        app_module.recompute_approvals(db, app_module.get_default_organization_id(db), limit=10)

        updated = db.applicants.find_one({'email': 'stale@test.com'})
        assert updated['application']['status'] == 'Withdrawn'
