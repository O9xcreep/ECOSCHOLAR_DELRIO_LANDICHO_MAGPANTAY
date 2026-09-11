# -*- coding: utf-8 -*-
"""GET /api/applicants/status-counts computes every tab's badge count in one
pass (see applicant_status_counts() in app.py) instead of the Applications page
firing one GET /api/applicants request per tab - three of which independently
re-scanned and recomputed compute_admin_status() over the same "Newly
Submitted" pool. This checks the consolidated counts match what the existing
per-tab GET /api/applicants?status=... filtering already proves correct."""
import app as app_module


class TestApplicantStatusCounts:
    def test_requires_auth(self, client):
        res = client.get('/api/applicants/status-counts')
        assert res.status_code == 401

    def test_student_forbidden(self, client, auth_headers):
        res = client.get('/api/applicants/status-counts', headers=auth_headers('student'))
        assert res.status_code == 403

    def test_counts_match_the_per_tab_filters(self, client, db, auth_headers):
        db.document_requirements.insert_many([
            {'label': 'Form A', 'required': True, 'enabled': True},
            {'label': 'Form B', 'required': True, 'enabled': True},
            {'label': app_module.SELFIE_DOC_LABEL, 'required': True, 'enabled': True},
        ])
        db.applicants.insert_many([
            # Newly Submitted: no required docs uploaded at all
            {'full_name': 'NoDocs', 'email': 'nodocs@test.com', 'academic': {},
             'application': {'status': 'Newly Submitted'}, 'documents': []},
            # Incomplete: some but not all required docs uploaded
            {'full_name': 'Partial', 'email': 'partial@test.com', 'academic': {},
             'application': {'status': 'Newly Submitted'},
             'documents': [{'document_name': 'Form A', 'status': 'Uploaded'}]},
            # Pending Verification: every required doc uploaded
            {'full_name': 'Complete', 'email': 'complete@test.com', 'academic': {},
             'application': {'status': 'Newly Submitted'},
             'documents': [
                 {'document_name': 'Form A', 'status': 'Uploaded'},
                 {'document_name': 'Form B', 'status': 'Uploaded'},
                 {'document_name': app_module.SELFIE_DOC_LABEL, 'status': 'Uploaded'},
             ]},
            {'full_name': 'Approved1', 'email': 'a1@test.com', 'application': {'status': 'Approved'}},
            {'full_name': 'Rejected1', 'email': 'r1@test.com', 'ml_status': 'Not Eligible', 'application': {'status': 'Rejected'}},
            {'full_name': 'Waitlisted1', 'email': 'w1@test.com', 'ml_status': 'Eligible', 'application': {'status': 'Rejected'}},
            {'full_name': 'Withdrawn1', 'email': 'wd1@test.com', 'application': {'status': 'Withdrawn'}},
        ])

        res = client.get('/api/applicants/status-counts', headers=auth_headers())
        counts = res.get_json()
        assert res.status_code == 200

        for status in ('Newly Submitted', 'Pending Verification', 'Incomplete', 'Waitlisted', 'Approved', 'Rejected', 'Withdrawn'):
            expected = client.get(
                f'/api/applicants?page=1&limit=1&status={status}', headers=auth_headers()
            ).get_json()['total']
            assert counts[status] == expected, f"mismatch for {status}"

        assert counts['All'] == sum(
            counts[s] for s in ('Newly Submitted', 'Pending Verification', 'Incomplete', 'Waitlisted', 'Approved', 'Rejected', 'Withdrawn')
        )
        assert counts['Newly Submitted'] == 1
        assert counts['Incomplete'] == 1
        assert counts['Pending Verification'] == 1
        assert counts['Waitlisted'] == 1
        assert counts['Approved'] == 1
        assert counts['Rejected'] == 1
        assert counts['Withdrawn'] == 1

    def test_scoped_to_current_cycle_when_requested(self, client, db, auth_headers, open_cycle):
        db.applicants.insert_one({
            'full_name': 'OldCycle', 'email': 'old@test.com', 'academic': {},
            'application': {'status': 'Newly Submitted'}, 'documents': [],
            'cycle_id': 'some-other-cycle',
        })
        res = client.get('/api/applicants/status-counts?cycle=current', headers=auth_headers())
        counts = res.get_json()
        assert counts['Newly Submitted'] == 0
