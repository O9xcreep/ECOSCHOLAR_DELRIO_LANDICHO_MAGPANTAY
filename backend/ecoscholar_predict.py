"""
ecoscholar_predict.py

Loads the trained EcoScholar model bundle (classifier + regressor + scaler + feature
contract + encoding maps) and exposes a single function, score_applicant(), that takes
a raw applicant record (as your Flask backend would receive it from the frontend/DB) and
returns the eligibility decision and priority ranking score.

Files expected in the same directory (written by scripts/train_model.py):
    ecoscholar_classifier.joblib
    ecoscholar_regressor.joblib
    ecoscholar_scaler.joblib
    ecoscholar_feature_contract.json
    ecoscholar_encoding_maps.json

Feature encoding lives in ecoscholar_features.py, shared with the training script.

Usage in Flask:
    from ecoscholar_predict import score_applicant

    @app.route('/api/applicants/<applicant_id>/verify', methods=['POST'])
    def verify_applicant(applicant_id):
        applicant = get_applicant_from_db(applicant_id)  # however you fetch the record
        result = score_applicant(applicant)
        # result = {'eligible': 0/1, 'eligibility_probability': float,
        #           'priority_score': float, 'total_score_estimate': float}
        # write result to DB, set application status, log audit trail entry, notify applicant
        ...
"""

import json
import joblib
import os

import numpy as np

from ecoscholar_features import (
    build_feature_vector as _build_feature_vector,
    estimate_total_score as _estimate_total_score,
    cutoff_for_top_percent as _cutoff_for_top_percent,
    with_cutoff as _with_cutoff,
)

_DIR = os.path.dirname(os.path.abspath(__file__))

_classifier = joblib.load(os.path.join(_DIR, 'ecoscholar_classifier.joblib'))
_regressor = joblib.load(os.path.join(_DIR, 'ecoscholar_regressor.joblib'))
_scaler = joblib.load(os.path.join(_DIR, 'ecoscholar_scaler.joblib'))

with open(os.path.join(_DIR, 'ecoscholar_feature_contract.json'), encoding='utf-8') as f:
    _contract = json.load(f)

with open(os.path.join(_DIR, 'ecoscholar_encoding_maps.json'), encoding='utf-8') as f:
    _maps = json.load(f)

FEATURE_COLUMNS = _contract['feature_columns']
HOUSING_CATEGORIES = _contract['housing_categories']
BOUNDS = _maps['normalization_bounds']
DEFAULT_TOP_PERCENT = _maps['eligibility_bar']['default_top_percent']
SELECTABLE_TOP_PERCENTS = _maps['eligibility_bar']['selectable_top_percents']


def eligibility_cutoff(top_percent=None) -> float:
    """The Total Score cutoff for 'top X% of need' (default: the trained default bar)."""
    return _cutoff_for_top_percent(DEFAULT_TOP_PERCENT if top_percent is None else top_percent, _maps)


def build_feature_vector(applicant: dict):
    """One raw applicant record -> the encoded feature row the deployed models expect.
    See ecoscholar_features.build_feature_vector for the accepted keys."""
    return _build_feature_vector(applicant, _maps, _contract)


def estimate_total_score(applicant: dict) -> float:
    """The Chapter III Total Score for a new applicant, against the frozen training-set bounds."""
    return _estimate_total_score(applicant, _maps)


def score_applicant(applicant: dict, top_percent=None) -> dict:
    """
    Runs the deployed two-stage pipeline on one applicant record:
      - cutoff-aware XGBoost classifier -> eligibility decision + probability at the LGU's
        eligibility bar (`top_percent`, e.g. 30 = top 30% of need; default: the trained default)
      - Random Forest Regressor -> continuous priority ranking score (independent of the bar)
    Returns a dict ready to write back to the applicant's record / audit trail.
    """
    X = build_feature_vector(applicant)
    cutoff = eligibility_cutoff(top_percent)
    X_clf = _with_cutoff(X, cutoff, _contract)
    proba = float(_classifier.predict_proba(X_clf)[0, 1])
    eligible = int(_classifier.predict(X_clf)[0])
    priority_score = float(_regressor.predict(X)[0])
    total_score_estimate = estimate_total_score(applicant)

    return {
        'eligible': eligible,
        'eligibility_probability': round(proba, 4),
        'priority_score': round(priority_score, 2),
        'total_score_estimate': round(total_score_estimate, 2),
        'eligibility_cutoff': round(cutoff, 2),
        'eligibility_top_percent': DEFAULT_TOP_PERCENT if top_percent is None else top_percent,
    }


def explain_priority_score(applicant: dict) -> dict:
    """
    Exact per-feature decomposition of the regressor's priority score: for every tree, each
    split along the applicant's decision path credits the change in node mean to the split's
    feature (the tree-interpreter method). Averaged over the forest,
        baseline + sum(contributions) == _regressor.predict(X)
    where baseline is the training-set mean score. Returns {'baseline', 'contributions'}.
    """
    x = build_feature_vector(applicant).to_numpy()
    contributions = np.zeros(x.shape[1])
    baseline = 0.0
    for est in _regressor.estimators_:
        tree = est.tree_
        path = est.decision_path(x).indices  # root-to-leaf; child ids are always > parent ids
        values = tree.value[:, 0, 0]
        baseline += values[path[0]]
        for parent, child in zip(path[:-1], path[1:]):
            contributions[tree.feature[parent]] += values[child] - values[parent]
    n = len(_regressor.estimators_)
    return {
        'baseline': float(baseline / n),
        'contributions': {col: float(c / n) for col, c in zip(FEATURE_COLUMNS, contributions)},
    }


if __name__ == '__main__':
    # Quick manual smoke test
    sample_applicant = {
        'household_size': '2-5',
        'siblings': '2-3',
        'siblings_studying': '1-2',
        'father_education': 'High School',
        'mother_education': 'College',
        'father_occupation': 'Laborer/Driver',
        'mother_occupation': 'Informal/Vendor',
        'monthly_income_bracket': '₱ 5,001 - ₱ 10,000',
        'housing_situation': 'Rented',
        'gwa': 91,
        'holds_other_scholarship': False,
    }
    print(score_applicant(sample_applicant))
