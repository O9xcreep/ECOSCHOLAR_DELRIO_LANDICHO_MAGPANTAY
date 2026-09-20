# -*- coding: utf-8 -*-
"""Step 1 of the expert-rating plan: turns the survey CSV into anonymous rating
workbooks for independent reviewers, plus a private key that joins their ratings
back to the full survey rows later. Needs openpyxl (pip install openpyxl).

  python scripts/prepare_rating_sheets.py "<survey.csv>" [--out-dir DIR] [--raters 3]

Workbooks are .xlsx, not CSV, on purpose: Excel turns a CSV's "2-5" back into a
date, which is how the Liliw rows were mangled in the first place.
"""
import argparse
import os
import random
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# Excel read "2-5", "5-10", ... as dates (2 May, 5 Oct, ...) and saved them back as "02-May", "05-Oct".
BRACKET_FIX = {
    '02-May': '2-5', '05-Oct': '5-10', '02-Mar': '2-3', '01-Feb': '1-2',
    '04-May': '4-5', '06-Aug': '6-8', '03-May': '3-5',
}
ALLOWED_BRACKETS = {
    'Household/Family Members': {'2-5', '5-10'},
    'Number of Siblings': {'None', '2-3', '4-5', '6-8'},
    'Family Members Currently Studying': {'1-2', '3-5', '6-8'},
}
GWA_COLUMN = 'GWA Numeric'

# Only what a reviewer needs to judge need and merit. Deliberately left out:
# sex, municipality, school, course, and current scholarship status (which would
# anchor the raters).
PROFILE_COLUMNS = [
    (GWA_COLUMN, 'GWA (%)', 10),
    ('Household/Family Members', 'Household size', 14),
    ('Number of Siblings', 'Number of siblings', 14),
    ('Family Members Currently Studying', 'Family members currently studying', 20),
    ("Father's Highest Educational Attainment", "Father's education", 18),
    ("Mother's Highest Educational Attainment", "Mother's education", 18),
    ("Father's Occupation", "Father's occupation", 26),
    ("Mother's Occupation", "Mother's occupation", 26),
    ('Estimated Monthly Household Income', 'Monthly household income', 24),
    ('Housing Situation', 'Housing', 22),
]
DECISIONS = ['Award', 'Waitlist', 'Not award']
INPUT_FILL = PatternFill('solid', fgColor='FFF2CC')
HEADER_FILL = PatternFill('solid', fgColor='D9D9D9')


def clean_text(value):
    if pd.isna(value):
        return None
    text = re.sub(r'\s+', ' ', str(value)).strip()
    if not text:
        return None
    return text.capitalize() if text.islower() else text


def clean_row(raw_row):
    """Returns (profile, problems); problems non-empty means the row can't be rated."""
    profile, problems = {}, []
    for source, header, _ in PROFILE_COLUMNS:
        value = clean_text(raw_row.get(source))
        if value is None:
            problems.append(f'missing {header}')
            continue
        if source == GWA_COLUMN:
            try:
                gwa = float(value)
            except ValueError:
                problems.append(f'GWA not a number: {value!r}')
                continue
            if not 60 <= gwa <= 100:
                problems.append(f'GWA implausible: {gwa:g}')
                continue
            value = int(gwa) if gwa == int(gwa) else gwa
        elif source in ALLOWED_BRACKETS:
            value = BRACKET_FIX.get(value, value)
            if value not in ALLOWED_BRACKETS[source]:
                problems.append(f'unrecognized {header}: {value!r}')
                continue
        profile[source] = value
    return profile, problems


def write_workbook(path, profiles, title, award_share, criteria):
    wb = Workbook()
    guide = wb.active
    guide.title = 'Instructions'
    guide.column_dimensions['A'].width = 110
    last_row = len(profiles) + 1
    decision_col = get_column_letter(len(PROFILE_COLUMNS) + 2)
    lines = [
        (title, Font(bold=True, size=14)),
        ('', None),
        ('Each row is a real college student (anonymous). Imagine you are on the selection committee for a '
         'need-and-merit college scholarship. For every row, decide whether you would award it.', None),
        (f'Assume the program can fund about {award_share:.0%} of applicants.', None),
        ('', None),
        ('Decision (dropdown): Award, Waitlist, or Not award.', None),
        ('Priority (dropdown, 1-5): 1 = weakest case for the scholarship, 5 = strongest, weighing financial need and '
         'academic merit together.', None),
        ('Notes: optional. Every row needs a Decision and a Priority.', None),
        ('', None),
        ('Rules: rate on your own; do not discuss ratings with other reviewers until everyone has finished; do not '
         'try to identify anyone; do not change a rating after you have moved on.', None),
        ('', None),
        *([('Program criteria', Font(bold=True)), (criteria, None)] if criteria else
          [('Program criteria (fill in before sending): [paste the LGU scholarship guidelines here]',
            Font(bold=True))]),
        ('', None),
        (f'=COUNTA(Ratings!{decision_col}2:{decision_col}{last_row})&" of {len(profiles)} decisions entered"',
         Font(bold=True)),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        cell = guide.cell(row=i, column=1, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        if font:
            cell.font = font
        if text.startswith('Program criteria (fill in'):
            cell.fill = INPUT_FILL

    sheet = wb.create_sheet('Ratings')
    headers = ['ID'] + [h for _, h, _ in PROFILE_COLUMNS] + ['Decision', 'Priority (1-5)', 'Notes (optional)']
    widths = [10] + [w for _, _, w in PROFILE_COLUMNS] + [14, 14, 30]
    for col, (header, width) in enumerate(zip(headers, widths), start=1):
        cell = sheet.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = INPUT_FILL if col > len(PROFILE_COLUMNS) + 1 else HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        sheet.column_dimensions[get_column_letter(col)].width = width
    for row, profile in enumerate(profiles, start=2):
        sheet.cell(row=row, column=1, value=profile['ID'])
        for col, (source, _, _) in enumerate(PROFILE_COLUMNS, start=2):
            cell = sheet.cell(row=row, column=col, value=profile[source])
            cell.number_format = '@'
        for col in range(len(PROFILE_COLUMNS) + 2, len(headers) + 1):
            sheet.cell(row=row, column=col).fill = INPUT_FILL
    sheet.freeze_panes = 'B2'

    decision_check = DataValidation(type='list', formula1='"' + ','.join(DECISIONS) + '"', allow_blank=True,
                                    showErrorMessage=True, errorTitle='Decision',
                                    error='Choose Award, Waitlist, or Not award.')
    priority_check = DataValidation(type='list', formula1='"1,2,3,4,5"', allow_blank=True,
                                    showErrorMessage=True, errorTitle='Priority', error='Choose 1, 2, 3, 4, or 5.')
    decision_check.add(f'{decision_col}2:{decision_col}{last_row}')
    priority_col = get_column_letter(len(PROFILE_COLUMNS) + 3)
    priority_check.add(f'{priority_col}2:{priority_col}{last_row}')
    sheet.add_data_validation(decision_check)
    sheet.add_data_validation(priority_check)
    wb.active = 1
    wb.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('csv_path')
    parser.add_argument('--out-dir', default=None, help='default: EcoScholar_rating_sheets next to the CSV')
    parser.add_argument('--raters', type=int, default=3)
    parser.add_argument('--calibration', type=int, default=10, help='profiles set aside for the group warm-up')
    parser.add_argument('--award-share', type=float, default=0.33, help='shown to raters as the fundable share')
    parser.add_argument('--criteria-file', default=None,
                        help='UTF-8 text file with the program criteria to show reviewers')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.csv_path)), 'EcoScholar_rating_sheets')
    rater_dir = os.path.join(out_dir, 'for_raters')
    private_dir = os.path.join(out_dir, 'PRIVATE_do_not_share')
    os.makedirs(rater_dir, exist_ok=True)
    os.makedirs(private_dir, exist_ok=True)
    criteria = None
    if args.criteria_file:
        with open(args.criteria_file, encoding='utf-8') as f:
            criteria = f.read().strip() or None

    raw = pd.read_csv(args.csv_path, dtype=str)
    kept, excluded = [], []
    for _, raw_row in raw.iterrows():
        profile, problems = clean_row(raw_row)
        ref = {'Source File': raw_row.get('Source File'), 'Source Row': raw_row.get('Source Row'),
               'Municipality': raw_row.get('Municipality')}
        if problems:
            excluded.append({**ref, 'Reason': '; '.join(problems)})
        else:
            kept.append({'profile': profile, 'raw': raw_row.to_dict()})

    random.Random(args.seed).shuffle(kept)
    calibration, rated = kept[:args.calibration], kept[args.calibration:]
    key_rows = []
    for kind, group, prefix, width in (('calibration', calibration, 'CAL', 2), ('rated', rated, 'P', 3)):
        for i, item in enumerate(group, start=1):
            item['profile']['ID'] = f'{prefix}{i:0{width}d}'
            key_rows.append({'ID': item['profile']['ID'], 'Kind': kind, **item['raw'], **item['profile']})

    write_workbook(os.path.join(rater_dir, 'calibration_set.xlsx'), [c['profile'] for c in calibration],
                   'EcoScholar calibration set (practice - discuss these together)', args.award_share, criteria)
    for i in range(args.raters):
        order = [r['profile'] for r in rated]
        random.Random(args.seed + 1 + i).shuffle(order)
        letter = chr(ord('A') + i)
        write_workbook(os.path.join(rater_dir, f'rater_{letter}.xlsx'), order,
                       f'EcoScholar profile rating - reviewer {letter}', args.award_share, criteria)

    pd.DataFrame(key_rows).to_csv(os.path.join(private_dir, 'id_key.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(excluded, columns=['Source File', 'Source Row', 'Municipality', 'Reason']).to_csv(
        os.path.join(private_dir, 'excluded_rows.csv'), index=False, encoding='utf-8-sig')

    print(f'{len(raw)} survey rows -> {len(kept)} usable, {len(excluded)} excluded')
    for item in excluded:
        print(f"  excluded {item['Municipality']} row {item['Source Row']}: {item['Reason']}")
    print(f'{len(calibration)} calibration profiles, {len(rated)} profiles to rate x {args.raters} reviewers')
    print(f'Written to {out_dir}')


if __name__ == '__main__':
    main()
