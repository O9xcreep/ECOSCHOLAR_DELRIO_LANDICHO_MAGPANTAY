def test_app_is_up(client):
    res = client.get('/api/test')
    assert res.status_code == 200
