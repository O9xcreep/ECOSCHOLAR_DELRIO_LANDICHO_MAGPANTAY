# -*- coding: utf-8 -*-
"""Multi-org membership: student self-service join/switch (memberships.py),
self-service account deletion, and the approval-gated "request to join
another org" flow for admin/staff accounts (admin_management.py)."""
import io
from datetime import datetime
from unittest.mock import MagicMock

from bson import ObjectId
from werkzeug.security import generate_password_hash

import app as app_module
import memberships as memberships_module


def make_second_org(db, name='Second Org', code='SECOND01'):
    return db.organizations.insert_one({
        "name": name, "join_code": code, "status": "active",
        "created_at": None, "founding_admin_request_id": None,
    }).inserted_id


class TestLoginBackfillsMembership:
    """Accounts created before the memberships feature shipped have no
    membership row yet - login() creates one lazily so nobody needs a manual
    migration script to run first (see migrate_phase_b_memberships.py, which
    does the same thing in bulk for accounts that never log in again)."""

    def test_login_creates_missing_membership_for_legacy_account(self, client, db):
        from werkzeug.security import generate_password_hash
        org_id = app_module.get_default_organization_id(db)
        user_id = db.users.insert_one({
            'full_name': 'Legacy Member', 'email': 'legacy@test.com',
            'password': generate_password_hash('TestPass123'), 'role': 'lgu_member',
            'status': 'active', 'privacy_consent': True, 'organization_id': org_id,
            'permissions': {'can_review_applicants': True, 'can_manage_members': False, 'can_reset_program': False},
        }).inserted_id
        assert db.memberships.find_one({'user_id': user_id}) is None

        res = client.post('/api/login', json={'email': 'legacy@test.com', 'password': 'TestPass123'})
        assert res.status_code == 200

        membership = db.memberships.find_one({'user_id': user_id, 'organization_id': org_id})
        assert membership is not None
        assert membership['role'] == 'lgu_member'
        assert membership['permissions']['can_review_applicants'] is True

    def test_login_does_not_duplicate_existing_membership(self, client, db, make_user):
        user = make_user(email='notlegacy@test.com', password='TestPass123', role='student')
        client.post('/api/login', json={'email': 'notlegacy@test.com', 'password': 'TestPass123'})
        assert db.memberships.count_documents({'user_id': user['id']}) == 1

    def test_super_admin_login_creates_no_membership(self, client, auth_headers, db):
        auth_headers()
        assert db.memberships.count_documents({}) == 0


class TestStudentSelfServiceJoin:
    def test_join_creates_membership_and_switches(self, client, db, make_user):
        user = make_user(email='stu@test.com', password='TestPass123', role='student')
        second_org_id = make_second_org(db)
        res = client.post('/api/login', json={'email': 'stu@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] == str(second_org_id)

        membership = db.memberships.find_one({'user_id': user['id'], 'organization_id': second_org_id})
        assert membership is not None
        assert membership['role'] == 'student'
        assert db.users.find_one({'_id': user['id']})['organization_id'] == second_org_id

    def test_invalid_join_code_rejected(self, client, make_user):
        make_user(email='stu2@test.com', password='TestPass123', role='student')
        res = client.post('/api/login', json={'email': 'stu2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post('/api/organizations/join', headers=headers, json={'join_code': 'NOTREAL'})
        assert res.status_code == 400

    def test_admin_staff_cannot_use_self_service_join(self, client, auth_headers, db):
        headers = auth_headers('lgu_member')
        make_second_org(db)
        res = client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})
        assert res.status_code == 403

    def test_rejoining_same_org_is_idempotent(self, client, db, make_user):
        user = make_user(email='stu3@test.com', password='TestPass123', role='student')
        org_id = user['organization_id']
        join_code = db.organizations.find_one({'_id': org_id})['join_code']
        res = client.post('/api/login', json={'email': 'stu3@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.post('/api/organizations/join', headers=headers, json={'join_code': join_code})
        assert res.status_code == 200
        assert db.memberships.count_documents({'user_id': user['id'], 'organization_id': org_id}) == 1


class TestSwitchOrganization:
    def test_switch_between_two_memberships(self, client, db, make_user):
        user = make_user(email='switcher@test.com', password='TestPass123', role='student')
        first_org_id = user['organization_id']
        make_second_org(db)
        res = client.post('/api/login', json={'email': 'switcher@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})

        res = client.post('/api/organizations/switch', headers=headers, json={'organization_id': str(first_org_id)})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] == str(first_org_id)

    def test_switch_to_non_member_org_rejected(self, client, db, make_user):
        make_user(email='switcher2@test.com', password='TestPass123', role='student')
        other_org_id = make_second_org(db, name='Other', code='OTHER01')
        res = client.post('/api/login', json={'email': 'switcher2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post('/api/organizations/switch', headers=headers, json={'organization_id': str(other_org_id)})
        assert res.status_code == 404

    def test_super_admin_cannot_switch(self, client, auth_headers):
        res = client.post('/api/organizations/switch', headers=auth_headers(),
                           json={'organization_id': '000000000000000000000000'})
        assert res.status_code == 400


class TestListMemberships:
    def test_lists_all_orgs_with_active_flag(self, client, db, make_user):
        make_user(email='lister@test.com', password='TestPass123', role='student')
        make_second_org(db)
        res = client.post('/api/login', json={'email': 'lister@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        client.post('/api/organizations/join', headers=headers, json={'join_code': 'SECOND01'})

        # Re-login for a fresh token reflecting the switch, same as the real
        # frontend does via setSession() with the join response's token.
        res = client.post('/api/login', json={'email': 'lister@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}

        res = client.get('/api/memberships', headers=headers)
        assert res.status_code == 200
        memberships = res.get_json()['memberships']
        assert len(memberships) == 2
        assert sum(1 for m in memberships if m['is_active']) == 1

    def test_super_admin_has_no_memberships(self, client, auth_headers):
        res = client.get('/api/memberships', headers=auth_headers())
        assert res.get_json()['memberships'] == []


class TestDeleteOwnAccount:
    def test_wrong_password_rejected(self, client, make_user):
        make_user(email='del1@test.com', password='TestPass123', role='student')
        res = client.post('/api/login', json={'email': 'del1@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.delete('/api/account', headers=headers, json={'password': 'WrongPass1'})
        # Not 401 - the frontend signs the user out on any 401.
        assert res.status_code == 403

    def test_success_deletes_user_and_memberships_and_revokes_token(self, client, db, make_user):
        user = make_user(email='del2@test.com', password='TestPass123', role='student')
        res = client.post('/api/login', json={'email': 'del2@test.com', 'password': 'TestPass123'})
        token = res.get_json()['token']
        headers = {'Authorization': f"Bearer {token}"}

        res = client.delete('/api/account', headers=headers, json={'password': 'TestPass123'})
        assert res.status_code == 200
        assert db.users.find_one({'_id': user['id']}) is None
        assert db.memberships.count_documents({'user_id': user['id']}) == 0

        # Token revoked - a follow-up request with the same token 401s.
        res = client.get('/api/profile', headers=headers)
        assert res.status_code == 401

    def test_lgu_admin_seat_holder_blocked(self, client, auth_headers, db):
        from werkzeug.security import generate_password_hash
        headers = auth_headers()
        create_res = client.post('/api/admins', headers=headers, json={'full_name': 'Seat', 'email': 'seat@test.com'})
        seat_id = create_res.get_json()['admin']['id']
        client.post(f'/api/admins/{seat_id}/transfer-admin', headers=headers)
        db.users.update_one({'email': 'seat@test.com'},
                             {'$set': {'password': generate_password_hash('TestPass123'), 'password_set': True}})

        res = client.post('/api/login', json={'email': 'seat@test.com', 'password': 'TestPass123'})
        seat_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.delete('/api/account', headers=seat_headers, json={'password': 'TestPass123'})
        assert res.status_code == 400
        assert db.users.find_one({'email': 'seat@test.com'}) is not None

    def test_super_admin_cannot_self_delete(self, client, auth_headers):
        res = client.delete('/api/account', headers=auth_headers(), json={'password': 'TestPass123'})
        assert res.status_code == 403


def _login_headers(client, email, password='TestPass123'):
    res = client.post('/api/login', json={'email': email, 'password': password})
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


def _add_membership(db, user_id, org_id, role):
    db.memberships.insert_one({
        'user_id': user_id, 'organization_id': org_id, 'role': role,
        'permissions': None, 'municipality': None, 'joined_at': datetime.utcnow(),
    })


def _populate_org(db, org_id, gridfs_id):
    """One row in every collection an organization owns."""
    db.applicants.insert_one({
        'full_name': 'Some Applicant', 'email': f'applicant-{org_id}@test.com', 'organization_id': org_id,
        'documents': [{'document_name': 'School ID', 'gridfs_id': gridfs_id, 'status': 'Uploaded'}],
    })
    db.duplicate_flags.insert_one({'organization_id': org_id, 'resolved': False})
    db.notifications.insert_one({'organization_id': org_id, 'message': 'hi'})
    db.document_requirements.insert_one({'organization_id': org_id, 'label': 'School ID'})
    db.form_fields.insert_one({'organization_id': org_id, 'label': 'Extra'})
    db.program_cycles.insert_one({'organization_id': org_id, 'label': 'Program 1', 'closed_at': None})
    db.settings.insert_one({'organization_id': org_id, 'applicant_limit': 5})
    db.admin_requests.insert_one({
        'organization_id': org_id, 'status': 'pending', 'proof_of_employment': {'gridfs_id': ObjectId()},
    })


ORG_SCOPED_COLLECTIONS = (
    'applicants', 'duplicate_flags', 'notifications', 'document_requirements',
    'form_fields', 'program_cycles', 'settings', 'admin_requests', 'memberships',
)


# Registration answers a student's account carries (auth.PROFILE_FIELDS).
STUDENT_PROFILE = {
    'dob': '2003-05-01', 'gender': 'Female', 'contactNumber': '09171234567',
    'address': 'Brgy 1, Liliw, Laguna', 'fatherName': 'Pa Student', 'monthlyIncome': 9000.0,
    'familySize': 5, 'hasOtherScholarship': 'no',
}


class TestDeleteOrganization:
    """DELETE /api/organizations/<id> - the Admin-seat holder permanently
    deleting their own organization, including everything it owns."""

    def _setup(self, client, db, make_user):
        """A default org with an Admin plus one of each kind of account tied to
        it, and a second org whose data must survive. Users are created before
        the second org exists, since get_default_organization_id() returns
        whichever org is first in the collection."""
        org_id = app_module.get_default_organization_id(db)
        cast = {
            'boss': make_user(email='boss@test.com', role='lgu_admin'),
            'staff': make_user(email='staff@test.com', role='lgu_member'),
            'only_student': make_user(email='only@test.com', role='student'),
            'multi_student': make_user(email='multi@test.com', role='student'),
        }
        other_org_id = make_second_org(db)
        _add_membership(db, cast['multi_student']['id'], other_org_id, 'student')
        for key in ('only_student', 'multi_student'):
            db.users.update_one({'_id': cast[key]['id']}, {'$set': STUDENT_PROFILE})
        return org_id, other_org_id, cast

    def _delete(self, client, headers, org_id, password='TestPass123', confirm_name='Default Organization'):
        return client.delete(f'/api/organizations/{org_id}', headers=headers,
                              json={'password': password, 'confirm_name': confirm_name})

    def test_deletes_everything_the_org_owns(self, client, db, make_user, monkeypatch):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        applicant_file_id = ObjectId()
        _populate_org(db, org_id, applicant_file_id)
        _populate_org(db, other_org_id, ObjectId())
        fake_fs = MagicMock()
        monkeypatch.setattr(memberships_module, '_fs', fake_fs)

        res = self._delete(client, _login_headers(client, 'boss@test.com'), org_id)

        assert res.status_code == 200
        assert db.organizations.find_one({'_id': org_id}) is None
        for collection in ORG_SCOPED_COLLECTIONS:
            assert db[collection].count_documents({'organization_id': org_id}) == 0, collection
        fake_fs.delete.assert_any_call(applicant_file_id)
        assert fake_fs.delete.call_count == 2  # the applicant's document + the admin request's proof

        # Every other org's data is untouched.
        assert db.organizations.find_one({'_id': other_org_id}) is not None
        for collection in ORG_SCOPED_COLLECTIONS[:-1]:
            assert db[collection].count_documents({'organization_id': other_org_id}) == 1, collection

    def test_accounts_are_cleaned_up_by_how_much_they_have_left(self, client, db, make_user):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        res = self._delete(client, _login_headers(client, 'boss@test.com'), org_id)
        assert res.status_code == 200

        # A student with nothing else on the platform keeps their login but is
        # wiped clean, and is flagged so the app can tell them what happened.
        only = db.users.find_one({'_id': cast['only_student']['id']})
        assert only['email'] == 'only@test.com'
        assert only['organization_id'] is None
        assert only['disbanded_organization_name'] == 'Default Organization'
        assert not any(field in only for field in STUDENT_PROFILE)

        # A student in another org too keeps everything, moved into that org.
        multi = db.users.find_one({'_id': cast['multi_student']['id']})
        assert multi['organization_id'] == other_org_id
        assert 'disbanded_organization_name' not in multi
        assert all(multi[field] == value for field, value in STUDENT_PROFILE.items())
        assert db.memberships.count_documents({'user_id': multi['_id']}) == 1

        # Staff keep their account, left with no org and no permissions.
        for key in ('staff', 'boss'):
            user = db.users.find_one({'_id': cast[key]['id']})
            assert user is not None
            assert user['organization_id'] is None
            assert user['role'] == 'lgu_member'
            assert not any(user['permissions'].values())
            assert user['disbanded_organization_name'] == 'Default Organization'

    def test_disbanded_student_is_told_and_can_join_another_org(self, client, db, make_user):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        # A session that's already open when the org gets deleted.
        stale_headers = _login_headers(client, 'only@test.com')
        self._delete(client, _login_headers(client, 'boss@test.com'), org_id)

        # Even that stale session can find out why it's empty.
        body = client.get('/api/memberships', headers=stale_headers).get_json()
        assert body['memberships'] == []
        assert body['disbanded_organization_name'] == 'Default Organization'

        # Their saved profile is gone, so the next application form starts blank.
        profile = client.get('/api/profile', headers=stale_headers).get_json()['profile']
        assert all(profile[field] == '' for field in STUDENT_PROFILE)

        # They can still sign in, and joining another org with a code ends the notice.
        res = client.post('/api/organizations/join', headers=_login_headers(client, 'only@test.com'),
                           json={'join_code': 'SECOND01'})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] == str(other_org_id)
        assert 'disbanded_organization_name' not in db.users.find_one({'_id': cast['only_student']['id']})
        joined_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        body = client.get('/api/memberships', headers=joined_headers).get_json()
        assert body['disbanded_organization_name'] is None
        assert [m['organization_id'] for m in body['memberships']] == [str(other_org_id)]

    def test_disbanded_staff_are_told_and_the_notice_ends_once_they_reach_another_org(self, client, db, make_user):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        stale_headers = _login_headers(client, 'staff@test.com')
        self._delete(client, _login_headers(client, 'boss@test.com'), org_id)

        # Even on a session that was open when the org was deleted, and even for
        # the ex-Admin who deleted it (who logs back in with no org).
        body = client.get('/api/memberships', headers=stale_headers).get_json()
        assert body['memberships'] == []
        assert body['disbanded_organization_name'] == 'Default Organization'
        boss_headers = _login_headers(client, 'boss@test.com')
        body = client.get('/api/memberships', headers=boss_headers).get_json()
        assert body['disbanded_organization_name'] == 'Default Organization'

        # Once another org approves them (a membership row appears) and they're
        # switched into it, the notice ends.
        _add_membership(db, cast['staff']['id'], other_org_id, 'lgu_member')
        res = client.post('/api/organizations/switch', headers=_login_headers(client, 'staff@test.com'),
                           json={'organization_id': str(other_org_id)})
        assert res.status_code == 200
        assert 'disbanded_organization_name' not in db.users.find_one({'_id': cast['staff']['id']})
        joined_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        assert client.get('/api/memberships', headers=joined_headers).get_json()['disbanded_organization_name'] is None

    def test_student_moved_elsewhere_has_no_active_org_on_a_stale_session(self, client, db, make_user):
        """The student portal relies on this to notice a session still naming the
        deleted org and switch the student into the org they were moved to."""
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        stale_headers = _login_headers(client, 'multi@test.com')
        self._delete(client, _login_headers(client, 'boss@test.com'), org_id)

        body = client.get('/api/memberships', headers=stale_headers).get_json()
        assert [m['organization_id'] for m in body['memberships']] == [str(other_org_id)]
        assert not any(m['is_active'] for m in body['memberships'])
        assert body['disbanded_organization_name'] is None

    def test_admin_with_nowhere_else_to_go_is_signed_out(self, client, db, make_user):
        org_id, _, _ = self._setup(client, db, make_user)
        headers = _login_headers(client, 'boss@test.com')

        res = self._delete(client, headers, org_id)

        body = res.get_json()
        assert body['signed_out'] is True
        assert 'token' not in body
        assert client.get('/api/profile', headers=headers).status_code == 401

    def test_admin_who_belongs_elsewhere_is_moved_there(self, client, db, make_user):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        _add_membership(db, cast['boss']['id'], other_org_id, 'lgu_member')

        res = self._delete(client, _login_headers(client, 'boss@test.com'), org_id)

        body = res.get_json()
        assert 'signed_out' not in body
        assert body['user']['organization_id'] == str(other_org_id)
        assert body['user']['role'] == 'lgu_member'
        assert body['token']
        assert db.users.find_one({'_id': cast['boss']['id']})['organization_id'] == other_org_id

    def test_deleting_a_non_active_org_leaves_the_session_alone(self, client, db, make_user):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        _add_membership(db, cast['boss']['id'], other_org_id, 'lgu_admin')
        headers = _login_headers(client, 'boss@test.com')

        res = self._delete(client, headers, other_org_id, confirm_name='Second Org')

        body = res.get_json()
        assert res.status_code == 200
        assert 'token' not in body and 'signed_out' not in body
        assert db.organizations.find_one({'_id': other_org_id}) is None
        assert db.organizations.find_one({'_id': org_id}) is not None
        assert db.users.find_one({'_id': cast['boss']['id']})['organization_id'] == org_id
        assert client.get('/api/profile', headers=headers).status_code == 200

    def test_login_does_not_recreate_membership_in_deleted_org(self, client, db, make_user):
        org_id, _, cast = self._setup(client, db, make_user)
        # A pre-memberships legacy account: cached org, but no membership row.
        legacy_id = db.users.insert_one({
            'full_name': 'Legacy', 'email': 'legacy@test.com', 'role': 'lgu_member', 'status': 'active',
            'password': generate_password_hash('TestPass123'), 'organization_id': org_id,
            'permissions': {'can_review_applicants': True, 'can_manage_members': False, 'can_reset_program': False},
        }).inserted_id

        self._delete(client, _login_headers(client, 'boss@test.com'), org_id)

        assert db.users.find_one({'_id': legacy_id})['organization_id'] is None
        assert client.post('/api/login', json={'email': 'legacy@test.com', 'password': 'TestPass123'}).status_code == 200
        assert db.memberships.count_documents({'user_id': legacy_id}) == 0

    def test_wrong_password_rejected_without_signing_out(self, client, db, make_user):
        org_id, _, _ = self._setup(client, db, make_user)
        res = self._delete(client, _login_headers(client, 'boss@test.com'), org_id, password='WrongPass1')
        # Not 401 - the frontend signs the user out on any 401.
        assert res.status_code == 403
        assert db.organizations.find_one({'_id': org_id}) is not None

    def test_name_must_match_exactly(self, client, db, make_user):
        org_id, _, _ = self._setup(client, db, make_user)
        headers = _login_headers(client, 'boss@test.com')
        for wrong in ('', 'default organization', 'Default'):
            res = self._delete(client, headers, org_id, confirm_name=wrong)
            assert res.status_code == 400
        assert db.organizations.find_one({'_id': org_id}) is not None

    def test_only_the_admin_seat_holder_can_delete(self, client, db, make_user):
        org_id, other_org_id, cast = self._setup(client, db, make_user)
        other_admin = make_user(email='otherboss@test.com', role='lgu_admin', organization_id=other_org_id)

        for email in ('staff@test.com', 'only@test.com', 'otherboss@test.com'):
            res = self._delete(client, _login_headers(client, email), org_id)
            assert res.status_code == 403, email
        assert db.organizations.find_one({'_id': org_id}) is not None

    def test_super_admin_cannot_delete(self, client, db, auth_headers):
        org_id = app_module.get_default_organization_id(db)
        res = self._delete(client, auth_headers(), org_id)
        assert res.status_code == 400
        assert db.organizations.find_one({'_id': org_id}) is not None

    def test_requires_login(self, client, db):
        org_id = app_module.get_default_organization_id(db)
        assert client.delete(f'/api/organizations/{org_id}', json={}).status_code == 401


class TestRequestJoinOrg:
    def test_lgu_member_can_submit_request(self, client, auth_headers, db):
        # auth_headers (via make_user -> get_default_organization_id) must run
        # BEFORE a second org is inserted - get_default_organization_id()
        # returns whichever org happens to be first in the collection with no
        # other filter, so creating "Second Org" first would make IT the
        # "default" org the fixture user lands in.
        headers = auth_headers('lgu_member')
        make_second_org(db)
        data = {
            'join_code': 'SECOND01', 'municipality': 'Testville', 'contact_number': '09171234567',
            'message': 'please', 'file': (io.BytesIO(b'fake pdf content'), 'proof.pdf'),
        }
        res = client.post('/api/admin-requests/join-org', headers=headers,
                           data=data, content_type='multipart/form-data')
        assert res.status_code == 201
        req = db.admin_requests.find_one({'request_kind': 'add_membership'})
        assert req is not None
        assert req['status'] == 'pending'

    def test_student_cannot_submit_request(self, client, auth_headers, db):
        headers = auth_headers('student')
        make_second_org(db)
        data = {
            'join_code': 'SECOND01', 'municipality': 'X', 'contact_number': '123',
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        }
        res = client.post('/api/admin-requests/join-org', headers=headers,
                           data=data, content_type='multipart/form-data')
        assert res.status_code == 403

    def test_already_current_org_rejected(self, client, auth_headers, db):
        own_org_id = app_module.get_default_organization_id(db)
        own_code = db.organizations.find_one({'_id': own_org_id})['join_code']
        data = {
            'join_code': own_code, 'municipality': 'X', 'contact_number': '123',
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        }
        res = client.post('/api/admin-requests/join-org', headers=auth_headers('lgu_member'),
                           data=data, content_type='multipart/form-data')
        assert res.status_code == 400


class TestApproveJoinOrgRequest:
    def test_approval_creates_membership_not_new_user(self, client, db, make_user):
        requester = make_user(email='req@test.com', password='TestPass123', role='lgu_member',
                               permissions={'can_review_applicants': False})
        second_org_id = make_second_org(db)
        make_user(email='secondadmin@test.com', password='TestPass123', role='lgu_admin',
                  organization_id=second_org_id)

        res = client.post('/api/login', json={'email': 'req@test.com', 'password': 'TestPass123'})
        requester_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        data = {
            'join_code': 'SECOND01', 'municipality': 'X', 'contact_number': '123',
            'file': (io.BytesIO(b'fake'), 'proof.pdf'),
        }
        client.post('/api/admin-requests/join-org', headers=requester_headers, data=data, content_type='multipart/form-data')
        req = db.admin_requests.find_one({'request_kind': 'add_membership'})

        res = client.post('/api/login', json={'email': 'secondadmin@test.com', 'password': 'TestPass123'})
        second_admin_headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=second_admin_headers,
                           json={'permissions': {'can_review_applicants': True}})
        assert res.status_code == 201
        assert 'membership' in res.get_json()

        # No new login was created - same email, same account.
        assert db.users.count_documents({'email': 'req@test.com'}) == 1
        membership = db.memberships.find_one({'user_id': requester['id'], 'organization_id': second_org_id})
        assert membership is not None
        assert membership['role'] == 'lgu_member'
        assert membership['permissions']['can_review_applicants'] is True

    def test_already_member_rejected_on_approve(self, client, db, make_user):
        requester = make_user(email='req2@test.com', password='TestPass123', role='lgu_member')
        second_org_id = make_second_org(db)
        db.admin_requests.insert_one({
            'request_kind': 'add_membership', 'user_id': requester['id'], 'full_name': 'Req2',
            'email': 'req2@test.com', 'password_hash': None, 'municipality': 'X', 'contact_number': '123',
            'message': '', 'proof_of_employment': None, 'status': 'pending', 'first_approval': None,
            'second_approval': None, 'created_at': None, 'reviewed_at': None, 'reviewed_by': None,
            'organization_id': second_org_id, 'is_founding': False,
        })
        db.memberships.insert_one({
            'user_id': requester['id'], 'organization_id': second_org_id, 'role': 'lgu_member',
            'permissions': {'can_review_applicants': False, 'can_manage_members': False, 'can_reset_program': False},
            'municipality': 'X', 'joined_at': None,
        })
        req = db.admin_requests.find_one({'request_kind': 'add_membership'})

        second_admin = make_user(email='secondadmin2@test.com', password='TestPass123', role='lgu_admin',
                                  organization_id=second_org_id)
        res = client.post('/api/login', json={'email': 'secondadmin2@test.com', 'password': 'TestPass123'})
        headers = {'Authorization': f"Bearer {res.get_json()['token']}"}
        res = client.post(f'/api/admin-requests/{req["_id"]}/approve', headers=headers, json={})
        assert res.status_code == 409
