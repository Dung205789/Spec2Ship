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
