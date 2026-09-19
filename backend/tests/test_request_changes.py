# -*- coding: utf-8 -*-
"""PUT /api/applications/<id>/request-changes: an LGU member's alternative to
Verify when documents are missing/unclear. Reuses the Withdrawn status so the
applicant can freely resubmit; admin_comment distinguishes it from a
self-withdrawn application."""
from bson import ObjectId

import app as app_module
import ml_scoring

VALID_APPLY_PAYLOAD = {
    'contactNumber': '09171234567', 'address': 'X', 'gender': 'Male', 'dob': '2003-01-01',
    'religion': 'X', 'citizenship': 'Filipino',
    'fatherName': 'X', 'fatherOccupation': 'Informal/Vendor', 'fatherEducation': 'High School',
    'motherName': 'X', 'motherOccupation': 'Informal/Vendor', 'motherEducation': 'High School',
    'monthlyIncome': '10000', 'familySize': '4', 'numSiblings': '1', 'numSiblingsStudying': '1',
    'housingSituation': 'Owned', 'school': 'X', 'schoolAddress': 'X', 'course': 'BSCS',
    'yearLevel': '2', 'gpa': '90', 'academicYear': '2026', 'semester': '1st',
}


class TestRequestChanges:
    def test_requires_auth(self, client, db):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'application': {'status': 'Newly Submitted'},
        }).inserted_id
        res = client.put(f'/api/applications/{applicant_id}/request-changes', json={'comment': 'fix it'})
        assert res.status_code == 401

    def test_student_forbidden(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'application': {'status': 'Newly Submitted'},
        }).inserted_id
        res = client.put(f'/api/applications/{applicant_id}/request-changes',
                          headers=auth_headers('student'), json={'comment': 'fix it'})
        assert res.status_code == 403

    def test_comment_is_required(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'application': {'status': 'Newly Submitted'},
        }).inserted_id
        res = client.put(f'/api/applications/{applicant_id}/request-changes',
                          headers=auth_headers(), json={'comment': '   '})
        assert res.status_code == 400

    def test_sets_withdrawn_with_admin_comment(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'email': 'x@test.com', 'application': {'status': 'Pending Verification'},
        }).inserted_id
        res = client.put(f'/api/applications/{applicant_id}/request-changes',
                          headers=auth_headers(), json={'comment': 'Please upload a clearer School ID.'})
        assert res.status_code == 200, res.get_json()

        updated = db.applicants.find_one({'_id': applicant_id})
        assert updated['application']['status'] == 'Withdrawn'
        assert updated['application']['admin_comment'] == 'Please upload a clearer School ID.'
        assert updated['audit_trail'][0]['action'] == 'Changes requested'
        assert updated['audit_trail'][0]['remarks'] == 'Please upload a clearer School ID.'

    def test_ml_fields_untouched(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'ml_score': 0, 'ml_status': 'Pending',
            'application': {'status': 'Incomplete'},
        }).inserted_id
        client.put(f'/api/applications/{applicant_id}/request-changes',
                   headers=auth_headers(), json={'comment': 'missing docs'})
        updated = db.applicants.find_one({'_id': applicant_id})
        assert updated['ml_score'] == 0
        assert updated['ml_status'] == 'Pending'

    def test_blocked_on_already_decided_or_withdrawn(self, client, db, auth_headers):
        for status in ('Approved', 'Rejected', 'Withdrawn'):
            applicant_id = db.applicants.insert_one({
                'full_name': status, 'application': {'status': status},
            }).inserted_id
            res = client.put(f'/api/applications/{applicant_id}/request-changes',
                              headers=auth_headers(), json={'comment': 'x'})
            assert res.status_code == 400, status

    def test_applicant_serialization_exposes_admin_comment(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one({
            'full_name': 'X', 'application': {'status': 'Newly Submitted'},
        }).inserted_id
        client.put(f'/api/applications/{applicant_id}/request-changes',
                   headers=auth_headers(), json={'comment': 'needs a valid ID'})
        res = client.get('/api/applicants', headers=auth_headers())
        applicant = next(a for a in res.get_json()['applicants'] if a['id'] == str(applicant_id))
        assert applicant['admin_comment'] == 'needs a valid ID'
        assert applicant['application_status'] == 'Withdrawn'


class TestResubmitAfterRequestChanges:
    """The whole point: the applicant must be able to freely resubmit afterward,
    same as after a self-initiated withdraw."""

    def test_student_can_resubmit_after_changes_requested(self, client, db, make_user, open_cycle):
        student = make_user(email='changes-requested@test.com', password='TestPass123', role='student')
        applicant_id = db.applicants.insert_one({
            'full_name': 'Changes Requested', 'email': 'changes-requested@test.com',
            'user_id': student['id'], 'cycle_id': open_cycle,
            'application': {'status': 'Newly Submitted'},
        }).inserted_id

        admin = make_user(email='reviewer@test.com', password='TestPass123', role='admin')
        admin_login = client.post('/api/login', json={'email': 'reviewer@test.com', 'password': 'TestPass123'})
        admin_headers = {'Authorization': f"Bearer {admin_login.get_json()['token']}"}
        res = client.put(f'/api/applications/{applicant_id}/request-changes',
                          headers=admin_headers, json={'comment': 'Please resubmit with a clearer ID.'})
        assert res.status_code == 200

        student_login = client.post('/api/login', json={'email': 'changes-requested@test.com', 'password': 'TestPass123'})
        student_headers = {'Authorization': f"Bearer {student_login.get_json()['token']}"}
        res = client.post('/api/apply', headers=student_headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Changes Requested', 'email': 'changes-requested@test.com'})
        assert res.status_code == 200, res.get_json()

        docs = list(db.applicants.find({'email': 'changes-requested@test.com'}))
        assert len(docs) == 2
        assert any(d['application']['status'] == 'Withdrawn' and d['application'].get('admin_comment') for d in docs)
        assert any(d['application']['status'] == 'Newly Submitted' for d in docs)

    def test_resubmission_starts_unscored_and_is_never_auto_approved(self, client, db, make_user, open_cycle):
        """The old record can carry a stale ml_status of 'Eligible' (from before
        opening the modal stopped saving one). The resubmission is a brand-new
        record, so it must start unscored, be the only one the admin list shows,
        and stay untouched by viewing its score or by a later re-ranking."""
        student = make_user(email='resub@test.com', password='TestPass123', role='student')
        old_id = db.applicants.insert_one({
            'full_name': 'Resub', 'email': 'resub@test.com', 'user_id': student['id'],
            'cycle_id': open_cycle, 'ml_score': 80, 'ml_status': 'Eligible',
            'application': {'status': 'Newly Submitted'},
        }).inserted_id

        make_user(email='reviewer@test.com', password='TestPass123', role='admin')
        admin_login = client.post('/api/login', json={'email': 'reviewer@test.com', 'password': 'TestPass123'})
        admin_headers = {'Authorization': f"Bearer {admin_login.get_json()['token']}"}
        res = client.put(f'/api/applications/{old_id}/request-changes',
                          headers=admin_headers, json={'comment': 'Please resubmit with a clearer ID.'})
        assert res.status_code == 200

        student_login = client.post('/api/login', json={'email': 'resub@test.com', 'password': 'TestPass123'})
        student_headers = {'Authorization': f"Bearer {student_login.get_json()['token']}"}
        res = client.post('/api/apply', headers=student_headers,
                           json={**VALID_APPLY_PAYLOAD, 'fullName': 'Resub', 'email': 'resub@test.com'})
        assert res.status_code == 200, res.get_json()
        new_id = ObjectId(res.get_json()['applicant_id'])

        new = db.applicants.find_one({'_id': new_id})
        assert new['ml_score'] == 0
        assert new['ml_status'] == 'Pending'
        assert new['application']['status'] == 'Newly Submitted'

        listed = client.get('/api/applicants', headers=admin_headers).get_json()['applicants']
        assert [a['id'] for a in listed if a['email'] == 'resub@test.com'] == [str(new_id)]

        res = client.get(f'/api/score-applicant/{new_id}', headers=admin_headers)
        assert res.status_code == 200
        new = db.applicants.find_one({'_id': new_id})
        assert new['ml_score'] == 0
        assert new['ml_status'] == 'Pending'

        ml_scoring.recompute_approvals(db, app_module.get_default_organization_id(db), 10)
        assert db.applicants.find_one({'_id': new_id})['application']['status'] == 'Newly Submitted'
        assert db.applicants.find_one({'_id': old_id})['application']['status'] == 'Withdrawn'
