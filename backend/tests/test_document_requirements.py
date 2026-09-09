# -*- coding: utf-8 -*-
"""Document requirements seeding, including the selfie step added in this phase
(backend/app.py SELFIE_DOC_LABEL) and its backfill into deployments that were
already seeded with the original six-document checklist."""

SELFIE_DOC_LABEL = 'Selfie / Face Photo'


class TestDocumentRequirementsSeeding:
    def test_fresh_seed_includes_selfie_as_required(self, client, db, auth_headers):
        res = client.get('/api/document-requirements', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        labels = {r['label']: r for r in body['requirements']}
        assert SELFIE_DOC_LABEL in labels
        assert labels[SELFIE_DOC_LABEL]['required'] is True
        assert labels[SELFIE_DOC_LABEL]['enabled'] is True

    def test_backfills_selfie_into_a_pre_existing_checklist(self, client, db, auth_headers):
        """Simulates a deployment seeded before this phase existed: six
        requirements, no selfie. The next GET should add it without touching
        the others."""
        db.document_requirements.insert_many([
            {'label': 'Enrollment Form', 'required': True, 'enabled': True, 'order': 0},
            {'label': 'School ID', 'required': True, 'enabled': True, 'order': 1},
        ])
        res = client.get('/api/document-requirements', headers=auth_headers())
        body = res.get_json()
        labels = [r['label'] for r in body['requirements']]
        assert labels.count('Enrollment Form') == 1
        assert labels.count('School ID') == 1
        assert SELFIE_DOC_LABEL in labels

    def test_backfill_only_runs_once(self, client, db, auth_headers):
        client.get('/api/document-requirements', headers=auth_headers())
        client.get('/api/document-requirements', headers=auth_headers())
        assert db.document_requirements.count_documents({'label': SELFIE_DOC_LABEL}) == 1

    def test_default_requirements_are_flagged_is_default(self, client, auth_headers):
        res = client.get('/api/document-requirements', headers=auth_headers())
        labels = {r['label']: r for r in res.get_json()['requirements']}
        assert labels['Enrollment Form']['is_default'] is True
        assert labels[SELFIE_DOC_LABEL]['is_default'] is True

    def test_custom_requirement_is_not_flagged_is_default(self, client, auth_headers):
        client.get('/api/document-requirements', headers=auth_headers())  # seed defaults
        res = client.post('/api/document-requirements', headers=auth_headers(),
                           json={'label': 'Custom Certificate', 'required': False})
        assert res.status_code == 201
        assert res.get_json()['requirement']['is_default'] is False


class TestCannotDeleteDefaultRequirements:
    def test_default_requirement_cannot_be_deleted(self, client, db, auth_headers):
        client.get('/api/document-requirements', headers=auth_headers())  # seed defaults
        enrollment = db.document_requirements.find_one({'label': 'Enrollment Form'})

        res = client.delete(f"/api/document-requirements/{enrollment['_id']}", headers=auth_headers())
        assert res.status_code == 400
        assert db.document_requirements.find_one({'_id': enrollment['_id']}) is not None

    def test_custom_requirement_can_still_be_deleted(self, client, auth_headers):
        client.get('/api/document-requirements', headers=auth_headers())  # seed defaults
        create_res = client.post('/api/document-requirements', headers=auth_headers(),
                                  json={'label': 'Custom Certificate', 'required': False})
        req_id = create_res.get_json()['requirement']['id']

        res = client.delete(f'/api/document-requirements/{req_id}', headers=auth_headers())
        assert res.status_code == 200

    def test_default_requirement_can_still_be_disabled_and_unrequired(self, client, db, auth_headers):
        """Deletion is blocked, but toggling enabled/required must keep working -
        that's still how an LGU opts out of a default document it doesn't need."""
        client.get('/api/document-requirements', headers=auth_headers())  # seed defaults
        enrollment = db.document_requirements.find_one({'label': 'Enrollment Form'})

        res = client.put(f"/api/document-requirements/{enrollment['_id']}", headers=auth_headers(),
                          json={'enabled': False, 'required': False})
        assert res.status_code == 200
        assert res.get_json()['requirement']['enabled'] is False
        assert res.get_json()['requirement']['required'] is False
