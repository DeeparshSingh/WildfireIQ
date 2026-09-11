"""Runtime settings: the API keys entered in the app's Settings panel.

Two endpoints. `GET /keys` says which of the owner's server keys are set,
what each unlocks, and whether writes are protected, so the frontend can show
a notice where a feature is missing its key. `PUT /keys` stores new values
from the panel's server section and immediately runs the ingest job behind
any key that was just added, so the layer fills in without waiting for the
next scheduled tick. When `ADMIN_TOKEN` is set, `PUT` requires the matching
`X-Admin-Token` header.

Values are never returned. See `keys.py` for the two kinds of key.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..ingest.base import run_job
from ..ingest.registry import all_jobs
from ..keys import KEY_FEATURES, KEY_JOBS, KEY_NAMES, keystore
from ..owner import admin_token
from ..settings import get_settings
from ._envelope import Envelope, Meta

router = APIRouter()
log = structlog.get_logger("settings")


class KeysUpdate(BaseModel):
    """A partial update. Omit a key to leave it alone; send null or "" to clear it."""

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
        # Always true in practice: a token is generated when none is set.
        "write_protected": bool(admin_token(get_settings().admin_token)),
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


def _require_admin(header_token: str | None) -> None:
    expected = admin_token(get_settings().admin_token)
    if expected and (header_token or "") != expected:
        raise HTTPException(401, "Server keys are owner-only. The admin token did not match.")


@router.put("/keys", summary="Store the owner's server keys (admin token when configured)")
async def keys_update(
    body: KeysUpdate, x_admin_token: str | None = Header(default=None)
) -> dict[str, Any]:
    _require_admin(x_admin_token)
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
