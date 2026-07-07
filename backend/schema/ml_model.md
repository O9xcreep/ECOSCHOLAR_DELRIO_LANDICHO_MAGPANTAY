# Eligibility model (`model_combined.pkl`)

Trained in Colab, bundled as a dict with these keys:

- **`classifier`** (XGBoost, uncalibrated) — answers "eligible or not?"
- **`regressor`** (RandomForestRegressor, `best_overall_name`) — predicts a
  continuous `total_score` used for ranking applicants against each other
- **`scaler`** (StandardScaler) — applied before the **classifier only**; the
  regressor uses raw unscaled features
- **`regressor_score_cutoff`** (58.985) — informational reference only.
  Eligibility is decided by the classifier, not this cutoff (per project
  decision — the two can disagree on a given applicant, and that's fine;
  the UI just shows both numbers)
- **`features`** — the exact ordered list of 27 column names the models
  expect (see below)
- **`education_map`** — `{'None': 0, 'Elementary': 1, 'High School': 2, 'Vocational': 3, 'College': 4, 'Postgraduate': 5}`
- **`occupation_categories`** — `['Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade', 'Office/Clerical', 'Professional', 'Deceased/Not Applicable']`
- **`housing_situations`** — `['Owned', 'Rented', 'Living with relatives', 'Informal settler']`

## Feature order (must match exactly - `app.py`'s `build_feature_row()` builds
this dynamically from `features`, so retraining with reordered columns is safe)

```
0  gpa                                  9  father_occ_Informal/Vendor      18 mother_occ_Laborer/Driver
1  sex_encoded                          10 father_occ_Laborer/Driver       19 mother_occ_Office/Clerical
2  family_size                          11 father_occ_Office/Clerical      20 mother_occ_Professional
3  num_siblings                         12 father_occ_Professional         21 mother_occ_Skilled Trade
4  num_siblings_studying                13 father_occ_Skilled Trade        22 mother_occ_Unemployed
5  father_education_level               14 father_occ_Unemployed           23 housing_Informal settler
6  mother_education_level               15 mother_occ_Deceased/Not Applic. 24 housing_Living with relatives
7  monthly_income                       16 mother_occ_Informal/Vendor      25 housing_Owned
8  has_other_scholarship                17 mother_occ_Laborer/Driver       26 housing_Rented
```

Occupation/housing one-hot columns are full (no dropped reference category)
and alphabetically ordered - matches pandas `get_dummies` default behavior.

## Encodings not in the bundle (confirmed with the model author)

- **`sex_encoded`**: `1` if `sex == 'Male'`, `0` otherwise (including
  `'Female'`). Not saved in the bundle - if the model is ever retrained,
  reconfirm this convention hasn't changed.
- **GPA scale**: 75-99 (percentage), *not* the Philippine 1.00-5.00 GWA
  scale used by applicants who applied before this model existed.

## Known limitation: legacy applicants

Applicants who applied before this model was wired in don't have
`monthly_income`, `housing_situation`, `num_siblings`, `num_siblings_studying`,
`father_education`, or `mother_education` on their record, and their `gpa` is
on the old 1.00-5.00 scale instead of 75-99. `build_feature_row()` detects
this (missing required fields) and returns `ok=False` - `score_applicant`
returns a 409 for those, and `rank_applicants` silently excludes them from
the ranked list rather than guessing at converted/defaulted values for a
system that gates real financial aid.

The admin Reports page's GWA distribution chart (`frontend/.../reports.jsx`)
normalizes both scales to percentage for display purposes only, approximating
legacy 1.00-5.00 values via the same band mapping as `ocr.py`'s `find_gpa`.
This approximation is fine for a chart but must never feed the eligibility
model - only `build_feature_row()`'s hard 409/exclusion behavior above governs
actual scoring.
