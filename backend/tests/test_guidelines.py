# -*- coding: utf-8 -*-
"""Application Guidelines: student-facing read, admin-only edit, stored as a
single HTML blob on the org's settings doc instead of hardcoded in the
frontend."""
import app as app_module


def get_settings_doc(db):
    org_id = app_module.get_default_organization_id(db)
    return db.settings.find_one({'organization_id': org_id})


class TestGetGuidelines:
    def test_requires_auth(self, client):
        res = client.get('/api/guidelines')
        assert res.status_code == 401

    def test_student_can_read(self, client, auth_headers):
        res = client.get('/api/guidelines', headers=auth_headers('student'))
        assert res.status_code == 200
        assert 'html' in res.get_json()

    def test_defaults_to_seeded_content_when_never_set(self, client, auth_headers):
        res = client.get('/api/guidelines', headers=auth_headers('student'))
        assert 'General Eligibility Criteria' in res.get_json()['html']


class TestUpdateGuidelines:
    def test_requires_admin_role(self, client, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers('student'), json={'html': '<p>Hi</p>'})
        assert res.status_code == 403

    def test_lgu_member_cannot_edit_even_with_permissions(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_manage_members': True, 'can_reset_program': True})
        res = client.put('/api/guidelines', headers=headers, json={'html': '<p>Hi</p>'})
        assert res.status_code == 403

    def test_admin_can_update_and_it_is_reflected_on_read(self, client, db, auth_headers):
        headers = auth_headers()
        res = client.put('/api/guidelines', headers=headers, json={'html': '<h2>New Rules</h2><p>Read carefully.</p>'})
        assert res.status_code == 200
        assert 'New Rules' in res.get_json()['html']

        stored = get_settings_doc(db)
        assert 'New Rules' in stored['guidelines_html']

        read_res = client.get('/api/guidelines', headers=auth_headers('student'))
        assert 'New Rules' in read_res.get_json()['html']

    def test_lgu_admin_can_update(self, client, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers('lgu_admin'), json={'html': '<p>Updated</p>'})
        assert res.status_code == 200

    def test_empty_html_rejected(self, client, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers(), json={'html': '   '})
        assert res.status_code == 400

    def test_missing_html_rejected(self, client, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers(), json={})
        assert res.status_code == 400

    def test_too_long_html_rejected(self, client, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers(), json={'html': '<p>x</p>' * 50000})
        assert res.status_code == 400

    def test_script_tags_stripped(self, client, db, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers(),
                          json={'html': '<p>Hello</p><script>alert(1)</script>'})
        assert res.status_code == 200
        stored = get_settings_doc(db)['guidelines_html']
        assert '<script>' not in stored
        assert 'Hello' in stored

    def test_inline_event_handlers_stripped(self, client, db, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers(),
                          json={'html': '<img src="x" onerror="alert(1)">'})
        assert res.status_code == 200
        stored = get_settings_doc(db)['guidelines_html']
        assert 'onerror' not in stored

    def test_javascript_href_neutralized(self, client, db, auth_headers):
        res = client.put('/api/guidelines', headers=auth_headers(),
                          json={'html': '<a href="javascript:alert(1)">click</a>'})
        assert res.status_code == 200
        stored = get_settings_doc(db)['guidelines_html']
        assert 'javascript:' not in stored
