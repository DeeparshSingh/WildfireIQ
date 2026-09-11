"""Owner control: signed commands, the kill switch, and the ways back in.

The properties worth pinning are the ones the whole design rests on: only the
owner's key can produce a command, an old command cannot undo a newer one,
every failure mode leaves the deployment running rather than locking its owner
out, and a pause never blocks the two routes used to diagnose a pause.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from wildfireiq_api import owner as owner_module
from wildfireiq_api.main import create_app
from wildfireiq_api.owner import OwnerControl, admin_token, key_fingerprint, verify


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_command(
    key: Ed25519PrivateKey, state: str, message: str = "", *, issued_at: datetime | None = None
) -> str:
    payload = {
        "v": 1,
        "state": state,
        "message": message,
        "issued_at": (issued_at or datetime.now(UTC)).isoformat(),
        "nonce": "test",
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{b64e(raw)}.{b64e(key.sign(raw))}"


@pytest.fixture
def owner_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def public_b64(owner_key: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives import serialization

    return b64e(
        owner_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
    )


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, public_b64: str) -> OwnerControl:
    """A control object with its own files and a test key as the owner."""
    monkeypatch.setattr(owner_module, "CONTROL_PATH", tmp_path / "control.json")
    monkeypatch.setattr(owner_module, "SEEN_PATH", tmp_path / "seen.json")
    monkeypatch.setattr(owner_module, "LOCAL_STATE_PATH", tmp_path / "local.json")
    monkeypatch.setattr(owner_module, "OWNER_PUBLIC_KEY_B64", public_b64)
    monkeypatch.delenv("WILDFIREIQ_CONTROL", raising=False)
    return OwnerControl()


# ── signatures ───────────────────────────────────────────────────────────


def test_only_the_owners_key_produces_a_valid_command(
    owner_key: Ed25519PrivateKey, public_b64: str
) -> None:
    good = make_command(owner_key, "paused", "back at six")
    assert verify(good, source="test", public_key_b64=public_b64).state == "paused"

    impostor = make_command(Ed25519PrivateKey.generate(), "running")
    with pytest.raises(ValueError, match="not the owner"):
        verify(impostor, source="test", public_key_b64=public_b64)


def test_a_tampered_payload_is_refused(owner_key: Ed25519PrivateKey, public_b64: str) -> None:
    """Editing the state in a captured command must invalidate the signature."""
    token = make_command(owner_key, "paused")
    payload_b64, sig = token.rsplit(".", 1)
    raw = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    raw["state"] = "running"
    forged = b64e(json.dumps(raw, separators=(",", ":"), sort_keys=True).encode()) + "." + sig
    with pytest.raises(ValueError):
        verify(forged, source="test", public_key_b64=public_b64)


@pytest.mark.parametrize("token", ["", "garbage", "no-dot-here", "!!!.???", b64e(b"{}") + ".AAAA"])
def test_malformed_commands_raise_rather_than_crash(token: str, public_b64: str) -> None:
    with pytest.raises(ValueError):
        verify(token, source="test", public_key_b64=public_b64)


def test_an_unknown_state_is_refused(owner_key: Ed25519PrivateKey, public_b64: str) -> None:
    with pytest.raises(ValueError, match="unknown state"):
        verify(make_command(owner_key, "self_destruct"), source="t", public_key_b64=public_b64)


def test_fingerprint_is_readable_and_survives_a_bad_key() -> None:
    fp = key_fingerprint("pttrY-NjChcESOHEdEGYkZo6syhsDcc_lfYmd3NUMpA")
    assert fp.count(":") == 3 and len(fp) == 19, "four short groups, easy to read aloud"
    assert key_fingerprint("pttrY-NjChcESOHEdEGYkZo6syhsDcc_lfYmd3NUMpA") == fp
    assert key_fingerprint("not base64 at all !!!") == "invalid"
    # Valid base64, wrong length for an Ed25519 key: also invalid, rather
    # than a plausible fingerprint that silently fails every signature.
    assert key_fingerprint("AAAA") == "invalid"


# ── fail-open ────────────────────────────────────────────────────────────


def test_no_command_means_running(isolated: OwnerControl) -> None:
    assert isolated.state == "running"
    assert isolated.blocks("/api/fires/current", "GET") is None


def test_an_unreadable_control_file_leaves_the_deployment_running(
    isolated: OwnerControl,
) -> None:
    owner_module.CONTROL_PATH.write_text("{ not json")
    isolated.reload()
    assert isolated.state == "running", "a broken file must never lock the owner out"
    assert isolated.health().problems, "but it must be reported"


def test_a_forged_command_leaves_the_deployment_running(isolated: OwnerControl) -> None:
    forged = make_command(Ed25519PrivateKey.generate(), "paused")
    owner_module.CONTROL_PATH.write_text(json.dumps({"command": forged}))
    isolated.reload()
    assert isolated.state == "running"
    assert any("rejected" in p for p in isolated.health().problems)


# ── the kill switch ──────────────────────────────────────────────────────


def test_a_pause_blocks_the_api_but_never_the_diagnostic_routes(
    isolated: OwnerControl, owner_key: Ed25519PrivateKey
) -> None:
    owner_module.CONTROL_PATH.write_text(
        json.dumps({"command": make_command(owner_key, "paused", "Down for maintenance")})
    )
    isolated.reload()
    assert isolated.state == "paused"
    assert isolated.blocks("/api/fires/current", "GET") == "Down for maintenance"
    assert isolated.blocks("/healthz", "GET") is None
    assert isolated.blocks("/api/ownership", "GET") is None


def test_readonly_allows_reads_and_refuses_writes(
    isolated: OwnerControl, owner_key: Ed25519PrivateKey
) -> None:
    owner_module.CONTROL_PATH.write_text(
        json.dumps({"command": make_command(owner_key, "readonly")})
    )
    isolated.reload()
    assert isolated.blocks("/api/fires/current", "GET") is None
    assert isolated.blocks("/api/settings/keys", "PUT") is not None
    assert isolated.blocks("/api/admin/jobs/x/run", "POST") is not None


def test_the_env_var_works_when_the_filesystem_does_not(
    isolated: OwnerControl, owner_key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The break-glass route: no file write needed, just a variable."""
    monkeypatch.setenv("WILDFIREIQ_CONTROL", make_command(owner_key, "paused", "env pause"))
    isolated.reload()
    assert isolated.state == "paused"
    assert isolated.health().command_source == "env"


# ── rollback ─────────────────────────────────────────────────────────────


def test_an_older_command_cannot_undo_a_newer_one(
    isolated: OwnerControl, owner_key: Ed25519PrivateKey
) -> None:
    now = datetime.now(UTC)
    owner_module.CONTROL_PATH.write_text(
        json.dumps({"command": make_command(owner_key, "paused", issued_at=now)})
    )
    isolated.reload()
    assert isolated.state == "paused"

    # Someone replays a genuine, older "running" command they captured. The
    # pause must hold: refusing the rollback by falling open to "running" would
    # give the replay precisely what it was replayed for.
    stale = make_command(owner_key, "running", issued_at=now - timedelta(hours=1))
    owner_module.CONTROL_PATH.write_text(json.dumps({"command": stale}))
    isolated.reload()
    assert isolated.state == "paused"
    assert any("rollback" in p for p in isolated.health().problems)

    # Over HTTP it is refused outright rather than silently ignored.
    with pytest.raises(ValueError, match="older"):
        isolated.adopt(stale, source="http")

    # Deleting the file is still a clean way back, and needs the machine.
    owner_module.CONTROL_PATH.unlink()
    isolated.reload()
    assert isolated.state == "running"


def test_a_newer_command_replaces_an_older_one(
    isolated: OwnerControl, owner_key: Ed25519PrivateKey
) -> None:
    isolated.adopt(make_command(owner_key, "paused"), source="http")
    assert isolated.state == "paused"
    later = make_command(owner_key, "running", issued_at=datetime.now(UTC) + timedelta(seconds=1))
    isolated.adopt(later, source="http")
    assert isolated.state == "running"


# ── the admin-token channel ──────────────────────────────────────────────


def test_the_most_recent_instruction_wins_across_channels(
    isolated: OwnerControl, owner_key: Ed25519PrivateKey
) -> None:
    """Neither channel can strand the other."""
    old_signed = make_command(owner_key, "paused", issued_at=datetime.now(UTC) - timedelta(hours=2))
    owner_module.CONTROL_PATH.write_text(json.dumps({"command": old_signed}))
    isolated.reload()
    assert isolated.state == "paused"

    isolated.set_local_state("running")  # the owner, from the UI, just now
    assert isolated.state == "running"
    assert isolated.health().command_source == "admin-token"

    fresh_signed = make_command(
        owner_key, "paused", issued_at=datetime.now(UTC) + timedelta(seconds=2)
    )
    isolated.adopt(fresh_signed, source="http")
    assert isolated.state == "paused", "a newer signed command overrides the token"


def test_the_token_state_survives_a_restart(isolated: OwnerControl) -> None:
    isolated.set_local_state("paused", "gone fishing")
    fresh = OwnerControl()
    assert fresh.state == "paused"
    assert fresh.blocks("/api/fires/current", "GET") == "gone fishing"


# ── the admin token itself ───────────────────────────────────────────────


def test_a_token_is_generated_when_none_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Protected by default: nobody has to create a .env file."""
    monkeypatch.setattr(owner_module, "OWNER_STATE_PATH", tmp_path / "owner.json")
    first = admin_token("")
    assert len(first) > 20
    assert admin_token("") == first, "and it is stable across calls"
    assert json.loads((tmp_path / "owner.json").read_text())["admin_token"] == first


def test_a_configured_token_wins_over_the_generated_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(owner_module, "OWNER_STATE_PATH", tmp_path / "owner.json")
    assert admin_token("  chosen-by-hand  ") == "chosen-by-hand"


# ── over HTTP ────────────────────────────────────────────────────────────


@pytest.fixture
def client(isolated: OwnerControl, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(owner_module, "control", isolated)
    from wildfireiq_api import main as main_module
    from wildfireiq_api.routers import ownership as ownership_router

    monkeypatch.setattr(main_module, "control", isolated)
    monkeypatch.setattr(ownership_router, "control", isolated)
    return TestClient(create_app())


def test_the_ownership_endpoint_names_the_owner_and_hides_nothing_secret(
    client: TestClient,
) -> None:
    body = client.get("/api/ownership").json()["data"]
    assert body["owner"]
    assert body["key_fingerprint"]
    assert body["state"] == "running"
    assert "private" not in json.dumps(body).lower()


def test_a_signed_command_over_http_pauses_the_deployment(
    client: TestClient, owner_key: Ed25519PrivateKey
) -> None:
    token = make_command(owner_key, "paused", "Owner paused this")
    applied = client.post("/api/ownership/command", json={"command": token})
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["state"] == "paused"

    blocked = client.get("/api/fires/current")
    assert blocked.status_code == 503
    assert blocked.json()["detail"] == "Owner paused this"
    # Still diagnosable, which is the point.
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/ownership").status_code == 200


def test_a_pause_can_always_be_lifted_over_http(
    client: TestClient, owner_key: Ed25519PrivateKey
) -> None:
    """The route that applies a command must never be blocked by a pause.

    It was: the open-path check compared the exact path, so /api/ownership
    answered while /api/ownership/command did not. A kill switch that cannot
    be switched back is a way to lock yourself out of your own deployment.
    """
    paused = client.post(
        "/api/ownership/command", json={"command": make_command(owner_key, "paused")}
    )
    assert paused.status_code == 200
    assert client.get("/api/fires/current").status_code == 503

    resume = make_command(owner_key, "running", issued_at=datetime.now(UTC) + timedelta(seconds=1))
    lifted = client.post("/api/ownership/command", json={"command": resume})
    assert lifted.status_code == 200, "the owner must be able to resume from anywhere"
    assert lifted.json()["data"]["state"] == "running"
    assert client.get("/api/fires/current").status_code == 200


def test_the_token_route_also_works_while_paused(
    client: TestClient,
    owner_key: Ed25519PrivateKey,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(owner_module, "OWNER_STATE_PATH", tmp_path / "owner.json")
    client.post("/api/ownership/command", json={"command": make_command(owner_key, "paused")})
    assert client.get("/api/fires/current").status_code == 503
    resumed = client.post(
        "/api/ownership/state",
        json={"state": "running"},
        headers={"X-Admin-Token": admin_token("")},
    )
    assert resumed.status_code == 200
    assert client.get("/api/fires/current").status_code == 200


def test_an_unsigned_command_over_http_is_refused(client: TestClient) -> None:
    impostor = make_command(Ed25519PrivateKey.generate(), "paused")
    assert client.post("/api/ownership/command", json={"command": impostor}).status_code == 403
    assert client.get("/api/fires/current").status_code != 503


def test_the_state_endpoint_needs_the_admin_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(owner_module, "OWNER_STATE_PATH", tmp_path / "owner.json")
    token = admin_token("")

    assert client.post("/api/ownership/state", json={"state": "paused"}).status_code == 401
    wrong = client.post(
        "/api/ownership/state", json={"state": "paused"}, headers={"X-Admin-Token": "guess"}
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/api/ownership/state",
        json={"state": "paused", "message": "brb"},
        headers={"X-Admin-Token": token},
    )
    assert ok.status_code == 200
    assert client.get("/api/fires/current").status_code == 503


# ── the owner's command line ─────────────────────────────────────────────


def test_the_cli_signs_the_state_names_the_server_accepts() -> None:
    """The subcommand a person types is not the state name the API expects.

    `pause` reads better than `paused` on a command line, so the CLI maps
    between them. It got that mapping wrong once and signed "pause", which the
    API refused as an unknown state -- a command the owner could not use.
    """
    import importlib.util

    from wildfireiq_api.owner import VALID_STATES

    spec = importlib.util.spec_from_file_location(
        "owner_cli", Path(__file__).resolve().parents[3] / "scripts" / "owner.py"
    )
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    assert set(cli.STATE_FOR) == {"pause", "readonly", "resume"}
    for subcommand, state in cli.STATE_FOR.items():
        assert state in VALID_STATES, f"`owner.py {subcommand}` signs an unusable state"
