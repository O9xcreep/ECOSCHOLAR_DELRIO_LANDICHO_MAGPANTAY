# -*- coding: utf-8 -*-
"""Custom form fields (Form Builder). Checkbox fields can optionally carry an
options list, same as select; one with no options stays a simple Yes/No
toggle, so existing checkbox fields are unaffected."""


class TestCreateFormField:
    def test_select_requires_at_least_one_option(self, client, auth_headers):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'fav_color', 'label': 'Favorite Color', 'type': 'select', 'section': 'personal',
        })
        assert res.status_code == 400

    def test_checkbox_options_are_persisted(self, client, auth_headers, db):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'transport_modes', 'label': 'How do you get to school?', 'type': 'checkbox',
            'section': 'personal', 'options': ['Walking', 'Jeepney', 'Bicycle'],
        })
        assert res.status_code == 201
        field = res.get_json()['field']
        assert field['options'] == ['Walking', 'Jeepney', 'Bicycle']

        stored = db.form_fields.find_one({'key': 'transport_modes'})
        assert stored['options'] == ['Walking', 'Jeepney', 'Bicycle']

    def test_checkbox_without_options_stays_a_simple_toggle(self, client, auth_headers):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'agrees_to_terms', 'label': 'I agree to the terms', 'type': 'checkbox',
            'section': 'personal',
        })
        assert res.status_code == 201
        assert res.get_json()['field']['options'] == []

    def test_checkbox_options_must_be_a_list(self, client, auth_headers):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'bad_options', 'label': 'Bad Options', 'type': 'checkbox',
            'section': 'personal', 'options': 'not-a-list',
        })
        assert res.status_code == 400

    def test_text_field_options_are_dropped(self, client, auth_headers):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'plain_text', 'label': 'Plain Text', 'type': 'text', 'section': 'personal',
            'options': ['Should', 'Be', 'Ignored'],
        })
        assert res.status_code == 201
        assert res.get_json()['field']['options'] == []


class TestFormLockedWhileProgramOpen:
    """The form can only be edited before a program starts or after it ends;
    changing what's expected mid-program would invalidate submissions in flight."""

    def test_create_field_blocked_while_open(self, client, auth_headers, open_cycle):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'blocked_field', 'label': 'Blocked', 'type': 'text', 'section': 'personal',
        })
        assert res.status_code == 409

    def test_update_field_blocked_while_open(self, client, auth_headers, db, open_cycle):
        field_id = db.form_fields.insert_one({
            'key': 'existing', 'label': 'Existing', 'type': 'text', 'section': 'personal',
            'required': False, 'enabled': True, 'options': [], 'order': 0,
        }).inserted_id
        res = client.put(f'/api/form-fields/{field_id}', headers=auth_headers(), json={'enabled': False})
        assert res.status_code == 409

    def test_delete_field_blocked_while_open(self, client, auth_headers, db, open_cycle):
        field_id = db.form_fields.insert_one({
            'key': 'existing2', 'label': 'Existing2', 'type': 'text', 'section': 'personal',
            'required': False, 'enabled': True, 'options': [], 'order': 0,
        }).inserted_id
        res = client.delete(f'/api/form-fields/{field_id}', headers=auth_headers())
        assert res.status_code == 409

    def test_create_doc_requirement_blocked_while_open(self, client, auth_headers, open_cycle):
        res = client.post('/api/document-requirements', headers=auth_headers(), json={'label': 'New Doc'})
        assert res.status_code == 409

    def test_update_doc_requirement_blocked_while_open(self, client, auth_headers, db, open_cycle):
        import app as app_module
        org_id = app_module.get_default_organization_id(db)
        req_id = db.document_requirements.insert_one({
            'label': 'Doc', 'required': True, 'enabled': True, 'order': 0, 'organization_id': org_id,
        }).inserted_id
        res = client.put(f'/api/document-requirements/{req_id}', headers=auth_headers(), json={'enabled': False})
        assert res.status_code == 409

    def test_delete_doc_requirement_blocked_while_open(self, client, auth_headers, db, open_cycle):
        import app as app_module
        org_id = app_module.get_default_organization_id(db)
        req_id = db.document_requirements.insert_one({
            'label': 'Doc2', 'required': True, 'enabled': True, 'order': 0, 'organization_id': org_id,
        }).inserted_id
        res = client.delete(f'/api/document-requirements/{req_id}', headers=auth_headers())
        assert res.status_code == 409

    def test_hidden_builtin_fields_blocked_while_open(self, client, auth_headers, open_cycle):
        res = client.put('/api/settings', headers=auth_headers(), json={'hidden_builtin_fields': ['religion']})
        assert res.status_code == 409

    def test_other_settings_still_editable_while_open(self, client, auth_headers, open_cycle):
        """Only the form-shape fields are locked - unrelated settings must keep working."""
        res = client.put('/api/settings', headers=auth_headers(), json={'max_accepted': 15})
        assert res.status_code == 200

    def test_create_field_allowed_when_no_cycle_exists(self, client, auth_headers):
        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'allowed_field', 'label': 'Allowed', 'type': 'text', 'section': 'personal',
        })
        assert res.status_code == 201

    def test_create_field_allowed_once_program_ends(self, client, auth_headers, db):
        import app as app_module
        from datetime import datetime, timedelta
        org_id = app_module.get_default_organization_id(db)
        cycle_id = app_module.do_program_reset(db, org_id, 'test-setup@test.com')
        db.program_cycles.update_one({'_id': cycle_id}, {'$set': {'deadline': datetime.utcnow() - timedelta(days=1)}})

        res = client.post('/api/form-fields', headers=auth_headers(), json={
            'key': 'after_deadline_field', 'label': 'After Deadline', 'type': 'text', 'section': 'personal',
        })
        assert res.status_code == 201
