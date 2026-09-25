// Shared by the application form and the registration form on the login page.
// The eligibility model was trained on bracketed income (see income_to_bracket()
// in backend/helpers.py), not an exact peso figure - it collapses whatever number this form
// submits into one of these same five brackets before the model ever sees it, so
// asking for a range directly loses the model nothing. `value` is a representative
// figure comfortably inside each bracket's boundaries (never on an edge), stored
// as monthly_income exactly like a typed number always was - every other feature
// that reads it (income_to_bracket, the admin score-breakdown heuristic, exports)
// keeps working unchanged.
export const INCOME_RANGES = [
  { label: 'Below ₱5,000', value: 2500 },
  { label: '₱5,001 - ₱10,000', value: 7500 },
  { label: '₱10,000 - ₱15,000', value: 12500 },
  { label: '₱15,000 - ₱20,000', value: 17500 },
  { label: '₱20,000 and above', value: 25000 },
]
