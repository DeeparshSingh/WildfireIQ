"""The server's API keys: the owner's, entered once in the app's Settings panel.

Two kinds of key exist and they are kept apart on purpose.

Visitor keys stay in the visitor's browser and never reach this store. The
Cesium Ion token is only ever used by the browser, so it lives in local
storage and nowhere else. A visitor's own OpenRouter key travels with each
chat request as a header and is used for that request alone, so anyone can
bring their own key to the assistant without the server keeping it.

Server keys are the owner's, and there is one set for the whole deployment:
the NASA FIRMS key and WAQI token drive scheduled jobs that run with no
browser attached, and an OpenRouter key here is the default the assistant
uses for visitors who have not brought their own. They are entered in the
Settings panel's server section and stored in `data/runtime/keys.json`,
which is ignored by git and survives a restart.

Writes are guarded by `ADMIN_TOKEN` (settings.py). With it set, `PUT
/api/settings/keys` requires the matching `X-Admin-Token` header, so a
visitor to a public deployment cannot change or clear the owner's keys. With
it unset — a laptop, one person — writes are open, and the panel says so.

The values never leave this module in a response. `status()` reports only
whether each key is set.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Final

from .paths import DATA_ROOT

#: The owner's server-side credentials, by the names the panel and API use.
KEY_NAMES: Final[tuple[str, ...]] = (
    "firms_map_key",
    "waqi_token",
    "openrouter_api_key",
)

#: Which feature each key unlocks. Reported by /api/settings/keys so the
#: frontend can word its notices without a second copy of this table.
KEY_FEATURES: Final[dict[str, str]] = {
    "firms_map_key": "satellite hotspots layer",
    "waqi_token": "pollutant breakdown on the air-quality page",
    "openrouter_api_key": "the assistant, for visitors who do not bring their own key",
}

#: The ingest job that turns a newly entered key into data on screen. The
#: settings router runs it right after a save, so the reader does not wait
#: for the next cron tick to see the layer fill in.
KEY_JOBS: Final[dict[str, str]] = {
    "firms_map_key": "firms_hotspots",
    "waqi_token": "waqi_kamloops",
}

STORE_PATH: Final[Path] = DATA_ROOT / "runtime" / "keys.json"


class KeyStore:
    """In-memory copy of the keys, mirrored to one JSON file."""

    def __init__(self, path: Path = STORE_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._values: dict[str, str] = {name: "" for name in KEY_NAMES}
        self._loaded = False

    # ── loading and saving ────────────────────────────────────────────

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt file is treated as empty rather than crashing the
            # app; the browser re-pushes its copy on the next page load.
            return
        if isinstance(raw, dict):
            for name in KEY_NAMES:
                value = raw.get(name)
                if isinstance(value, str):
                    self._values[name] = value.strip()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._values, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)

    # ── the interface the rest of the app uses ────────────────────────

    def get(self, name: str) -> str:
        """The current value, or an empty string when the key is not set."""
        if name not in KEY_NAMES:
            raise KeyError(name)
        with self._lock:
            self._load()
            return self._values[name]

    def status(self) -> dict[str, bool]:
        """Whether each key is set. Never the values."""
        with self._lock:
            self._load()
            return {name: bool(self._values[name]) for name in KEY_NAMES}

    def update(self, changes: dict[str, str | None]) -> list[str]:
        """Apply a partial update; a None or empty string clears that key.

        Returns the names whose value went from empty to set, so the caller
        can start the ingest job that depends on each one.
        """
        unknown = sorted(set(changes) - set(KEY_NAMES))
        if unknown:
            raise KeyError(", ".join(unknown))
        with self._lock:
            self._load()
            newly_set: list[str] = []
            for name, value in changes.items():
                clean = (value or "").strip()
                if clean and not self._values[name]:
                    newly_set.append(name)
                self._values[name] = clean
            self._save()
            return newly_set

    def reset_for_tests(self) -> None:
        """Forget everything, including what was loaded from disk."""
        with self._lock:
            self._values = {name: "" for name in KEY_NAMES}
            self._loaded = True


keystore = KeyStore()
