# Fix discount calculation rounding

Fixes 3 bugs:
1. apply_discount: uses Python banker rounding → replaced with Decimal ROUND_HALF_UP
2. apply_tax: uses floor division (//) → replaced with Decimal ROUND_HALF_UP
3. calculate_final_price: tax was calculated on subtotal → now calculated on after_discount
