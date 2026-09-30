"""
ecoscholar_features.py

Turns one applicant record into the model's feature vector, and computes the Chapter III
Total Score. Shared by ecoscholar_predict.py (serving) and scripts/train_model.py
(training) so the two can never disagree about how a field is encoded.

No model files are loaded here; every function takes the encoding `maps` and feature
`contract` dicts (the contents of ecoscholar_encoding_maps.json and
ecoscholar_feature_contract.json) as arguments.

Parent occupation is encoded as a *need score* (0-100, higher = more financial need) looked
up from the 8 options in the application form's occupation dropdown, and the models are
constrained so a higher need score can never lower an applicant's result. That is what keeps
an unemployed or deceased parent from counting against an applicant.
"""

import numpy as np
import pandas as pd

# The eligibility classifier takes the LGU's eligibility bar as one extra input, expressed in
# Total Score points, so a single trained model serves any bar without retraining.
CUTOFF_COLUMN = 'EligibilityCutoff'


def cutoff_for_top_percent(top_percent, maps):
    """'Top X% of need' -> the Total Score a qualifying applicant must reach. Percentiles are
    those of the training survey's Total Scores (maps['total_score_percentiles'], one value per
    percentile 0-100), so the bar means the same thing every cycle instead of being re-ranked
    against whoever happens to apply."""
    table = maps['total_score_percentiles']
    return float(np.interp(100 - top_percent, np.arange(len(table)), table))


def with_cutoff(X, cutoff, contract):
    """Feature rows -> the classifier's input: the same rows plus the eligibility bar."""
    return X.assign(**{CUTOFF_COLUMN: float(cutoff)})[contract['classifier_columns']]


def bracket_midpoint(val, none_value=0):
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


def occupation_need(raw, maps):
    """Need score (0-100) for one of the form's occupation options. A blank or unrecognised
    value gets the neutral `occupation_need_unknown` score rather than counting for or against."""
    unknown = maps['occupation_need_unknown']
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return float(unknown)
    lookup = {k.lower(): v for k, v in maps['occupation_need_map'].items()}
    return float(lookup.get(str(raw).strip().lower(), unknown))


def build_feature_vector(applicant, maps, contract):
    """
    One raw applicant record -> a 1-row DataFrame in the exact column order the models were
    trained on. `applicant` keys (matching the survey schema in Chapter III):

        household_size / siblings_studying: number or bracket string, e.g. 4 or '2-5'
        father_education / mother_education: one of the education_map keys
        father_occupation / mother_occupation: one of the application form's occupation options
        monthly_income_bracket: one of the income_bracket_map keys
        housing_situation: 'Owned' | 'Rented' | 'Living with relatives' | 'Informal settler'
        gwa: number, 75-99 scale
        holds_other_scholarship: bool or 0/1
    """
    row = {}
    row['Household_Size_Num'] = bracket_midpoint(applicant.get('household_size'))
    # Raw sibling count ('siblings') is deliberately NOT a feature: the Total Score formula
    # below never reads it (only household size and siblings-studying feed the burden term),
    # and it's highly correlated with both of those (r=0.79-0.85 on the training survey) -
    # feeding it in only added multicollinearity, not signal. Still accepted as an input key
    # (harmlessly ignored) so callers that still pass it don't need to change.
    row['Siblings_Studying_Num'] = bracket_midpoint(applicant.get('siblings_studying'), none_value=0)
    row['Father_Edu_Ord'] = maps['education_map'].get(applicant.get('father_education'), np.nan)
    row['Mother_Edu_Ord'] = maps['education_map'].get(applicant.get('mother_education'), np.nan)
    row['Income_Num'] = maps['income_bracket_map'].get(applicant.get('monthly_income_bracket'), np.nan)
    gwa = applicant.get('gwa')
    row['GWA Numeric'] = float(gwa) if gwa is not None and gwa >= 50 else np.nan
    row['Holds_Other_Scholarship'] = int(bool(applicant.get('holds_other_scholarship', False)))
    row['FatherOccNeed'] = occupation_need(applicant.get('father_occupation'), maps)
    row['MotherOccNeed'] = occupation_need(applicant.get('mother_occupation'), maps)
    # A single ordinal precarity score (housing_precarity_map: Owned=0, ... Informal settler=100,
    # same map estimate_total_score() uses below), not one dummy per category. Three independent
    # one-hot dummies each only constrain themselves against an implicit "no housing dummy set"
    # baseline, which does NOT transitively guarantee Living with relatives scores no better than
    # the more precarious Rented (found by test - two dummies changing at once isn't
    # covered by either one's own constraint). A single monotonic column guarantees the full
    # ordering, and also gives a sensible score to Informal settler even though the training
    # survey has no such rows (a one-hot dummy for it would otherwise just read all-zero, i.e.
    # indistinguishable from an unrecognised value).
    row['HousingPrecarity'] = float(maps['housing_precarity_map'].get(applicant.get('housing_situation'), 50))

    # Assemble in the EXACT column order the model was trained on
    vec = pd.DataFrame([row])
    for col in contract['feature_columns']:
        if col not in vec.columns:
            vec[col] = 0.0
    vec = vec[contract['feature_columns']].astype(float)
    # The random forest (monotone-constrained) can't take NaN, so a blank field is filled with
    # its training-set median. Absent while training builds the medians in the first place.
    imputation = maps.get('imputation_values')
    if imputation:
        vec = vec.fillna(imputation)
    return vec


def estimate_total_score(applicant, maps):
    """
    The Total Score formula (Chapter III) for one applicant, normalized against the FROZEN
    bounds in the encoding maps so scores stay comparable to the eligibility cutoff over time
    rather than drifting as new batches of applicants come in. Weights come from
    maps['total_score_weights'].
    """
    bounds, w = maps['normalization_bounds'], maps['total_score_weights']

    def norm(val, lo, hi):
        if val is None:
            return 50.0  # neutral fallback if a field is missing
        return 100 * (val - lo) / (hi - lo) if hi > lo else 50.0

    gwa = applicant.get('gwa')
    income = maps['income_bracket_map'].get(applicant.get('monthly_income_bracket'))
    hh = bracket_midpoint(applicant.get('household_size'))
    sib_study = bracket_midpoint(applicant.get('siblings_studying'), none_value=0)
    f_edu = maps['education_map'].get(applicant.get('father_education'))
    m_edu = maps['education_map'].get(applicant.get('mother_education'))
    avg_edu = (f_edu + m_edu) / 2 if f_edu is not None and m_edu is not None else None
    housing_precarity = maps['housing_precarity_map'].get(applicant.get('housing_situation'), 50)

    G = norm(gwa, bounds['gwa_min'], bounds['gwa_max'])
    N = 100 - norm(income, bounds['income_min'], bounds['income_max'])
    hh_norm = norm(hh, bounds['household_min'], bounds['household_max'])
    sib_norm = norm(sib_study, bounds['siblings_studying_min'], bounds['siblings_studying_max'])
    B = 0.5 * hh_norm + 0.5 * sib_norm
    E = 100 - norm(avg_edu, bounds['avg_edu_min'], bounds['avg_edu_max'])
    O = (occupation_need(applicant.get('father_occupation'), maps)
         + occupation_need(applicant.get('mother_occupation'), maps)) / 2
    H = housing_precarity

    total = (w['gwa'] * G + w['income'] * N + w['burden'] * B + w['education'] * E
             + w['occupation'] * O + w['housing'] * H)
    if applicant.get('holds_other_scholarship'):
        total -= w['other_scholarship_penalty']
    return max(0.0, total)
