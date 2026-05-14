"""Historical climate + CMIP6 projections (Phase 6).

Backed by:
  • `data/processed/seasonal_metrics.parquet` — built by
    `wildfireiq_api.ml.seasonal_metrics`. Per-year joined fire + weather +
    Van Wagner FWI metrics for the Thompson-Okanagan.
  • `data/processed/climate_projections.parquet` — CMIP6 ensemble
    placeholder (observed + ssp126 + ssp245 + ssp585) shipped from Phase 1.

Every endpoint accepts `?format=csv` to return a `text/csv` body — that's
what powers the "Download CSV" buttons in the Climate Trend page.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response

from . import _data
from ._envelope import Envelope, Meta
from ..ml.trends import theil_sen_with_ci

router = APIRouter()


# ─── Helpers ───────────────────────────────────────────────────────────


def _to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    keys = sorted({k for r in rows for k in r.keys()})
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=keys)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in keys})
    return out.getvalue()


def _envelope_or_csv(
    rows: list[dict[str, Any]],
    *,
    fmt: str,
    source: str,
    attribution: str,
    note: str | None = None,
) -> Any:
    if fmt == "csv":
        return Response(
            content=_to_csv(rows),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=climate.csv"},
        )
    return Envelope[list](
        data=rows,
        meta=Meta(source=source, attribution=attribution, phase="6", note=note),
    ).model_dump(mode="json")


# ─── Endpoints ─────────────────────────────────────────────────────────


@router.get("/seasonal", summary="Per-year fire+climate metrics, 1999-present")
async def seasonal(format: str = "json") -> Any:  # noqa: A002
    rows = _data.seasonal_metrics()
    return _envelope_or_csv(
        rows,
        fmt=format,
        source="seasonal_metrics",
        attribution="BC Wildfire Service · Open-Meteo ERA5 · WildfireIQ Van Wagner FWI",
        note=None if rows else "Run `uv run python -m wildfireiq_api.ml.seasonal_metrics` to build.",
    )


@router.get("/trends", summary="Theil-Sen slopes + bootstrap 95% CI for key metrics")
async def trends() -> dict[str, Any]:
    rows = _data.seasonal_metrics()
    if not rows:
        return Envelope[dict](
            data={},
            meta=Meta(source="seasonal_metrics", attribution="", phase="6",
                       note="No seasonal metrics yet."),
        ).model_dump(mode="json")

    import numpy as np

    yrs = np.array([r["year"] for r in rows], dtype=float)

    metrics_to_trend = [
        "mean_jul_temp_c",
        "julaug_precip_mm",
        "mean_julaug_vpd_kpa",
        "max_julaug_fwi",
        "days_fwi_ge_19",
        "area_burned_ha",
        "season_length_days",
    ]
    out: dict[str, Any] = {}
    for m in metrics_to_trend:
        vals = np.array([r.get(m) if r.get(m) is not None else np.nan for r in rows], dtype=float)
        t = theil_sen_with_ci(yrs, vals, n_boot=1000)
        out[m] = {
            "slope_per_year": t.slope,
            "intercept": t.intercept,
            "slope_ci_lo": t.slope_ci_lo,
            "slope_ci_hi": t.slope_ci_hi,
            "n_years": t.n,
            "delta_over_span": (
                t.slope * (yrs.max() - yrs.min()) if t.slope == t.slope else float("nan")
            ),
        }

    return Envelope[dict](
        data={"year_min": int(yrs.min()), "year_max": int(yrs.max()), "metrics": out},
        meta=Meta(
            source="seasonal_metrics",
            attribution="Theil-Sen slope · 1000-bootstrap 95% CI",
            phase="6",
        ),
    ).model_dump(mode="json")


@router.get("/ribbon", summary="Fire-season ribbon: first/last DOY per year")
async def ribbon(format: str = "json") -> Any:  # noqa: A002
    rows = _data.seasonal_metrics()
    ribbon_rows = [
        {
            "year": r["year"],
            "start_doy": r.get("season_start_doy"),
            "end_doy": r.get("season_end_doy"),
            "length_days": r.get("season_length_days"),
            "area_burned_ha": r.get("area_burned_ha"),
        }
        for r in rows
        if r.get("season_start_doy") is not None
    ]
    return _envelope_or_csv(
        ribbon_rows,
        fmt=format,
        source="seasonal_metrics",
        attribution="BC Wildfire Service",
    )


@router.get("/projection", summary="Climate projection for a SSP scenario + variable")
async def projection(
    ssp: str = "ssp245",
    var: str = "tasmean",
    format: str = "json",  # noqa: A002
) -> Any:
    rows = _data.climate_projections(ssp=ssp, var=var)
    return _envelope_or_csv(
        rows,
        fmt=format,
        source="climatedata_projections",
        attribution="CMIP6 ensemble placeholder (Phase 1) · ClimateData.ca structure",
        note="Synthetic CMIP6 ensemble — wired for shape; real ensemble swap is a parquet replace.",
    )


@router.get("/projections-all", summary="All SSP scenarios for a single variable")
async def projections_all(var: str = "tasmean") -> dict[str, Any]:
    out: dict[str, list[dict[str, Any]]] = {}
    for s in ("observed", "ssp126", "ssp245", "ssp585"):
        out[s] = _data.climate_projections(ssp=s, var=var)
    return Envelope[dict](
        data={"variable": var, "scenarios": out},
        meta=Meta(
            source="climatedata_projections",
            attribution="CMIP6 ensemble placeholder · ClimateData.ca structure",
            phase="6",
            note="Phase 1 synthetic placeholder; real CMIP6 ensemble drop-in is a parquet replace.",
        ),
    ).model_dump(mode="json")


@router.get("/fwi-projection", summary="Heuristic FWI≥19 days by decade")
async def fwi_projection() -> dict[str, Any]:
    """Coarse extrapolation: fit historical `days_fwi_ge_19 ~ mean_jul_temp_c`
    then evaluate it on each SSP scenario's projected July temperature by
    decade. Explicitly disclosed as a heuristic, not a physics model run.
    """
    import numpy as np

    rows = _data.seasonal_metrics()
    if not rows:
        return Envelope[dict](
            data={},
            meta=Meta(source="fwi_projection", attribution="", phase="6", note="No data"),
        ).model_dump(mode="json")

    T = np.array([r.get("mean_jul_temp_c", np.nan) for r in rows], dtype=float)
    D = np.array([r.get("days_fwi_ge_19", np.nan) for r in rows], dtype=float)
    mask = np.isfinite(T) & np.isfinite(D)
    T = T[mask]
    D = D[mask]
    if len(T) < 5:
        return Envelope[dict](
            data={},
            meta=Meta(source="fwi_projection", attribution="", phase="6", note="Not enough data"),
        ).model_dump(mode="json")

    A = np.vstack([T, np.ones_like(T)]).T
    slope, intercept = np.linalg.lstsq(A, D, rcond=None)[0]
    baseline_T = float(np.mean(T[-10:]))

    deltas = {"ssp126": 1.0, "ssp245": 1.8, "ssp585": 2.9}
    decades = [2000, 2010, 2020, 2030, 2040]

    def days_for(T_july: float) -> int:
        return max(0, int(round(float(slope) * T_july + float(intercept))))

    out: dict[str, list[dict[str, Any]]] = {}
    for scn, dT in deltas.items():
        scn_rows: list[dict[str, Any]] = []
        for dec in decades:
            if dec <= 2020:
                yrs_in = [r for r in rows if dec <= r["year"] < dec + 10 and r.get("mean_jul_temp_c") is not None]
                if not yrs_in:
                    continue
                Td = float(np.mean([r["mean_jul_temp_c"] for r in yrs_in]))
                obs = True
            else:
                frac = (dec - 2020) / 20.0
                Td = baseline_T + dT * frac
                obs = False
            scn_rows.append({"decade": dec, "july_temp_c": Td, "days_fwi_ge_19": days_for(Td), "observed": obs})
        out[scn] = scn_rows

    return Envelope[dict](
        data={
            "method": (
                "Linear regression of historical July mean temp → days FWI≥19, "
                "evaluated on per-decade July temperatures (observed pre-2020; "
                "baseline + scenario ΔT thereafter). Coarse heuristic, not a "
                "physics-driven projection."
            ),
            "fit": {"slope_days_per_C": float(slope), "intercept": float(intercept), "n": int(len(T))},
            "scenarios": out,
        },
        meta=Meta(
            source="fwi_projection_heuristic",
            attribution="WildfireIQ derived · disclosed as coarse extrapolation",
            phase="6",
        ),
    ).model_dump(mode="json")


@router.get("/tru-carbon", summary="TRU campus carbon (feature-flagged)")
async def tru_carbon() -> dict[str, Any]:
    p = Path(__file__).resolve().parents[4] / "data" / "tru_carbon.csv"
    if not p.exists():
        return Envelope[dict](
            data={"available": False, "rows": []},
            meta=Meta(source="tru_carbon", attribution="TRU Sustainability Office", phase="6",
                      note="data/tru_carbon.csv not present"),
        ).model_dump(mode="json")
    import pandas as pd

    df = pd.read_csv(p)
    return Envelope[dict](
        data={"available": True, "rows": df.to_dict(orient="records")},
        meta=Meta(source="tru_carbon", attribution="TRU Sustainability Office", phase="6"),
    ).model_dump(mode="json")
