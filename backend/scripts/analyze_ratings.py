# -*- coding: utf-8 -*-
"""Steps 4-6 of the expert-rating plan: reads the completed rater workbooks
(made by prepare_rating_sheets.py), reports how much the reviewers agree,
builds consensus labels with a held-out test split, and scores the current
formula and deployed model against those labels.

  python scripts/analyze_ratings.py "<folder with completed rater_*.xlsx>" [--key PATH] [--out-dir DIR]

Writes labels.csv (private: it carries the full survey rows) and
agreement_report.txt into --out-dir.
"""
import argparse
import glob
import itertools
import os
import re
import sys

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score, roc_auc_score
from sklearn.model_selection import train_test_split

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ['Award', 'Waitlist', 'Not award']
DECISION_LOOKUP = {c.lower(): c for c in CATEGORIES}


def read_rater(path):
    rows = list(load_workbook(path, data_only=True)['Ratings'].values)
    header = list(rows[0])
    id_col, decision_col, priority_col = (header.index(h) for h in ('ID', 'Decision', 'Priority (1-5)'))
    records, problems = {}, []
    for row in rows[1:]:
        rating_id, decision, priority = row[id_col], row[decision_col], row[priority_col]
        clean_decision = None
        if decision is not None and str(decision).strip():
            clean_decision = DECISION_LOOKUP.get(str(decision).strip().lower())
            if clean_decision is None:
                problems.append(f'{rating_id}: unknown Decision {decision!r}')
        clean_priority = None
        if priority is not None and str(priority).strip():
            try:
                clean_priority = int(float(priority))
            except ValueError:
                pass
            if clean_priority not in (1, 2, 3, 4, 5):
                problems.append(f'{rating_id}: Priority must be 1-5, got {priority!r}')
                clean_priority = None
        records[rating_id] = {'Decision': clean_decision, 'Priority': clean_priority}
    return pd.DataFrame.from_dict(records, orient='index'), problems


def fleiss_kappa(counts):
    n_raters = counts[0].sum()
    category_share = counts.sum(axis=0) / counts.sum()
    per_item = ((counts ** 2).sum(axis=1) - n_raters) / (n_raters * (n_raters - 1))
    expected = (category_share ** 2).sum()
    if expected == 1:
        return float('nan')
    return (per_item.mean() - expected) / (1 - expected)


def verdict(kappa):
    if np.isnan(kappa):
        return 'undefined (everyone chose the same answer)'
    if kappa >= 0.6:
        return 'good (>= 0.6)'
    if kappa >= 0.4:
        return 'usable (0.4-0.6)'
    return 'too noisy to train on (< 0.4)'


def applicant_from_key_row(row):
    sys.path.insert(0, SCRIPTS_DIR)
    from train_model import map_occupation  # same free-text -> dropdown-category rules used at training time
    father_occ, _ = map_occupation(row["Father's Occupation"])
    mother_occ, _ = map_occupation(row["Mother's Occupation"])
    return {
        'sex': row['Sex'], 'household_size': row['Household/Family Members'],
        'siblings': row['Number of Siblings'], 'siblings_studying': row['Family Members Currently Studying'],
        'father_education': row["Father's Highest Educational Attainment"],
        'mother_education': row["Mother's Highest Educational Attainment"],
        # Raw survey text ("Tricycle driver", "OFW", ...) has to be mapped onto one of the 7
        # dropdown categories first - occupation_need() only recognizes the mapped categories,
        # so passing raw text through unmapped silently scored every applicant's occupation
        # term as the neutral default (50) instead of their actual need score.
        'father_occupation': father_occ, 'mother_occupation': mother_occ,
        'monthly_income_bracket': row['Estimated Monthly Household Income'],
        'housing_situation': row['Housing Situation'], 'gwa': float(row['GWA Numeric']),
        'holds_other_scholarship': False,  # reviewers never saw scholar status, so compare like for like
    }


def baseline_scores(labeled):
    sys.path.insert(0, BACKEND_DIR)
    import ecoscholar_predict as ep
    formula, model = [], []
    for _, row in labeled.iterrows():
        applicant = applicant_from_key_row(row)
        formula.append(ep.estimate_total_score(applicant))
        model.append(ep.score_applicant(applicant)['priority_score'])
    return {'Formula (Chapter III total score)': np.array(formula), 'Deployed model (priority score)': np.array(model)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('sheets_dir', help='folder holding the completed rater_*.xlsx files')
    parser.add_argument('--key', default=None, help='id_key.csv (default: PRIVATE_do_not_share/ next to for_raters/)')
    parser.add_argument('--out-dir', default=None, help='default: <sheets_dir>/analysis')
    parser.add_argument('--test-share', type=float, default=0.25, help='share of profiles held out for testing')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    key_path = args.key or os.path.join(os.path.dirname(os.path.abspath(args.sheets_dir)),
                                        'PRIVATE_do_not_share', 'id_key.csv')
    if not os.path.exists(key_path):
        sys.exit(f'Cannot find the private key at {key_path} - pass --key.')
    out_dir = args.out_dir or os.path.join(args.sheets_dir, 'analysis')
    os.makedirs(out_dir, exist_ok=True)

    paths = sorted(p for p in glob.glob(os.path.join(args.sheets_dir, 'rater_*.xlsx')))
    if len(paths) < 2:
        sys.exit(f'Need at least 2 completed rater_*.xlsx files in {args.sheets_dir}.')
    raters = {}
    for path in paths:
        name = re.search(r'rater_(.+)\.xlsx$', os.path.basename(path)).group(1)
        frame, problems = read_rater(path)
        if problems:
            sys.exit(f'Rater {name} has invalid entries - fix these and re-run:\n  ' + '\n  '.join(problems[:20]))
        raters[name] = frame
    names = list(raters)
    first_ids = set(raters[names[0]].index)
    for name in names[1:]:
        if set(raters[name].index) != first_ids:
            sys.exit(f'Rater {name} does not contain the same profile IDs as rater {names[0]}.')

    decisions = pd.DataFrame({n: raters[n]['Decision'] for n in names})
    priorities = pd.DataFrame({n: raters[n]['Priority'] for n in names})
    complete = decisions.notna().all(axis=1) & priorities.notna().all(axis=1)
    report = [f'Reviewers: {", ".join(names)}  |  profiles: {len(decisions)}  |  fully rated by everyone: {complete.sum()}']
    for n in names:
        missing = int(decisions[n].isna().sum() + priorities[n].isna().sum())
        if missing:
            report.append(f'  reviewer {n}: {missing} blank Decision/Priority cells')
    if complete.sum() < 30:
        sys.exit('\n'.join(report) + '\nToo few fully rated profiles to analyze.')
    decisions, priorities = decisions[complete], priorities[complete].astype(int)
    n_raters = len(names)
    is_award = decisions == 'Award'

    three_way = pd.DataFrame({c: (decisions == c).sum(axis=1) for c in CATEGORIES}).values
    binary = np.column_stack([is_award.sum(axis=1), n_raters - is_award.sum(axis=1)])
    kappa_3, kappa_2 = fleiss_kappa(three_way), fleiss_kappa(binary)
    report += ['', 'AGREEMENT (ceiling for any model)',
               f'  Fleiss kappa, Award / Waitlist / Not award : {kappa_3:.2f}  -> {verdict(kappa_3)}',
               f'  Fleiss kappa, Award vs everything else     : {kappa_2:.2f}  -> {verdict(kappa_2)}']
    for a, b in itertools.combinations(names, 2):
        report.append(f'  {a} vs {b}: Cohen kappa (Award) {cohen_kappa_score(is_award[a], is_award[b]):.2f}'
                      f' | Spearman (priority) {spearmanr(priorities[a], priorities[b])[0]:.2f}')
    others_corr = [spearmanr(priorities[n], priorities.drop(columns=n).mean(axis=1))[0] for n in names]
    report.append(f'  each reviewer vs the mean of the others (priority Spearman): {np.mean(others_corr):.2f} average')

    votes = is_award.sum(axis=1)
    labels = pd.DataFrame({
        'award_votes': votes, 'n_raters': n_raters, 'award_share': (votes / n_raters).round(3),
        'consensus_award': votes * 2 > n_raters,
        'priority_mean': priorities.mean(axis=1).round(2), 'priority_sd': priorities.std(axis=1).round(2),
        'contested': (votes > 0) & (votes < n_raters),
    })
    labels['split'] = 'train'
    _, test_ids = train_test_split(labels.index, test_size=args.test_share, random_state=args.seed,
                                   stratify=labels['consensus_award'])
    labels.loc[test_ids, 'split'] = 'test'
    report += ['', 'CONSENSUS LABELS (Award = more than half of reviewers; Waitlist counts as not Award)',
               f'  Award: {int(labels.consensus_award.sum())} of {len(labels)} ({labels.consensus_award.mean():.0%})'
               f'  |  contested (reviewers split): {int(labels.contested.sum())}'
               f'  |  held-out test set: {len(test_ids)} profiles']

    key = pd.read_csv(key_path, dtype=str)
    key = key[key['Kind'] == 'rated'].set_index('ID')
    unknown = set(labels.index) - set(key.index)
    if unknown:
        sys.exit(f'{len(unknown)} rated IDs are not in the key, e.g. {sorted(unknown)[:3]}.')
    labeled = key.join(labels, how='inner')

    report += ['', f'CURRENT SCORERS VS THE EXPERTS (all {len(labeled)} profiles; these were not trained on the ratings)',
               f'  {"scorer":38s} {"Spearman vs priority":>21s} {"AUC vs Award":>13s} {"precision@K":>12s}']
    k = int(labeled['consensus_award'].sum())
    y = labeled['consensus_award'].astype(int).values
    for scorer, scores in baseline_scores(labeled).items():
        top_k = np.argsort(-scores)[:k]
        report.append(f'  {scorer:38s} {spearmanr(scores, labeled["priority_mean"])[0]:21.2f}'
                      f' {roc_auc_score(y, scores):13.2f} {y[top_k].mean():12.2f}')
    report.append(f'  (precision@K: of the top {k} by score, the share the reviewers also chose to Award)')
    report.append(f'  A model trained on these labels is only worth shipping if it beats these rows on the test split.')

    labeled.reset_index().to_csv(os.path.join(out_dir, 'labels.csv'), index=False, encoding='utf-8-sig')
    with open(os.path.join(out_dir, 'agreement_report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(report))
    print(f'\nWritten to {out_dir}')


if __name__ == '__main__':
    main()
