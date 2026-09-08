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
