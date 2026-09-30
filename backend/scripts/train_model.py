# -*- coding: utf-8 -*-
"""Retrains the EcoScholar eligibility classifier + priority regressor from the survey CSV
and writes the five files ecoscholar_predict.py loads.

    python scripts/train_model.py "<path to EcoScholar_Combined_Dataset_300.csv>"
    python scripts/train_model.py "<csv>" --evaluate-only      # cross-validate, write nothing
    python scripts/train_model.py "<csv>" --out some/dir       # write somewhere else

What it does, in order:
  1. Cleans the survey (Excel turned brackets like "2-5" into dates like "02-May" in some rows).
  2. Maps each free-text parent occupation onto the 8 options in the application form's dropdown,
     so the model only ever sees values the form can actually send. Rules are in OCCUPATION_RULES;
     the full raw -> category table is printed so it can be reviewed.
  3. Scores every applicant with the Chapter III Total Score, now including an occupation-need
     term (OCCUPATION_NEED, weights in TOTAL_SCORE_WEIGHTS), and labels the top 30% eligible.
     Raw sibling count is dropped from the feature set entirely: an expanded correlation
     analysis (scripts/feature_correlation_analysis.py) showed it's redundant with household
     size and siblings-studying (r=0.79-0.85) and it isn't part of the Total Score formula.
  4. Cross-validates, then fits the classifier and regressor. MONOTONE_DIRECTIONS constrains the
     features an audit showed an unconstrained model gets backwards (both parents' education,
     occupation need, housing), so a WORSE circumstance on any of them can never LOWER a
     prediction. evaluate() prints that audit.
  5. The eligibility classifier is CUTOFF-AWARE: one calibrated XGBoost that takes the LGU's
     eligibility bar (as a Total Score cutoff) as an extra input, so an LGU can move the bar
     (e.g. from the top 30% to the top 20% of need) without retraining. It is trained on every
     applicant repeated once per bar in TRAIN_TOP_PERCENTS, labelled against that bar, and is
     monotone-constrained to be non-increasing in the cutoff, so a stricter bar can never admit
     MORE applicants. Calibration folds are grouped by applicant, so the same person never
     appears on both sides of a fold. evaluate_bars() cross-validates it at every selectable bar.
     No class-weighting: across the stacked bars the positive rate already spans 5-60%, and
     class-weighting lowered precision without improving F1 (see the notebook's adaptive
     eligibility bar section).
  6. Writes the artifacts and checks that ecoscholar_predict.score_applicant reproduces the
     models' own predictions on every survey row.

STUDY ASSUMPTIONS (not sourced; confirm with the panel): the OCCUPATION_NEED values, the 5%
occupation weight (carved out of the parents'-education weight so the total stays 100%), and the
rule that a housewife/house husband counts as "Unemployed" (that parent earns no income; the form
labels the option "Unemployed (including Housewife/Househusband)").

Two scores follow the survey's own income data rather than assumption
(notebooks/no_constraint_experiments.py, Part A):
  - "OFW" is its own option scored 0, the same as Professional: OFW households report the highest
    income in the survey (mean about P21,000, against about P20,000-21,000 for Professional).
  - Housing scores Rented (60) above Living with relatives (40): renters report the lowest income
    of any housing group (mean P5,714, 95% at P10,000 or less, against P9,688 and 69%).
"""
import argparse
import json
import os
import re
import sys
import warnings

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import GroupKFold, RepeatedStratifiedKFold, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
from ecoscholar_features import (build_feature_vector, estimate_total_score,  # noqa: E402
                                 cutoff_for_top_percent, with_cutoff, CUTOFF_COLUMN)

warnings.filterwarnings('ignore')

ELIGIBLE_PERCENTILE = 70          # the default bar: top 30% of Total Score are eligible
DEFAULT_TOP_PERCENT = 100 - ELIGIBLE_PERCENTILE
TRAIN_TOP_PERCENTS = list(range(5, 61, 5))        # bars the cutoff-aware classifier is trained on
SELECTABLE_TOP_PERCENTS = list(range(10, 61, 5))  # bars an LGU may choose (inside the trained range)
RANDOM_STATE = 42

# The application form's occupation dropdown (frontend ApplicationForm.jsx / helpers.py),
# with how much financial need each option signals. Higher = more need.
OCCUPATION_NEED = {
    'Unemployed': 100,
    'Deceased/Not Applicable': 100,
    'Informal/Vendor': 70,
    'Laborer/Driver': 60,
    'Skilled Trade': 40,
    'Office/Clerical': 20,
    'Professional': 0,
    'OFW': 0,
}
OCCUPATION_NEED_UNKNOWN = 50      # blank / unrecognised -> neutral, counts neither for nor against

# The form's housing dropdown, with how precarious each option is. Higher = more need.
# 'Informal settler' has no rows in the survey; its score is an assumption.
HOUSING_PRECARITY = {'Owned': 0, 'Living with relatives': 40, 'Rented': 60, 'Informal settler': 100}

# Chapter III weights, with the parents'-education 10% split into education 5% + occupation 5%.
TOTAL_SCORE_WEIGHTS = {
    'gwa': 0.30, 'income': 0.30, 'burden': 0.20, 'education': 0.05,
    'occupation': 0.05, 'housing': 0.10, 'other_scholarship_penalty': 15,
}
assert abs(sum(v for k, v in TOTAL_SCORE_WEIGHTS.items() if k != 'other_scholarship_penalty') - 1.0) < 1e-9

# Survey free text -> dropdown option. First matching rule wins; `None` means "unknown".
OCCUPATION_RULES = [
    ('Deceased/Not Applicable', ['deceased']),
    ('Unemployed', ['housewife', 'house wife', 'hoysewife', 'hohsewife', 'househusband', 'house husband']),
    ('OFW', ['ofw']),
    ('Informal/Vendor', ['vendor', 'sari sari', 'sari-sari', 'online seller', 'karinderya', 'lottery',
                         'rice dealer', 'small business', 'self employed', 'kakanin', 'repacker',
                         'slipper', 'shoe maker', 'sewer']),
    ('Skilled Trade', ['carpenter', 'welder', 'mechanic', 'technician', 'electrician', 'lineman',
                       'chef', 'tailor', 'barber', 'hair dresser']),
    ('Professional', ['teacher', 'police', 'engineer', 'nurse', 'pharmacist', 'accountant',
                      'insurance agent', 'manager', 'company officer', 'councilor', 'konsehal',
                      'politician', 'politics']),
    ('Office/Clerical', ['government employee', 'office', 'admin', 'cashier', 'sales lady', 'saleslady',
                         'salesperson', 'sales person', 'teller', 'secretary', 'municipal', 'bhw',
                         'health worker', 'healthcare', 'coordinator', 'promodiser']),
    ('Laborer/Driver', ['driver', 'tricycle', 'trucycle', 'trjcycle', 'jeepney', 'truck', 'rider',
                        'construction', 'laborer', 'utility', 'ultility', 'gasoline', 'laundry', 'farm', 'famer',
                        'fisher', 'caretaker', 'factory', 'service crew', 'waitress', 'canteen', 'guard']),
]

# Excel date-mangled brackets in the Liliw rows
DATE_FIXED_BRACKETS = {'02-May': '2-5', '05-Oct': '5-10', '02-Mar': '2-3', '04-May': '4-5',
                       '06-Aug': '6-8', '01-Feb': '1-2', '03-May': '3-5'}

# Every feature whose direction the Total Score formula already fixes: +1 = raising the feature
# must never LOWER the prediction, -1 = raising it must never RAISE the prediction. Derived
# directly from estimate_total_score() in ecoscholar_features.py - keep the two in sync if the
# formula changes. Used to AUDIT every model (does it get this feature's direction right on its
# own?), whether or not that feature is actually constrained during training - see
# MONOTONE_DIRECTIONS below and the "unconstrained" column evaluate() prints.
#   GWA up                       -> merit score up            -> total up    (+1)
#   income up                    -> need score down            -> total down (-1)
#   household size / siblings-studying up -> burden up         -> total up   (+1, +1)
#   parent education up          -> education-need down        -> total down (-1, -1)
#   holds another scholarship    -> flat 15-point penalty       -> total down (-1)
#   occupation need up           -> occupation-need score up    -> total up   (+1, +1)
#   housing precarity up (Owned=0 ... Rented=60) -> housing-need score up (+1)
# Housing is one ordinal column (HousingPrecarity, from housing_precarity_map), not one dummy per
# category - three independent one-hot dummies each only constrain themselves against an implicit
# "no dummy set" baseline, which does NOT transitively guarantee, say, Living with relatives scores
# no better than the more precarious Rented (two dummies changing at once isn't covered by
# either one's own constraint - found by test, see ecoscholar_features.py). A single monotonic
# column gives the full ordering.
# Sex is excluded from the feature set entirely (not just unconstrained): the formula gives it no
# role in eligibility, and leaving it in as an input - even unconstrained - would let the model
# pick up incidental correlations with the label that have nothing to do with need.
ALL_FORMULA_DIRECTIONS = {
    'GWA Numeric': 1,
    'Income_Num': -1,
    'Household_Size_Num': 1,
    'Siblings_Studying_Num': 1,
    'Father_Edu_Ord': -1,
    'Mother_Edu_Ord': -1,
    'Holds_Other_Scholarship': -1,
    'FatherOccNeed': 1,
    'MotherOccNeed': 1,
    'HousingPrecarity': 1,
}

# The SUBSET of ALL_FORMULA_DIRECTIONS actually enforced as training constraints - chosen by
# evidence, not guessed from the marginal correlation table. Constraining every
# formula-direction feature (12 of them) guarantees 0 wrong-direction predictions but cost real
# regressor accuracy (Spearman 0.96 -> 0.93, MAE nearly doubled): too blunt an instrument for
# features the data already gets right on its own.
#
# The audit that decides this (evaluate()'s "unconstrained" column - moving each feature from
# its lowest to highest observed value, holding everything else fixed, and checking whether the
# UNCONSTRAINED model's prediction ever moves the wrong way) is a check on the model's
# CONDITIONAL behaviour, which is not the same thing as the feature's marginal correlation with
# Total Score. GWA is the clearest example: its marginal correlation is weak and not
# significant (r=-0.09, p=0.10 - see feature_correlation_analysis.py), which looked like exactly
# the kind of risk this file should guard against, but the audit shows the unconstrained model
# already gets GWA's conditional direction right 100% of the time (0/3600) - so constraining it
# would only cost accuracy for a risk that doesn't actually exist. Income has the same story.
# Occupation, on the other hand, is confirmed at real risk even after the other fixes here
# (5.4-13.8% of checks moved the wrong way unconstrained) - the original bug this file exists to
# fix - and so are both parents' education (2.2-5.5%) and housing (0.7-2.8% per category, before
# it was collapsed into one ordinal column). Household size, siblings-studying and holding
# another scholarship were audited too and left out: under 0.2% unconstrained, not worth
# constraining.
MONOTONE_DIRECTIONS = {
    'Father_Edu_Ord': ALL_FORMULA_DIRECTIONS['Father_Edu_Ord'],
    'Mother_Edu_Ord': ALL_FORMULA_DIRECTIONS['Mother_Edu_Ord'],
    'FatherOccNeed': ALL_FORMULA_DIRECTIONS['FatherOccNeed'],
    'MotherOccNeed': ALL_FORMULA_DIRECTIONS['MotherOccNeed'],
    'HousingPrecarity': ALL_FORMULA_DIRECTIONS['HousingPrecarity'],
}

XGB_PARAMS = dict(n_estimators=200, max_depth=4, learning_rate=0.1, eval_metric='logloss',
                  random_state=RANDOM_STATE)
RF_PARAMS = dict(n_estimators=200, max_depth=8, min_samples_leaf=2, random_state=RANDOM_STATE, n_jobs=-1)


def map_occupation(raw):
    """Survey free text -> one of the dropdown options, or None (unknown). Returns (category, matched)."""
    if pd.isna(raw) or not str(raw).strip():
        return None, True
    s = re.sub(r'\s+', ' ', str(raw).strip().lower())
    for category, keywords in OCCUPATION_RULES:
        if any(k in s for k in keywords):
            return category, True
    return None, False


def load_survey(csv_path):
    raw = pd.read_csv(csv_path)
    for col in ['Household/Family Members', 'Number of Siblings', 'Family Members Currently Studying']:
        raw[col] = raw[col].astype('string').str.strip().replace(DATE_FIXED_BRACKETS)

    def s(x):
        return None if pd.isna(x) else str(x).strip()

    holds = raw['Scholarship'].notna() & (raw['Scholarship'].astype('string').str.strip() != '')
    applicants, mapping, unmapped = [], {}, set()
    for (_, r), holds_scholarship in zip(raw.iterrows(), holds):
        cats = {}
        for who, col in (('father', "Father's Occupation"), ('mother', "Mother's Occupation")):
            cat, matched = map_occupation(r[col])
            cats[who] = cat
            key = (re.sub(r'\s+', ' ', str(r[col]).strip().lower()) if not pd.isna(r[col]) else '(blank)', cat)
            mapping[key] = mapping.get(key, 0) + 1
            if not matched:
                unmapped.add(str(r[col]).strip())
        applicants.append(dict(
            sex=s(r['Sex']), household_size=s(r['Household/Family Members']),
            siblings=s(r['Number of Siblings']), siblings_studying=s(r['Family Members Currently Studying']),
            father_education=s(r["Father's Highest Educational Attainment"]),
            mother_education=s(r["Mother's Highest Educational Attainment"]),
            father_occupation=cats['father'], mother_occupation=cats['mother'],
            monthly_income_bracket=s(r['Estimated Monthly Household Income']),
            housing_situation=s(r['Housing Situation']),
            gwa=None if pd.isna(r['GWA Numeric']) else float(r['GWA Numeric']),
            holds_other_scholarship=bool(holds_scholarship)))
    return applicants, mapping, unmapped


def print_mapping(mapping, unmapped):
    print('\nSurvey occupation -> dropdown option (count):')
    by_cat = {}
    for (raw, cat), n in mapping.items():
        by_cat.setdefault(cat or 'unknown (neutral)', []).append((raw, n))
    for cat in list(OCCUPATION_NEED) + ['unknown (neutral)']:
        items = sorted(by_cat.get(cat, []), key=lambda t: -t[1])
        total = sum(n for _, n in items)
        print(f"  {cat} [{total}]: " + '; '.join(f'{raw}({n})' for raw, n in items))
    if unmapped:
        print(f"  NOT MATCHED by any rule (treated as unknown): {sorted(unmapped)}")


def build_config(base_maps):
    """Encoding maps + feature contract for the new model. Education/income maps and the frozen
    normalisation bounds are carried over unchanged from the existing files."""
    maps = {k: base_maps[k] for k in ('education_map', 'income_bracket_map')}
    maps['housing_precarity_map'] = HOUSING_PRECARITY
    maps['normalization_bounds'] = base_maps['normalization_bounds']
    maps['occupation_need_map'] = OCCUPATION_NEED
    maps['occupation_need_unknown'] = OCCUPATION_NEED_UNKNOWN
    maps['total_score_weights'] = TOTAL_SCORE_WEIGHTS
    # housing_categories is kept for reference/display only - HousingPrecarity (below) replaced
    # the old one-hot-per-category encoding, so nothing builds feature columns from this anymore.
    housing_categories = list(HOUSING_PRECARITY)
    columns = ['Household_Size_Num', 'Siblings_Studying_Num',
               'Father_Edu_Ord', 'Mother_Edu_Ord', 'Income_Num', 'GWA Numeric',
               'Holds_Other_Scholarship', 'FatherOccNeed', 'MotherOccNeed', 'HousingPrecarity']
    contract = {'feature_columns': columns, 'numeric_columns': columns,
                'classifier_columns': columns + [CUTOFF_COLUMN],
                'housing_categories': housing_categories,
                'monotone_constraints': {**MONOTONE_DIRECTIONS, CUTOFF_COLUMN: -1}}
    return maps, contract


def constraints_for(columns):
    return tuple(MONOTONE_DIRECTIONS.get(c, 0) for c in columns)


def _build_models(cst, scale_pos_weight=None):
    """Shared by make_models() (the deployed model) and evaluate() (its CV variants), so a
    constraint or weighting change can't drift between what's evaluated and what's shipped."""
    xgb = XGBClassifier(monotone_constraints=cst if any(cst) else None,
                        scale_pos_weight=scale_pos_weight or 1, **XGB_PARAMS)
    clf = CalibratedClassifierCV(xgb, method='isotonic',
                                 cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE))
    reg = RandomForestRegressor(monotonic_cst=list(cst) if any(cst) else None, **RF_PARAMS)
    return clf, reg


def make_models(columns, scale_pos_weight=None):
    return _build_models(constraints_for(columns), scale_pos_weight)


def percentile_table(score):
    """Total Score at every percentile 0-100 - what cutoff_for_top_percent() interpolates."""
    return [float(np.percentile(score, p)) for p in range(101)]


def stack_for_bars(X, score, table, contract):
    """Every applicant repeated once per training bar, each copy carrying that bar's cutoff as
    the extra input and labelled eligible iff its Total Score reaches that cutoff. Returns the
    stacked rows, labels, and each row's applicant index (for grouped calibration folds)."""
    maps = {'total_score_percentiles': table}
    parts, labels = [], []
    for top in TRAIN_TOP_PERCENTS:
        cutoff = cutoff_for_top_percent(top, maps)
        parts.append(with_cutoff(X, cutoff, contract))
        labels.append((score >= cutoff).astype(int))
    groups = np.tile(np.arange(len(X)), len(TRAIN_TOP_PERCENTS))
    return pd.concat(parts, ignore_index=True), np.concatenate(labels), groups


def make_cutoff_classifier(contract, groups, X_stacked, y_stacked):
    cst = tuple(contract['monotone_constraints'].get(c, 0) for c in contract['classifier_columns'])
    xgb = XGBClassifier(monotone_constraints=cst, **XGB_PARAMS)
    folds = list(GroupKFold(n_splits=5).split(X_stacked, y_stacked, groups))
    return CalibratedClassifierCV(xgb, method='isotonic', cv=folds)


def evaluate_bars(X, score, contract):
    """Cross-validates the cutoff-aware classifier at every selectable bar (5-fold x 2 repeats):
    F1 / precision / recall per bar, plus a check that a stricter bar never admits an applicant
    a looser bar rejected (should always read 0)."""
    default_y = (score >= np.percentile(score, ELIGIBLE_PERCENTILE)).astype(int)
    rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=2, random_state=RANDOM_STATE)
    rows, violations, checks = [], 0, 0
    for tr, te in rcv.split(X, default_y):
        table = percentile_table(score[tr])
        SX, Sy, groups = stack_for_bars(X.iloc[tr], score[tr], table, contract)
        clf = make_cutoff_classifier(contract, groups, SX, Sy).fit(SX, Sy)
        preds = {}
        for top in SELECTABLE_TOP_PERCENTS:
            cutoff = cutoff_for_top_percent(top, {'total_score_percentiles': table})
            y_te = (score[te] >= cutoff).astype(int)
            preds[top] = clf.predict(with_cutoff(X.iloc[te], cutoff, contract))
            rows.append((top, f1_score(y_te, preds[top], zero_division=0),
                         precision_score(y_te, preds[top], zero_division=0),
                         recall_score(y_te, preds[top], zero_division=0)))
        for strict, loose in zip(SELECTABLE_TOP_PERCENTS, SELECTABLE_TOP_PERCENTS[1:]):
            violations += int((preds[strict] > preds[loose]).sum())
            checks += len(te)
    table = (pd.DataFrame(rows, columns=['top %', 'F1', 'precision', 'recall'])
             .groupby('top %').mean().round(4))
    return table, violations, checks


def audit_monotonicity(clf, reg, X_te, cols, directions, bounds):
    """For each feature in `directions`, moves it from its lowest to highest observed value
    (holding everything else fixed) and reports how often the classifier/regressor prediction
    moved the WRONG way - regardless of whether that feature was actually constrained during
    training. Used both to verify a constraint held and to measure how often an UNCONSTRAINED
    model gets a feature backwards on its own, which is what tells us whether that feature
    needs the constraint at all."""
    rows = {}
    for col, direction in directions.items():
        if col not in bounds:
            continue
        lo_val, hi_val = bounds[col]
        lo, hi = X_te.copy(), X_te.copy()
        lo[col], hi[col] = lo_val, hi_val
        r_lo, r_hi = reg.predict(lo[cols]), reg.predict(hi[cols])
        c_lo, c_hi = clf.predict(lo[cols]), clf.predict(hi[cols])
        wrong_reg = (r_hi < r_lo - 1e-9) if direction > 0 else (r_hi > r_lo + 1e-9)
        wrong_clf = (c_hi < c_lo) if direction > 0 else (c_hi > c_lo)
        rows[col] = (int(wrong_reg.sum() + wrong_clf.sum()), 2 * len(X_te))
    return rows


def evaluate(X, y, score, directions):
    """Repeated stratified 5-fold CV across three variants - with constraints (the shipped
    setup, no class-weight), unconstrained (to justify that the constraints are needed at
    all), and with constraints AND scale_pos_weight (to check what class-weighting costs or
    buys on top, particularly recall on the Eligible minority class / the false-negative rate)
    - plus, for EVERY formula-direction feature regardless of variant, how often each model
    gets that feature's direction backwards on held-out applicants. scale_pos_weight is
    computed from each fold's TRAINING labels only, never the held-out fold, so it can't leak
    test-set class balance into training."""
    rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=6, random_state=RANDOM_STATE)
    cols = list(X.columns)
    bounds = {c: (float(X[c].min()), float(X[c].max())) for c in ALL_FORMULA_DIRECTIONS if c in X}
    runs = {'with constraints': (True, False), 'unconstrained': (False, False),
           'with constraints + class-weight': (True, True)}
    out = {k: [] for k in runs}
    wrong = {k: {c: [0, 0] for c in bounds} for k in runs}
    for tr, te in rcv.split(X, y):
        spw = float((y[tr] == 0).sum()) / float((y[tr] == 1).sum())
        for run_label, (use_constraints, use_weight) in runs.items():
            cst = tuple(directions.get(c, 0) for c in cols) if use_constraints else tuple(0 for _ in cols)
            clf, reg = _build_models(cst, spw if use_weight else None)
            clf.fit(X.iloc[tr][cols], y[tr])
            reg.fit(X.iloc[tr][cols], score[tr])
            pred = reg.predict(X.iloc[te][cols])
            pred_y = clf.predict(X.iloc[te][cols])
            out[run_label].append((f1_score(y[te], pred_y),
                                   precision_score(y[te], pred_y, zero_division=0),
                                   recall_score(y[te], pred_y, zero_division=0),
                                   spearmanr(score[te], pred)[0], np.abs(score[te] - pred).mean()))
            for col, (bad, n) in audit_monotonicity(clf, reg, X.iloc[te], cols, ALL_FORMULA_DIRECTIONS, bounds).items():
                wrong[run_label][col][0] += bad
                wrong[run_label][col][1] += n
    table = pd.DataFrame({k: np.mean(v, axis=0) for k, v in out.items()},
                         index=['classifier F1', 'classifier precision', 'classifier recall',
                               'regressor Spearman', 'regressor MAE']).T.round(4)
    wrong_table = pd.DataFrame({
        run_label: {c: f'{bad}/{n} ({100*bad/n:.1f}%)' for c, (bad, n) in cols.items()}
        for run_label, cols in wrong.items()
    })
    return table, wrong_table


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv', help='survey CSV (EcoScholar_Combined_Dataset_300.csv)')
    ap.add_argument('--out', default=BACKEND_DIR, help='where to write the model files (default: backend/)')
    ap.add_argument('--evaluate-only', action='store_true', help='cross-validate and print; write nothing')
    args = ap.parse_args()

    with open(os.path.join(BACKEND_DIR, 'ecoscholar_encoding_maps.json'), encoding='utf-8') as f:
        base_maps = json.load(f)
    maps, contract = build_config(base_maps)

    applicants, mapping, unmapped = load_survey(args.csv)
    print_mapping(mapping, unmapped)

    # Blank survey fields (a GWA of 2 is treated as blank too) are filled with the training median;
    # the same medians are stored in the maps so serving fills blanks identically.
    X_raw = pd.concat([build_feature_vector(a, maps, contract) for a in applicants], ignore_index=True)
    maps['imputation_values'] = {c: float(v) for c, v in X_raw.median().items()}
    X = X_raw.fillna(maps['imputation_values'])
    print(f"Blank values imputed with the median: "
          f"{ {c: int(n) for c, n in X_raw.isna().sum().items() if n} }")
    score = np.array([estimate_total_score(a, maps) for a in applicants])
    cutoff = float(np.percentile(score, ELIGIBLE_PERCENTILE))
    y = (score >= cutoff).astype(int)
    maps['eligibility_cutoff'] = cutoff   # the default bar's cutoff, for reference
    print(f"\n{len(X)} applicants, {X.shape[1]} features, default Total Score cutoff "
          f"(P{ELIGIBLE_PERCENTILE}) = {cutoff:.3f}, eligible = {y.mean():.1%}")

    table, wrong_table = evaluate(X, y, score, MONOTONE_DIRECTIONS)
    print('\nCross-validation (5-fold x 6 repeats, held-out rows):')
    print(table.to_string())
    print(f'\nMonotonicity audit: moving each formula-direction feature from its lowest to '
          f'highest observed value, on held-out applicants - how often the prediction moved the '
          f'WRONG way. "with constraints" trains with MONOTONE_DIRECTIONS applied (should read '
          f'0/... for every constrained feature - a nonzero count there is a bug); '
          f'"unconstrained" trains with no constraints at all, which is what tells us whether an '
          f'unconstrained feature actually needs one:')
    print(wrong_table.to_string())

    bars, violations, checks = evaluate_bars(X, score, contract)
    print('\nCutoff-aware classifier, cross-validated at every selectable eligibility bar '
          '(5-fold x 2 repeats):')
    print(bars.to_string())
    print(f'Stricter bar admitted someone a looser bar rejected: {violations}/{checks} (must be 0)')

    if args.evaluate_only:
        return

    maps['total_score_percentiles'] = percentile_table(score)
    maps['eligibility_bar'] = {'default_top_percent': DEFAULT_TOP_PERCENT,
                               'selectable_top_percents': SELECTABLE_TOP_PERCENTS,
                               'trained_top_percents': TRAIN_TOP_PERCENTS}
    SX, Sy, groups = stack_for_bars(X, score, maps['total_score_percentiles'], contract)
    clf = make_cutoff_classifier(contract, groups, SX, Sy).fit(SX, Sy)
    _, reg = make_models(list(X.columns))
    reg.fit(X, score)
    # n_jobs=-1 helped training but is saved into the model, and would spawn a thread pool for every
    # single-applicant prediction (bad on a host with a fractional CPU share).
    reg.set_params(n_jobs=1)
    scaler = StandardScaler().fit(X)   # not used by score_applicant (tree models are scale-invariant); kept for the bundle

    os.makedirs(args.out, exist_ok=True)
    joblib.dump(clf, os.path.join(args.out, 'ecoscholar_classifier.joblib'))
    joblib.dump(reg, os.path.join(args.out, 'ecoscholar_regressor.joblib'))
    joblib.dump(scaler, os.path.join(args.out, 'ecoscholar_scaler.joblib'))
    with open(os.path.join(args.out, 'ecoscholar_feature_contract.json'), 'w', encoding='utf-8') as f:
        json.dump(contract, f, indent=2)
    with open(os.path.join(args.out, 'ecoscholar_encoding_maps.json'), 'w', encoding='utf-8') as f:
        json.dump(maps, f, indent=2)   # ASCII-escaped (₱), so it reads the same under any locale
    print(f'\nWrote 5 model files to {args.out}')

    # The serving code must reproduce the models' own predictions row for row.
    if os.path.abspath(args.out) == os.path.abspath(BACKEND_DIR):
        import ecoscholar_predict as ep
        default_cutoff = cutoff_for_top_percent(DEFAULT_TOP_PERCENT, maps)
        p_clf = clf.predict_proba(with_cutoff(X, default_cutoff, contract))[:, 1]
        p_reg = reg.predict(X)
        got = [ep.score_applicant(a) for a in applicants]
        assert np.allclose([g['eligibility_probability'] for g in got], p_clf, atol=1e-4), 'classifier mismatch'
        assert np.allclose([g['priority_score'] for g in got], p_reg, atol=1e-2), 'regressor mismatch'
        assert np.allclose([g['total_score_estimate'] for g in got], score, atol=1e-2), 'total score mismatch'
        print(f'Parity check passed: ecoscholar_predict reproduces the models on all {len(applicants)} rows.')
    else:
        print('(--out is not backend/, so the ecoscholar_predict parity check was skipped.)')


if __name__ == '__main__':
    main()
