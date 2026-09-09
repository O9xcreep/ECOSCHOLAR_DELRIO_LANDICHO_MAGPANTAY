# -*- coding: utf-8 -*-
"""Custom form fields (Form Builder). Checkbox fields can optionally carry an
options list, same as select - a checkbox field with no options stays the
original simple Yes/No toggle, so existing checkbox fields are unaffected."""


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
