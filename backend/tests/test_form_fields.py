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


class TestFormConfigPermissionGating:
    """Form fields, document requirements, and the built-in-field toggles are
    all "the form" - gated by can_reset_program (full-access roles always
    have it). The rest of PUT /api/settings (accepted-applicant limit, result
    visibility, the reset confirmation password) stays full-access-only."""

    NEW_FIELD = {'key': 'perm_test_field', 'label': 'Perm Test', 'type': 'text', 'section': 'personal'}

    def test_lgu_member_with_can_reset_program_can_create_a_form_field(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        res = client.post('/api/form-fields', headers=headers, json=self.NEW_FIELD)
        assert res.status_code == 201

    def test_lgu_member_without_can_reset_program_cannot_create_a_form_field(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True, 'can_manage_members': True})
        res = client.post('/api/form-fields', headers=headers, json=self.NEW_FIELD)
        assert res.status_code == 403

    def test_lgu_member_with_can_reset_program_can_create_a_document_requirement(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        res = client.post('/api/document-requirements', headers=headers, json={'label': 'Barangay Certificate', 'required': True})
        assert res.status_code == 201

    def test_lgu_member_without_can_reset_program_cannot_create_a_document_requirement(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        res = client.post('/api/document-requirements', headers=headers, json={'label': 'Barangay Certificate', 'required': True})
        assert res.status_code == 403

    def test_lgu_member_with_can_reset_program_can_toggle_hidden_builtin_fields(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        res = client.put('/api/settings', headers=headers, json={'hidden_builtin_fields': ['religion']})
        assert res.status_code == 200
        assert res.get_json()['hidden_builtin_fields'] == ['religion']

    def test_lgu_member_without_can_reset_program_cannot_toggle_hidden_builtin_fields(self, client, auth_headers):
        headers = auth_headers('lgu_member', permissions={'can_review_applicants': True})
        res = client.put('/api/settings', headers=headers, json={'hidden_builtin_fields': ['religion']})
        assert res.status_code == 403

    def test_can_reset_program_alone_does_not_unlock_the_other_settings(self, client, auth_headers):
        """max_accepted, result visibility, and the reset password stay
        full-access-only even for a member who can reset the program."""
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        assert client.put('/api/settings', headers=headers, json={'max_accepted': 5}).status_code == 403
        assert client.put('/api/settings', headers=headers, json={'results_visible_override': True}).status_code == 403
        assert client.put('/api/settings', headers=headers, json={'reset_password': 'newpassword1'}).status_code == 403

    def test_mixing_a_restricted_key_with_hidden_builtin_fields_is_rejected(self, client, auth_headers):
        """A can_reset_program member can't smuggle a restricted setting past
        the gate by bundling it in the same request as an allowed one."""
        headers = auth_headers('lgu_member', permissions={'can_reset_program': True})
        res = client.put('/api/settings', headers=headers,
                          json={'hidden_builtin_fields': ['religion'], 'max_accepted': 999})
        assert res.status_code == 403

    def test_lgu_admin_can_still_change_every_setting(self, client, auth_headers):
        headers = auth_headers('lgu_admin')
        assert client.put('/api/settings', headers=headers, json={'max_accepted': 7}).status_code == 200


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
