"""
ecoscholar_predict.py

Loads the trained EcoScholar model bundle (classifier + regressor + scaler + feature
contract + encoding maps) and exposes a single function, score_applicant(), that takes
a raw applicant record (as your Flask backend would receive it from the frontend/DB) and
returns the eligibility decision and priority ranking score.

Files expected in the same directory (produced by the notebook's "Deployment" section):
    ecoscholar_classifier.joblib
    ecoscholar_regressor.joblib
    ecoscholar_scaler.joblib
    ecoscholar_feature_contract.json
    ecoscholar_encoding_maps.json

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
import re
import joblib
import numpy as np
import pandas as pd
import os

_DIR = os.path.dirname(os.path.abspath(__file__))

_classifier = joblib.load(os.path.join(_DIR, 'ecoscholar_classifier.joblib'))
_regressor = joblib.load(os.path.join(_DIR, 'ecoscholar_regressor.joblib'))
_scaler = joblib.load(os.path.join(_DIR, 'ecoscholar_scaler.joblib'))

with open(os.path.join(_DIR, 'ecoscholar_feature_contract.json')) as f:
    _contract = json.load(f)

with open(os.path.join(_DIR, 'ecoscholar_encoding_maps.json')) as f:
    _maps = json.load(f)

FEATURE_COLUMNS = _contract['feature_columns']
OCCUPATION_CATEGORIES = _contract['occupation_categories']
HOUSING_CATEGORIES = _contract['housing_categories']
BOUNDS = _maps['normalization_bounds']
ELIGIBILITY_CUTOFF = _maps['eligibility_cutoff']


def _group_occupation(raw):
    """Must exactly mirror the grouping logic used during training (Stage 1)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or str(raw).strip() == '':
        return 'Unknown'
    s = re.sub(r'\s+', ' ', str(raw).strip().lower())
    typo_fix = {'famer': 'farmer', 'trucycle driver': 'tricycle driver',
                'ultility worker': 'utility worker', 'house wife': 'housewife'}
    s = typo_fix.get(s, s)
    if s in ('unknown', ''):
        return 'Unknown'
    if 'deceased' in s:
        return 'Deceased/None'
    if 'ofw' in s:
        return 'OFW'
    if 'farm' in s or 'fisher' in s:
        return 'Farmer/Fisherman'
    if any(k in s for k in ['tricycle', 'jeepney', 'driver', 'delivery rider', 'truck']):
        return 'Driver/Transport'
    if any(k in s for k in ['welder', 'electrician', 'carpenter', 'mechanic', 'technician', 'construction']):
        return 'Skilled Trade/Construction'
    if any(k in s for k in ['vendor', 'sari-sari', 'sari sari', 'sales lady', 'saleslady',
                             'online seller', 'store owner']):
        return 'Vendor/Retail'
    if any(k in s for k in ['security guard', 'lady guard', 'utility worker', 'waitress',
                             'cashier', 'service crew', 'laundry', 'canteen', 'shoe maker']):
        return 'Service Worker'
    if any(k in s for k in ['government employee', "gov't", 'office staff', 'admin staff',
                             'teacher', 'brgy', 'municipal worker', 'bhw', 'bank teller', 'politics']):
        return 'Government/Office Employee'
    if 'housewife' in s or 'house husband' in s:
        return 'Homemaker'
    return 'Other'


def _bracket_midpoint(val, none_value=0):
    """Converts a bracket string like '2-5' to its numeric midpoint. Accepts a plain number too."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower()
    if s == 'none':
        return none_value
    if '-' in s:
        lo, hi = s.split('-')
        return (float(lo) + float(hi)) / 2
    return float(s)


def build_feature_vector(applicant: dict) -> pd.DataFrame:
    """
    Transforms one raw applicant record into the exact encoded feature vector the
    deployed models expect. `applicant` should have these keys (matching the survey
    schema in Chapter III):

        sex: 'Male' | 'Female'
        household_size: number or bracket string, e.g. 4 or '2-5'
        siblings: number or bracket string
        siblings_studying: number or bracket string
        father_education: one of the education_map keys
        mother_education: one of the education_map keys
        father_occupation: free text (any casing/typo -- grouped automatically)
        mother_occupation: free text
        monthly_income_bracket: one of the income_bracket_map keys
        housing_situation: 'Owned' | 'Rented' | 'Living with relatives' | 'Informal settler'
        gwa: number, 75-99 scale
        holds_other_scholarship: bool or 0/1
    """
    row = {}
    row['Sex_Bin'] = _maps['sex_map'].get(applicant.get('sex'), np.nan)
    row['Household_Size_Num'] = _bracket_midpoint(applicant.get('household_size'))
    row['Siblings_Num'] = _bracket_midpoint(applicant.get('siblings'), none_value=0)
    row['Siblings_Studying_Num'] = _bracket_midpoint(applicant.get('siblings_studying'), none_value=0)
    row['Father_Edu_Ord'] = _maps['education_map'].get(applicant.get('father_education'), np.nan)
    row['Mother_Edu_Ord'] = _maps['education_map'].get(applicant.get('mother_education'), np.nan)
    row['Income_Num'] = _maps['income_bracket_map'].get(applicant.get('monthly_income_bracket'), np.nan)
    gwa = applicant.get('gwa')
    row['GWA Numeric'] = float(gwa) if gwa is not None and gwa >= 50 else np.nan
    row['Holds_Other_Scholarship'] = int(bool(applicant.get('holds_other_scholarship', False)))

    father_group = _group_occupation(applicant.get('father_occupation'))
    mother_group = _group_occupation(applicant.get('mother_occupation'))
    for cat in OCCUPATION_CATEGORIES:
        row[f'FatherOcc_{cat}'] = 1.0 if father_group == cat else 0.0
        row[f'MotherOcc_{cat}'] = 1.0 if mother_group == cat else 0.0

    housing = applicant.get('housing_situation')
    for cat in HOUSING_CATEGORIES:
        row[f'Housing_{cat}'] = 1.0 if housing == cat else 0.0

    # Assemble in the EXACT column order the model was trained on
    vec = pd.DataFrame([row])
    for col in FEATURE_COLUMNS:
        if col not in vec.columns:
            vec[col] = 0.0
    vec = vec[FEATURE_COLUMNS].astype(float)
    return vec


def estimate_total_score(applicant: dict) -> float:
    """
    Recomputes the Total Score formula (Chapter III) for a new applicant, normalized
    against the FROZEN training-set bounds saved in ecoscholar_encoding_maps.json, so
    scores stay comparable to the deployed cutoff over time rather than drifting as new
    batches of applicants come in.
    """
    def norm(val, lo, hi):
        if val is None:
            return 50.0  # neutral fallback if a field is missing
        return 100 * (val - lo) / (hi - lo) if hi > lo else 50.0

    gwa = applicant.get('gwa')
    income = _maps['income_bracket_map'].get(applicant.get('monthly_income_bracket'))
    hh = _bracket_midpoint(applicant.get('household_size'))
    sib_study = _bracket_midpoint(applicant.get('siblings_studying'), none_value=0)
    f_edu = _maps['education_map'].get(applicant.get('father_education'))
    m_edu = _maps['education_map'].get(applicant.get('mother_education'))
    avg_edu = (f_edu + m_edu) / 2 if f_edu is not None and m_edu is not None else None
    housing_precarity = _maps['housing_precarity_map'].get(applicant.get('housing_situation'), 50)

    G = norm(gwa, BOUNDS['gwa_min'], BOUNDS['gwa_max'])
    N = 100 - norm(income, BOUNDS['income_min'], BOUNDS['income_max'])
    hh_norm = norm(hh, BOUNDS['household_min'], BOUNDS['household_max'])
    sib_norm = norm(sib_study, BOUNDS['siblings_studying_min'], BOUNDS['siblings_studying_max'])
    B = 0.5 * hh_norm + 0.5 * sib_norm
    E = 100 - norm(avg_edu, BOUNDS['avg_edu_min'], BOUNDS['avg_edu_max'])
    H = housing_precarity

    total = 0.30 * G + 0.30 * N + 0.20 * B + 0.10 * E + 0.10 * H
    if applicant.get('holds_other_scholarship'):
        total -= 15
    return max(0.0, total)


def score_applicant(applicant: dict) -> dict:
    """
    Runs the deployed two-stage pipeline on one applicant record:
      - XGBoost classifier -> binary eligibility decision + probability
      - Random Forest Regressor -> continuous priority ranking score
    Returns a dict ready to write back to the applicant's record / audit trail.
    """
    X = build_feature_vector(applicant)
    proba = float(_classifier.predict_proba(X)[0, 1])
    eligible = int(_classifier.predict(X)[0])
    priority_score = float(_regressor.predict(X)[0])
    total_score_estimate = estimate_total_score(applicant)

    return {
        'eligible': eligible,
        'eligibility_probability': round(proba, 4),
        'priority_score': round(priority_score, 2),
        'total_score_estimate': round(total_score_estimate, 2),
        'eligibility_cutoff': round(ELIGIBILITY_CUTOFF, 2),
    }


if __name__ == '__main__':
    # Quick manual smoke test
    sample_applicant = {
        'sex': 'Female',
        'household_size': '2-5',
        'siblings': '2-3',
        'siblings_studying': '1-2',
        'father_education': 'High School',
        'mother_education': 'College',
        'father_occupation': 'Tricycle driver',
        'mother_occupation': 'Vendor',
        'monthly_income_bracket': '₱ 5,001 - ₱ 10,000',
        'housing_situation': 'Rented',
        'gwa': 91,
        'holds_other_scholarship': False,
    }
    print(score_applicant(sample_applicant))
