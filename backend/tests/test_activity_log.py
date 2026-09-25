# -*- coding: utf-8 -*-
"""System-wide activity log (activity.py / activity_routes.py), plus the
upload ownership check and the audit-trail entries for submissions/uploads."""
import io
from bson import ObjectId


def login(client, user):
    res = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


class TestLoginEventsAreLogged:
    def test_successful_login_is_logged(self, client, db, make_user):
        user = make_user(email='ok@test.com')
        login(client, user)
        entry = db.activity_logs.find_one({"action": "Logged in"})
        assert entry is not None
        assert entry['outcome'] == 'success'
        assert entry['actor']['email'] == 'ok@test.com'
        assert entry['organization_id'] == user['organization_id']

    def test_wrong_password_is_logged_as_failure(self, client, db, make_user):
        make_user(email='victim@test.com')
        res = client.post('/api/login', json={'email': 'victim@test.com', 'password': 'wrong-password'})
        assert res.status_code == 401
        entry = db.activity_logs.find_one({"action": "Failed login - wrong password"})
        assert entry['outcome'] == 'failure'
        assert entry['actor']['email'] == 'victim@test.com'

    def test_unknown_email_is_logged_as_failure(self, client, db):
        client.post('/api/login', json={'email': 'nobody@test.com', 'password': 'whatever1'})
        entry = db.activity_logs.find_one({"action": "Failed login - no account with this email"})
        assert entry['outcome'] == 'failure'
        assert entry['actor']['email'] == 'nobody@test.com'

    def test_logout_is_logged(self, client, db, make_user):
        headers = login(client, make_user(email='bye@test.com'))
        client.post('/api/logout', headers=headers)
        assert db.activity_logs.find_one({"action": "Logged out", "actor.email": "bye@test.com"})

    def test_passwords_are_never_logged(self, client, db, make_user):
        make_user(email='secret@test.com', password='SuperSecret99')
        client.post('/api/login', json={'email': 'secret@test.com', 'password': 'SuperSecret99'})
        client.post('/api/login', json={'email': 'secret@test.com', 'password': 'WrongSecret99'})
        for entry in db.activity_logs.find():
            assert 'Secret99' not in str(entry)


class TestWhoCanReadTheActivityLog:
    def test_lgu_admin_can_read_their_organizations_log(self, client, auth_headers):
        headers = auth_headers('lgu_admin')
        res = client.get('/api/activity-logs', headers=headers)
        assert res.status_code == 200
        actions = [log['action'] for log in res.get_json()['logs']]
        assert 'Logged in' in actions

    def test_super_admin_can_read_the_log(self, client, auth_headers):
        res = client.get('/api/activity-logs', headers=auth_headers('admin'))
        assert res.status_code == 200

    def test_member_with_every_permission_cannot_read_it(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={
            'can_review_applicants': True, 'can_manage_members': True, 'can_reset_program': True})
        assert client.get('/api/activity-logs', headers=headers).status_code == 403

    def test_student_cannot_read_it(self, client, auth_headers):
        assert client.get('/api/activity-logs', headers=auth_headers('student')).status_code == 403

    def test_demoted_admin_loses_access_immediately(self, client, db, auth_headers):
        """The token still says lgu_admin, but the membership no longer does."""
        headers = auth_headers('lgu_admin')
        db.memberships.update_many({"role": "lgu_admin"}, {"$set": {"role": "lgu_member"}})
        assert client.get('/api/activity-logs', headers=headers).status_code == 403

    def test_lgu_admin_never_sees_another_organizations_log(self, client, db, auth_headers):
        headers = auth_headers('lgu_admin')
        db.activity_logs.insert_one({
            "created_at": __import__('datetime').datetime.utcnow(), "category": "auth",
            "action": "Other LGU event", "outcome": "success", "actor": {"email": "x@other.test"},
            "organization_id": ObjectId(),
        })
        actions = [log['action'] for log in client.get('/api/activity-logs', headers=headers).get_json()['logs']]
        assert 'Other LGU event' not in actions

    def test_filters_by_outcome_and_search(self, client, make_user, auth_headers):
        make_user(email='target@test.com')
        client.post('/api/login', json={'email': 'target@test.com', 'password': 'nope-nope'})
        headers = auth_headers('lgu_admin')
        res = client.get('/api/activity-logs?outcome=failure&q=target@', headers=headers)
        logs = res.get_json()['logs']
        assert logs and all(log['outcome'] == 'failure' for log in logs)
        assert all('target@test.com' == log['actor_email'] for log in logs)


class TestUploadOwnership:
    def _upload(self, client, headers, applicant_id):
        return client.post('/api/upload', headers=headers, content_type='multipart/form-data', data={
            'file': (io.BytesIO(b'fake image bytes'), 'id.jpg'),
            'applicant_id': str(applicant_id),
            'document_name': 'School ID',
        })

    def test_student_cannot_upload_to_someone_elses_application(self, client, db, make_user):
        owner = make_user(email='owner@test.com')
        intruder = make_user(email='intruder@test.com')
        applicant_id = db.applicants.insert_one({
            'full_name': 'Owner', 'email': 'owner@test.com', 'user_id': owner['id'],
            'application': {'status': 'Newly Submitted'}, 'documents': [],
        }).inserted_id

        res = self._upload(client, login(client, intruder), applicant_id)
        assert res.status_code == 403
        assert db.applicants.find_one({'_id': applicant_id})['documents'] == []
        blocked = db.activity_logs.find_one({"action": "Blocked upload to another applicant's application"})
        assert blocked['outcome'] == 'failure'
        assert blocked['actor']['email'] == 'intruder@test.com'

    def test_owner_upload_adds_audit_trail_and_activity_entries(self, client, db, make_user):
        owner = make_user(email='owner2@test.com')
        applicant_id = db.applicants.insert_one({
            'full_name': 'Owner Two', 'email': 'owner2@test.com', 'user_id': owner['id'],
            'application': {'status': 'Newly Submitted'}, 'documents': [], 'audit_trail': [],
        }).inserted_id

        res = self._upload(client, login(client, owner), applicant_id)
        assert res.status_code == 200, res.get_json()
        trail = db.applicants.find_one({'_id': applicant_id})['audit_trail']
        assert trail[-1]['action'] == 'Document uploaded: School ID'
        assert trail[-1]['performed_by'] == 'owner2@test.com'
        assert db.activity_logs.find_one({"action": "Uploaded a document", "actor.email": "owner2@test.com"})

    def test_legacy_record_without_user_id_matches_by_email(self, client, db, make_user):
        owner = make_user(email='legacy@test.com')
        applicant_id = db.applicants.insert_one({
            'full_name': 'Legacy', 'email': 'legacy@test.com',
            'application': {'status': 'Newly Submitted'}, 'documents': [],
        }).inserted_id
        assert self._upload(client, login(client, owner), applicant_id).status_code == 200


class TestSubmissionStartsTheAuditTrail:
    def test_submitted_application_has_a_first_audit_entry(self, client, db, make_user, open_cycle):
        from tests.test_withdraw import VALID_APPLY_PAYLOAD
        student = make_user(email='submit-trail@test.com')
        res = client.post('/api/apply', headers=login(client, student),
                          json={**VALID_APPLY_PAYLOAD, 'fullName': 'Submit Trail', 'email': 'submit-trail@test.com'})
        assert res.status_code == 200, res.get_json()
        applicant = db.applicants.find_one({'email': 'submit-trail@test.com'})
        first = applicant['audit_trail'][0]
        assert first['action'] == 'Application submitted'
        assert first['new_status'] == 'Newly Submitted'
        assert db.activity_logs.find_one({"action": "Submitted a scholarship application"})


class TestSettingsChangesAreLogged:
    def test_changing_the_limit_is_logged_without_secrets(self, client, db, auth_headers):
        headers = auth_headers('lgu_admin')
        res = client.put('/api/settings', headers=headers, json={'max_accepted': 7, 'reset_password': 'resetme123'})
        assert res.status_code == 200, res.get_json()
        entry = db.activity_logs.find_one({"action": "Changed program settings"})
        assert 'accepted applicant limit set to 7' in entry['details'].lower()
        assert 'reset confirmation password changed' in entry['details'].lower()
        assert 'resetme123' not in str(entry)
