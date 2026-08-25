"""Spec2Ship patcher evaluation harness.

Compares patcher backends ("rules" vs "openai") on 2 grounded scenarios taken
from the real sample_workspace, using real functional checks rather than
keyword matching:

  1. discount-rounding-bug: a real, pre-existing bug in tinyshop/pricing.py.
     Ground truth = the two tests in tests/test_pricing.py, PLUS a stricter
     semantic probe (see below) that the given tests don't cover.
  2. add-health-endpoint: a feature request. Ground truth = a live GET
     /health call against the patched app returns 200 with a JSON body.

Why a semantic probe beyond the given tests: the first real run of this
harness caught the OpenAI patcher passing both given pytest cases while using
Python's `round()` (banker's/round-half-to-even) instead of true round-half-up
as the ticket asked for — `round(895.5) == 896` by coincidence, but
`round(894.5) == 894` where true half-up requires 895. A patch can satisfy
every test in a fixed suite and still not satisfy the stated requirement;
this harness checks the requirement directly, not just the given tests.

Usage (from backend/, with its venv active and .env holding OPENAI_API_KEY):
    ../.venv/Scripts/python.exe ../eval/run_eval.py
"""

from __future__ import annotations

DISCOUNT_TICKET = (
    "Fix the discount rounding bug in tinyshop/pricing.py. "
    "apply_discount() currently floors the result (int() truncates) instead of "
    "rounding half-up to the nearest cent, which fails tests/test_pricing.py. "
    "Rounding must be true round-half-up (e.g. 894.5 -> 895), not "
    "round-half-to-even."
)
DISCOUNT_SIGNALS = (
    "FAILED tests/test_pricing.py::test_discount_rounding_over_http - assert 895 == 896\n"
    "  # 995 cents with 10% discount => 895.5 => expected round-half-up to 896, got 895 (floored)"
)

HEALTH_TICKET = (
    "Add a /health endpoint to the tinyshop FastAPI app (tinyshop/main.py) for "
    "service monitoring and deployment checks. It should return HTTP 200 with a "
    "JSON body on GET /health."
)
HEALTH_SIGNALS = "No /health route currently exists on the tinyshop FastAPI app."

# Half-up rounding probe values NOT covered by tests/test_pricing.py, chosen
# specifically because Python's built-in round() (banker's rounding) disagrees
# with true half-up on them.
HALF_UP_PROBES = [
    # (total_cents, percent, expected_discounted_cents under true half-up)
    (1789, 50, 895),   # 894.5 -> half-up 895 (round() gives 894)
    (1791, 50, 896),   # 895.5 -> half-up 896 (round() gives 896 too, sanity check)
    (2683, 50, 1342),  # 1341.5 -> half-up 1342 (round() gives 1342, sanity check)
    (2681, 50, 1341),  # 1340.5 -> half-up 1341 (round() gives 1340)
]

CASES = [
    {
        "id": "discount-rounding-bug",
        "ticket": DISCOUNT_TICKET,
        "signals": DISCOUNT_SIGNALS,
        "check": "discount",
    },
    {
        "id": "add-health-endpoint",
        "ticket": HEALTH_TICKET,
        "signals": HEALTH_SIGNALS,
        "check": "health",
    },
]

PATCHER_MODES = ["rules", "openai"]
