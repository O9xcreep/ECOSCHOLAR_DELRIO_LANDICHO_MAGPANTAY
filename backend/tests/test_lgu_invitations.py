import pytest

import admin_management
import app as app_module

URL = '/api/organizations/invitations'
BODY = {'lgu_type': 'Municipality', 'municipality': 'Nagcarlan', 'province': 'Laguna',
        'full_name': 'Ana Reyes', 'email': 'Ana@lgu.gov.ph'}


@pytest.fixture
def owner(auth_headers):
    return auth_headers(is_system_owner=True)


def _invite(client, headers, **overrides):
    return client.post(URL, headers=headers, json={**BODY, **overrides})


def _names(client):
    return [o['name'] for o in client.get('/api/organizations/directory').get_json()['organizations']]


def test_invited_lgu_goes_live_only_after_activation(client, db, owner):
    assert _invite(client, owner).status_code == 201
    org = db.organizations.find_one({'name': 'Municipality of Nagcarlan'})
    assert org['status'] == 'invited' and org['name'] not in _names(client)
    assert client.get(f"/api/organizations/lookup?code={org['join_code']}").status_code == 404

    client.post('/api/admins/resend-setup-otp', json={'email': 'ana@lgu.gov.ph'})
    code = db.otps.find_one({'email': 'ana@lgu.gov.ph'})['code']
    token = client.post('/api/admins/verify-setup-code',
                        json={'email': 'ana@lgu.gov.ph', 'code': code}).get_json()['token']
    res = client.post('/api/admins/complete-invite-setup', json={'token': token, 'new_password': 'Password123'})
    assert res.status_code == 200
    user = res.get_json()['user']
    assert user['role'] == 'lgu_admin' and user['organization_id'] == str(org['_id'])
    listed = client.get('/api/organizations/directory').get_json()['organizations']
    assert [o['province'] for o in listed if o['name'] == org['name']] == ['Laguna']


def test_only_the_system_owner_can_invite(client, db, auth_headers):
    headers = auth_headers()
    org_id = app_module.get_default_organization_id(db)
    assert _invite(client, headers).status_code == 403
    assert client.get(URL, headers=headers).status_code == 403
    assert client.post(f'{URL}/{org_id}/resend', headers=headers).status_code == 403
    assert client.delete(f'{URL}/{org_id}', headers=headers).status_code == 403


@pytest.mark.parametrize('name', ['nagcarlan', ' Nagcarlan ', 'Municipality of Nagcarlan', 'Nagcarlan City'])
def test_the_same_lgu_cannot_be_invited_twice(client, owner, name):
    _invite(client, owner)
    assert _invite(client, owner, municipality=name, email='b@lgu.gov.ph').status_code == 409


def test_same_town_name_in_another_province_is_a_different_lgu(client, owner):
    _invite(client, owner, municipality='San Jose', province='Batangas')
    assert _invite(client, owner, municipality='San Jose', province='Romblon', email='b@lgu.gov.ph').status_code == 201


def test_existing_organization_without_a_province_counts_as_a_duplicate(client, db, owner):
    db.organizations.insert_one({'name': 'Old', 'municipality': 'Nagcarlan', 'status': 'active', 'join_code': 'OLDCODE1'})
    assert _invite(client, owner).status_code == 409


@pytest.mark.parametrize('bad', [{'province': 'Atlantis'}, {'lgu_type': 'x'}, {'municipality': ' '},
                                 {'email': 'nope'}, {'full_name': ''}, {'email': 5}])
def test_invalid_invitations_are_rejected(client, db, owner, bad):
    assert _invite(client, owner, **bad).status_code == 400
    assert db.organizations.count_documents({'status': 'invited'}) == 0


def test_cancelling_frees_the_location_and_email(client, db, owner):
    _invite(client, owner)
    org = db.organizations.find_one({'status': 'invited'})
    assert client.delete(f"{URL}/{org['_id']}", headers=owner).status_code == 200
    assert not db.users.find_one({'email': 'ana@lgu.gov.ph'})
    assert _invite(client, owner).status_code == 201


def test_an_active_lgu_cannot_be_cancelled(client, db, owner):
    org_id = app_module.get_default_organization_id(db)
    assert client.delete(f'{URL}/{org_id}', headers=owner).status_code == 404
    assert db.organizations.find_one({'_id': org_id})


def test_public_requests_are_closed_by_default(client, monkeypatch):
    monkeypatch.setattr(admin_management, 'PUBLIC_ADMIN_REQUESTS', False)
    for path in ('/start', '/verify-start-otp', '/start-google', ''):
        assert client.post('/api/admin-requests' + path, json={'email': 'a@b.co'}).status_code == 403
