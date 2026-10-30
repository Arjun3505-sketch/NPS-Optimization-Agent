"""Smoke tests for the recommender and API. Needs data/processed candidate tables + income paths.
Usage: PYTHONPATH=. python tests/test_recommend.py"""
from fastapi.testclient import TestClient

from src.api.main import app
from src.policy.recommend import recommend

client = TestClient(app)


def test_budget_monotone_and_valid():
    lo = recommend(tier="high", epsilon=0.02, n_trials=40)
    hi = recommend(tier="high", epsilon=0.15, n_trials=40)
    assert lo["params"]["equity_start"] <= hi["params"]["equity_start"]
    for g in lo["glide_path"]:
        assert abs(g["equity"] + g["corporate_debt"] + g["govt_securities"] - 1) < 1e-9
    assert len(lo["glide_path"]) == 36 and lo["glide_path"][-1]["age"] == 60


def test_employment_type_resolves_and_matches_tier():
    a = recommend(employment_type="self_employed", epsilon=0.05, n_trials=40)
    assert a["tier"] == "high"


def test_api_ok_and_errors():
    assert client.get("/health").json() == {"status": "ok"}
    r = client.post("/recommend", json={"tier": "low", "epsilon": 0.05, "n_trials": 40})
    assert r.status_code == 200 and "outcomes" in r.json()
    assert client.post("/recommend", json={"epsilon": 0.05}).status_code == 422
    assert client.post("/recommend", json={"tier": "low", "epsilon": 0.0001, "n_trials": 40}).status_code in (200, 422)
    assert client.post("/recommend", json={"tier": "bogus"}).status_code == 422


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS:", n)
