"""Pricing rules for tinyshop.

apply_discount() currently rounds down instead of half-up.
The test suite captures the expected behaviour.
"""


def apply_discount(total_cents: int, percent: int) -> int:
    """Apply percentage discount. Returns discounted price in cents.
    Rounding: half-up to nearest cent.
    """
    from decimal import Decimal, ROUND_HALF_UP
    discount = (Decimal(total_cents) * Decimal(percent) / Decimal(100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(Decimal(total_cents) - discount)
