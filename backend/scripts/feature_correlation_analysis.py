# -*- coding: utf-8 -*-
"""Expanded correlation analysis of the EcoScholar model's features, run on the real
applicant survey. Goes beyond a single Pearson matrix by using the coefficient that
matches each pair of variable types, which is what "expanded" usually means for this kind
of methodology write-up:

  - Pearson r + Spearman rho    two numeric/ordinal features (e.g. income vs GWA)
  - Point-biserial r            a numeric feature vs a binary one (sex, holds another
                                 scholarship, each housing dummy, Eligible) - numerically
                                 identical to Pearson r on a 0/1-coded variable, reported
                                 with its own significance test since it answers "does this
                                 feature move eligibility"
  - Cramer's V (bias-corrected, Bergsma 2013)
                                 two RAW categorical fields before encoding (sex, housing
                                 situation, occupation category, education level, income
                                 bracket) - shows association Pearson can't, e.g. whether
                                 housing situation clusters with income bracket
  - Variance Inflation Factor   multicollinearity among the exact features the deployed
                                 classifier/regressor are trained on together - two features
                                 can each correlate weakly with the outcome and still be
                                 redundant with each other, which pairwise correlation alone
                                 won't show

Uses the SAME cleaning, occupation mapping and feature encoding as scripts/train_model.py
and the currently deployed ecoscholar_encoding_maps.json / ecoscholar_feature_contract.json,
so this reflects the model actually in ecoscholar_classifier.joblib, not a re-derivation of it.

Needs matplotlib + seaborn (not in requirements.txt - this is a one-off analysis script, not
something the deployed app runs): pip install matplotlib seaborn

    python scripts/feature_correlation_analysis.py "<path to survey csv>" [--out-dir DIR]

Writes 3 heatmap PNGs + 3 CSVs (private: they carry per-applicant survey data, so the
default --out-dir sits next to the input CSV, not inside the repo) and prints the sorted
correlation tables.
"""
import argparse
import os
import sys
import warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ecoscholar_predict as ep  # noqa: E402 - loads the deployed model's maps/contract
import train_model as tm  # noqa: E402 - reuses load_survey()'s cleaning + occupation mapping

# Friendlier labels for the printed tables and heatmaps than the internal column names.
# NOTE: this list predates two model changes made after this analysis first ran (both directly
# motivated by it) - Siblings_Num was dropped as a feature (redundant with household size and
# siblings-studying, r=0.79-0.85, and not part of the Total Score formula), and the three
# Housing_* one-hot dummies were replaced with a single HousingPrecarity ordinal column. Rerun
# this script against the current model to see the correlations under the new feature set.
LABELS = {
    'Sex_Bin': 'Sex (Male=1)', 'Household_Size_Num': 'Household size',
    'Siblings_Studying_Num': 'Siblings studying',
    'Father_Edu_Ord': "Father's education", 'Mother_Edu_Ord': "Mother's education",
    'Income_Num': 'Monthly income', 'GWA Numeric': 'GWA',
    'Holds_Other_Scholarship': 'Holds other scholarship',
    'FatherOccNeed': "Father's occupation need", 'MotherOccNeed': "Mother's occupation need",
    'HousingPrecarity': 'Housing precarity',
    'Total_Score': 'Total Score', 'Eligible': 'Eligible',
}
# Raw (unencoded) categorical fields, for the Cramer's V table.
CATEGORICAL_FIELDS = ['sex', 'housing_situation', 'father_occupation', 'mother_occupation',
                      'father_education', 'mother_education', 'monthly_income_bracket']


def stars(p):
    return '***' if p < .001 else '**' if p < .01 else '*' if p < .05 else ''


def cramers_v(a, b):
    """Bias-corrected Cramer's V (Bergsma, 2013) - the uncorrected version is inflated on
    small samples, which matters here (n=300, some occupation categories have <10 rows)."""
    ct = pd.crosstab(a, b)
    n = ct.to_numpy().sum()
    chi2 = stats.chi2_contingency(ct, correction=False)[0]
    r, k = ct.shape
    if n <= 1 or r < 2 or k < 2:
        return np.nan
    phi2 = max(0, chi2 / n - (k - 1) * (r - 1) / (n - 1))
    rcorr = r - (r - 1) ** 2 / (n - 1)
    kcorr = k - (k - 1) ** 2 / (n - 1)
    denom = min(kcorr - 1, rcorr - 1)
    return np.sqrt(phi2 / denom) if denom > 0 else np.nan


def compute_vif(X):
    """VIF_i = 1 / (1 - R^2 of feature i regressed on every other feature). Avoids adding
    statsmodels as a dependency just for this - sklearn's LinearRegression gives the same R^2."""
    vifs = {}
    for col in X.columns:
        y = X[col].to_numpy()
        if np.std(y) < 1e-9:            # a dummy that's ~constant here (e.g. no Informal
            vifs[col] = np.nan           # settler rows) makes VIF meaningless, not just large
            continue
        others = X.drop(columns=[col]).to_numpy()
        r2 = LinearRegression().fit(others, y).score(others, y)
        vifs[col] = np.inf if r2 >= 1 - 1e-10 else 1 / (1 - r2)
    return pd.Series(vifs, name='VIF').sort_values(ascending=False)


def label(col):
    return LABELS.get(col, col)


def heatmap(matrix, title, path, fmt='.2f'):
    cols = [label(c) for c in matrix.columns]
    fig, ax = plt.subplots(figsize=(max(8, 0.55 * len(cols)), max(6, 0.5 * len(cols))))
    sns.heatmap(matrix.set_axis(cols, axis=0).set_axis(cols, axis=1), annot=True, fmt=fmt,
               cmap='RdBu_r', vmin=-1, vmax=1, center=0, square=True, linewidths=.4,
               annot_kws={'size': 7}, ax=ax, cbar_kws={'shrink': .8})
    ax.set_title(title, fontweight='bold')
    plt.xticks(rotation=45, ha='right', fontsize=8)
    plt.yticks(fontsize=8)
    plt.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def sorted_vs_target(df, feature_cols, target_col):
    rows = []
    for c in feature_cols:
        r, p = stats.pearsonr(df[c], df[target_col])
        rows.append({'feature': label(c), 'r': round(r, 3), 'p': round(p, 4), 'sig': stars(p)})
    return pd.DataFrame(rows).reindex(pd.DataFrame(rows).r.abs().sort_values(ascending=False).index)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv', help='survey CSV (EcoScholar_Combined_Dataset_300.csv)')
    ap.add_argument('--out-dir', default=None, help='default: <folder holding the csv>/correlation_analysis')
    args = ap.parse_args()

    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.csv)), 'correlation_analysis')
    os.makedirs(out_dir, exist_ok=True)

    applicants, _, _ = tm.load_survey(args.csv)
    X = pd.concat([ep.build_feature_vector(a) for a in applicants], ignore_index=True)
    X['Total_Score'] = [ep.estimate_total_score(a) for a in applicants]
    X['Eligible'] = (X['Total_Score'] >= ep.ELIGIBILITY_CUTOFF).astype(int)
    feature_cols = list(ep.FEATURE_COLUMNS)
    print(f'n = {len(X)} applicants, {len(feature_cols)} model features, '
          f'eligible = {X["Eligible"].mean():.1%} (cutoff {ep.ELIGIBILITY_CUTOFF:.2f})')

    # --- 1) Pearson + Spearman, every feature + Total_Score + Eligible ---
    all_cols = feature_cols + ['Total_Score', 'Eligible']
    pearson = X[all_cols].corr(method='pearson')
    spearman = X[all_cols].corr(method='spearman')
    pearson.to_csv(os.path.join(out_dir, 'pearson_matrix.csv'))
    spearman.to_csv(os.path.join(out_dir, 'spearman_matrix.csv'))
    heatmap(pearson, 'Pearson correlation - all model features + Total Score + Eligible',
           os.path.join(out_dir, 'pearson_heatmap.png'))
    heatmap(spearman, 'Spearman correlation - all model features + Total Score + Eligible',
           os.path.join(out_dir, 'spearman_heatmap.png'))

    # --- 2) Each feature vs Total_Score (Pearson r = the standard "feature vs continuous
    #    outcome" correlation) and vs Eligible (point-biserial r, same formula on a 0/1 target) ---
    vs_total = sorted_vs_target(X, feature_cols, 'Total_Score')
    vs_eligible = sorted_vs_target(X, feature_cols, 'Eligible')
    vs_total.to_csv(os.path.join(out_dir, 'correlation_vs_total_score.csv'), index=False)
    vs_eligible.to_csv(os.path.join(out_dir, 'correlation_vs_eligible.csv'), index=False)
    pd.set_option('display.width', 100)
    print('\n=== Pearson r vs Total Score (sorted by |r|) ===')
    print(vs_total.to_string(index=False))
    print('\n=== Point-biserial r vs Eligible (sorted by |r|) ===')
    print(vs_eligible.to_string(index=False))

    # --- 3) Cramer's V among the raw categorical fields, before any encoding ---
    raw = pd.DataFrame({f: [a.get(f) or '(blank)' for a in applicants] for f in CATEGORICAL_FIELDS})
    cv = pd.DataFrame(index=CATEGORICAL_FIELDS, columns=CATEGORICAL_FIELDS, dtype=float)
    for a in CATEGORICAL_FIELDS:
        for b in CATEGORICAL_FIELDS:
            cv.loc[a, b] = 1.0 if a == b else cramers_v(raw[a], raw[b])
    cv.to_csv(os.path.join(out_dir, 'cramers_v_matrix.csv'))
    heatmap(cv, "Cramer's V - raw categorical fields (before encoding)",
           os.path.join(out_dir, 'cramers_v_heatmap.png'))
    print("\n=== Cramer's V, raw categorical fields (0 = independent, 1 = perfectly associated) ===")
    print(cv.round(3).to_string())
    print('Category counts (small categories make Cramer\'s V noisy):')
    for f in CATEGORICAL_FIELDS:
        print(f'  {f}: {raw[f].value_counts().to_dict()}')

    # --- 4) Multicollinearity among the features actually trained together ---
    vif = compute_vif(X[feature_cols])
    print('\n=== Variance Inflation Factor (>5 moderate, >10 high multicollinearity) ===')
    print(vif.rename(index=label).round(2).to_string())

    print(f'\nWritten to {out_dir}: pearson_matrix.csv, spearman_matrix.csv, '
          f'correlation_vs_total_score.csv, correlation_vs_eligible.csv, cramers_v_matrix.csv, '
          f'pearson_heatmap.png, spearman_heatmap.png, cramers_v_heatmap.png')


if __name__ == '__main__':
    main()
