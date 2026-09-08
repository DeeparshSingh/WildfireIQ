"""AI wildfire risk grid, served by the pooled multi-region LightGBM model."""

from typing import Any

from fastapi import APIRouter, HTTPException

from ..ml.risk_infer import predict_grid
from ._envelope import Envelope, Meta

router = APIRouter()


@router.get("/grid", summary="Full multi-region risk grid")
async def grid() -> dict[str, Any]:
    payload = predict_grid()
    if payload is None:
        raise HTTPException(
            503,
            "Risk model artifacts not found. Run `uv run python -m wildfireiq_api.ml.train_risk`.",
        )
    n_regions = len(payload.get("regions", []))
    n_cells = len(payload.get("cells", []))
    return Envelope[dict](
        data=payload,
        meta=Meta(
            source="wildfire_risk_v1",
            attribution="LightGBM · pooled multi-region, 1999-2021 train, 2022 val, 2023 test. Per-region held-out PR-AUC reported in the model card.",
            note=f"{n_cells} H3 r=5 cells across {n_regions} regions",
        ),
    ).model_dump(mode="json")
