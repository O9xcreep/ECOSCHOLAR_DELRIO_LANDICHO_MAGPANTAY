# -*- coding: utf-8 -*-
"""Pagination/search/filter on GET /api/applicants, and bulk-verify validation."""


def seed_applicants(db, n=25, status='Approved'):
    docs = [{'full_name': f'Applicant {i}', 'email': f'app{i}@test.com',
             'academic': {'course': 'BS Computer Science'},
             'application': {'status': status}} for i in range(n)]
    db.applicants.insert_many(docs)


class TestApplicantsPagination:
    def test_requires_admin_role(self, client, auth_headers):
        student_headers = auth_headers('student')
        res = client.get('/api/applicants', headers=student_headers)
        assert res.status_code == 403

    def test_requires_auth(self, client):
        res = client.get('/api/applicants')
        assert res.status_code == 401

    def test_no_page_param_returns_everything(self, client, db, auth_headers):
        seed_applicants(db, n=25)
        res = client.get('/api/applicants', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert len(body['applicants']) == 25
        assert 'total' not in body  # unpaginated shape, unchanged from before

    def test_page_param_paginates(self, client, db, auth_headers):
        seed_applicants(db, n=25)
        res = client.get('/api/applicants?page=1&limit=10', headers=auth_headers())
        body = res.get_json()
        assert res.status_code == 200
        assert len(body['applicants']) == 10
        assert body['total'] == 25
        assert body['pages'] == 3
        assert body['page'] == 1

    def test_second_page(self, client, db, auth_headers):
        seed_applicants(db, n=25)
        res = client.get('/api/applicants?page=3&limit=10', headers=auth_headers())
        body = res.get_json()
        assert len(body['applicants']) == 5  # last page, remainder

    def test_status_filter_single(self, client, db, auth_headers):
        seed_applicants(db, n=5, status='Approved')
        seed_applicants(db, n=3, status='Rejected')
        res = client.get('/api/applicants?page=1&limit=50&status=Approved', headers=auth_headers())
        assert res.get_json()['total'] == 5

    def test_status_filter_comma_list(self, client, db, auth_headers):
        seed_applicants(db, n=5, status='Approved')
        seed_applicants(db, n=3, status='Rejected')
        seed_applicants(db, n=2, status='Newly Submitted')
        res = client.get('/api/applicants?page=1&limit=50&status=Approved,Rejected', headers=auth_headers())
        assert res.get_json()['total'] == 8

    def test_search_by_name(self, client, db, auth_headers):
        db.applicants.insert_many([
            {'full_name': 'Juan Dela Cruz', 'application': {'status': 'Approved'}, 'academic': {}},
            {'full_name': 'Maria Santos', 'application': {'status': 'Approved'}, 'academic': {}},
        ])
        res = client.get('/api/applicants?page=1&limit=50&q=Juan', headers=auth_headers())
        body = res.get_json()
        assert body['total'] == 1
        assert body['applicants'][0]['full_name'] == 'Juan Dela Cruz'

    def test_invalid_page_param(self, client, auth_headers):
        res = client.get('/api/applicants?page=notanumber', headers=auth_headers())
        assert res.status_code == 400

    def test_limit_capped_at_100(self, client, db, auth_headers):
        seed_applicants(db, n=5)
        res = client.get('/api/applicants?page=1&limit=99999', headers=auth_headers())
        assert res.get_json()['limit'] == 100

    def test_sort_by_gpa_ascending(self, client, db, auth_headers):
        db.applicants.insert_many([
            {'full_name': 'Low GWA', 'academic': {'gpa': 75}, 'application': {'status': 'Approved'}},
            {'full_name': 'High GWA', 'academic': {'gpa': 95}, 'application': {'status': 'Approved'}},
        ])
        res = client.get('/api/applicants?page=1&limit=10&sort=gpa', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert names == ['Low GWA', 'High GWA']

    def test_sort_by_gpa_descending(self, client, db, auth_headers):
        db.applicants.insert_many([
            {'full_name': 'Low GWA', 'academic': {'gpa': 75}, 'application': {'status': 'Approved'}},
            {'full_name': 'High GWA', 'academic': {'gpa': 95}, 'application': {'status': 'Approved'}},
        ])
        res = client.get('/api/applicants?page=1&limit=10&sort=-gpa', headers=auth_headers())
        names = [a['full_name'] for a in res.get_json()['applicants']]
        assert names == ['High GWA', 'Low GWA']

    def test_invalid_sort_field_rejected(self, client, auth_headers):
        res = client.get('/api/applicants?page=1&limit=10&sort=password', headers=auth_headers())
        assert res.status_code == 400


class TestBulkVerify:
    def test_requires_admin(self, client, auth_headers):
        res = client.put('/api/applications/bulk-verify',
                          headers=auth_headers('student'), json={'applicant_ids': ['x']})
        assert res.status_code == 403

    def test_empty_list_rejected(self, client, auth_headers):
        res = client.put('/api/applications/bulk-verify', headers=auth_headers(), json={'applicant_ids': []})
        assert res.status_code == 400

    def test_too_many_ids_rejected(self, client, auth_headers):
        res = client.put('/api/applications/bulk-verify',
                          headers=auth_headers(), json={'applicant_ids': ['x'] * 101})
        assert res.status_code == 400

    def test_invalid_id_reported_not_raised(self, client, auth_headers):
        res = client.put('/api/applications/bulk-verify',
                          headers=auth_headers(), json={'applicant_ids': ['not-a-real-id']})
        assert res.status_code == 200
        body = res.get_json()
        assert body['succeeded'] == 0
        assert body['results'][0]['error']
