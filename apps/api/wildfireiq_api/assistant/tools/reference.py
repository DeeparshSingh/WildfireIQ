"""Reference tools: the project's own documentation, model metrics, data freshness.

These are what let the assistant answer questions *about the platform*
rather than about the weather — "how accurate is this model", "where does
the fire data come from", "is this up to date". Without them the assistant
would have to guess at its own provenance, which is the one thing a
research tool must never do.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text

from ...db import session_scope
from ...paths import MODELS_ROOT, REPO_ROOT
from .. import gazetteer
from .base import ToolResult, tool

#: Documents the assistant may quote. Everything here is written for
#: publication — model cards, architecture notes, the README — so there is
#: nothing to redact.
_DOC_SOURCES: tuple[tuple[str, str], ...] = (
    ("README.md", "Project README"),
    ("documents/model-cards/wildfire_risk_v1.md", "Model card — wildfire risk"),
    ("documents/model-cards/aq_forecaster_v1.md", "Model card — air-quality forecaster"),
    ("documents/how-it-works.md", "How the platform works and how to extend it"),
    ("documents/architecture.md", "Architecture"),
    ("documents/data-dictionary.md", "Data dictionary"),
    ("documents/assistant.md", "How this assistant works"),
)

_STOPWORDS = frozenset(
    "a an the and or of to in on for is are was were be been it its this that with "
    "how what why when where does do can i you we my your".split()
)


@dataclass(frozen=True, slots=True)
class _Section:
    doc: str
    heading: str
    body: str
    tokens: frozenset[str]


@lru_cache(maxsize=1)
def _index() -> tuple[_Section, ...]:
    """Split every reference document into heading-delimited sections.

    A whole model card is 6,000 tokens; one section is 200. Retrieving
    sections rather than files is the difference between the assistant
    citing a specific claim and it re-reading its own documentation on
    every question.
    """
    sections: list[_Section] = []
    for relative, label in _DOC_SOURCES:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        current_heading = label
        buffer: list[str] = []

        def flush(heading: str, lines: list[str], doc: str = label) -> None:
            body = "\n".join(lines).strip()
            if len(body) < 40:
                return
            words = {w for w in re.findall(r"[a-z0-9]+", (heading + " " + body).lower())}
            sections.append(
                _Section(doc=doc, heading=heading, body=body, tokens=frozenset(words - _STOPWORDS))
            )

        for line in content.splitlines():
            if line.startswith("#"):
                flush(current_heading, buffer)
                current_heading = line.lstrip("#").strip() or label
                buffer = []
            else:
                buffer.append(line)
        flush(current_heading, buffer)

    return tuple(sections)


@tool(
    name="search_documentation",
    description=(
        "Search WildfireIQ's own documentation — model cards, architecture "
        "notes, data dictionary, README — and return the most relevant "
        "sections. Use this for any question about how the platform works: "
        "model accuracy, training data, which features matter, known "
        "limitations, where a dataset comes from, how the FWI is computed. "
        "Prefer this over answering methodology questions from memory."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, e.g. 'PR-AUC held out 2023'.",
            },
            "limit": {"type": "integer", "description": "Sections, max 5. Default 3."},
        },
        "required": ["query"],
    },
    ttl_s=3600,
    tags=("reference",),
)
def search_documentation(query: str, limit: int = 3) -> ToolResult:
    terms = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOPWORDS}
    if not terms:
        raise ValueError("query had no searchable words")

    scored: list[tuple[float, _Section]] = []
    for section in _index():
        overlap = terms & section.tokens
        if not overlap:
            continue
        # Coverage of the query matters more than the size of the section;
        # a heading hit is worth extra because headings name topics.
        score = len(overlap) / len(terms)
        if terms & {w for w in re.findall(r"[a-z0-9]+", section.heading.lower())}:
            score += 0.5
        scored.append((score, section))

    if not scored:
        raise RuntimeError(
            f"nothing in the documentation matches {query!r}. "
            "Say so rather than inventing an answer."
        )

    scored.sort(key=lambda t: -t[0])
    limit = max(1, min(int(limit), 5))
    return ToolResult(
        data={
            "query": query,
            "sections": [
                {
                    "document": section.doc,
                    "heading": section.heading,
                    "text": section.body[:2200],
                }
                for _, section in scored[:limit]
            ],
        },
        source="WildfireIQ project documentation",
    )


@tool(
    name="get_model_performance",
    description=(
        "Held-out test metrics for the project's trained models: the wildfire "
        "risk classifier and the air-quality forecaster. Use whenever the user "
        "asks how accurate, how good, or how validated the predictions are. "
        "Report the numbers honestly, including the regions where the model "
        "underperforms its own baseline."
    ),
    parameters={
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "enum": ["wildfire_risk_v1", "aq_forecaster_v1", "all"],
                "description": "Default 'all'.",
            }
        },
    },
    ttl_s=3600,
    tags=("reference",),
)
def get_model_performance(model: str = "all") -> ToolResult:
    wanted = ["wildfire_risk_v1", "aq_forecaster_v1"] if model == "all" else [model]
    out: dict[str, Any] = {}
    for name in wanted:
        path: Path = MODELS_ROOT / name / "metrics.json"
        if not path.exists():
            out[name] = {"error": "this model is not trained on this deployment"}
            continue
        out[name] = json.loads(path.read_text())

    if not out:
        raise RuntimeError("no model metrics available")
    return ToolResult(
        data=out,
        source="WildfireIQ training artifacts (data/models/*/metrics.json)",
        note=(
            "The wildfire model trains on 1999-2021, calibrates on 2022, and is "
            "scored on a fully held-out 2023. Its Lower Mainland PR-AUC sits below "
            "the FWI baseline; do not average that away."
        ),
    )


@tool(
    name="get_data_freshness",
    description=(
        "Health of the ingest pipeline: when each dataset was last refreshed "
        "and whether it succeeded. Use when the user asks whether the data is "
        "current, or when a tool returned something that looks stale."
    ),
    parameters={
        "type": "object",
        "properties": {
            "job": {"type": "string", "description": "One job name. Omit for all."},
            "only_problems": {
                "type": "boolean",
                "description": "Only failing or overdue jobs. Default false.",
            },
        },
    },
    ttl_s=120,
    tags=("reference", "system"),
)
async def get_data_freshness(job: str | None = None, only_problems: bool = False) -> ToolResult:
    query = """
        SELECT job_name, status, finished_at, note, error
        FROM ingest_runs
        WHERE id IN (SELECT MAX(id) FROM ingest_runs GROUP BY job_name)
        ORDER BY job_name
    """
    async with session_scope() as session:
        result = await session.execute(text(query))
        rows = [dict(r._mapping) for r in result]

    if not rows:
        raise RuntimeError("no ingest runs have been recorded yet")

    now = datetime.now(UTC)
    entries: list[dict[str, Any]] = []
    for row in rows:
        if job and row["job_name"] != job:
            continue
        age_minutes: int | None = None
        try:
            finished = datetime.fromisoformat(str(row["finished_at"]))
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=UTC)
            age_minutes = int((now - finished).total_seconds() // 60)
        except (TypeError, ValueError):
            pass
        problem = row["status"] != "ok" or (age_minutes is not None and age_minutes > 24 * 60)
        if only_problems and not problem:
            continue
        entries.append(
            {
                "job": row["job_name"],
                "status": row["status"],
                "age_minutes": age_minutes,
                "note": row["note"],
                "error": (row["error"] or "")[:200] or None,
            }
        )

    healthy = sum(1 for e in entries if e["status"] == "ok")
    return ToolResult(
        data={
            "jobs_reported": len(entries),
            "healthy": healthy,
            "jobs": entries,
        },
        source="WildfireIQ ingest_runs table",
        as_of=now.isoformat(timespec="seconds"),
        note=(
            "cwfis_fwi_daily fails against an upstream NRCan GeoServer outage. "
            "The Fire Weather Index is derived independently from Van Wagner's "
            "equations, so that failure does not degrade the risk model."
        ),
    )


@tool(
    name="resolve_place",
    description=(
        "Check whether a place name is known and get its coordinates and "
        "modelled region. Use when a name is ambiguous or when another tool "
        "reported it as unknown, so you can offer the user real alternatives "
        "rather than guessing."
    ),
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "The place name to look up."}},
        "required": ["query"],
    },
    ttl_s=3600,
    tags=("reference",),
)
def resolve_place(query: str) -> ToolResult:
    resolution = gazetteer.resolve(query)
    return ToolResult(
        data={
            "query": query,
            "match": resolution.place.as_dict() if resolution.place else None,
            "confidence": resolution.confidence,
            "alternatives": [p.as_dict() for p in resolution.alternatives],
            "coverage": (
                "The AI risk model covers four regions: Thompson-Okanagan, "
                "Central Okanagan, Lower Mainland, Prince George. Fire, "
                "evacuation and hotspot data cover all of British Columbia."
            ),
        },
        source="WildfireIQ British Columbia gazetteer",
    )
