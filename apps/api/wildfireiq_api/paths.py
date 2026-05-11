"""Canonical filesystem layout for WildfireIQ data."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT: Path = Path(__file__).resolve().parents[3]
DATA_ROOT: Path = REPO_ROOT / "data"
RAW_ROOT: Path = DATA_ROOT / "raw"
PROCESSED_ROOT: Path = DATA_ROOT / "processed"
GEO_ROOT: Path = DATA_ROOT / "geo"
LOGS_ROOT: Path = DATA_ROOT / "logs"
MODELS_ROOT: Path = DATA_ROOT / "models"


def ensure_dirs() -> None:
    """Ensure required runtime directories exist."""
    for d in (RAW_ROOT, PROCESSED_ROOT, GEO_ROOT, LOGS_ROOT, MODELS_ROOT):
        d.mkdir(parents=True, exist_ok=True)
