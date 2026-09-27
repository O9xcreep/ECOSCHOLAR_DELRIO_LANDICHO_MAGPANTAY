# -*- coding: utf-8 -*-
"""Field-level encryption of applicants' sensitive personal information
(field_crypto.py): stored as ciphertext, served decrypted to authorized
users, and still matched for name + date-of-birth duplicate detection."""
import pytest

from field_crypto import encrypt_field, decrypt_field, is_encrypted, blind_index, ENCRYPTED_APPLICANT_FIELDS
from tests.test_withdraw import VALID_APPLY_PAYLOAD


def login(client, user):
    res = client.post('/api/login', json={'email': user['email'], 'password': user['password']})
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


class TestCipher:
    def test_round_trip(self):
        assert decrypt_field(encrypt_field('Brgy. San Jose, Tiaong')) == 'Brgy. San Jose, Tiaong'

    def test_ciphertext_hides_the_value_and_differs_each_time(self):
        a, b = encrypt_field('09171234567'), encrypt_field('09171234567')
        assert a != b
        assert '0917' not in a and a.startswith('enc:v1:')

    def test_legacy_plaintext_and_empty_values_pass_through(self):
        assert decrypt_field('plain old address') == 'plain old address'
        assert decrypt_field(None) is None
        assert encrypt_field('') == ''

    def test_tampered_ciphertext_is_rejected(self):
        value = encrypt_field('secret')
        tampered = value[:-4] + ('AAAA' if not value.endswith('AAAA') else 'BBBB')
        with pytest.raises(ValueError):
            decrypt_field(tampered)

    def test_blind_index_matches_equal_dates_only(self):
        assert blind_index('2003-01-01') == blind_index('2003-01-01')
        assert blind_index('2003-01-01') != blind_index('2003-01-02')


class TestApplicationsAreStoredEncrypted:
    def _apply(self, client, headers, **overrides):
        return client.post('/api/apply', headers=headers, json={**VALID_APPLY_PAYLOAD, **overrides})

    def test_sensitive_fields_are_ciphertext_in_the_database(self, client, db, make_user, open_cycle):
        student = make_user(email='enc-apply@test.com')
        res = self._apply(client, login(client, student), fullName='Enc Apply', email='enc-apply@test.com',
                          address='123 Mabini St, Liliw', contactNumber='09998887777', dob='2004-05-06',
                          fatherName='Pedro Cruz', motherName='Maria Cruz', religion='Catholic')
        assert res.status_code == 200, res.get_json()

        stored = db.applicants.find_one({'email': 'enc-apply@test.com'})
        for field in ENCRYPTED_APPLICANT_FIELDS:
            assert is_encrypted(stored[field]), field
        assert 'Mabini' not in str(stored) and '09998887777' not in str(stored)
        # ML inputs and search fields stay readable
        assert stored['monthly_income'] == 10000.0
        assert stored['full_name'] == 'Enc Apply'

    def test_owner_sees_decrypted_values(self, client, db, make_user, open_cycle):
        student = make_user(email='enc-view@test.com')
        headers = login(client, student)
        self._apply(client, headers, fullName='Enc View', email='enc-view@test.com', address='45 Rizal Ave, Tiaong')
        res = client.get('/api/student/application?email=enc-view@test.com', headers=headers)
        assert res.get_json()['application']['address'] == '45 Rizal Ave, Tiaong'

    def test_name_and_birthdate_duplicate_still_detected(self, client, db, make_user, open_cycle):
        first = make_user(email='dup-one@test.com')
        second = make_user(email='dup-two@test.com')
        assert self._apply(client, login(client, first), fullName='Same Person', email='dup-one@test.com',
                           dob='2002-02-02').status_code == 200
        res = self._apply(client, login(client, second), fullName='Same Person', email='dup-two@test.com',
                          dob='2002-02-02')
        assert res.status_code == 409, res.get_json()

    def test_duplicate_against_a_legacy_plaintext_record(self, client, db, make_user, open_cycle):
        db.applicants.insert_one({
            'full_name': 'Old Record', 'email': 'old@test.com', 'date_of_birth': '2001-01-01',
            'cycle_id': open_cycle, 'application': {'status': 'Newly Submitted'},
        })
        student = make_user(email='new@test.com')
        res = self._apply(client, login(client, student), fullName='Old Record', email='new@test.com',
                          dob='2001-01-01')
        assert res.status_code == 409
