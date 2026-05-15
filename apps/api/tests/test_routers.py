"""End-to-end router tests via FastAPI TestClient.

These tests load real parquets from `data/processed/`. If a parquet is
missing the test is skipped (not failed) so the suite is robust on a
fresh clone where ingest hasn't been bootstrapped.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wildfireiq_api.main import create_app


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = REPO_ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ─── Health & system ──────────────────────────────────────────────────


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "version" in body
    assert "bbox" in body and len(body["bbox"]) == 4


def test_healthz_no_cache_header_overridden(client: TestClient) -> None:
    """healthz is not /api/* so the Cache-Control middleware shouldn't tag it."""
    r = client.get("/healthz")
    assert r.headers.get("cache-control") is None


# ─── Cache-Control middleware ─────────────────────────────────────────


def test_api_get_has_short_cache(client: TestClient) -> None:
    r = client.get("/api/fires/current")
    assert r.status_code == 200
    assert "max-age=60" in (r.headers.get("cache-control") or "")


def test_long_cache_endpoints_use_longer_max_age(client: TestClient) -> None:
    r = client.get("/api/firesmart/achievements")
    assert r.status_code == 200
    cc = r.headers.get("cache-control") or ""
    assert "max-age=300" in cc


# ─── Envelope shape ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/fires/current",
        "/api/fires/historical?year=2023",
        "/api/firesmart/checklist?dwelling=house&season=summer",
        "/api/firesmart/achievements",
        "/api/firesmart/neighbourhoods",
        "/api/firesmart/season-context",
    ],
)
def test_envelope_shape(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200
    body = r.json()
    assert "data" in body, f"{path} missing `data`"
    assert "meta" in body, f"{path} missing `meta`"
    meta = body["meta"]
    assert "phase" in meta
    assert "source" in meta


# ─── Domain-specific contracts ────────────────────────────────────────


def test_firesmart_filters_by_dwelling(client: TestClient) -> None:
    house = client.get("/api/firesmart/checklist?dwelling=house&season=summer").json()["data"]["actions"]
    townhome = client.get("/api/firesmart/checklist?dwelling=townhome&season=summer").json()["data"]["actions"]
    # Townhome dwellers should see fewer applicable actions than a detached house.
    assert len(townhome) < len(house)


def test_firesmart_season_ordering_changes(client: TestClient) -> None:
    """Action ordering must change with the season — that's the headline feature."""
    spring_top = client.get("/api/firesmart/checklist?dwelling=house&season=spring").json()["data"]["actions"][0]["id"]
    summer_top = client.get("/api/firesmart/checklist?dwelling=house&season=summer").json()["data"]["actions"][0]["id"]
    fall_top = client.get("/api/firesmart/checklist?dwelling=house&season=fall").json()["data"]["actions"][0]["id"]
    # At least two of the three seasons should differ.
    assert len({spring_top, summer_top, fall_top}) >= 2


def test_firesmart_score_oracle(client: TestClient) -> None:
    r = client.post(
        "/api/firesmart/score",
        json={
            "completed_ids": ["im_roof_debris"],
            "dwelling": "house",
            "season": "summer",
            "situation": [],
            "photos": 0,
            "streak": 1,
            "flags": {},
            "today": "2026-05-14",
        },
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["points"] >= 1
    assert any(b["id"] == "first_steps" for b in d["badges"])


def test_evac_check_returns_a_status(client: TestClient) -> None:
    r = client.get("/api/evac/check?lat=50.6745&lon=-120.3273")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["status"] in {"clear", "alert", "order"}
    assert d["queried"]["lat"] == pytest.approx(50.6745)


# ─── Climate router ───────────────────────────────────────────────────


def _skip_if_no_seasonal() -> None:
    if not (PROCESSED / "seasonal_metrics.parquet").exists():
        pytest.skip("seasonal_metrics.parquet not built")


def test_climate_seasonal_json(client: TestClient) -> None:
    _skip_if_no_seasonal()
    r = client.get("/api/climate/seasonal")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert len(rows) > 5
    assert "year" in rows[0]


def test_climate_seasonal_csv(client: TestClient) -> None:
    _skip_if_no_seasonal()
    r = client.get("/api/climate/seasonal?format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    body = r.text
    assert body.splitlines()[0].count(",") >= 5  # multi-column header


def test_climate_trends_have_ci(client: TestClient) -> None:
    _skip_if_no_seasonal()
    r = client.get("/api/climate/trends")
    assert r.status_code == 200
    m = r.json()["data"]["metrics"]
    t = m["mean_jul_temp_c"]
    assert t["slope_ci_lo"] <= t["slope_per_year"] <= t["slope_ci_hi"]


def test_climate_ribbon_csv(client: TestClient) -> None:
    _skip_if_no_seasonal()
    r = client.get("/api/climate/ribbon?format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_climate_fwi_projection_method_disclosed(client: TestClient) -> None:
    _skip_if_no_seasonal()
    r = client.get("/api/climate/fwi-projection")
    assert r.status_code == 200
    d = r.json()["data"]
    assert "method" in d
    assert "heuristic" in d["method"].lower() or "coarse" in d["method"].lower()


def test_tru_carbon_flag_default_unavailable(client: TestClient) -> None:
    r = client.get("/api/climate/tru-carbon")
    assert r.status_code == 200
    # We don't ship a real TRU CSV, so this must report unavailable.
    assert r.json()["data"]["available"] is False
