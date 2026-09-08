# -*- coding: utf-8 -*-
"""Program reset (backend/app.py do_program_reset(), POST /api/program-reset,
GET /api/program-cycles): archiving the current cycle and opening a new one
without deleting anything, plus every "current cycle only" query this feature
introduced (recompute_approvals, GET /api/applicants?cycle=current,
GET /api/student/application, the submit_application duplicate check)."""
from datetime import datetime

import app as app_module


def set_reset_password(db, password='ResetPass123'):
    db.settings.update_one(
        {'_id': 'global'},
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
        res = client.post('/api/program-reset', headers=headers, json={'password': 'CorrectPass1'})
        assert res.status_code == 200

    def test_lgu_admin_can_reset_without_any_explicit_permission_flag(self, client, db):
        from werkzeug.security import generate_password_hash
        db.users.insert_one({
            'full_name': 'LGU Admin', 'email': 'lguadmin@test.com',
            'password': generate_password_hash('TestPass123'), 'role': 'lgu_admin',
            'status': 'active', 'privacy_consent': True,
        })
        res = client.post('/api/login', json={'email': 'lguadmin@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        set_reset_password(db, 'CorrectPass1')
        res = client.post('/api/program-reset', headers=headers, json={'password': 'CorrectPass1'})
        assert res.status_code == 200

    def test_fails_when_no_reset_password_configured(self, client, auth_headers):
        res = client.post('/api/program-reset', headers=auth_headers(), json={'password': 'anything'})
        assert res.status_code == 400
        assert 'reset confirmation password' in res.get_json()['error'].lower()

    def test_wrong_password_rejected(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        res = client.post('/api/program-reset', headers=auth_headers(), json={'password': 'WrongPass1'})
        assert res.status_code == 403

    def test_correct_password_resets_and_opens_new_cycle(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        res = client.post('/api/program-reset', headers=auth_headers(),
                           json={'password': 'CorrectPass1', 'label': 'My New Cycle'})
        assert res.status_code == 200
        body = res.get_json()
        assert body['current_cycle']['label'] == 'My New Cycle'
        assert body['current_cycle']['is_current'] is True
        assert db.program_cycles.count_documents({}) == 1

    def test_second_reset_closes_first_and_opens_second(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'label': 'Cycle A'})
        res = client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'label': 'Cycle B'})
        body = res.get_json()
        assert body['current_cycle']['label'] == 'Cycle B'
        cycle_a = db.program_cycles.find_one({'label': 'Cycle A'})
        assert cycle_a['closed_at'] is not None

    def test_reset_clears_results_visibility_override(self, client, auth_headers, db):
        set_reset_password(db, 'CorrectPass1')
        db.settings.update_one({'_id': 'global'}, {'$set': {'results_visible_override': True}})
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})
        assert db.settings.find_one({'_id': 'global'}).get('results_visible_override') is False

    def test_first_reset_backfills_cycle_id_onto_pre_existing_data(self, client, auth_headers, db):
        """Pre-existing applicants (cycle_id: None) must end up pointing at the new
        retroactive Cycle 0 record, not left dangling - otherwise list_program_cycles
        shows both an empty 'Cycle 0' AND a separate legacy bucket for the same data."""
        applicant_id = db.applicants.insert_one({'full_name': 'Pre-existing', 'email': 'pre@test.com'}).inserted_id
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})

        cycle0 = db.program_cycles.find_one({'label': 'Cycle 0 (before cycle tracking)'})
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
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})
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
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1', 'label': 'New'})
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
        client.post('/api/program-reset', headers=admin_headers, json={'password': 'CorrectPass1'})

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
        client.post('/api/program-reset', headers=admin_headers, json={'password': 'CorrectPass1'})

        res = client.post('/api/login', json={'email': 'closed@test.com', 'password': 'TestPass123'})
        student_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.get('/api/student/application?email=closed@test.com', headers=student_headers)
        assert res.get_json()['application'] is None

    def test_admin_can_still_see_archived_application_via_applicants_list(self, client, db, auth_headers):
        db.applicants.insert_one({'full_name': 'Archived', 'email': 'archived@test.com',
                                   'application': {'status': 'Approved'}})
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})
        res = client.get('/api/applicants', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert 'Archived' in names

    def test_applicants_endpoint_cycle_current_excludes_archived(self, client, db, auth_headers):
        db.applicants.insert_one({'full_name': 'Archived2', 'email': 'archived2@test.com',
                                   'application': {'status': 'Newly Submitted'}})
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})
        res = client.get('/api/applicants?cycle=current', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert 'Archived2' not in names

    def test_applicants_endpoint_default_still_shows_everything(self, client, db, auth_headers):
        """Opt-in, not opt-out - omitting ?cycle must behave exactly as before this
        feature existed, since Reports/Dashboard/CSV-export all rely on that."""
        db.applicants.insert_one({'full_name': 'Archived3', 'email': 'archived3@test.com',
                                   'application': {'status': 'Newly Submitted'}})
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})
        res = client.get('/api/applicants', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert 'Archived3' in names

    def test_recompute_approvals_does_not_touch_archived_cycle(self, client, db, auth_headers):
        old_id = db.applicants.insert_one({
            'full_name': 'Old Eligible', 'email': 'old@test.com', 'ml_score': 99, 'ml_status': 'Eligible',
            'application': {'status': 'Approved'},
        }).inserted_id
        set_reset_password(db, 'CorrectPass1')
        client.post('/api/program-reset', headers=auth_headers(), json={'password': 'CorrectPass1'})

        new_id = db.applicants.insert_one({
            'full_name': 'New Eligible', 'email': 'new@test.com', 'ml_score': 50, 'ml_status': 'Eligible',
            'cycle_id': app_module.get_current_cycle_id(db),
            'application': {'status': 'Newly Submitted'},
        }).inserted_id

        app_module.recompute_approvals(db, limit=1, reviewed_by='tester')

        old_status = db.applicants.find_one({'_id': old_id})['application']['status']
        new_status = db.applicants.find_one({'_id': new_id})['application']['status']
        assert old_status == 'Approved'  # untouched - belongs to the archived cycle
        assert new_status == 'Approved'  # the only eligible applicant in the current cycle
