"""Pricing rules for tinyshop.

apply_discount() currently rounds down instead of half-up.
The test suite captures the expected behaviour.
"""


def apply_discount(total_cents: int, percent: int) -> int:
    """Return discounted total in cents.

    Rules:
    - percent is an integer 0..100
    - rounding is **half-up** to the nearest cent

    Current implementation is wrong (rounds down).
    """
    percent = max(0, min(100, percent))

    # BUG: int() floors, so 895.5 becomes 895 (should be 896)
    return int(total_cents * (100 - percent) / 100)
