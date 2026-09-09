# -*- coding: utf-8 -*-
"""Multi-tenancy Phase A: get_default_organization_id() bootstraps exactly one
organization and every write to a per-tenant collection tags itself with it,
ahead of any query actually filtering on organization_id (that's Phase C).
Nothing here should change existing behavior - it's purely additive."""
import app as app_module

REGISTER_PAYLOAD = {
    'full_name': 'Org Test Student', 'email': 'orgtest@test.com', 'password': 'TestPass123',
    'dob': '2003-01-01', 'gender': 'Male', 'religion': 'X', 'citizenship': 'Filipino',
    'contactNumber': '09171234567', 'address': 'Test',
    'fatherName': 'F', 'fatherOccupation': 'Laborer/Driver', 'fatherEducation': 'College',
    'motherName': 'M', 'motherOccupation': 'Laborer/Driver', 'motherEducation': 'College',
    'monthlyIncome': '10000', 'familySize': '4', 'numSiblings': '1', 'numSiblingsStudying': '1',
    'housingSituation': 'Owned', 'hasOtherScholarship': 'no', 'otherScholarshipDetails': '',
}


class TestGetDefaultOrganizationId:
    def test_creates_one_organization_on_first_call(self, db):
        assert db.organizations.count_documents({}) == 0
        org_id = app_module.get_default_organization_id(db)
        assert db.organizations.count_documents({}) == 1
        org = db.organizations.find_one({"_id": org_id})
        assert org["status"] == "active"
        assert org["name"] == "Default Organization"
        assert org["join_code"]

    def test_idempotent_across_calls(self, db):
        first = app_module.get_default_organization_id(db)
        second = app_module.get_default_organization_id(db)
        assert first == second
        assert db.organizations.count_documents({}) == 1

    def test_join_code_is_unique_indexed(self, db):
        # The real index is only ever created once, at app.py import time -
        # the per-test collection-drop fixture wipes it along with the data,
        # so re-create it here to prove the *constraint* (not the one-time
        # app-startup call) actually rejects a duplicate join_code.
        db.organizations.create_index('join_code', unique=True)
        app_module.get_default_organization_id(db)

        import pymongo.errors
        try:
            db.organizations.insert_one({
                "name": "Duplicate", "join_code": db.organizations.find_one({})["join_code"],
                "status": "active", "created_at": None, "founding_admin_request_id": None,
            })
            raised = False
        except pymongo.errors.DuplicateKeyError:
            raised = True
        assert raised


class TestNewDataIsTaggedWithOrganizationId:
    """Spot-checks across the collections that get tagged at write time -
    not exhaustive, but covers each app-facing entry point that creates data."""

    def test_registration_tags_the_new_user(self, client, db):
        org_id = app_module.get_default_organization_id(db)
        join_code = db.organizations.find_one({"_id": org_id})["join_code"]
        res = client.post('/api/register', json={**REGISTER_PAYLOAD, 'join_code': join_code})
        assert res.status_code == 201
        user = db.users.find_one({'email': 'orgtest@test.com'})
        org_id = app_module.get_default_organization_id(db)
        assert user['organization_id'] == org_id

    def test_admin_added_directly_is_tagged(self, client, auth_headers, db):
        res = client.post('/api/admins', headers=auth_headers(),
                           json={'full_name': 'New Admin', 'email': 'newadmin-org@test.com'})
        assert res.status_code == 201
        user = db.users.find_one({'email': 'newadmin-org@test.com'})
        org_id = app_module.get_default_organization_id(db)
        assert user['organization_id'] == org_id

    def test_custom_form_field_is_tagged(self, client, auth_headers, db):
        res = client.post('/api/form-fields', headers=auth_headers(),
                           json={'key': 'org_test_field', 'label': 'Org Test', 'type': 'text', 'section': 'personal'})
        assert res.status_code == 201
        field = db.form_fields.find_one({'key': 'org_test_field'})
        org_id = app_module.get_default_organization_id(db)
        assert field['organization_id'] == org_id

    def test_document_requirements_seed_is_tagged(self, client, auth_headers, db):
        client.get('/api/document-requirements', headers=auth_headers())
        org_id = app_module.get_default_organization_id(db)
        seeded = list(db.document_requirements.find({}))
        assert len(seeded) > 0
        assert all(d.get('organization_id') == org_id for d in seeded)


class TestTokenCarriesOrganizationId:
    def test_login_response_includes_organization_id(self, client, db, make_user):
        org_id = app_module.get_default_organization_id(db)
        user = make_user(email='orgtoken@test.com', password='TestPass123', role='student')
        db.users.update_one({'_id': user['id']}, {'$set': {'organization_id': org_id}})

        res = client.post('/api/login', json={'email': 'orgtoken@test.com', 'password': 'TestPass123'})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] == str(org_id)

    def test_login_with_no_organization_id_does_not_crash(self, client, make_user):
        """A user predating this migration (or one inserted directly in a
        test) has no organization_id field at all - must not 500."""
        user = make_user(email='no-org@test.com', password='TestPass123', role='student', organization_id=False)
        res = client.post('/api/login', json={'email': 'no-org@test.com', 'password': 'TestPass123'})
        assert res.status_code == 200
        assert res.get_json()['user']['organization_id'] is None


class TestLookupOrganization:
    def test_valid_code_returns_organization_name(self, client, db):
        org_id = app_module.get_default_organization_id(db)
        join_code = db.organizations.find_one({"_id": org_id})["join_code"]
        res = client.get(f'/api/organizations/lookup?code={join_code}')
        assert res.status_code == 200
        assert res.get_json()['organization']['name'] == 'Default Organization'

    def test_lowercase_code_still_matches(self, client, db):
        org_id = app_module.get_default_organization_id(db)
        join_code = db.organizations.find_one({"_id": org_id})["join_code"]
        res = client.get(f'/api/organizations/lookup?code={join_code.lower()}')
        assert res.status_code == 200

    def test_invalid_code_rejected(self, client, db):
        res = client.get('/api/organizations/lookup?code=NOTREAL')
        assert res.status_code == 404

    def test_pending_organization_not_findable(self, client, db):
        db.organizations.insert_one({
            "name": "Pending Org", "join_code": "PEND01", "status": "pending",
            "created_at": None, "founding_admin_request_id": None,
        })
        res = client.get('/api/organizations/lookup?code=PEND01')
        assert res.status_code == 404


class TestGetMyOrganization:
    def test_admin_sees_own_join_code(self, client, auth_headers, db):
        org_id = app_module.get_default_organization_id(db)
        expected_code = db.organizations.find_one({"_id": org_id})["join_code"]
        res = client.get('/api/organizations/mine', headers=auth_headers())
        assert res.status_code == 200
        body = res.get_json()['organization']
        assert body['join_code'] == expected_code
        assert body['name'] == 'Default Organization'

    def test_lgu_member_without_permission_cannot_view(self, client, auth_headers):
        res = client.get('/api/organizations/mine', headers=auth_headers('lgu_member'))
        assert res.status_code == 403

    def test_lgu_member_with_manage_members_can_view(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_manage_members': True})
        res = client.get('/api/organizations/mine', headers=headers)
        assert res.status_code == 200
