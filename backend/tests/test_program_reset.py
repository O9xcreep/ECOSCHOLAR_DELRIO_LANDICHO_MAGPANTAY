# -*- coding: utf-8 -*-
"""Program reset (helpers.do_program_reset(), POST /api/program-reset,
GET /api/program-cycles): archiving the current cycle and opening a new one
without deleting anything, plus every "current cycle only" query this
introduced (recompute_approvals, GET /api/applicants?cycle=current,
GET /api/student/application, the submit_application duplicate check)."""
from datetime import datetime, timedelta

import app as app_module


FUTURE_DEADLINE = '2099-01-01T00:00:00'


def set_reset_password(db, password='ResetPass123'):
    org_id = app_module.get_default_organization_id(db)
    db.settings.update_one(
        {'organization_id': org_id},
        {'$set': {'reset_password_hash': app_module.generate_password_hash(password)}},
        upsert=True
    )


class TestSettingsResetPassword:
    def test_get_settings_never_returns_the_hash(self, client, auth_headers, db):
        set_reset_password(db)
        res = client.get('/api/settings', headers=auth_headers())
        body = res.get_json()
        assert 'reset_password_hash' not in body
        assert body['reset_password_set'] is True

    def test_defaults_to_not_set(self, client, auth_headers):
        res = client.get('/api/settings', headers=auth_headers())
        assert res.get_json()['reset_password_set'] is False

    def test_set_reset_password_too_short_rejected(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(), json={'reset_password': 'abc'})
        assert res.status_code == 400

    def test_clear_reset_password_with_null(self, client, auth_headers, db):
        set_reset_password(db)
        res = client.put('/api/settings', headers=auth_headers(), json={'reset_password': None})
        assert res.get_json()['reset_password_set'] is False


class TestProgramResetEndpoint:
    def test_lgu_member_without_can_reset_program_is_forbidden(self, client, auth_headers):
        """can_manage_members and can_review_applicants don't imply can_reset_program -
        it's opt-in per member, separate from the other two."""
        headers = auth_headers('lgu_member', permissions={'can_manage_members': True, 'can_review_applicants': True})
        res = client.post('/api/program-reset', headers=headers, json={'password': 'x'})
        assert res.status_code == 403

    def test_lgu_member_with_can_reset_program_is_allowed(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        res = client.post('/api/program-reset', headers=headers, json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        assert res.status_code == 200

    def test_lgu_admin_can_reset_without_any_explicit_permission_flag(self, client, db):
        from werkzeug.security import generate_password_hash
        db.users.insert_one({
            'full_name': 'LGU Admin', 'email': 'lguadmin@test.com',
            'password': generate_password_hash('TestPass123'), 'role': 'lgu_admin',
            'status': 'active', 'privacy_consent': True,
            'organization_id': app_module.get_default_organization_id(db),
        })
        res = client.post('/api/login', json={'email': 'lguadmin@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        set_reset_password(db, 'CorrectPass1')
        res = client.post('/api/program-reset', headers=headers, json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        assert res.status_code == 200

    def test_fails_when_no_reset_password_configured(self, client, auth_headers):
        res = client.post('/api/program-reset', headers=auth_headers(), json={'password': 'anything', 'deadline': FUTURE_DEADLINE})
        assert res.status_code == 400
        assert 'reset confirmation password' in res.get_json()['error'].lower()

    def test_wrong_password_rejected(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        res = client.post('/api/program-reset', headers=auth_headers(), json={'password': 'WrongPass1', 'deadline': FUTURE_DEADLINE})
        assert res.status_code == 403

    def test_correct_password_resets_and_opens_new_cycle(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        res = client.post('/api/program-reset', headers=auth_headers(),
                           json={'password': 'CorrectPass1', 'label': 'My New Cycle', 'deadline': FUTURE_DEADLINE})
        assert res.status_code == 200
        body = res.get_json()
        assert body['current_cycle']['label'] == 'My New Cycle'
        assert body['current_cycle']['is_current'] is True
        assert db.program_cycles.count_documents({}) == 1

    def test_second_reset_closes_first_and_opens_second(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'label': 'Cycle A', 'deadline': FUTURE_DEADLINE})
        res = client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'label': 'Cycle B', 'deadline': FUTURE_DEADLINE})
        body = res.get_json()
        assert body['current_cycle']['label'] == 'Cycle B'
        cycle_a = db.program_cycles.find_one({'label': 'Cycle A'})
        assert cycle_a['closed_at'] is not None

    def test_reset_clears_results_visibility_override(self, client, auth_headers, db):
        org_id = app_module.get_default_organization_id(db)
        set_reset_password(db, 'CorrectPass1')
        db.settings.update_one({'organization_id': org_id}, {'$set': {'results_visible_override': True}})
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        assert db.settings.find_one({'organization_id': org_id}).get('results_visible_override') is False

    def test_first_reset_backfills_cycle_id_onto_pre_existing_data(self, client, auth_headers, db):
        """Pre-existing applicants (cycle_id: None) must end up pointing at the
        retroactive Cycle 0 record, or list_program_cycles would show both an
        empty 'Cycle 0' and a separate legacy bucket for the same data."""
        applicant_id = db.applicants.insert_one({'full_name': 'Pre-existing', 'email': 'pre@test.com'}).inserted_id
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})

        cycle0 = db.program_cycles.find_one({'label': 'Program 0 (before program tracking)'})
        assert cycle0 is not None
        applicant = db.applicants.find_one({'_id': applicant_id})
        assert applicant['cycle_id'] == cycle0['_id']
        assert db.applicants.count_documents({'cycle_id': None}) == 0

    def test_nothing_is_deleted(self, client, auth_headers, db):
        applicant_id = db.applicants.insert_one({
            'full_name': 'A', 'email': 'a@test.com',
            'application': {'status': 'Approved'},
        }).inserted_id
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        assert db.applicants.find_one({'_id': applicant_id}) is not None


class TestProgramCyclesListing:
    def test_legacy_bucket_shown_when_pre_reset_data_exists(self, client, auth_headers, db):
        db.applicants.insert_one({'full_name': 'A', 'email': 'a@test.com'})
        res = client.get('/api/program-cycles', headers=auth_headers())
        cycles = res.get_json()['cycles']
        assert any(c['id'] is None and c['applicant_count'] == 1 for c in cycles)

    def test_no_legacy_bucket_when_no_pre_reset_data(self, client, auth_headers):
        res = client.get('/api/program-cycles', headers=auth_headers())
        assert res.get_json()['cycles'] == []

    def test_after_reset_current_cycle_listed_as_current(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'label': 'New', 'deadline': FUTURE_DEADLINE})
        res = client.get('/api/program-cycles', headers=auth_headers())
        cycles = res.get_json()['cycles']
        current = [c for c in cycles if c['label'] == 'New'][0]
        assert current['is_current'] is True


class TestCurrentCycleScoping:
    def test_student_can_reapply_after_reset(self, client, db, make_user):
        """The whole point of a reset: someone who applied before must be able to
        apply again in the new cycle without tripping the duplicate-email check."""
        student = make_user(email='reapply@test.com', password='TestPass123', role='student')
        db.applicants.insert_one({
            'full_name': 'Reapply Person', 'email': 'reapply@test.com', 'user_id': student['id'],
            'application': {'status': 'Rejected'},
        })
        admin = make_user(email='admin2@test.com', password='TestPass123', role='admin')
        admin_res = client.post('/api/login', json={'email': 'admin2@test.com', 'password': 'TestPass123'})
        admin_headers = {'Authorization': f"Bearer {admin_res.get_json()['token']}"}
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=admin_headers, json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})

        res = client.post('/api/login', json={'email': 'reapply@test.com', 'password': 'TestPass123'})
        student_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        payload = {
            'fullName': 'Reapply Person', 'email': 'reapply@test.com', 'contactNumber': '09171234567',
            'address': 'X', 'gender': 'Male', 'dob': '2003-01-01', 'religion': 'X', 'citizenship': 'Filipino',
            'fatherName': 'X', 'fatherOccupation': 'Informal/Vendor', 'fatherEducation': 'High School',
            'motherName': 'X', 'motherOccupation': 'Informal/Vendor', 'motherEducation': 'High School',
            'monthlyIncome': '10000', 'familySize': '4', 'numSiblings': '1', 'numSiblingsStudying': '1',
            'housingSituation': 'Owned', 'school': 'X', 'schoolAddress': 'X', 'course': 'BSCS',
            'yearLevel': '2', 'gpa': '90', 'academicYear': '2026', 'semester': '1st',
        }
        res = client.post('/api/apply', headers=student_headers, json=payload)
        assert res.status_code == 200, res.get_json()

    def test_student_application_hidden_after_their_cycle_closes(self, client, db, make_user):
        student = make_user(email='closed@test.com', password='TestPass123', role='student')
        db.applicants.insert_one({
            'full_name': 'Closed Cycle Person', 'email': 'closed@test.com', 'user_id': student['id'],
            'application': {'status': 'Approved', 'submitted_at': datetime.utcnow()},
        })
        admin = make_user(email='admin3@test.com', password='TestPass123', role='admin')
        admin_res = client.post('/api/login', json={'email': 'admin3@test.com', 'password': 'TestPass123'})
        admin_headers = {'Authorization': f"Bearer {admin_res.get_json()['token']}"}
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=admin_headers, json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})

        res = client.post('/api/login', json={'email': 'closed@test.com', 'password': 'TestPass123'})
        student_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.get('/api/student/application?email=closed@test.com', headers=student_headers)
        assert res.get_json()['application'] is None

    def test_admin_can_still_see_archived_application_via_applicants_list(self, client, db, auth_headers):
        db.applicants.insert_one({'full_name': 'Archived', 'email': 'archived@test.com',
                                   'application': {'status': 'Approved'}})
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        res = client.get('/api/applicants', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert 'Archived' in names

    def test_applicants_endpoint_cycle_current_excludes_archived(self, client, db, auth_headers):
        db.applicants.insert_one({'full_name': 'Archived2', 'email': 'archived2@test.com',
                                   'application': {'status': 'Newly Submitted'}})
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        res = client.get('/api/applicants?cycle=current', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert 'Archived2' not in names

    def test_applicants_endpoint_default_still_shows_everything(self, client, db, auth_headers):
        """Opt-in, not opt-out - omitting ?cycle must behave exactly as before this
        feature existed, since Reports/Dashboard/CSV-export all rely on that."""
        db.applicants.insert_one({'full_name': 'Archived3', 'email': 'archived3@test.com',
                                   'application': {'status': 'Newly Submitted'}})
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})
        res = client.get('/api/applicants', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert 'Archived3' in names

    def test_recompute_approvals_does_not_touch_archived_cycle(self, client, db, auth_headers):
        old_id = db.applicants.insert_one({
            'full_name': 'Old Eligible', 'email': 'old@test.com', 'ml_score': 99, 'ml_status': 'Eligible',
            'application': {'status': 'Approved'},
        }).inserted_id
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'deadline': FUTURE_DEADLINE})

        org_id = app_module.get_default_organization_id(db)
        new_id = db.applicants.insert_one({
            'full_name': 'New Eligible', 'email': 'new@test.com', 'ml_score': 50, 'ml_status': 'Eligible',
            'cycle_id': app_module.get_current_cycle_id(db, org_id),
            'application': {'status': 'Newly Submitted'},
        }).inserted_id

        app_module.recompute_approvals(db, org_id, limit=1, reviewed_by='tester')

        old_status = db.applicants.find_one({'_id': old_id})['application']['status']
        new_status = db.applicants.find_one({'_id': new_id})['application']['status']
        assert old_status == 'Approved'  # untouched - belongs to the archived cycle
        assert new_status == 'Approved'  # the only eligible applicant in the current cycle


VALID_APPLY_PAYLOAD = {
    'contactNumber': '09171234567', 'address': 'X', 'gender': 'Male', 'dob': '2003-01-01',
    'religion': 'X', 'citizenship': 'Filipino',
    'fatherName': 'X', 'fatherOccupation': 'Informal/Vendor', 'fatherEducation': 'High School',
    'motherName': 'X', 'motherOccupation': 'Informal/Vendor', 'motherEducation': 'High School',
    'monthlyIncome': '10000', 'familySize': '4', 'numSiblings': '1', 'numSiblingsStudying': '1',
    'housingSituation': 'Owned', 'school': 'X', 'schoolAddress': 'X', 'course': 'BSCS',
    'yearLevel': '2', 'gpa': '90', 'academicYear': '2026', 'semester': '1st',
}


class TestProgramDeadline:
    """A deadline is a hard cutoff enforced by is_cycle_open(). No program set
    up behaves the same as closed/expired: students can't submit until an
    admin explicitly opens one."""

    def test_no_cycle_at_all_blocks_submission(self, client, make_user):
        student = make_user(email='nocycle@test.com', password='TestPass123', role='student')
        login = client.post('/api/login', json={'email': student['email'], 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = client.post('/api/apply', headers=headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'No Cycle', 'email': 'nocycle@test.com'})
        assert res.status_code == 403

    def test_future_deadline_allows_submission(self, client, db, make_user, auth_headers):
        set_reset_password(db, 'CorrectPass1')
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        res = client.post('/api/program-reset', headers=auth_headers(),
                           json={'password': 'CorrectPass1', 'deadline': future})
        assert res.status_code == 200
        assert res.get_json()['current_cycle']['is_open'] is True

        student = make_user(email='future-deadline@test.com', password='TestPass123', role='student')
        login = client.post('/api/login', json={'email': student['email'], 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
        res = client.post('/api/apply', headers=headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Future Deadline', 'email': 'future-deadline@test.com'})
        assert res.status_code == 200, res.get_json()

    def test_past_deadline_blocks_submission_even_though_cycle_not_manually_closed(self, client, db, make_user, open_cycle):
        org_id = app_module.get_default_organization_id(db)
        past = datetime.utcnow() - timedelta(days=1)
        db.program_cycles.update_one({'_id': open_cycle}, {'$set': {'deadline': past}})

        student = make_user(email='past-deadline@test.com', password='TestPass123', role='student')
        login = client.post('/api/login', json={'email': student['email'], 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
        res = client.post('/api/apply', headers=headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Past Deadline', 'email': 'past-deadline@test.com'})
        assert res.status_code == 403

        # The cycle is still "current" (closed_at unset) - just no longer open.
        cycle = app_module.get_current_cycle(db, org_id)
        assert cycle['_id'] == open_cycle
        assert app_module.is_cycle_open(cycle) is False

    def test_program_reset_rejects_a_non_future_deadline(self, client, db, auth_headers):
        set_reset_password(db, 'CorrectPass1')
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        res = client.post('/api/program-reset', headers=auth_headers(),
                           json={'password': 'CorrectPass1', 'deadline': past})
        assert res.status_code == 400

    def test_student_application_endpoint_reports_cycle_status_before_applying(self, client, db, make_user, open_cycle):
        student = make_user(email='checkcycle@test.com', password='TestPass123', role='student')
        login = client.post('/api/login', json={'email': student['email'], 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

        res = client.get('/api/student/application?email=checkcycle@test.com', headers=headers)
        body = res.get_json()
        assert body['application'] is None
        assert body['current_cycle']['is_open'] is True


class TestProgramManagerAccess:
    """Settings -> System is for anyone with can_reset_program, so the data it
    reads/writes has to be reachable with just that permission - not also
    can_review_applicants, which gates the Applications/Ranking pages."""

    PROGRAM_ONLY = {'can_reset_program': True}
    REVIEW_ONLY = {'can_review_applicants': True}

    def test_program_manager_can_export_applicants(self, client, auth_headers, db):
        db.applicants.insert_one({'full_name': 'Exportable', 'email': 'exp@test.com',
                                   'application': {'status': 'Approved'}})
        res = client.get('/api/applicants/export', headers=auth_headers('lgu_member', permissions=self.PROGRAM_ONLY))
        assert res.status_code == 200
        assert [a['full_name'] for a in res.get_json()['applicants']] == ['Exportable']

    def test_export_requires_can_reset_program(self, client, auth_headers):
        res = client.get('/api/applicants/export', headers=auth_headers('lgu_member', permissions=self.REVIEW_ONLY))
        assert res.status_code == 403
        assert client.get('/api/applicants/export', headers=auth_headers('student')).status_code == 403

    def test_export_hides_superseded_withdrawn_records(self, client, auth_headers, db):
        db.applicants.insert_one({'full_name': 'Old', 'email': 'a@test.com',
                                   'application': {'status': 'Withdrawn', 'superseded_by': 'newer'}})
        db.applicants.insert_one({'full_name': 'New', 'email': 'a@test.com',
                                   'application': {'status': 'Newly Submitted'}})
        res = client.get('/api/applicants/export', headers=auth_headers('lgu_admin'))
        assert [a['full_name'] for a in res.get_json()['applicants']] == ['New']

    def test_cycle_list_readable_with_either_permission(self, client, auth_headers):
        assert client.get('/api/program-cycles', headers=auth_headers('lgu_member', permissions=self.PROGRAM_ONLY)).status_code == 200
        assert client.get('/api/program-cycles', headers=auth_headers('lgu_member', permissions=self.REVIEW_ONLY)).status_code == 200

    def test_cycle_list_forbidden_without_either_permission(self, client, auth_headers):
        res = client.get('/api/program-cycles', headers=auth_headers('lgu_member', permissions={'can_manage_members': True}))
        assert res.status_code == 403


class TestUpdateCurrentCycleDeadline:
    URL = '/api/program-cycles/current/deadline'

    def _future(self, days=5):
        return (datetime.utcnow() + timedelta(days=days)).isoformat()

    def test_program_manager_can_extend_the_live_deadline(self, client, auth_headers, db, open_cycle):
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        res = client.put(self.URL, headers=headers, json={'deadline': self._future()})
        assert res.status_code == 200
        assert res.get_json()['deadline'] is not None
        assert db.program_cycles.find_one({'_id': open_cycle})['deadline'] is not None

    def test_requires_can_reset_program(self, client, auth_headers, open_cycle):
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        assert client.put(self.URL, headers=headers, json={'deadline': self._future()}).status_code == 403

    def test_deadline_is_required(self, client, auth_headers, open_cycle):
        assert client.put(self.URL, headers=auth_headers(), json={}).status_code == 400

    def test_past_deadline_rejected(self, client, auth_headers, open_cycle):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        assert client.put(self.URL, headers=auth_headers(), json={'deadline': past}).status_code == 400

    def test_no_running_program_rejected(self, client, auth_headers):
        res = client.put(self.URL, headers=auth_headers(), json={'deadline': self._future()})
        assert res.status_code == 400
