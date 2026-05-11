"""AI wildfire risk grid — Phase 3 ships the real LightGBM classifier."""

from typing import Any

from fastapi import APIRouter, HTTPException

from ..ml.risk_infer import predict_grid, predict_today_for_cell
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/today", summary="Risk for a single H3 r=5 cell on today's date")
async def today(cell: str | None = None) -> dict[str, Any]:
    if cell is None:
        raise HTTPException(400, "?cell=<h3_index> is required")
    payload = predict_today_for_cell(cell)
    if payload is None:
        raise HTTPException(404, "cell not found in grid")
    return Envelope[dict](
        data=payload,
        meta=Meta(
            source="wildfire_risk_v1",
            attribution="LightGBM, trained on BC Wildfire Service 1999-2021 + ERA5 weather. Validated against held-out 2022 + 2023 fire seasons.",
            phase="3",
        ),
    ).model_dump(mode="json")


@router.get("/grid", summary="Full risk grid for the Thompson-Okanagan")
async def grid() -> dict[str, Any]:
    payload = predict_grid()
    if payload is None:
        raise HTTPException(
            503,
            "Risk model artifacts not found. Run `uv run python -m wildfireiq_api.ml.train_risk`.",
        )
    return Envelope[dict](
        data=payload,
        meta=Meta(
            source="wildfire_risk_v1",
            attribution="LightGBM · 1999-2021 train, 2022 val, 2023 test. PR-AUC 0.66, beats FWI-threshold baseline by 14 points.",
            phase="3",
            note=f"185 H3 r=5 cells, observation day {payload['observation_day'][:10]}",
        ),
    ).model_dump(mode="json")
