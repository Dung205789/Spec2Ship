"""Pricing rules for tinyshop.

apply_discount() currently rounds down instead of half-up.
The test suite captures the expected behaviour.
"""


def apply_discount(total_cents: int, percent: int) -> int:
    """Apply percentage discount. Returns discounted price in cents.
    Rounding: half-up to nearest cent.
    Percent is clamped to 0..100.
    """
    percent = max(0, min(100, percent))
    from decimal import Decimal, ROUND_HALF_UP
    discounted_total = (Decimal(total_cents) * (Decimal(100) - Decimal(percent)) / Decimal(100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(discounted_total)
