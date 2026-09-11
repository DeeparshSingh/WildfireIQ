"""Runtime settings: the API keys entered in the app's Settings panel.

Two endpoints. `GET /keys` says which keys are set and what each unlocks, so
the frontend can show a notice where a feature is missing its key. `PUT /keys`
stores new values, pushed from the browser's local storage, and immediately
runs the ingest job behind any key that was just added so the layer fills in
without waiting for the next scheduled tick.

Values are never returned. See `keys.py` for the trust model.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ingest.base import run_job
from ..ingest.registry import all_jobs
from ..keys import KEY_FEATURES, KEY_JOBS, KEY_NAMES, keystore
from ._envelope import Envelope, Meta

router = APIRouter()
log = structlog.get_logger("settings")


class KeysUpdate(BaseModel):
    """A partial update. Omit a key to leave it alone; send null or "" to clear it."""

    cesium_ion_token: str | None = None
    firms_map_key: str | None = None
    waqi_token: str | None = None
    openrouter_api_key: str | None = None


def _status_payload() -> dict[str, Any]:
    status = keystore.status()
    return {
        "keys": {
            name: {"configured": status[name], "unlocks": KEY_FEATURES[name]} for name in KEY_NAMES
        },
        "all_configured": all(status.values()),
    }


@router.get("/keys", summary="Which API keys are set (never their values)")
async def keys_status() -> dict[str, Any]:
    return Envelope[dict](
        data=_status_payload(),
        meta=Meta(source="settings.keys", attribution="WildfireIQ"),
    ).model_dump(mode="json")


async def _run_dependent_jobs(newly_set: list[str]) -> None:
    """Start the ingest behind each newly added key, in the background.

    The request returns at once; a FIRMS pull can take a few seconds, and
    the reader should see "saved", not a spinner.
    """
    jobs = all_jobs()
    for name in newly_set:
        job_name = KEY_JOBS.get(name)
        if not job_name or job_name not in jobs:
            continue
        try:
            report = await run_job(jobs[job_name])
            log.info("settings.key_job", key=name, job=job_name, status=report.status)
        except Exception as exc:
            log.warning("settings.key_job_failed", key=name, job=job_name, error=str(exc))


@router.put("/keys", summary="Store API keys entered in the Settings panel")
async def keys_update(body: KeysUpdate) -> dict[str, Any]:
    changes = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if not changes:
        raise HTTPException(400, "No keys in the request body.")
    try:
        newly_set = keystore.update(changes)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown key: {exc}") from exc

    log.info("settings.keys_updated", changed=sorted(changes), newly_set=newly_set)
    if newly_set:
        asyncio.get_running_loop().create_task(_run_dependent_jobs(newly_set))

    return Envelope[dict](
        data={**_status_payload(), "newly_set": newly_set},
        meta=Meta(
            source="settings.keys",
            attribution="WildfireIQ",
            note=(
                "Ingest for the newly added key is running; its data appears within a minute."
                if newly_set
                else None
            ),
        ),
    ).model_dump(mode="json")
