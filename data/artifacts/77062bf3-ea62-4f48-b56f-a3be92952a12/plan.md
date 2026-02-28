# Plan

## Ticket
Fix all failing tests. Analyze test output and apply minimal patch. Do not modify tests.

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
