# Eligibility model (EcoScholar classifier + regressor, per Chapter III methodology)

Trained model bundle, shipped as separate files (not one pickle):

- **`ecoscholar_classifier.joblib`** (calibrated, cutoff-aware XGBoost) — answers
  "eligible or not?" at the LGU's eligibility bar, plus a probability
  (`eligibility_probability`). The bar is one extra input column, so a single
  model serves every bar; see "Adjustable eligibility bar" below
- **`ecoscholar_regressor.joblib`** (RandomForestRegressor) — predicts
  `priority_score`, a continuous ranking score used to break ties when there
  are more eligible applicants than accepted-applicant slots
- **`ecoscholar_scaler.joblib`** (StandardScaler) — applied before the
  **classifier only**; the regressor uses raw unscaled features
- **`ecoscholar_feature_contract.json`** — the exact ordered list of feature
  columns both models expect (11: sex, household size, siblings studying,
  both parents' education and occupation-need, income, GWA, holds-other-
  scholarship, and a single ordinal housing-precarity score - no raw sibling
  count, no per-occupation or per-housing-category dummies),
  `classifier_columns` (those 11 plus `EligibilityCutoff`, the classifier's
  input), and `monotone_constraints` (which features are monotone-constrained
  and in which direction, including the cutoff)
- **`ecoscholar_encoding_maps.json`** — `sex_map`, `education_map`,
  `income_bracket_map`, `housing_precarity_map`, `occupation_need_map`, the
  frozen normalization bounds and `total_score_weights` used by
  `estimate_total_score()`, `imputation_values` (training medians for blank
  fields), `total_score_percentiles` (the training survey's Total Score at
  every percentile 0-100, used to turn "top X% of need" into a cutoff),
  `eligibility_bar` (default, selectable and trained bars), and
  `eligibility_cutoff` (~47.8, the default bar's cutoff, for reference)
- **`ecoscholar_features.py`** — the feature encoding and the Total Score
  formula, shared by `ecoscholar_predict.py` (serving) and
  `scripts/train_model.py` (training) so the two can't drift apart
- **`ecoscholar_predict.py`** — loads the five files above and exposes
  `score_applicant(applicant: dict) -> dict`
- **`scripts/train_model.py`** — retrains and rewrites all five files from the
  survey CSV, cross-validates, and checks that `ecoscholar_predict` reproduces
  the trained models row for row. Run it from `backend/` with the path to the
  survey CSV (`--evaluate-only` to cross-validate without writing anything)
- **`notebooks/ecoscholar_ml_pipeline.ipynb`** — the same pipeline as
  `train_model.py` and `feature_correlation_analysis.py`, narrated end to end
  in one self-contained Colab/Jupyter notebook (load → clean → correlate →
  engineer features → audit and choose monotonic constraints by evidence →
  train → evaluate → explain what the trained classifier is actually doing).
  This is the thesis-facing artifact; `train_model.py` is the one the backend
  actually depends on to retrain. Uses lighter cross-validation (3-fold × 2
  repeats vs `train_model.py`'s 5×6) so it runs in a couple of minutes -
  same conclusions, less statistical precision. Opens in Colab directly; its
  first cell installs anything Colab doesn't already have, and its data cell
  prompts a file upload if the survey CSV isn't found locally.
- **`scripts/feature_correlation_analysis.py`** — expanded correlation
  analysis (Pearson, Spearman, point-biserial, Cramer's V, VIF) of the
  model's features against Total Score/eligibility, run on the real survey.
  Directly motivated two of `train_model.py`'s design choices below - it's
  not just a report, rerun it after any feature change
- **`ecoscholar_integration.py`** — reference/example glue code the model
  was delivered with. **Not used** - it assumes a different Mongo schema
  (top-level `status`, boolean `mlEligible`, camelCase `auditTrail`) than
  ours (nested `application.status`, string `ml_status`, snake_case
  `audit_trail`). `app.py`'s own `build_feature_row()` / `score_with_model()`
  do the real integration against our actual schema instead.

## Two real schema gaps between our form and this model's training data

The model expects richer inputs than our form's dropdowns naturally
produce. Both are handled without changing the form:

1. **Income**: the model was trained on bracketed income
   (`"₱ 5,001 - ₱ 10,000"` → 7500), our form collects an exact number.
   `income_to_bracket()` in `app.py` buckets our raw number into the
   matching label. Boundaries must stay in sync with
   `ecoscholar_encoding_maps.json`'s `income_bracket_map`.
2. **Occupation**: the survey collected free-text occupation, but our form
   uses a constrained 7-option dropdown. The model is trained on the
   dropdown's options only: `scripts/train_model.py` maps each survey answer
   onto one of the 7 (`OCCUPATION_RULES`, printed for review on every run),
   and each option is encoded as a **need score** from 0 (Professional) to 100
   (Unemployed, Deceased/Not Applicable), `occupation_need_map` in the
   encoding maps. A blank or unrecognised occupation scores the neutral 50.
   The Total Score the models learn includes an occupation term (5%, taken
   from the parents'-education weight), and both models are **monotone
   constrained**: a higher need score can never lower an applicant's
   eligibility or priority score. `tests/test_ml_occupation.py` enforces this.
   The need values, the 5% weight, "housewife = Unemployed" and "OFW =
   unknown" are study assumptions (see the `train_model.py` docstring) and
   change the Chapter III formula. The previous model used 11 free-text
   categories, ignored the difference between Unemployed and Professional, and
   sometimes scored unemployed/deceased-parent applicants lower.

Also: our form's `"Postgraduate"` (no space) is translated to the model's
`"Post Graduate"` (with a space) via `EDUCATION_LABEL_FIX` in `app.py`.

## Correlation-driven design choices

`scripts/feature_correlation_analysis.py`'s findings on the real survey led to two changes in
`scripts/train_model.py`, both verified by cross-validation before being kept:

1. **Raw sibling count (`Siblings_Num`) was dropped as a feature.** It's highly correlated with
   household size and siblings-studying (r=0.79-0.85) and isn't part of the Total Score formula
   at all (only household size and siblings-studying feed the burden term) - pure redundancy.
   Removing it didn't change accuracy (it couldn't: no label ever depended on it).
2. **Housing went from three one-hot dummies to a single ordinal `HousingPrecarity` column**
   (from `housing_precarity_map`: Owned=0, Rented=40, Living with relatives=60, Informal
   settler=100 - same map `estimate_total_score()` uses). Three independent dummies each only
   constrain themselves against an implicit "no dummy set" baseline; that does **not**
   transitively guarantee, say, Rented never outscores the more precarious Living with
   relatives - two dummies changing at once isn't covered by either one's own monotonic
   constraint. `tests/test_ml_monotonicity.py` caught exactly this on the old encoding. The
   single-column version also gives Informal settler a sensible score by extrapolation even
   though the training survey has zero such rows, where a one-hot dummy for it would have just
   read all-zero (indistinguishable from an unrecognised value).

**Monotonic constraints were extended past occupation, but only to features an audit showed
actually needed it** - not every feature whose direction the formula fixes. `train_model.py`'s
`evaluate()` moves each formula-direction feature from its lowest to highest observed value,
holding everything else fixed, and checks how often an *unconstrained* model's prediction moves
the wrong way anyway. That's a check on the model's conditional behaviour, not the same thing as
the feature's marginal correlation with Total Score:

- **GWA and income already came out at 0% wrong-direction even fully unconstrained**, despite
  GWA's marginal correlation with Total Score being weak and not statistically significant
  (r=-0.09, p=0.10) - exactly the kind of feature this file's approach would flag as risky by
  the correlation table alone. The audit showed that risk doesn't actually materialize, so
  neither is constrained (constraining every formula-direction feature was tried and cost real
  regressor accuracy - Spearman 0.96 → 0.93, MAE nearly doubled - for features that didn't need
  it).
- **Both parents' education (2.2-5.5% wrong-direction unconstrained), occupation (5.4-13.8%,
  the original bug this file exists to fix) and housing (0.7-2.8%) are constrained** - real,
  confirmed risk.
- Household size, siblings-studying, and holding another scholarship were audited too and left
  unconstrained: under 0.2%, not worth the accuracy cost.

See `MONOTONE_DIRECTIONS` / `ALL_FORMULA_DIRECTIONS` in `train_model.py` for the exact set and
the reasoning. Sex is the one feature with no formula-fixed direction at all, so it's excluded
from both.

## `app.py` integration points

- **`build_feature_row(applicant)`** — maps one MongoDB applicant document
  into the flat dict `score_applicant()` expects (`sex`, `household_size`,
  `siblings_studying`, `father_education`, `mother_education`,
  `father_occupation`, `mother_occupation`, `monthly_income_bracket`,
  `housing_situation`, `gwa`, `holds_other_scholarship`; `siblings` is still
  passed through but silently ignored - see the "correlation-driven design
  choices" section). Returns `(row, False)` if the applicant predates the
  fields this model needs - same legacy-applicant gate as before, see below.
- **`score_with_model(row, top_percent=None)`** — calls
  `score_applicant(row, top_percent)` and returns
  `(priority_score, 'Eligible' | 'Not Eligible')`. Every route passes the
  organization's own bar (`get_eligibility_top_percent`); omitting it means
  the trained default (top 30%).
- **`reapply_eligibility_bar(db, org_id)`** — run when an LGU changes its bar
  (`PUT /api/settings` with `eligibility_top_percent`): re-decides eligibility
  for every applicant already reviewed in the current cycle, rejects and
  notifies those who no longer meet the bar, then re-ranks against the
  applicant limit so newly eligible applicants are approved or waitlisted.
- **`build_score_breakdown(applicant)`** — a separate heuristic used only
  for the admin UI's progress bars and the plain-English rejection reason.
  Reads the applicant's raw stored fields directly (not `build_feature_row`'s
  output), so it's intentionally decoupled from whichever model is
  deployed - it is **not** the model's actual internal feature attribution
  either way.

## Adjustable eligibility bar

Two separate LGU settings decide who gets a scholarship:

- the **eligibility bar** (`eligibility_top_percent`, default 30) decides who
  qualifies at all: an applicant must be within the top X% of need, measured
  against the training survey's Total Score distribution (so it means the same
  thing every cycle and is not a quota of each cycle's applicants);
- the **applicant limit** (`max_accepted`) decides how many qualifying
  applicants are funded, by priority score; the rest are waitlisted.

The classifier handles any bar in `ELIGIBILITY_TOP_PERCENT_CHOICES` (top 10-60%)
without retraining. `train_model.py` repeats every survey applicant once per bar
in `TRAIN_TOP_PERCENTS` (top 5-60%), each copy carrying that bar's cutoff as the
`EligibilityCutoff` input and labelled against it. The model is constrained to be
non-increasing in the cutoff, so a stricter bar can never admit more applicants,
and it keeps the occupation, education and housing constraints at every bar. Its
isotonic calibration folds are grouped by applicant, so the same person never
lands on both sides of a fold. It has no class-weighting: across the stacked bars
the eligible share already runs from 5% to 60%, and in the notebook's comparison
class-weighting lowered precision without improving F1. Cross-validated F1 is
lower at very strict bars (fewer eligible examples to learn from), which is why
the admin UI warns at top 10%. `tests/test_ml_cutoff.py` pins these guarantees.

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
