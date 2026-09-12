# -*- coding: utf-8 -*-
"""Admin-facing computed application status: the document-completeness
family (Newly Submitted/Incomplete/Pending Verification), and Waitlisted (a
Rejected-but-model-Eligible applicant, see recompute_approvals). Neither is
stored; both are computed in compute_admin_status() and must be
filterable/countable through GET /api/applicants like a real status."""
import app as app_module


def make_applicant(status='Rejected', ml_status=None, full_name='A', email='a@test.com'):
    doc = {
        'full_name': full_name, 'email': email, 'academic': {},
        'application': {'status': status},
    }
    if ml_status is not None:
        doc['ml_status'] = ml_status
    return doc


class TestWaitlistedComputedStatus:
    def test_rejected_and_eligible_shows_as_waitlisted(self, client, db, auth_headers):
        db.applicants.insert_one(make_applicant(status='Rejected', ml_status='Eligible', email='w1@test.com'))
        res = client.get('/api/applicants?page=1&limit=50&status=All', headers=auth_headers())
        app_ = next(a for a in res.get_json()['applicants'] if a['email'] == 'w1@test.com')
        assert app_['application_status'] == 'Waitlisted'

    def test_rejected_and_not_eligible_stays_rejected(self, client, db, auth_headers):
        db.applicants.insert_one(make_applicant(status='Rejected', ml_status='Not Eligible', email='r1@test.com'))
        res = client.get('/api/applicants?page=1&limit=50&status=All', headers=auth_headers())
        app_ = next(a for a in res.get_json()['applicants'] if a['email'] == 'r1@test.com')
        assert app_['application_status'] == 'Rejected'

    def test_rejected_with_no_ml_status_stays_rejected(self, client, db, auth_headers):
        """No ml_status field at all (e.g. pre-model data) must not be
        mistaken for Eligible."""
        db.applicants.insert_one(make_applicant(status='Rejected', email='r2@test.com'))
        res = client.get('/api/applicants?page=1&limit=50&status=All', headers=auth_headers())
        app_ = next(a for a in res.get_json()['applicants'] if a['email'] == 'r2@test.com')
        assert app_['application_status'] == 'Rejected'

    def test_approved_unaffected(self, client, db, auth_headers):
        db.applicants.insert_one(make_applicant(status='Approved', ml_status='Eligible', email='ap1@test.com'))
        res = client.get('/api/applicants?page=1&limit=50&status=All', headers=auth_headers())
        app_ = next(a for a in res.get_json()['applicants'] if a['email'] == 'ap1@test.com')
        assert app_['application_status'] == 'Approved'

    def test_single_applicant_endpoint_also_relabels(self, client, db, auth_headers):
        applicant_id = db.applicants.insert_one(make_applicant(status='Rejected', ml_status='Eligible')).inserted_id
        res = client.get(f'/api/applicants/{applicant_id}', headers=auth_headers())
        assert res.get_json()['applicant']['application_status'] == 'Waitlisted'


class TestWaitlistedFiltering:
    def test_status_waitlisted_returns_only_eligible_rejects(self, client, db, auth_headers):
        db.applicants.insert_many([
            make_applicant(status='Rejected', ml_status='Eligible', email='w@test.com'),
            make_applicant(status='Rejected', ml_status='Not Eligible', email='r@test.com'),
            make_applicant(status='Approved', ml_status='Eligible', email='ap@test.com'),
        ])
        res = client.get('/api/applicants?page=1&limit=50&status=Waitlisted', headers=auth_headers())
        body = res.get_json()
        assert body['total'] == 1
        assert body['applicants'][0]['email'] == 'w@test.com'
        assert body['applicants'][0]['application_status'] == 'Waitlisted'

    def test_status_rejected_excludes_waitlisted(self, client, db, auth_headers):
        """From now on "Rejected" means true rejects only - a caller wanting
        the old undifferentiated set has to ask for both explicitly."""
        db.applicants.insert_many([
            make_applicant(status='Rejected', ml_status='Eligible', email='w@test.com'),
            make_applicant(status='Rejected', ml_status='Not Eligible', email='r@test.com'),
        ])
        res = client.get('/api/applicants?page=1&limit=50&status=Rejected', headers=auth_headers())
        body = res.get_json()
        assert body['total'] == 1
        assert body['applicants'][0]['email'] == 'r@test.com'

    def test_decided_group_excludes_waitlisted(self, client, db, auth_headers):
        db.applicants.insert_many([
            make_applicant(status='Approved', email='ap@test.com'),
            make_applicant(status='Rejected', ml_status='Not Eligible', email='r@test.com'),
            make_applicant(status='Withdrawn', email='wd@test.com'),
            make_applicant(status='Rejected', ml_status='Eligible', email='w@test.com'),
        ])
        res = client.get('/api/applicants?page=1&limit=50&status=Approved,Rejected,Withdrawn', headers=auth_headers())
        body = res.get_json()
        emails = {a['email'] for a in body['applicants']}
        assert body['total'] == 3
        assert emails == {'ap@test.com', 'r@test.com', 'wd@test.com'}

    def test_all_tab_total_still_counts_waitlisted(self, client, db, auth_headers):
        """ALL_STATUSES must list Waitlisted explicitly on the frontend, or
        splitting Rejected here would silently undercount the "All" tab."""
        db.applicants.insert_many([
            make_applicant(status='Approved', email='ap@test.com'),
            make_applicant(status='Rejected', ml_status='Not Eligible', email='r@test.com'),
            make_applicant(status='Rejected', ml_status='Eligible', email='w@test.com'),
        ])
        all_statuses = 'Newly Submitted,Pending Verification,Incomplete,Approved,Rejected,Withdrawn,Waitlisted'
        res = client.get(f'/api/applicants?page=1&limit=50&status={all_statuses}', headers=auth_headers())
        assert res.get_json()['total'] == 3

    def test_waitlisted_filter_combined_with_search(self, client, db, auth_headers):
        """The status split and the search box both want the query's $or
        slot - make sure combining them doesn't drop either condition."""
        db.applicants.insert_many([
            make_applicant(status='Rejected', ml_status='Eligible', full_name='Juan Dela Cruz', email='juan@test.com'),
            make_applicant(status='Rejected', ml_status='Eligible', full_name='Maria Santos', email='maria@test.com'),
        ])
        res = client.get('/api/applicants?page=1&limit=50&status=Waitlisted&q=Juan', headers=auth_headers())
        body = res.get_json()
        assert body['total'] == 1
        assert body['applicants'][0]['full_name'] == 'Juan Dela Cruz'


class TestDocCompletenessStatusesStillWork:
    """Regression check: renaming compute_display_status's caller to
    compute_admin_status inside get_applicants() must not break the Round 2
    computed statuses."""

    def test_newly_submitted_with_no_docs(self, client, db, auth_headers):
        db.applicants.insert_one({
            'full_name': 'X', 'email': 'x@test.com', 'academic': {},
            'application': {'status': 'Newly Submitted'}, 'documents': [],
        })
        res = client.get('/api/applicants?page=1&limit=50&status=Newly Submitted', headers=auth_headers())
        assert res.get_json()['total'] == 1

    def test_incomplete_vs_pending_verification_split(self, client, db, auth_headers):
        # Includes the selfie label since get_doc_requirements_collection()
        # auto-backfills it as required; omitting it would make every
        # applicant "Incomplete" regardless of Form A/B.
        db.document_requirements.insert_many([
            {'label': 'Form A', 'required': True, 'enabled': True},
            {'label': 'Form B', 'required': True, 'enabled': True},
            {'label': app_module.SELFIE_DOC_LABEL, 'required': True, 'enabled': True},
        ])
        db.applicants.insert_many([
            {'full_name': 'Partial', 'email': 'partial@test.com', 'academic': {},
             'application': {'status': 'Newly Submitted'},
             'documents': [{'document_name': 'Form A', 'status': 'Uploaded'},
                           {'document_name': app_module.SELFIE_DOC_LABEL, 'status': 'Uploaded'}]},
            {'full_name': 'Complete', 'email': 'complete@test.com', 'academic': {},
             'application': {'status': 'Newly Submitted'},
             'documents': [{'document_name': 'Form A', 'status': 'Uploaded'},
                           {'document_name': 'Form B', 'status': 'Uploaded'},
                           {'document_name': app_module.SELFIE_DOC_LABEL, 'status': 'Uploaded'}]},
        ])
        incomplete = client.get('/api/applicants?page=1&limit=50&status=Incomplete', headers=auth_headers()).get_json()
        pending = client.get('/api/applicants?page=1&limit=50&status=Pending Verification', headers=auth_headers()).get_json()
        assert incomplete['total'] == 1 and incomplete['applicants'][0]['email'] == 'partial@test.com'
        assert pending['total'] == 1 and pending['applicants'][0]['email'] == 'complete@test.com'
