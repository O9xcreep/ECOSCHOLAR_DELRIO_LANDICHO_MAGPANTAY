# -*- coding: utf-8 -*-
"""The eligibility classifier takes the LGU's eligibility bar ("top X% of need") as an input, so
one trained model serves any bar in ELIGIBILITY_TOP_PERCENT_CHOICES - see
scripts/train_model.py. These tests pin down what that must guarantee, and how changing the bar
re-decides a program's already-reviewed applicants."""
import itertools

import pytest

import app as app_module
import ecoscholar_predict as ep
from helpers import ELIGIBILITY_TOP_PERCENT_CHOICES, DEFAULT_ELIGIBILITY_TOP_PERCENT


def make_applicant(gpa=90, income=8000, family_size=5, housing='Rented', occupation='Laborer/Driver'):
    return {
        'gender': 'Female', 'family_size': family_size, 'num_siblings': 3, 'num_siblings_studying': 2,
        'father_education': 'High School', 'mother_education': 'High School',
        'father_occupation': occupation, 'mother_occupation': occupation,
        'monthly_income': income, 'housing_situation': housing,
        'academic': {'gpa': gpa}, 'has_other_scholarship': False,
    }


def applicant_grid():
    for gpa, income, size, housing in itertools.product((84, 90, 95), (2500, 7500, 12500, 25000), (3, 7),
                                                        ('Owned', 'Rented')):
        yield make_applicant(gpa=gpa, income=income, family_size=size, housing=housing)


def score(applicant, top_percent=None):
    row, ok = app_module.build_feature_row(applicant)
    assert ok
    return app_module.score_with_model(row, top_percent)


class TestOneModelServesEveryBar:
    def test_the_backend_choices_match_what_the_model_was_trained_for(self):
        assert ELIGIBILITY_TOP_PERCENT_CHOICES == ep.SELECTABLE_TOP_PERCENTS
        assert DEFAULT_ELIGIBILITY_TOP_PERCENT == ep.DEFAULT_TOP_PERCENT

    def test_a_stricter_bar_never_admits_someone_a_looser_bar_rejects(self):
        loosest_first = sorted(ELIGIBILITY_TOP_PERCENT_CHOICES, reverse=True)   # 60% ... 10%
        for applicant in applicant_grid():
            eligible = [score(applicant, p)[1] == 'Eligible' for p in loosest_first]
            assert eligible == sorted(eligible, reverse=True), \
                f'eligibility went back up as the bar tightened: {list(zip(loosest_first, eligible))}'

    def test_a_stricter_bar_admits_fewer_applicants_overall(self):
        grid = list(applicant_grid())
        admitted = {p: sum(score(a, p)[1] == 'Eligible' for a in grid) for p in (10, 30, 60)}
        assert admitted[10] < admitted[30] < admitted[60]

    def test_omitting_the_bar_means_the_default_bar(self):
        for applicant in applicant_grid():
            assert score(applicant) == score(applicant, DEFAULT_ELIGIBILITY_TOP_PERCENT)

    def test_the_priority_score_does_not_depend_on_the_bar(self):
        for applicant in applicant_grid():
            assert len({score(applicant, p)[0] for p in ELIGIBILITY_TOP_PERCENT_CHOICES}) == 1

    def test_more_need_still_never_counts_against_an_applicant_at_any_bar(self):
        by_need = ['Professional', 'Office/Clerical', 'Skilled Trade', 'Laborer/Driver', 'Informal/Vendor', 'Unemployed']
        for p in (10, 30, 60):
            for gpa, income in itertools.product((84, 92), (2500, 12500)):
                eligible = [score(make_applicant(gpa=gpa, income=income, occupation=o), p)[1] == 'Eligible'
                            for o in by_need]
                assert eligible == sorted(eligible), f'bar top {p}%: more occupation need lowered eligibility'


class TestEligibilityBarSetting:
    def test_defaults_to_the_trained_default(self, client, auth_headers):
        data = client.get('/api/settings', headers=auth_headers()).get_json()
        assert data['eligibility_top_percent'] == DEFAULT_ELIGIBILITY_TOP_PERCENT
        assert data['eligibility_top_percent_choices'] == ELIGIBILITY_TOP_PERCENT_CHOICES
        assert data['eligibility_cutoff'] == round(ep.eligibility_cutoff(), 2)

    @pytest.mark.parametrize('bad', [7, 65, '30', 30.0, True, None])
    def test_rejects_a_bar_outside_the_trained_choices(self, client, auth_headers, bad):
        res = client.put('/api/settings', headers=auth_headers(), json={'eligibility_top_percent': bad})
        assert res.status_code == 400

    def test_saves_a_valid_bar_and_reports_its_cutoff(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(), json={'eligibility_top_percent': 20})
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        assert body['eligibility_top_percent'] == 20
        assert body['eligibility_cutoff'] == round(ep.eligibility_cutoff(20), 2)
        assert body['eligibility_cutoff'] > round(ep.eligibility_cutoff(30), 2)   # stricter bar, higher cutoff

    def test_members_without_program_permission_cannot_change_it(self, client, auth_headers):
        res = client.put('/api/settings', headers=auth_headers(role='lgu_member', permissions={}),
                         json={'eligibility_top_percent': 20})
        assert res.status_code == 403


class TestChangingTheBarReDecidesReviewedApplicants:
    @staticmethod
    def borderline_applicant():
        """An applicant who qualifies under the loosest bar but not the strictest."""
        for applicant in applicant_grid():
            if score(applicant, 60)[1] == 'Eligible' and score(applicant, 10)[1] == 'Not Eligible':
                return applicant
        pytest.fail('no applicant in the grid sits between the strictest and loosest bars')

    def insert_reviewed(self, db, cycle_id, applicant, top_percent, email):
        ml_score, ml_status = score(applicant, top_percent)
        status = 'Approved' if ml_status == 'Eligible' else 'Rejected'
        return db.applicants.insert_one({
            **applicant, 'full_name': email, 'email': email, 'cycle_id': cycle_id,
            'ml_score': ml_score, 'ml_status': ml_status, 'application': {'status': status},
        }).inserted_id

    def test_tightening_the_bar_rejects_applicants_who_no_longer_meet_it(self, client, db, auth_headers, open_cycle):
        applicant = self.borderline_applicant()
        applicant_id = self.insert_reviewed(db, open_cycle, applicant, 60, 'border@test.com')
        assert db.applicants.find_one({'_id': applicant_id})['application']['status'] == 'Approved'

        res = client.put('/api/settings', headers=auth_headers(), json={'eligibility_top_percent': 10})
        assert res.status_code == 200, res.get_json()
        assert res.get_json()['eligibility_changes'] == {'now_eligible': 0, 'now_not_eligible': 1}

        doc = db.applicants.find_one({'_id': applicant_id})
        assert doc['ml_status'] == 'Not Eligible'
        assert doc['application']['status'] == 'Rejected'
        assert 'eligibility bar changed' in doc['audit_trail'][-1]['action']

    def test_loosening_the_bar_admits_applicants_who_now_meet_it(self, client, db, auth_headers, open_cycle):
        applicant = self.borderline_applicant()
        headers = auth_headers()
        assert client.put('/api/settings', headers=headers,
                          json={'eligibility_top_percent': 10, 'max_accepted': 50}).status_code == 200
        applicant_id = self.insert_reviewed(db, open_cycle, applicant, 10, 'border2@test.com')
        assert db.applicants.find_one({'_id': applicant_id})['ml_status'] == 'Not Eligible'

        res = client.put('/api/settings', headers=headers, json={'eligibility_top_percent': 60})
        assert res.get_json()['eligibility_changes'] == {'now_eligible': 1, 'now_not_eligible': 0}
        doc = db.applicants.find_one({'_id': applicant_id})
        assert doc['ml_status'] == 'Eligible'
        assert doc['application']['status'] == 'Approved'   # within the applicant limit

    def test_withdrawn_and_unreviewed_applicants_are_left_alone(self, client, db, auth_headers, open_cycle):
        applicant = self.borderline_applicant()
        withdrawn = db.applicants.insert_one({**applicant, 'email': 'w@test.com', 'cycle_id': open_cycle,
                                              'ml_status': 'Eligible', 'ml_score': 60,
                                              'application': {'status': 'Withdrawn'}}).inserted_id
        pending = db.applicants.insert_one({**applicant, 'email': 'p@test.com', 'cycle_id': open_cycle,
                                            'ml_status': 'Pending', 'ml_score': 0,
                                            'application': {'status': 'Newly Submitted'}}).inserted_id

        client.put('/api/settings', headers=auth_headers(), json={'eligibility_top_percent': 10})
        assert db.applicants.find_one({'_id': withdrawn})['application']['status'] == 'Withdrawn'
        assert db.applicants.find_one({'_id': pending})['ml_status'] == 'Pending'
