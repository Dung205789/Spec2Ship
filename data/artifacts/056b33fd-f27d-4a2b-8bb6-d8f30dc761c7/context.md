## KB docs (from workspace /docs)
### coding_standards.md
# Coding Standards

- Prefer small, focused functions.
- Validate inputs and clamp ranges where needed.
- For money calculations, be explicit about rounding rules.


### ticket_examples.md
# Ticket Examples

1. Fix failing tests in discount calculation.
2. Add a /health endpoint for smoke tests.


### coding_standards.md
# Coding Standards

- Prefer small, focused functions.
- Validate inputs and clamp ranges where needed.
- For money calculations, be explicit about rounding rules.


### ticket_examples.md
# Ticket Examples

1. Fix failing tests in discount calculation.
2. Add a /health endpoint for smoke tests.


## Code context (most relevant files)
**Keywords**: assertionerror, test_failure, tests, test_discount_rounding_over_http, recomputation, test_pricing, performance, unnecessary, structures, optimize, improve, passing, remove, failed, assert
**Files mentioned in failures**: tests/test_pricing.py

### Workspace structure
```
  README.md
  docs/
    coding_standards.md
    ticket_examples.md
  pyproject.toml
  tests/
    test_pricing.py
  tinyshop/
    __init__.py
    main.py
    pricing.py
```

### tests/test_pricing.py (score=54)
```python
from fastapi.testclient import TestClient

from tinyshop.main import app


client = TestClient(app)


def test_discount_rounding_over_http():
    # 999 cents with 10% discount => 899.1 => should round to 899
    r = client.post("/discount", json={"total_cents": 999, "percent": 10})
    assert r.status_code == 200
    assert r.json()["discounted_cents"] == 899

    # 995 cents with 10% => 895.5 => should round to 896
    r = client.post("/discount", json={"total_cents": 995, "percent": 10})
    assert r.status_code == 200
    assert r.json()["discounted_cents"] == 896


def test_percent_is_clamped():
    r = client.post("/discount", json={"total_cents": 1000, "percent": 150})
    assert r.status_code == 200
    assert r.json()["discounted_cents"] == 0
```

### pyproject.toml (score=5)
```toml
[project]
name = "tinyshop"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
  "fastapi==0.115.6",
  "uvicorn==0.30.6",
]

[project.optional-dependencies]
test = [
  "pytest==8.3.3",
]
```