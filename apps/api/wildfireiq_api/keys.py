"""Runtime API keys, entered in the app rather than in a file.

The platform needs four third-party credentials: a Cesium Ion token for the
globe's terrain and imagery, a NASA FIRMS key for satellite hotspots, a WAQI
token for the pollutant breakdown, and an OpenRouter key for the assistant.
None of them is required for the platform to run; each one unlocks a feature.

They used to live in `.env`. That is fine for one developer on one machine
and wrong for everything else: a reader who opens the app has no `.env`, a
deployment on another server needs the file copied by hand, and the browser
half of the app cannot read a server-side file anyway. So the keys are now
entered once in the Settings panel, kept in the browser's local storage, and
pushed to this store so the scheduled jobs and the assistant — which run
server-side, with no browser attached — can use them too.

Persistence is a single JSON file under `data/runtime/`, which is ignored by
git. The store loads it on first access and rewrites it on every change, so a
backend restart keeps the keys; the browser also re-pushes its copy on every
page load, so the two stay in agreement even if the file is deleted.

The values never leave this module in a response. `status()` reports only
whether each key is set.

Trust model: there is no authentication on this API, and this store accepts
writes from anyone who can reach it. That is the right trade for the two
places the platform runs — a laptop, and one person's own server bound to
localhost or a private network. It would be the wrong trade for a public
host, and the architecture notes say so.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Final

from .paths import DATA_ROOT

#: The four credentials, by the names the Settings panel and the API use.
KEY_NAMES: Final[tuple[str, ...]] = (
    "cesium_ion_token",
    "firms_map_key",
    "waqi_token",
    "openrouter_api_key",
)

#: Which feature each key unlocks. Reported by /api/settings/keys so the
#: frontend can word its notices without a second copy of this table.
KEY_FEATURES: Final[dict[str, str]] = {
    "cesium_ion_token": "3D globe terrain and imagery",
    "firms_map_key": "satellite hotspots layer",
    "waqi_token": "pollutant breakdown on the air-quality page",
    "openrouter_api_key": "the assistant",
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
