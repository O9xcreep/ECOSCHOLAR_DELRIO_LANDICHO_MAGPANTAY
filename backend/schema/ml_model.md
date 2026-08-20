# Eligibility model (EcoScholar classifier + regressor, per Chapter III methodology)

Trained model bundle, shipped as separate files (not one pickle):

- **`ecoscholar_classifier.joblib`** (XGBoost) — answers "eligible or not?",
  plus a probability (`eligibility_probability`)
- **`ecoscholar_regressor.joblib`** (RandomForestRegressor) — predicts
  `priority_score`, a continuous ranking score used to break ties when there
  are more eligible applicants than accepted-applicant slots
- **`ecoscholar_scaler.joblib`** (StandardScaler) — applied before the
  **classifier only**; the regressor uses raw unscaled features
- **`ecoscholar_feature_contract.json`** — the exact ordered list of feature
  columns both models expect, plus the occupation/housing category lists
  used to build the one-hot columns
- **`ecoscholar_encoding_maps.json`** — `sex_map`, `education_map`,
  `income_bracket_map`, `housing_precarity_map`, the frozen normalization
  bounds used by `estimate_total_score()`, and `eligibility_cutoff`
  (~48.575) — informational reference only; eligibility is decided by the
  classifier, not this cutoff, same design as before
- **`ecoscholar_predict.py`** — loads the four files above and exposes
  `score_applicant(applicant: dict) -> dict`. Not modified by this app;
  treated as the trusted, self-contained scoring engine
- **`ecoscholar_integration.py`** — reference/example glue code the model
  was delivered with. **Not used** - it assumes a different Mongo schema
  (top-level `status`, boolean `mlEligible`, camelCase `auditTrail`) than
  ours (nested `application.status`, string `ml_status`, snake_case
  `audit_trail`). `app.py`'s own `build_feature_row()` / `score_with_model()`
  do the real integration against our actual schema instead.

## Two real schema gaps between our form and this model's training data

The model expects richer inputs than our form's dropdowns naturally
produce. Both are handled in `app.py`, not by changing the form:

1. **Income**: the model was trained on bracketed income
   (`"₱ 5,001 - ₱ 10,000"` → 7500), our form collects an exact number.
   `income_to_bracket()` in `app.py` buckets our raw number into the
   matching label. Boundaries must stay in sync with
   `ecoscholar_encoding_maps.json`'s `income_bracket_map`.
2. **Occupation**: the model groups free-text occupation into 11 categories
   (`_group_occupation()` in `ecoscholar_predict.py`, keyword/typo-based).
   Our form uses a constrained 7-option dropdown instead of free text - by
   product decision, several dropdown options (Skilled Trade,
   Office/Clerical, Professional, Unemployed) don't match any keyword and
   collapse into the model's generic `"Other"` category. This is an
   accepted precision tradeoff, not a bug - revisit only if the form ever
   switches occupation to free text.

Also: our form's `"Postgraduate"` (no space) is translated to the model's
`"Post Graduate"` (with a space) via `EDUCATION_LABEL_FIX` in `app.py`.

## `app.py` integration points

- **`build_feature_row(applicant)`** — maps one MongoDB applicant document
  into the flat dict `score_applicant()` expects (`sex`, `household_size`,
  `siblings`, `siblings_studying`, `father_education`, `mother_education`,
  `father_occupation`, `mother_occupation`, `monthly_income_bracket`,
  `housing_situation`, `gwa`, `holds_other_scholarship`). Returns
  `(row, False)` if the applicant predates the fields this model needs -
  same legacy-applicant gate as before, see below.
- **`score_with_model(row)`** — calls `score_applicant(row)` and returns
  `(priority_score, 'Eligible' | 'Not Eligible')`, the same two-value shape
  every call site already expects.
- **`build_score_breakdown(applicant)`** — a separate heuristic used only
  for the admin UI's progress bars and the plain-English rejection reason.
  Reads the applicant's raw stored fields directly (not `build_feature_row`'s
  output), so it's intentionally decoupled from whichever model is
  deployed - it is **not** the model's actual internal feature attribution
  either way.

## Known limitation: legacy applicants

Applicants who applied before an eligibility model existed don't have
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

## Discrimination safeguard still applies

LGU-custom fields (see Form Builder) are stored under `applicant.extra_fields`
and are never read by `build_feature_row()` - swapping the model doesn't
change this. No custom field can reach the classifier or regressor,
regardless of which model is deployed behind them.
