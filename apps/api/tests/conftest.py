"""Shared fixtures.

The runtime key store persists to `data/runtime/keys.json`. Every test gets a
store pointed at its own temporary file and emptied, so a suite run can never
read a developer's real keys or leave test values behind for the app.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wildfireiq_api import keys as keys_module


@pytest.fixture(autouse=True)
def _isolated_keystore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = keys_module.keystore
    monkeypatch.setattr(store, "_path", tmp_path / "keys.json")
    store.reset_for_tests()
    yield store
    store.reset_for_tests()
