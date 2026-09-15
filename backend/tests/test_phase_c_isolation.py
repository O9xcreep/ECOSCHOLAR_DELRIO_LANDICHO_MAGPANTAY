# -*- coding: utf-8 -*-
"""Multi-tenancy Phase C: route-level query scoping by organization_id across
applicants, settings, guidelines, form fields, document requirements,
duplicate flags, program cycles, and stats/ranking. Two organizations on
one deployment must never see or touch each other's data."""
from datetime import datetime

import app as app_module


def make_org(db, name):
    return db.organizations.insert_one({
        "name": name, "join_code": app_module.generate_join_code(),
        "status": "active", "created_at": datetime.utcnow(), "founding_admin_request_id": None,
    }).inserted_id


def login_headers(client, user):
    res = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


def two_orgs_with_admins(db, make_user, client):
    """Org A is the auto-created default org; Org B is a second, freshly made
    one. Returns (org_a_id, headers_a, org_b_id, headers_b)."""
    org_a_id = app_module.get_default_organization_id(db)
    admin_a = make_user(email='admin-a@test.com', password='TestPass123', role='admin', organization_id=org_a_id)
    org_b_id = make_org(db, 'Org B')
    admin_b = make_user(email='admin-b@test.com', password='TestPass123', role='admin', organization_id=org_b_id)
    return org_a_id, login_headers(client, admin_a), org_b_id, login_headers(client, admin_b)


def make_applicant(db, org_id, email, full_name='Test Applicant', **overrides):
    doc = {
        'full_name': full_name, 'email': email, 'organization_id': org_id,
        'ml_score': 80, 'ml_status': 'Eligible',
        'application': {'status': 'Newly Submitted'},
        'academic': {'academic_year': '2026', 'gpa': 1.5, 'course': 'BSCS'},
        'monthly_income': 10000, 'housing_situation': 'Rented',
        'num_siblings': 1, 'num_siblings_studying': 1,
        'father_education': 'College', 'mother_education': 'College',
        'father_occupation': 'Laborer/Driver', 'mother_occupation': 'Laborer/Driver',
        'family_size': 4, 'gender': 'Male', 'has_other_scholarship': False,
        'documents': [], 'audit_trail': [],
    }
    doc.update(overrides)
    return db.applicants.insert_one(doc).inserted_id


class TestApplicantListIsolation:
    def test_admin_only_sees_own_org_applicants(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        make_applicant(db, org_a, 'a1@test.com', full_name='Org A Applicant')
        make_applicant(db, org_b, 'b1@test.com', full_name='Org B Applicant')

        res_a = client.get('/api/applicants', headers=headers_a).get_json()
        names_a = [a['full_name'] for a in res_a['applicants']]
        assert 'Org A Applicant' in names_a
        assert 'Org B Applicant' not in names_a

        res_b = client.get('/api/applicants', headers=headers_b).get_json()
        names_b = [a['full_name'] for a in res_b['applicants']]
        assert 'Org B Applicant' in names_b
        assert 'Org A Applicant' not in names_b

    def test_paginated_listing_also_isolated(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        make_applicant(db, org_a, 'a1@test.com', full_name='Org A Applicant')
        make_applicant(db, org_b, 'b1@test.com', full_name='Org B Applicant')

        res = client.get('/api/applicants?page=1&limit=50', headers=headers_a).get_json()
        assert res['total'] == 1
        assert res['applicants'][0]['full_name'] == 'Org A Applicant'

    def test_cannot_fetch_another_orgs_applicant_by_id(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        applicant_id = make_applicant(db, org_a, 'a1@test.com')

        res = client.get(f'/api/applicants/{applicant_id}', headers=headers_b)
        assert res.get_json()['applicant'] is None

    def test_cannot_update_status_of_another_orgs_applicant(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        applicant_id = make_applicant(db, org_a, 'a1@test.com')

        res = client.put(f'/api/applications/{applicant_id}/status', headers=headers_b,
                          json={'status': 'Incomplete'})
        assert res.status_code == 404

    def test_cannot_see_another_orgs_audit_trail(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        applicant_id = make_applicant(db, org_a, 'a1@test.com', audit_trail=[
            {'action': 'test', 'performed_at': datetime.utcnow()}
        ])

        res = client.get(f'/api/audit-trail/{applicant_id}', headers=headers_b)
        assert res.get_json()['trail'] == []


class TestSettingsIsolation:
    def test_settings_are_independent_per_org(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)

        client.put('/api/settings', headers=headers_a, json={'max_accepted': 5})
        client.put('/api/settings', headers=headers_b, json={'max_accepted': 99})

        assert client.get('/api/settings', headers=headers_a).get_json()['max_accepted'] == 5
        assert client.get('/api/settings', headers=headers_b).get_json()['max_accepted'] == 99

    def test_guidelines_are_independent_per_org(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)

        client.put('/api/guidelines', headers=headers_a, json={'html': '<p>Org A rules</p>'})
        client.put('/api/guidelines', headers=headers_b, json={'html': '<p>Org B rules</p>'})

        assert 'Org A rules' in client.get('/api/guidelines', headers=headers_a).get_json()['html']
        assert 'Org B rules' in client.get('/api/guidelines', headers=headers_b).get_json()['html']


class TestFormFieldsIsolation:
    def test_org_b_does_not_see_org_as_custom_field(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)

        client.post('/api/form-fields', headers=headers_a,
                    json={'key': 'org_a_field', 'label': 'Org A Field', 'type': 'text', 'section': 'personal'})

        keys_b = [f['key'] for f in client.get('/api/form-fields', headers=headers_b).get_json()['fields']]
        assert 'org_a_field' not in keys_b

    def test_two_orgs_can_reuse_the_same_field_key(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)

        res_a = client.post('/api/form-fields', headers=headers_a,
                             json={'key': 'shared_key', 'label': 'A', 'type': 'text', 'section': 'personal'})
        res_b = client.post('/api/form-fields', headers=headers_b,
                             json={'key': 'shared_key', 'label': 'B', 'type': 'text', 'section': 'personal'})
        assert res_a.status_code == 201
        assert res_b.status_code == 201

    def test_cannot_edit_another_orgs_field(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        field_id = client.post('/api/form-fields', headers=headers_a,
                                json={'key': 'a_field', 'label': 'A', 'type': 'text', 'section': 'personal'}
                                ).get_json()['field']['id']

        res = client.put(f'/api/form-fields/{field_id}', headers=headers_b, json={'label': 'Hijacked'})
        assert res.status_code == 404


class TestDocumentRequirementsIsolation:
    def test_each_org_gets_its_own_seeded_defaults(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)

        reqs_a = client.get('/api/document-requirements', headers=headers_a).get_json()['requirements']
        reqs_b = client.get('/api/document-requirements', headers=headers_b).get_json()['requirements']
        assert len(reqs_a) == len(app_module.DEFAULT_DOC_REQUIREMENTS)
        assert len(reqs_b) == len(app_module.DEFAULT_DOC_REQUIREMENTS)
        # Different document requirement documents (different _id's) per org.
        assert {r['id'] for r in reqs_a}.isdisjoint({r['id'] for r in reqs_b})

    def test_two_orgs_can_reuse_the_same_label(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)

        res_a = client.post('/api/document-requirements', headers=headers_a, json={'label': 'Custom Doc'})
        res_b = client.post('/api/document-requirements', headers=headers_b, json={'label': 'Custom Doc'})
        assert res_a.status_code == 201
        assert res_b.status_code == 201

    def test_cannot_delete_another_orgs_requirement(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        req_id = client.post('/api/document-requirements', headers=headers_a,
                              json={'label': 'A Only Doc'}).get_json()['requirement']['id']

        res = client.delete(f'/api/document-requirements/{req_id}', headers=headers_b)
        assert res.status_code == 404


class TestDuplicateFlagsIsolation:
    def test_org_b_does_not_see_org_as_flags(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        applicant_id = make_applicant(db, org_a, 'a1@test.com')
        db.duplicate_flags.insert_one({
            'applicant_id': applicant_id, 'duplicate_of_id': applicant_id, 'reason': 'email',
            'flagged_at': datetime.utcnow(), 'resolved': False, 'organization_id': org_a,
        })

        flags_b = client.get('/api/duplicate-flags', headers=headers_b).get_json()['flags']
        assert flags_b == []
        flags_a = client.get('/api/duplicate-flags', headers=headers_a).get_json()['flags']
        assert len(flags_a) == 1

    def test_cannot_resolve_another_orgs_flag(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        applicant_id = make_applicant(db, org_a, 'a1@test.com')
        flag_id = db.duplicate_flags.insert_one({
            'applicant_id': applicant_id, 'duplicate_of_id': applicant_id, 'reason': 'email',
            'flagged_at': datetime.utcnow(), 'resolved': False, 'organization_id': org_a,
        }).inserted_id

        res = client.put(f'/api/duplicate-flags/{flag_id}/resolve', headers=headers_b)
        assert res.status_code == 404
        assert db.duplicate_flags.find_one({'_id': flag_id})['resolved'] is False


class TestProgramCyclesAndStatsIsolation:
    def test_program_reset_only_affects_the_resetting_org(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        client.put('/api/settings', headers=headers_a, json={'reset_password': 'ResetPass123'})

        res = client.post('/api/program-reset', headers=headers_a, json={'password': 'ResetPass123', 'deadline': '2099-01-01T00:00:00'})
        assert res.status_code == 200

        cycles_a = client.get('/api/program-cycles', headers=headers_a).get_json()['cycles']
        cycles_b = client.get('/api/program-cycles', headers=headers_b).get_json()['cycles']
        assert len(cycles_a) == 1
        assert len(cycles_b) == 0

    def test_stats_only_count_own_org_applicants(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        make_applicant(db, org_a, 'a1@test.com')
        make_applicant(db, org_a, 'a2@test.com')
        make_applicant(db, org_b, 'b1@test.com')

        stats_a = client.get('/api/stats', headers=headers_a).get_json()
        stats_b = client.get('/api/stats', headers=headers_b).get_json()
        assert stats_a['total'] == 2
        assert stats_b['total'] == 1

    def test_rank_applicants_only_ranks_own_org(self, client, db, make_user):
        org_a, headers_a, org_b, headers_b = two_orgs_with_admins(db, make_user, client)
        make_applicant(db, org_a, 'a1@test.com', full_name='Org A Ranked', application={'status': 'Approved'})
        make_applicant(db, org_b, 'b1@test.com', full_name='Org B Ranked', application={'status': 'Approved'})

        res_b = client.get('/api/rank-applicants', headers=headers_b).get_json()
        names_b = [r['full_name'] for r in res_b['ranked']]
        assert 'Org B Ranked' in names_b
        assert 'Org A Ranked' not in names_b
