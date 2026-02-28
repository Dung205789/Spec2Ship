# tinyshop (sample workspace)

This workspace is intentionally small but real:

- FastAPI app in `tinyshop/main.py`
- Pricing logic in `tinyshop/pricing.py`
- Tests under `tests/` that hit the API over HTTP (FastAPI TestClient)

Starting state:

- One test fails because discount rounding is wrong (rounds down instead of half-up).

A successful Spec2Ship run should:

- show the failing baseline test in `baseline_pytest.log`
- propose a patch in `proposal.diff`
- pass all tests in `post_pytest.log`
- run a smoke request (see `smoke_test.log`)
