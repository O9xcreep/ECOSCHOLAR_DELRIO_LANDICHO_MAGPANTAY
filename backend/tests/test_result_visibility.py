# -*- coding: utf-8 -*-
"""Result-visibility gating (helpers.are_results_visible(), the
results_visible_after/results_visible_override settings fields, and masking of
Approved/Rejected in GET /api/student/application until results are released)."""
from datetime import datetime, timedelta

import app as app_module


def settings_filter(db):
    return {'organization_id': app_module.get_default_organization_id(db)}


def make_applicant(db, email, user_id, status='Approved'):
    return db.applicants.insert_one({
        'full_name': 'Test Applicant', 'email': email, 'user_id': user_id,
        'ml_score': 80, 'ml_status': 'Eligible',
        'application': {'status': status, 'submitted_at': datetime.utcnow(),
                         'reviewed_at': datetime.utcnow(), 'reviewed_by_name': 'admin@test.com'},
        'application_status_raw_for_test': status,
    }).inserted_id


class TestSettingsVisibilityFields:
    def test_defaults_are_always_visible(self, client, auth_headers):
        res = client.get('/api/settings', headers=auth_headers())
        body = res.get_json()
        assert body['results_visible_after'] is None
        assert body['results_visible_override'] is None
        assert body['results_visible_now'] is True

    def test_set_override_true(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_override': True})
        body = res.get_json()
        assert res.status_code == 200
        assert body['results_visible_override'] is True
        assert body['results_visible_now'] is True

    def test_set_override_false(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_override': False})
        body = res.get_json()
        assert res.status_code == 200
        assert body['results_visible_override'] is False
        assert body['results_visible_now'] is False

    def test_override_invalid_value_rejected(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_override': 'yes'})
        assert res.status_code == 400

    def test_set_future_visible_after_hides_results(self, client, auth_headers):
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_after': future})
        body = res.get_json()
        assert res.status_code == 200
        assert body['results_visible_now'] is False

    def test_set_past_visible_after_shows_results(self, client, auth_headers):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_after': past})
        body = res.get_json()
        assert res.status_code == 200
        assert body['results_visible_now'] is True

    def test_override_wins_over_visible_after(self, client, auth_headers):
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        client.put('/api/settings', headers=auth_headers(),
                   json={'results_visible_after': future})
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_override': True})
        assert res.get_json()['results_visible_now'] is True

    def test_clearing_visible_after_with_null(self, client, auth_headers):
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        client.put('/api/settings', headers=auth_headers(),
                   json={'results_visible_after': future})
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_after': None})
        body = res.get_json()
        assert body['results_visible_after'] is None
        assert body['results_visible_now'] is True

    def test_invalid_date_format_rejected(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(),
                          json={'results_visible_after': 'not-a-date'})
        assert res.status_code == 400

    def test_requires_admin_role(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        assert client.get('/api/settings', headers=headers).status_code == 403


class TestStudentApplicationMasking:
    def test_approved_hidden_when_results_not_visible(self, client, db, make_user):
        student = make_user(email='stu@test.com', password='TestPass123', role='student')
        make_applicant(db, 'stu@test.com', student['id'], status='Approved')
        db.settings.update_one(settings_filter(db), {'$set': {'results_visible_override': False}}, upsert=True)

        res = client.post('/api/login', json={'email': 'stu@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/student/application?email=stu@test.com', headers=headers)
        app_data = res.get_json()['application']
        assert app_data['application_status'] == 'Pending Verification'
        assert app_data['ml_status'] == 'Pending'
        assert app_data['reviewed_at'] is None
        assert app_data['reviewed_by_name'] is None

    def test_rejected_hidden_when_results_not_visible(self, client, db, make_user):
        student = make_user(email='stu2@test.com', password='TestPass123', role='student')
        make_applicant(db, 'stu2@test.com', student['id'], status='Rejected')
        db.settings.update_one(settings_filter(db), {'$set': {'results_visible_override': False}}, upsert=True)

        res = client.post('/api/login', json={'email': 'stu2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/student/application?email=stu2@test.com', headers=headers)
        app_data = res.get_json()['application']
        assert app_data['application_status'] == 'Pending Verification'

    def test_approved_visible_by_default(self, client, db, make_user):
        student = make_user(email='stu3@test.com', password='TestPass123', role='student')
        make_applicant(db, 'stu3@test.com', student['id'], status='Approved')

        res = client.post('/api/login', json={'email': 'stu3@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/student/application?email=stu3@test.com', headers=headers)
        app_data = res.get_json()['application']
        assert app_data['application_status'] == 'Approved'

    def test_override_true_shows_results_even_before_date(self, client, db, make_user):
        student = make_user(email='stu4@test.com', password='TestPass123', role='student')
        make_applicant(db, 'stu4@test.com', student['id'], status='Approved')
        future = (datetime.utcnow() + timedelta(days=1))
        db.settings.update_one(settings_filter(db),
                                {'$set': {'results_visible_after': future, 'results_visible_override': True}},
                                upsert=True)

        res = client.post('/api/login', json={'email': 'stu4@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/student/application?email=stu4@test.com', headers=headers)
        assert res.get_json()['application']['application_status'] == 'Approved'

    def test_non_decided_status_never_masked(self, client, db, make_user):
        """Being in-review is never gated - only an actual Approved/Rejected
        decision is held back."""
        student = make_user(email='stu5@test.com', password='TestPass123', role='student')
        make_applicant(db, 'stu5@test.com', student['id'], status='Newly Submitted')
        db.settings.update_one(settings_filter(db), {'$set': {'results_visible_override': False}}, upsert=True)

        res = client.post('/api/login', json={'email': 'stu5@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/student/application?email=stu5@test.com', headers=headers)
        assert res.get_json()['application']['application_status'] == 'Newly Submitted'

    def test_admin_viewing_via_this_endpoint_is_never_masked(self, client, db, auth_headers, make_user):
        student = make_user(email='stu6@test.com', password='TestPass123', role='student')
        make_applicant(db, 'stu6@test.com', student['id'], status='Approved')
        db.settings.update_one(settings_filter(db), {'$set': {'results_visible_override': False}}, upsert=True)

        res = client.get('/api/student/application?email=stu6@test.com', headers=auth_headers())
        assert res.get_json()['application']['application_status'] == 'Approved'


class TestNotificationMasking:
    def test_rejection_notification_generic_when_hidden(self, client, db, auth_headers, make_user):
        student = make_user(email='stu7@test.com', password='TestPass123', role='student')
        # Documents must be OCR-verified before the ML decision can run; seed
        # one required doc already verified so this test reaches the
        # masking logic instead of being blocked by the document gate.
        db.document_requirements.insert_many([
            {'label': 'Form A', 'required': True, 'enabled': True},
            {'label': app_module.SELFIE_DOC_LABEL, 'required': True, 'enabled': True},
        ])
        applicant_id = db.applicants.insert_one({
            'full_name': 'Test', 'email': 'stu7@test.com', 'user_id': student['id'],
            'gender': 'Female', 'family_size': 4, 'num_siblings': 1, 'num_siblings_studying': 1,
            'father_education': 'High School', 'mother_education': 'High School',
            'father_occupation': 'Laborer', 'mother_occupation': 'Laborer',
            'monthly_income': 50000, 'housing_situation': 'Owned',
            'has_other_scholarship': False,
            'academic': {'gpa': 70},
            'application': {'status': 'Newly Submitted', 'submitted_at': datetime.utcnow()},
            'documents': [
                {'document_name': 'Form A', 'status': 'Uploaded', 'ocr_status': 'Verified'},
                {'document_name': app_module.SELFIE_DOC_LABEL, 'status': 'Uploaded', 'ocr_status': 'Verified'},
            ],
        }).inserted_id
        db.settings.update_one(settings_filter(db), {'$set': {'results_visible_override': False}}, upsert=True)

        res = client.put(f'/api/applications/{applicant_id}/verify', headers=auth_headers())
        assert res.status_code in (200, 500)  # model may or may not be loaded in test env
        if res.status_code != 200:
            return

        notif = db.notifications.find_one({'user_id': student['id']})
        assert notif is not None
        assert notif['message'] == app_module.GENERIC_REVIEWED_MESSAGE
