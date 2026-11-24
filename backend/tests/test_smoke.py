import pytest
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

import admin_management


def test_app_is_up(client):
    res = client.get('/api/test')
    assert res.status_code == 200

@pytest.mark.parametrize('error', [
    ServerSelectionTimeoutError('cluster0.secret-host.mongodb.net: timed out'),
    OperationFailure('bad auth : authentication failed', code=8000),
    OperationFailure('Authentication failed.', code=18),
])
def test_database_outage_is_a_json_503(client, monkeypatch, error):
    def fail():
        raise error
    monkeypatch.setattr(admin_management, 'get_db', fail)
    res = client.get('/api/organizations/directory', headers={'Origin': 'http://localhost:5173'})
    assert res.status_code == 503
    assert 'temporarily unavailable' in res.get_json()['error']
    assert 'secret-host' not in res.get_data(as_text=True)
    assert res.headers['Access-Control-Allow-Origin'] == 'http://localhost:5173'


def test_other_database_errors_are_not_reported_as_an_outage(client, monkeypatch):
    def fail():
        raise OperationFailure('bad query', code=2)
    monkeypatch.setattr(admin_management, 'get_db', fail)
    monkeypatch.setitem(client.application.config, 'PROPAGATE_EXCEPTIONS', False)
    assert client.get('/api/organizations/directory').status_code == 500


def test_login_rejection_wrapped_in_a_timeout_is_logged_as_a_login_problem(client, monkeypatch, caplog):
    def fail():
        raise ServerSelectionTimeoutError(
            'No replica set members match selector "Primary()", '
            'error=OperationFailure("bad auth : authentication failed")')
    monkeypatch.setattr(admin_management, 'get_db', fail)
    assert client.get('/api/organizations/directory').status_code == 503
    assert 'check the credentials in MONGO_URI' in caplog.text
