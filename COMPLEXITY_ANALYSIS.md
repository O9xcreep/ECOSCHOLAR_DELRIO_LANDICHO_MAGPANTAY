# EcoScholar Algorithm Complexity

This document describes the time and space complexity of the applicant-ranking
and application-list operations in the current implementation. These estimates
cover algorithmic work; actual response time also depends on MongoDB indexes,
network latency, and the size of the trained machine-learning models.

## Variables

- **n**: applicant records returned for the requested cycle
- **k**: applicants with the required fields that can be scored (`k <= n`)
- **m**: database records examined by the computed-status filtering path
- **p**: number of applicants returned on one page
- **M**: cost of scoring one applicant with the fixed trained model

## Ranking applicants

The [`/api/rank-applicants` endpoint](backend/ml_scoring.py#L517) fetches
applicants, builds features and scores each applicant, sorts the scorable
applicants by score, and assigns rank numbers.

| Step | Time | Extra space |
|---|---:|---:|
| Build features and score each applicant | `O(n * M)` | `O(k)` for scored results |
| Sort the scorable applicants by score | `O(k log k)` | `O(k)` for the ranking data |
| Assign rank numbers | `O(k)` | `O(1)` beyond the result |
| **Overall, with the model fixed** | **`O(n log n)`** | **`O(n)`** |

`M` represents the cost of one applicant's feature preparation and model
inference. Since the deployed model and its feature count are fixed while the
number of applicants changes, `M` is treated as constant for this comparison.
The endpoint materializes the database results and ranked output in memory,
which is why its extra space is `O(n)`.

## Local synthetic benchmark

The in-memory ranking path was timed with synthetic applicants and the locally
loaded trained model. The benchmark included feature building, model scoring,
sorting, and rank assignment; it did not query MongoDB or measure network
latency. Times are medians, in milliseconds, from three full-ranking runs and
seven sort-only runs on Windows with Python 3.12.10.

| Applicants | Full ranking path (ms) | Sort and rank assignment only (ms) |
|---:|---:|---:|
| 50 | 2,218.85 | 0.0148 |
| 100 | 4,834.47 | 0.0280 |
| 200 | 10,961.76 | 0.0571 |
| 400 | 23,222.07 | 0.1226 |

Model scoring dominates the full-path timings at these input sizes, so the
results should not be used to infer the sorting complexity by themselves. The
Big-O analysis above comes from the code structure; these measurements are
illustrative, machine-specific performance observations, not a proof of
asymptotic complexity.

## Application filtering and search

The application list uses MongoDB to filter, count, sort, and paginate normal
queries. Its exact complexity depends on the query plan and available indexes;
there is no single bound that applies to every deployment. A query that must
scan the whole collection is `O(n)`, and sorting without a supporting index can
be `O(n log n)`. Search uses case-insensitive regular expressions on applicant
name and course, so its performance depends particularly on the data and
indexes.

For statuses that must be computed from document completeness, the backend
uses a Python fallback in [`get_applicants`](backend/applicants.py#L111). It
checks each of the `m` fetched records, sorts the matches, then serializes the
requested page:

- **Time:** `O(m log m)` in the worst case
- **Extra space:** `O(m)`
- Returning and rendering a page of `p` records takes `O(p)` work after the
  database query. The UI requests 20 records per page.

## Summary for a presentation

> With `n` applicants, EcoScholar scores each applicant and sorts the scorable
> results. Assuming a fixed trained model, ranking takes `O(n log n)` time and
> `O(n)` extra space. Computed-status filtering takes `O(m log m)` time in the
> worst case because it checks and sorts the matching records. Normal search
> and filtering are handled by MongoDB, so their performance depends on indexes
> and the database query plan.

## Code references

- [Applicant ranking](backend/ml_scoring.py#L517)
- [Applicant filtering and computed-status fallback](backend/applicants.py#L111)
- [Applications page requests and pagination](frontend/src/pages/admin/applications.jsx#L261)
