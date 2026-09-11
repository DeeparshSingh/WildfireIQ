"""Shared fixtures.

Two stores persist to `data/runtime/`: the API keys and the owner's control
state. Every test gets both pointed at its own temporary directory, so a suite
run can never read a developer's real keys, never pause their development
server, and never leave test values behind for the app.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wildfireiq_api import keys as keys_module
from wildfireiq_api import owner as owner_module


@pytest.fixture(autouse=True)
def _isolated_keystore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = keys_module.keystore
    monkeypatch.setattr(store, "_path", tmp_path / "keys.json")
    store.reset_for_tests()
    yield store
    store.reset_for_tests()


@pytest.fixture(autouse=True)
def _isolated_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Owner control, pointed at this test's own directory and left running."""
    for name in ("CONTROL_PATH", "SEEN_PATH", "LOCAL_STATE_PATH", "OWNER_STATE_PATH"):
        monkeypatch.setattr(owner_module, name, tmp_path / f"{name.lower()}.json")
    monkeypatch.delenv("WILDFIREIQ_CONTROL", raising=False)
    owner_module.control.reset_for_tests()
    yield owner_module.control
    owner_module.control.reset_for_tests()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """The header that authorises a change, using whatever token is in force.

    A token is generated on first use when none is configured, so this works
    without any environment setup and mirrors what a real deployment does.
    """
    return {"X-Admin-Token": owner_module.admin_token("")}
