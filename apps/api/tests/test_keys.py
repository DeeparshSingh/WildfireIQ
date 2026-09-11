"""The runtime key store and the Settings API in front of it.

Keys are entered in the app, not in a file, so the properties that matter are:
values persist across a restart, values never come back out of the API, an
unknown name is rejected, and entering a key starts the ingest that depends
on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wildfireiq_api import keys as keys_module
from wildfireiq_api.keys import KEY_NAMES, KeyStore
from wildfireiq_api.main import create_app
from wildfireiq_api.routers import settings as settings_router

# ── the store ────────────────────────────────────────────────────────────


def test_store_starts_empty_and_reports_every_key(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "keys.json")
    assert set(store.status()) == set(KEY_NAMES)
    assert not any(store.status().values())
    assert store.get("firms_map_key") == ""


def test_store_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    KeyStore(path).update({"waqi_token": "abc123"})
    fresh = KeyStore(path)
    assert fresh.get("waqi_token") == "abc123"
    assert fresh.status()["waqi_token"] is True


def test_store_reports_which_keys_were_newly_set(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "keys.json")
    assert store.update({"firms_map_key": "k1", "waqi_token": ""}) == ["firms_map_key"]
    # Re-saving the same key is not "newly set"; clearing then setting is.
    assert store.update({"firms_map_key": "k2"}) == []
    store.update({"firms_map_key": None})
    assert store.update({"firms_map_key": "k3"}) == ["firms_map_key"]


def test_store_strips_whitespace_and_treats_blank_as_clear(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "keys.json")
    store.update({"openrouter_api_key": "  sk-x  "})
    assert store.get("openrouter_api_key") == "sk-x"
    store.update({"openrouter_api_key": "   "})
    assert store.get("openrouter_api_key") == ""


def test_store_rejects_unknown_names(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "keys.json")
    with pytest.raises(KeyError):
        store.update({"aws_secret": "nope"})
    with pytest.raises(KeyError):
        store.get("aws_secret")


def test_store_survives_a_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    path.write_text("{not json")
    store = KeyStore(path)
    assert not any(store.status().values())


# ── the API ──────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_status_endpoint_reports_configured_flags_only(client: TestClient) -> None:
    keys_module.keystore.update({"waqi_token": "tok.super.secret"})
    body = client.get("/api/settings/keys").json()
    data = body["data"]
    assert data["keys"]["waqi_token"]["configured"] is True
    assert data["keys"]["firms_map_key"]["configured"] is False
    assert "unlocks" in data["keys"]["firms_map_key"]
    assert data["all_configured"] is False
    assert data["write_protected"] is True, "a token is generated when none is configured"
    assert "cesium_ion_token" not in data["keys"], "the browser-only token never reaches the server"
    assert "tok.super.secret" not in client.get("/api/settings/keys").text


def test_put_stores_keys_and_never_echoes_them(
    client: TestClient, monkeypatch, admin_headers
) -> None:
    ran: list[str] = []

    async def fake_run(newly_set: list[str]) -> None:
        ran.extend(newly_set)

    monkeypatch.setattr(settings_router, "_run_dependent_jobs", fake_run)
    res = client.put("/api/settings/keys", json={"waqi_token": "tok-999"}, headers=admin_headers)
    assert res.status_code == 200
    assert "tok-999" not in res.text
    assert res.json()["data"]["newly_set"] == ["waqi_token"]
    assert keys_module.keystore.get("waqi_token") == "tok-999"


def test_put_rejects_an_empty_body_and_ignores_unknown_fields(
    client: TestClient, admin_headers
) -> None:
    assert client.put("/api/settings/keys", json={}, headers=admin_headers).status_code == 400
    # Unknown fields are dropped by the model rather than stored.
    res = client.put(
        "/api/settings/keys", json={"aws_secret": "x", "waqi_token": "t"}, headers=admin_headers
    )
    assert res.status_code == 200
    assert not any(k == "aws_secret" for k in keys_module.keystore.status())


def test_put_can_clear_a_key(client: TestClient, monkeypatch, admin_headers) -> None:
    async def fake_run(newly_set: list[str]) -> None:
        return None

    monkeypatch.setattr(settings_router, "_run_dependent_jobs", fake_run)
    keys_module.keystore.update({"firms_map_key": "abc"})
    res = client.put("/api/settings/keys", json={"firms_map_key": None}, headers=admin_headers)
    assert res.json()["data"]["keys"]["firms_map_key"]["configured"] is False


# ── consumers ────────────────────────────────────────────────────────────


async def test_ingest_jobs_report_a_missing_key_by_pointing_at_settings() -> None:
    from types import SimpleNamespace

    from wildfireiq_api.ingest.firms_hotspots import FIRMSHotspotsJob
    from wildfireiq_api.ingest.waqi import WAQIKamloopsJob

    ctx = SimpleNamespace(client=None, log=None, started_at_utc=None)
    for job in (FIRMSHotspotsJob(), WAQIKamloopsJob()):
        report = await job.run(ctx)  # type: ignore[arg-type]
        assert report.status == "fail"
        assert "Settings" in (report.error or "")


def test_assistant_availability_follows_the_store() -> None:
    from wildfireiq_api.assistant.harness import availability

    assert availability()["configured"] is False
    keys_module.keystore.update({"openrouter_api_key": "sk-live"})
    assert availability()["configured"] is True


def test_browser_preflight_for_put_is_accepted(client: TestClient) -> None:
    """The panel saves with PUT from a different origin, so the preflight must pass.

    It did not: allow_methods listed GET and POST only, the OPTIONS request got
    a 400, and the panel reported the API unreachable while GETs worked.
    """
    res = client.options(
        "/api/settings/keys",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200, res.text
    assert "PUT" in res.headers.get("access-control-allow-methods", "")


# ── owner-only writes ────────────────────────────────────────────────────


def test_writes_are_protected_even_with_nothing_configured(
    client: TestClient, monkeypatch, admin_headers
) -> None:
    """Protected by default: a token is generated when none is set, so an
    unauthenticated write is refused without anyone having to configure it."""

    async def fake_run(newly_set: list[str]) -> None:
        return None

    monkeypatch.setattr(settings_router, "_run_dependent_jobs", fake_run)
    assert client.put("/api/settings/keys", json={"firms_map_key": "k"}).status_code == 401
    assert keys_module.keystore.get("firms_map_key") == ""
    ok = client.put("/api/settings/keys", json={"firms_map_key": "k"}, headers=admin_headers)
    assert ok.status_code == 200
    assert ok.json()["data"]["write_protected"] is True


def test_writes_need_the_admin_token_when_one_is_configured(
    client: TestClient, monkeypatch
) -> None:
    from wildfireiq_api.settings import Settings

    monkeypatch.setattr(
        settings_router, "get_settings", lambda: Settings(admin_token="owner-secret")
    )

    async def fake_run(newly_set: list[str]) -> None:
        return None

    monkeypatch.setattr(settings_router, "_run_dependent_jobs", fake_run)

    denied = client.put("/api/settings/keys", json={"firms_map_key": "k"})
    assert denied.status_code == 401
    assert keys_module.keystore.get("firms_map_key") == ""

    wrong = client.put(
        "/api/settings/keys", json={"firms_map_key": "k"}, headers={"X-Admin-Token": "guess"}
    )
    assert wrong.status_code == 401

    ok = client.put(
        "/api/settings/keys", json={"firms_map_key": "k"}, headers={"X-Admin-Token": "owner-secret"}
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["write_protected"] is True
    assert keys_module.keystore.get("firms_map_key") == "k"
    # Reading status never needs the token.
    assert client.get("/api/settings/keys").status_code == 200
