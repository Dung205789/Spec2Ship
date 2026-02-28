#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Reset tinyshop back to the known-broken state.
# This keeps the end-to-end workflow reproducible.

cat > "$ROOT/sample_workspace/tinyshop/pricing.py" <<'PY'
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
PY

# Remove /health if it was added in a previous run
MAIN="$ROOT/sample_workspace/tinyshop/main.py"
if grep -q "@app.get(\"/health\")" "$MAIN"; then
  python - <<'PY'
from pathlib import Path
p = Path("sample_workspace/tinyshop/main.py")
text = p.read_text(encoding="utf-8")
# keep everything up to the discount endpoint
marker = "@app.post(\"/discount\")"
idx = text.find(marker)
if idx != -1:
    # Keep header + discount endpoint only
    head = text[:idx]
    tail = text[idx:]
    # Remove any health endpoint blocks in between (simple heuristic)
    lines = (head + tail).splitlines(True)
    out = []
    skip = False
    for line in lines:
        if line.strip().startswith("@app.get(\"/health\")"):
            skip = True
        if not skip:
            out.append(line)
        if skip and line.startswith("@app.post(\"/discount\")"):
            skip = False
            out.append(line)
    p.write_text("".join(out), encoding="utf-8")
PY
fi

echo "Reset sample workspace: pricing bug restored"
