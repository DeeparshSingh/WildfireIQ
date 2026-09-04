"""The situation brief prepended to every conversation.

An agent that must call a tool before it can answer "is it smoky today?"
is slow and expensive, and it looks stupid doing it. So the harness pays
for the six numbers that answer most questions up front: today's risk per
region, the fire count, the evacuation count, the air quality, the
weather, and whether the pipeline is healthy.

That is roughly 250 tokens — about two hundredths of a cent — and it turns
the common case from *two* model turns plus a LightGBM run into one turn
with no tools at all. The tools remain for everything specific.

The brief is rebuilt at most once a minute and shared across users, since
it contains nothing user-specific.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import structlog

from ..ml.risk_infer import predict_grid
from ..routers import _data

log = structlog.get_logger(__name__)

_TTL_SECONDS = 60.0
_cache: tuple[float, str] | None = None


def _risk_line() -> str | None:
    grid = predict_grid()
    if grid is None:
        return None
    parts = [
        f"{r['label']}: {r['risk_level']} (p={r['p_region']:.2f}, FWI {r['fwi_today']:.0f})"
        for r in grid["regions"]
    ]
    day = str(grid["observation_day"])[:10]
    return f"AI wildfire risk for {day} — " + "; ".join(parts)


def _fires_line() -> str | None:
    rows = _data.fires_current()
    if not rows:
        return None
    stages = Counter(str(r.get("stage_of_control") or "Unknown") for r in rows)
    out_of_control = sum(v for k, v in stages.items() if "out of control" in k.lower())
    largest = max(rows, key=lambda r: float(r.get("hectares") or 0))
    return (
        f"Active BC fires: {len(rows)}"
        + (f", {out_of_control} out of control" if out_of_control else "")
        + f". Largest: {largest.get('fire_name') or largest.get('fire_id')} "
        f"at {float(largest.get('hectares') or 0):,.0f} ha"
    )


def _evac_line() -> str | None:
    rows = _data.evac_active()
    if not rows:
        return None
    live = [r for r in rows if "rescind" not in str(r.get("status") or "").lower()]
    orders = sum(1 for r in live if "order" in str(r.get("status") or "").lower())
    alerts = sum(1 for r in live if "alert" in str(r.get("status") or "").lower())
    return f"Evacuations in effect: {orders} orders, {alerts} alerts"


def _air_line() -> str | None:
    stations = _data.aqhi_current()
    pollutants = _data.aq_pollutants_latest()
    readings = [float(s["aqhi"]) for s in stations if s.get("aqhi") is not None]
    if not readings and not pollutants:
        return None
    bits: list[str] = []
    if readings:
        bits.append(f"AQHI across BC stations {min(readings):.0f}-{max(readings):.0f}")
    if pollutants and pollutants.get("pm25") is not None:
        bits.append(f"PM2.5 near Kamloops {float(pollutants['pm25']):.0f} µg/m³")
    return "Air quality: " + ", ".join(bits) if bits else None


def _weather_line() -> str | None:
    snapshot = _data.weather_current()
    context = _data.season_context()
    if snapshot is None:
        return None
    dry = context.get("days_since_5mm_rain")
    return (
        f"Kamloops now: {float(snapshot.get('temp_c') or 0):.0f} °C, "
        f"RH {float(snapshot.get('rh_pct') or 0):.0f}%, "
        f"wind {float(snapshot.get('wind_kmh') or 0):.0f} km/h"
        + (f"; {dry} days since ≥5 mm rain" if dry is not None else "")
    )


#: Each line is independent. One failing source must not cost the brief its
#: other five, so failures are logged and dropped.
_LINES = (
    ("risk", _risk_line),
    ("fires", _fires_line),
    ("evac", _evac_line),
    ("air", _air_line),
    ("weather", _weather_line),
)


def build_brief() -> str:
    """Render the current situation brief. Blocking; call in a thread."""
    global _cache

    now = time.monotonic()
    if _cache is not None and _cache[0] > now:
        return _cache[1]

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [f"Situation brief, generated {stamp}:"]
    for name, fn in _LINES:
        try:
            if line := fn():
                lines.append(f"- {line}")
        except Exception as exc:
            log.warning("assistant.brief.line_failed", line=name, error=str(exc))

    if len(lines) == 1:
        lines.append("- No live data is loaded on this deployment; rely on tools and say so.")

    text = "\n".join(lines)
    _cache = (now + _TTL_SECONDS, text)
    return text


def invalidate() -> None:
    """Drop the cached brief. Used by tests."""
    global _cache
    _cache = None


def brief_metadata() -> dict[str, Any]:
    """Whether a brief can currently be built, for the health endpoint."""
    return {"cached": _cache is not None, "ttl_seconds": _TTL_SECONDS}
