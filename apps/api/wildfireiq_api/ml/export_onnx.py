"""Convert trained LightGBM models to ONNX for portability.

Phase 3 spec verification step:
  > Both ONNX exports load in `onnxruntime` and produce identical
  > predictions to Python pickles within float32 tolerance.

LightGBM → ONNX conversion uses `onnxmltools.convert_lightgbm`. The
function below converts our wildfire-risk classifier (single model);
the AQ forecaster is 21 separate quantile models and we skip the bundle
conversion (acknowledged in the AQ model card).

Run:
    uv run python -m wildfireiq_api.ml.export_onnx
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
RISK_DIR = REPO_ROOT / "data" / "models" / "wildfire_risk_v1"


def _convert_lightgbm(booster, n_features: int):
    """Convert a LightGBM booster to an ONNX ModelProto."""
    import onnxmltools  # type: ignore
    from onnxmltools.convert.common.data_types import FloatTensorType  # type: ignore

    initial_types = [("input", FloatTensorType([None, n_features]))]
    return onnxmltools.convert_lightgbm(booster, initial_types=initial_types, target_opset=15)


def export_risk_model() -> Path:
    import lightgbm as lgb
    import onnxruntime as ort  # type: ignore

    model_txt = RISK_DIR / "model.txt"
    features_json = RISK_DIR / "features.json"
    if not model_txt.exists():
        raise FileNotFoundError(f"{model_txt} — train the risk model first (`make train-risk`)")

    booster = lgb.Booster(model_file=str(model_txt))
    features = json.loads(features_json.read_text())
    n = len(features)

    onnx_model = _convert_lightgbm(booster, n)
    out = RISK_DIR / "model.onnx"
    with out.open("wb") as f:
        f.write(onnx_model.SerializeToString())

    # Parity check: LightGBM prediction == ONNX prediction within float32 tolerance.
    rng = np.random.default_rng(7)
    X = rng.normal(size=(32, n)).astype(np.float32)
    py_pred = booster.predict(X)

    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    onnx_pred = sess.run(None, {"input": X})
    # ONNX classifier returns (labels, probabilities). The probabilities are
    # a list-of-dicts in some versions; pick the positive-class column.
    if isinstance(onnx_pred[1], list):
        onnx_prob = np.array([p[1] for p in onnx_pred[1]], dtype=np.float64)
    else:
        onnx_prob = np.asarray(onnx_pred[1])[:, 1].astype(np.float64)

    max_abs_diff = float(np.max(np.abs(py_pred - onnx_prob)))
    print(f"wildfire_risk_v1 → {out}")
    print(f"  parity: max |Δ| over 32 random rows = {max_abs_diff:.2e}")
    if max_abs_diff > 1e-4:
        print("  ⚠️  Parity worse than 1e-4. Investigate before relying on the ONNX export.")
    return out


def _main() -> None:
    export_risk_model()


if __name__ == "__main__":
    _main()
