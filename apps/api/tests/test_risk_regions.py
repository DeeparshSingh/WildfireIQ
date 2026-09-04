"""Multi-region risk grid: config integrity, artifacts, and serving contract.

The risk grid is the most intricate part of the platform: one pooled model
scores four regions, each from its own weather, and every H3 cell must
belong to exactly one region. These tests lock that invariant set so a
future change cannot silently double-count a cell, drop a region, or let
the per-region badge drift away from the hexagons drawn on the map.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from wildfireiq_api.constants import REGIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = REPO_ROOT / "data" / "processed"

CLASS_ORDER = ["Low", "Moderate", "High", "Extreme"]


# ─── Region configuration ─────────────────────────────────────────────


def test_region_config_is_well_formed() -> None:
    assert len(REGIONS) >= 2, "multi-region model needs at least two regions"
    keys = [r["key"] for r in REGIONS]
    assert len(keys) == len(set(keys)), "region keys must be unique"

    for r in REGIONS:
        for field in ("key", "label", "lat", "lon", "bbox", "weather_file"):
            assert field in r, f"{r.get('key')} missing {field}"
        w, s, e, n = r["bbox"]
        assert w < e, f"{r['key']} bbox west must be < east"
        assert s < n, f"{r['key']} bbox south must be < north"
        # Anchor city must sit inside its own bbox, otherwise the region is
        # scored on weather from somewhere else.
        assert s <= r["lat"] <= n, f"{r['key']} anchor lat outside bbox"
        assert w <= r["lon"] <= e, f"{r['key']} anchor lon outside bbox"


def test_region_weather_files_are_distinct() -> None:
    """Two regions sharing a weather file would score identically."""
    files = [r["weather_file"] for r in REGIONS]
    assert len(files) == len(set(files))


# ─── Built artifacts ──────────────────────────────────────────────────


def _density() -> pd.DataFrame:
    p = PROCESSED / "cell_density.parquet"
    if not p.exists():
        pytest.skip("cell_density.parquet not built; run `make risk-features`")
    return pd.read_parquet(p)


def test_density_covers_every_region_with_a_base_rate() -> None:
    d = _density()
    for col in ("h3_cell", "region", "region_label", "region_fire_rate", "weight"):
        assert col in d.columns, f"cell_density missing {col}"

    present = set(d["region"].unique())
    expected = {r["key"] for r in REGIONS if (PROCESSED / r["weather_file"]).exists()}
    assert present == expected, f"regions in density {present} != buildable {expected}"

    for key, grp in d.groupby("region"):
        rate = grp["region_fire_rate"].unique()
        assert len(rate) == 1, f"{key} has multiple base rates"
        assert 0.0 <= float(rate[0]) <= 1.0, f"{key} base rate out of range"


def test_every_cell_belongs_to_exactly_one_region() -> None:
    """Region bboxes may touch; the builder resolves overlap by region order.
    A duplicated H3 cell would render two hexagons with different colours."""
    d = _density()
    dupes = d["h3_cell"].duplicated().sum()
    assert dupes == 0, f"{dupes} H3 cells claimed by more than one region"


def test_density_weights_are_normalised() -> None:
    d = _density()
    assert (d["weight"] >= 0).all()
    assert (d["weight"] <= 1.0000001).all(), "weight must be a 0..1 fraction"
    assert (d["hist_fire_count"] >= 0).all()


def test_region_weather_archives_share_the_model_schema() -> None:
    required = {"day_local", "temp_max_c", "rh_min_pct", "wind_max_kmh", "precip_mm"}
    checked = 0
    for r in REGIONS:
        p = PROCESSED / r["weather_file"]
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        missing = required - set(df.columns)
        assert not missing, f"{r['weather_file']} missing {missing}"
        assert len(df) > 1000, f"{r['weather_file']} suspiciously short"
        checked += 1
    if checked == 0:
        pytest.skip("no region weather archives built yet")


# ─── Serving contract ─────────────────────────────────────────────────


def _grid() -> dict:
    from wildfireiq_api.ml.risk_infer import predict_grid

    g = predict_grid()
    if g is None:
        pytest.skip("risk artifacts not available; run `make risk-features`")
    return g


def test_grid_tags_every_cell_with_a_known_region() -> None:
    g = _grid()
    known = {r["key"] for r in g["regions"]}
    assert known, "grid returned no regions"
    for c in g["cells"]:
        assert c["region"] in known, f"cell {c['h3_cell']} has unknown region"
        assert c["region_label"], "cell missing a human-readable region label"


def test_grid_probabilities_and_classes_are_sane() -> None:
    g = _grid()
    for c in g["cells"]:
        assert 0.0 <= c["p_region"] <= 1.0
        assert 0.0 <= c["p_cell"] <= 1.0
        # A cell can never be riskier than its region's own probability.
        assert c["p_cell"] <= c["p_region"] + 1e-9
        assert c["risk_class"] in CLASS_ORDER


def test_each_region_scores_on_its_own_weather() -> None:
    """Distinct regions should not all report the identical probability and
    FWI; that would mean they are reading the same weather series."""
    g = _grid()
    if len(g["regions"]) < 2:
        pytest.skip("only one region built")
    fwis = {round(r["fwi_today"], 4) for r in g["regions"]}
    assert len(fwis) > 1, "every region reported the same FWI"


def test_region_risk_level_matches_the_rendered_hexagons() -> None:
    """The badge is the highest class covering >=15% of a region's cells.
    If this drifts, the card contradicts the map (the exact bug that made
    Vancouver read 'Extreme' while its hexagons were green)."""
    g = _grid()
    by_region: dict[str, list[str]] = {}
    for c in g["cells"]:
        by_region.setdefault(c["region"], []).append(c["risk_class"])

    for r in g["regions"]:
        classes = by_region[r["key"]]
        n = len(classes)
        expected = "Low"
        for cls in CLASS_ORDER:
            if classes.count(cls) / n >= 0.15:
                expected = cls
        assert r["risk_level"] == expected, (
            f"{r['key']} badge {r['risk_level']} != map-derived {expected}"
        )


def test_region_summaries_are_complete() -> None:
    g = _grid()
    for r in g["regions"]:
        for field in (
            "key",
            "label",
            "lat",
            "lon",
            "p_region",
            "fwi_today",
            "risk_level",
            "cffdrs_class",
            "observation_day",
            "n_cells",
        ):
            assert field in r, f"{r.get('key')} summary missing {field}"
        assert r["n_cells"] > 0
        assert r["risk_level"] in CLASS_ORDER


def test_home_region_geometry_is_not_duplicated() -> None:
    """The Thompson-Okanagan bbox appeared in three places: constants.BBOX,
    Settings.bbox_*, and REGIONS[0]. Editing one silently disagreed with the
    others; they now derive from the constants."""
    from wildfireiq_api import constants
    from wildfireiq_api.settings import get_settings

    s = get_settings()
    home = REGIONS[0]
    assert home["key"] == "thompson_okanagan", "the home region must stay first"
    assert tuple(home["bbox"]) == constants.BBOX
    assert (s.bbox_west, s.bbox_south, s.bbox_east, s.bbox_north) == constants.BBOX
    assert (home["lat"], home["lon"]) == (constants.KAMLOOPS_LAT, constants.KAMLOOPS_LON)
    assert (s.kamloops_lat, s.kamloops_lon) == (constants.KAMLOOPS_LAT, constants.KAMLOOPS_LON)
