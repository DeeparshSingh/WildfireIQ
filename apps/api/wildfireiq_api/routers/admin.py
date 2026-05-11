"""Admin endpoints — kick off ingests on demand, inspect runs."""

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..db import session_scope
from ..ingest.base import run_job
from ..ingest.registry import all_jobs
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/jobs", summary="List all ingest jobs and their cadences")
async def list_jobs() -> dict[str, Any]:
    rows = [
        {"name": j.name, "label": j.label, "cadence": j.cadence}
        for j in all_jobs().values()
    ]
    return Envelope[list](
        data=rows,
        meta=Meta(source="ingest.registry", attribution="WildfireIQ", phase="1"),
    ).model_dump(mode="json")


@router.post("/jobs/{name}/run", summary="Trigger one ingest job immediately")
async def trigger_job(name: str) -> dict[str, Any]:
    jobs = all_jobs()
    if name not in jobs:
        raise HTTPException(404, f"Unknown job: {name}. Known: {sorted(jobs)}")
    report = await run_job(jobs[name])
    return Envelope[dict](
        data={
            "name": name,
            "status": report.status,
            "rows_in": report.rows_in,
            "rows_written": report.rows_written,
            "duration_ms": report.duration_ms,
            "note": report.note,
            "error": report.error,
        },
        meta=Meta(source="ingest.run_job", attribution="WildfireIQ", phase="1"),
    ).model_dump(mode="json")


@router.get("/runs", summary="Last N ingest_runs entries")
async def list_runs(limit: int = 50, job: str | None = None) -> dict[str, Any]:
    query = (
        "SELECT job_name, started_at, finished_at, status, rows_in, rows_written, "
        "duration_ms, note, error FROM ingest_runs"
    )
    params: dict[str, Any] = {}
    if job:
        query += " WHERE job_name = :job"
        params["job"] = job
    query += " ORDER BY id DESC LIMIT :limit"
    params["limit"] = limit

    async with session_scope() as session:
        result = await session.execute(text(query), params)
        rows = [dict(r._mapping) for r in result]

    return Envelope[list](
        data=rows,
        meta=Meta(source="sqlite.ingest_runs", attribution="WildfireIQ", phase="1"),
    ).model_dump(mode="json")
