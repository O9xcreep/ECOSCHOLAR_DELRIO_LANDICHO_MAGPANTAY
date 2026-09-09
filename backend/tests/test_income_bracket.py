# -*- coding: utf-8 -*-
"""income_to_bracket() - the eligibility model was trained on bracketed income,
not an exact peso figure, so this is the one place a raw number actually
matters to scoring. The application form now collects a range directly rather
than a typed number (frontend/src/pages/student/ApplicationForm.jsx's
INCOME_RANGES) - these tests pin down that each range's representative value
still lands in the exact bracket its label promises, so that UI change can
never silently drift from what the model expects."""
import app as app_module

# Mirrors frontend/src/pages/student/ApplicationForm.jsx's INCOME_RANGES - keep
# these two lists in sync if either ever changes.
FORM_INCOME_RANGES = [
    ('Below ₱5,000', 2500, 'Below ₱ 5,000'),
    ('₱5,001 - ₱10,000', 7500, '₱ 5,001 - ₱ 10,000'),
    ('₱10,000 - ₱15,000', 12500, '₱ 10,000 - ₱ 15,000'),
    ('₱15,000 - ₱20,000', 17500, '₱ 15,000 - ₱ 20,000'),
    ('₱20,000 and above', 25000, '₱ 20,000 Above'),
]


class TestFormIncomeRangesMatchModelBrackets:
    def test_each_representative_value_lands_in_the_promised_bracket(self):
        for form_label, representative_value, expected_bracket in FORM_INCOME_RANGES:
            actual = app_module.income_to_bracket(representative_value)
            assert actual == expected_bracket, (
                f'Form option "{form_label}" (value={representative_value}) mapped to '
                f'bracket "{actual}", expected "{expected_bracket}"'
            )

    def test_representative_values_are_not_on_a_bracket_boundary(self):
        """Each value should classify the same way regardless of off-by-one
        boundary semantics - i.e. comfortably inside its bracket, not right on
        the edge where a future boundary tweak could silently reclassify it."""
        boundaries = {5000, 10000, 15000, 20000}
        for _, representative_value, _ in FORM_INCOME_RANGES:
            assert representative_value not in boundaries
