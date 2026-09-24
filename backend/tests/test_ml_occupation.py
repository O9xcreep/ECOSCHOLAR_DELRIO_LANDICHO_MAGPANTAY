# -*- coding: utf-8 -*-
"""Parent occupation is a model feature (encoded as a need score from the form's 7 dropdown
options) and the models are constrained so a higher need can never lower a result: an
unemployed or deceased parent must never count against an applicant. These tests pin that down,
plus the encoding details (income bracket keys, unknown occupation) the model depends on."""
import itertools

import pytest

import app as app_module
import ecoscholar_predict as ep
from ecoscholar_features import occupation_need

# Mirrors DEFAULT_OCCUPATION_CATEGORIES in helpers.py / the application form dropdown.
FORM_OCCUPATIONS = [
    'Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade',
    'Office/Clerical', 'Professional', 'Deceased/Not Applicable',
]
NEEDIEST = ['Unemployed', 'Deceased/Not Applicable']
LEAST_NEEDY = 'Professional'


def make_applicant(gpa=90, income=4000, father='Laborer/Driver', mother='Laborer/Driver',
                   housing='Rented', family_size=5):
    return {
        'gender': 'Female', 'family_size': family_size, 'num_siblings': 3, 'num_siblings_studying': 2,
        'father_education': 'High School', 'mother_education': 'High School',
        'father_occupation': father, 'mother_occupation': mother,
        'monthly_income': income, 'housing_situation': housing,
        'academic': {'gpa': gpa}, 'has_other_scholarship': False,
    }


def score(applicant):
    row, ok = app_module.build_feature_row(applicant)
    assert ok
    return app_module.score_with_model(row)   # (priority_score, 'Eligible' | 'Not Eligible')


def applicant_grid():
    # Spans the eligibility boundary so a leak shows up as a changed decision, not just a score.
    for gpa, income, housing, size in itertools.product(
            (84, 92), (2500, 12500, 25000), ('Owned', 'Rented'), (3, 6)):
        yield dict(gpa=gpa, income=income, housing=housing, family_size=size)


class TestOccupationNeverCountsAgainstAnApplicant:
    def test_the_grid_used_below_crosses_the_eligibility_boundary(self):
        """Otherwise the checks below could pass without ever exercising a decision."""
        statuses = {score(make_applicant(**kw))[1] for kw in applicant_grid()}
        assert statuses == {'Eligible', 'Not Eligible'}

    @pytest.mark.parametrize('parent', ['father', 'mother'])
    @pytest.mark.parametrize('needy', NEEDIEST)
    def test_unemployed_or_deceased_never_scores_below_professional(self, parent, needy):
        for kw in applicant_grid():
            pro_score, pro_status = score(make_applicant(**kw, **{parent: LEAST_NEEDY}))
            needy_score, needy_status = score(make_applicant(**kw, **{parent: needy}))
            assert needy_score >= pro_score, f'{parent} {needy} lowered the score for {kw}'
            assert (needy_status == 'Eligible') >= (pro_status == 'Eligible'), \
                f'{parent} {needy} cost eligibility for {kw}'

    @pytest.mark.parametrize('parent', ['father', 'mother'])
    def test_score_never_drops_as_occupation_need_rises(self, parent):
        by_need = sorted(FORM_OCCUPATIONS, key=lambda o: occupation_need(o, ep._maps))
        for kw in applicant_grid():
            results = [score(make_applicant(**kw, **{parent: o})) for o in by_need]
            scores = [r[0] for r in results]
            eligible = [r[1] == 'Eligible' for r in results]
            assert scores == sorted(scores), f'{parent}: score fell as need rose for {kw}: {list(zip(by_need, scores))}'
            assert eligible == sorted(eligible), f'{parent}: eligibility fell as need rose for {kw}'

    def test_unemployed_is_not_treated_the_same_as_professional(self):
        """Regression: the old model collapsed both into 'Other' and ignored the difference."""
        pro = [score(make_applicant(**kw, father=LEAST_NEEDY, mother=LEAST_NEEDY)) for kw in applicant_grid()]
        unemployed = [score(make_applicant(**kw, father='Unemployed', mother='Unemployed')) for kw in applicant_grid()]
        assert pro != unemployed
        assert sum(u[0] for u in unemployed) > sum(p[0] for p in pro)


class TestOccupationEncoding:
    def test_every_form_option_has_a_need_score(self):
        needs = ep._maps['occupation_need_map']
        assert set(needs) == set(FORM_OCCUPATIONS)

    def test_unemployed_and_deceased_are_the_highest_need(self):
        needs = {o: occupation_need(o, ep._maps) for o in FORM_OCCUPATIONS}
        assert needs['Unemployed'] == needs['Deceased/Not Applicable'] == max(needs.values())
        assert needs['Professional'] == min(needs.values())

    def test_blank_or_unrecognised_occupation_is_neutral_not_penalised(self):
        unknown = ep._maps['occupation_need_unknown']
        assert occupation_need(None, ep._maps) == unknown
        assert occupation_need('', ep._maps) == unknown
        assert occupation_need('astronaut', ep._maps) == unknown
        needs = [occupation_need(o, ep._maps) for o in FORM_OCCUPATIONS]
        assert min(needs) < unknown < max(needs)

    def test_lookup_ignores_case_and_surrounding_spaces(self):
        assert occupation_need('  unemployed ', ep._maps) == occupation_need('Unemployed', ep._maps)

    def test_stored_occupation_is_not_altered_by_scoring(self):
        applicant = make_applicant(father='Unemployed', mother='Deceased/Not Applicable')
        score(applicant)
        assert applicant['father_occupation'] == 'Unemployed'
        assert applicant['mother_occupation'] == 'Deceased/Not Applicable'


class TestModelFilesReadTheSameOnEveryMachine:
    def test_income_brackets_the_backend_produces_resolve_to_a_number(self):
        """The encoding maps hold '₱' in their keys. If they were ever read with the wrong
        encoding (as happened on Windows before they were read as UTF-8), every income would
        silently look missing and the model would stop seeing income at all."""
        for income in (2500, 7500, 12500, 17500, 25000):
            row, _ = app_module.build_feature_row(make_applicant(income=income))
            vec = ep.build_feature_vector(row)
            assert vec['Income_Num'].iloc[0] == income, f'income {income} did not map to its bracket'

    def test_feature_row_carries_the_applicants_real_occupation_to_the_model(self):
        row, _ = app_module.build_feature_row(make_applicant(father='Unemployed', mother='Professional'))
        vec = ep.build_feature_vector(row)
        assert vec['FatherOccNeed'].iloc[0] == occupation_need('Unemployed', ep._maps)
        assert vec['MotherOccNeed'].iloc[0] == occupation_need('Professional', ep._maps)
