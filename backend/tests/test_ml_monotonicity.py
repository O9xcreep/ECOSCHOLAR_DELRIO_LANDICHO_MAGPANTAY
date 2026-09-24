# -*- coding: utf-8 -*-
"""Beyond occupation (test_ml_occupation.py), the model is also monotone-constrained on both
parents' education and housing situation, and no longer sees raw sibling count at all - see
MONOTONE_DIRECTIONS in scripts/train_model.py for how that set was chosen (an audit of which
features an unconstrained model actually gets backwards on its own, not a guess from marginal
correlation). These tests pin down the resulting guarantees."""
import itertools

import pytest

import app as app_module
import ecoscholar_predict as ep

EDUCATION_LEVELS = ['None', 'Elementary', 'High School', 'Vocational', 'College', 'Postgraduate']
HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives']  # 'Informal settler' has no
# training rows in the survey and isn't a trained category - see schema/ml_model.md


def make_applicant(gpa=90, income=8000, father_education='High School', mother_education='High School',
                   housing='Rented', family_size=5, num_siblings=3):
    return {
        'gender': 'Female', 'family_size': family_size, 'num_siblings': num_siblings, 'num_siblings_studying': 2,
        'father_education': father_education, 'mother_education': mother_education,
        'father_occupation': 'Laborer/Driver', 'mother_occupation': 'Laborer/Driver',
        'monthly_income': income, 'housing_situation': housing,
        'academic': {'gpa': gpa}, 'has_other_scholarship': False,
    }


def score(applicant):
    row, ok = app_module.build_feature_row(applicant)
    assert ok
    return app_module.score_with_model(row)   # (priority_score, 'Eligible' | 'Not Eligible')


def applicant_grid():
    # Spans the eligibility boundary so a leak shows up as a changed decision, not just a score.
    for gpa, income, size in itertools.product((84, 92), (2500, 12500, 25000), (3, 6)):
        yield dict(gpa=gpa, income=income, family_size=size)


class TestLessParentEducationNeverCountsAgainstAnApplicant:
    @pytest.mark.parametrize('parent', ['father_education', 'mother_education'])
    def test_score_never_drops_as_education_falls(self, parent):
        by_level = EDUCATION_LEVELS  # already ordered None (least) -> Postgraduate (most)
        for kw in applicant_grid():
            results = [score(make_applicant(**kw, **{parent: lvl})) for lvl in by_level]
            scores = [r[0] for r in results]
            eligible = [r[1] == 'Eligible' for r in results]
            # `by_level` is ascending education; the score must be monotone NON-INCREASING in it
            # (less education -> need -> score can only stay the same or go up).
            assert scores == sorted(scores, reverse=True), \
                f'{parent}: score rose with MORE education for {kw}: {list(zip(by_level, scores))}'
            assert eligible == sorted(eligible, reverse=True), \
                f'{parent}: eligibility rose with more education for {kw}'

    def test_no_education_never_scores_below_postgraduate(self):
        for kw in applicant_grid():
            none_score, none_elig = score(make_applicant(**kw, father_education='None', mother_education='None'))
            pg_score, pg_elig = score(make_applicant(**kw, father_education='Postgraduate', mother_education='Postgraduate'))
            assert none_score >= pg_score
            if pg_elig == 'Eligible':
                assert none_elig == 'Eligible', f'Postgraduate parents were eligible but None-education parents were not, for {kw}'


class TestMorePrecariousHousingNeverCountsAgainstAnApplicant:
    def test_score_never_drops_as_housing_gets_more_precarious(self):
        # Owned (least precarious) -> Rented -> Living with relatives (most, of the trained categories)
        by_precarity = ['Owned', 'Rented', 'Living with relatives']
        for kw in applicant_grid():
            results = [score(make_applicant(**kw, housing=h)) for h in by_precarity]
            scores = [r[0] for r in results]
            eligible = [r[1] == 'Eligible' for r in results]
            assert scores == sorted(scores), \
                f'housing: score fell for a more precarious situation, {kw}: {list(zip(by_precarity, scores))}'
            assert eligible == sorted(eligible), f'housing: eligibility fell for a more precarious situation, {kw}'


class TestRawSiblingCountIsNotAModelFeature:
    """The Total Score formula never reads raw sibling count (only household size and
    siblings-studying feed the burden term), and it was highly correlated with both
    (r=0.79-0.85 on the training survey) - see ecoscholar_features.py. It's no longer sent to
    the model at all."""

    def test_siblings_num_is_not_in_the_feature_contract(self):
        assert 'Siblings_Num' not in ep.FEATURE_COLUMNS

    def test_changing_num_siblings_alone_never_changes_the_score(self):
        for kw in applicant_grid():
            baseline = score(make_applicant(**kw, num_siblings=0))
            for n in (1, 2, 5, 8):
                assert score(make_applicant(**kw, num_siblings=n)) == baseline, \
                    f'num_siblings={n} changed the result for {kw}, but siblings is not a model feature'
