# Plan

## Ticket
Fix discount rounding bug

apply_discount() uses int() which floors fractional cents.
Must use half-up rounding per spec.

Failing: 995 cents at 10% discount -> expected 896, got 895
Tests: test_discount_rounding_over_http, test_percent_is_clamped

## Signals
- [test_failure] 1 test(s) FAILED:   tests/test_pricing.py::test_discount_rounding_over_http - assert 895 == 896
- [test_failure] AssertionError: AssertionError

## Approach
- Identify root cause from failing test output
- Edit minimal files to fix the issue
- Re-run checks to verify fix
- Produce report

## Workspace profile
- name: tinyshop-python
- baseline: `python -m pytest -vv -ra`
- post: `python -m pytest -vv -ra`
