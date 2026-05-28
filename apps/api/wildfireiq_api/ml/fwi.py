"""Canadian Forest Fire Weather Index (FWI) System — vectorised pandas port.

Reference: Van Wagner & Pickett (1985) "Equations and FORTRAN program for the
Canadian Forest Fire Weather Index System". Information Report PI-X-3, Petawawa
National Forestry Institute, Canadian Forestry Service.

Computes the standard six FWI codes from daily noon-LST weather observations:
  FFMC — Fine Fuel Moisture Code
  DMC  — Duff Moisture Code
  DC   — Drought Code
  ISI  — Initial Spread Index
  BUI  — Buildup Index
  FWI  — Fire Weather Index

Why this exists: NRCan's CWFIS GeoServer (the primary source for live FWI) has
been returning HTTP 502 for the entire build window. Computing FWI ourselves
removes the dependency entirely and gives us per-day FWI for our 27-year
weather archive, which is the actual feature we need for the risk classifier.

Inputs (per row, daily noon-LST values):
  temp_c   — temperature (°C)
  rh_pct   — relative humidity (%, 0–100)
  wind_kmh — 10 m wind speed (km/h)
  precip_mm — 24-hour precip ending at noon (mm)
  month    — calendar month (1–12) — used for daylength/effective day length

Outputs: dataframe with ffmc, dmc, dc, isi, bui, fwi, dsr columns.

The carryover values (FFMC/DMC/DC) are sequential — yesterday's value feeds
into today's. We seed with the canonical Van Wagner spring start values
(FFMC=85, DMC=6, DC=15).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Day-length factors from Van Wagner (1987), for ~50° N latitude (lat 46–54).
# Index 0 unused; 1–12 = Jan–Dec.
DAYLENGTH_DMC = np.array(
    [0, 6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0]
)
DAYLENGTH_DC = np.array(
    [0, -1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6]
)


def _ffmc_one(ffmc_prev: float, t: float, rh: float, w: float, p: float) -> float:
    """One-day FFMC update. All inputs scalars."""
    rh = min(rh, 100.0)
    mo = 147.2 * (101.0 - ffmc_prev) / (59.5 + ffmc_prev)
    if p > 0.5:
        rf = p - 0.5
        mr = mo + 42.5 * rf * np.exp(-100.0 / (251.0 - mo)) * (1.0 - np.exp(-6.93 / rf))
        if mo > 150.0:
            mr += 0.0015 * (mo - 150.0) ** 2 * np.sqrt(rf)
        mo = min(mr, 250.0)
    ed = (
        0.942 * rh**0.679
        + 11.0 * np.exp((rh - 100.0) / 10.0)
        + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * rh))
    )
    if mo > ed:
        ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * np.sqrt(w) * (
            1.0 - (rh / 100.0) ** 8
        )
        kd = ko * 0.581 * np.exp(0.0365 * t)
        m = ed + (mo - ed) * 10.0 ** (-kd)
    else:
        ew = (
            0.618 * rh**0.753
            + 10.0 * np.exp((rh - 100.0) / 10.0)
            + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * rh))
        )
        if mo < ew:
            kl = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * np.sqrt(w) * (
                1.0 - ((100.0 - rh) / 100.0) ** 8
            )
            kw = kl * 0.581 * np.exp(0.0365 * t)
            m = ew - (ew - mo) * 10.0 ** (-kw)
        else:
            m = mo
    return float(59.5 * (250.0 - m) / (147.2 + m))


def _dmc_one(dmc_prev: float, t: float, rh: float, p: float, month: int) -> float:
    rh = min(rh, 100.0)
    if p > 1.5:
        re = 0.92 * p - 1.27
        mo = 20.0 + np.exp(5.6348 - dmc_prev / 43.43)
        if dmc_prev <= 33.0:
            b = 100.0 / (0.5 + 0.3 * dmc_prev)
        elif dmc_prev <= 65.0:
            b = 14.0 - 1.3 * np.log(dmc_prev)
        else:
            b = 6.2 * np.log(dmc_prev) - 17.2
        mr = mo + 1000.0 * re / (48.77 + b * re)
        pr = 244.72 - 43.43 * np.log(mr - 20.0)
        dmc_after_rain = max(pr, 0.0)
    else:
        dmc_after_rain = dmc_prev
    if t < -1.1:
        t = -1.1
    le = DAYLENGTH_DMC[month]
    k = 1.894 * (t + 1.1) * (100.0 - rh) * le * 1e-6
    return float(dmc_after_rain + 100.0 * k)


def _dc_one(dc_prev: float, t: float, p: float, month: int) -> float:
    if p > 2.8:
        rd = 0.83 * p - 1.27
        qo = 800.0 * np.exp(-dc_prev / 400.0)
        qr = qo + 3.937 * rd
        dr = 400.0 * np.log(800.0 / qr)
        dc_after_rain = max(dr, 0.0)
    else:
        dc_after_rain = dc_prev
    if t < -2.8:
        t = -2.8
    v = 0.36 * (t + 2.8) + DAYLENGTH_DC[month]
    if v < 0.0:
        v = 0.0
    return float(dc_after_rain + 0.5 * v)


def _isi_one(ffmc: float, w: float) -> float:
    mo = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
    ff = 19.115 * np.exp(mo * -0.1386) * (1.0 + mo**5.31 / 4.93e7)
    return float(ff * np.exp(0.05039 * w))


def _bui_one(dmc: float, dc: float) -> float:
    if dmc <= 0.4 * dc:
        if dc <= 0.0:
            return 0.0
        bui = 0.8 * dmc * dc / (dmc + 0.4 * dc)
    else:
        denom = dmc + 0.4 * dc
        if denom <= 0:
            return 0.0
        bui = dmc - (1.0 - 0.8 * dc / denom) * (0.92 + (0.0114 * dmc) ** 1.7)
    return float(max(bui, 0.0))


def _fwi_one(isi: float, bui: float) -> float:
    if bui <= 80.0:
        fd = 0.626 * bui**0.809 + 2.0
    else:
        fd = 1000.0 / (25.0 + 108.64 * np.exp(-0.023 * bui))
    b = 0.1 * isi * fd
    if b > 1.0:
        return float(np.exp(2.72 * (0.434 * np.log(b)) ** 0.647))
    return float(b)


def compute_fwi(
    df: pd.DataFrame,
    *,
    temp_col: str = "temp_max_c",
    rh_col: str = "rh_min_pct",
    wind_col: str = "wind_max_kmh",
    precip_col: str = "precip_mm",
    date_col: str = "day_local",
    ffmc_start: float = 85.0,
    dmc_start: float = 6.0,
    dc_start: float = 15.0,
) -> pd.DataFrame:
    """Iterate row-by-row in chronological order, producing FWI columns.

    Carryover values are reset each calendar year to the canonical spring
    start (April 1 conventions): FFMC=85, DMC=6, DC=15.
    """
    df = df.sort_values(date_col).reset_index(drop=True).copy()
    df[date_col] = pd.to_datetime(df[date_col])

    ffmc_prev = ffmc_start
    dmc_prev = dmc_start
    dc_prev = dc_start
    last_year: int | None = None

    ffmc_out: list[float] = []
    dmc_out: list[float] = []
    dc_out: list[float] = []
    isi_out: list[float] = []
    bui_out: list[float] = []
    fwi_out: list[float] = []
    dsr_out: list[float] = []

    for _, row in df.iterrows():
        d = row[date_col]
        if not isinstance(d, pd.Timestamp):
            d = pd.Timestamp(d)
        year = d.year
        month = d.month

        # Seasonal reset: spring start of each year for the carryover codes.
        # Months Dec–Mar fall back to start values (snow/winter pattern).
        if last_year is None or year != last_year or month <= 3 or month == 12:
            ffmc_prev = ffmc_start
            dmc_prev = dmc_start
            dc_prev = dc_start
            last_year = year

        t = float(row.get(temp_col, np.nan))
        rh = float(row.get(rh_col, np.nan))
        w = float(row.get(wind_col, np.nan))
        p = float(row.get(precip_col, 0.0) or 0.0)

        if np.isnan(t) or np.isnan(rh) or np.isnan(w):
            ffmc_out.append(np.nan); dmc_out.append(np.nan); dc_out.append(np.nan)
            isi_out.append(np.nan); bui_out.append(np.nan); fwi_out.append(np.nan)
            dsr_out.append(np.nan)
            continue

        ffmc = _ffmc_one(ffmc_prev, t, rh, w, p)
        dmc = _dmc_one(dmc_prev, t, rh, p, month)
        dc = _dc_one(dc_prev, t, p, month)
        isi = _isi_one(ffmc, w)
        bui = _bui_one(dmc, dc)
        fwi = _fwi_one(isi, bui)
        dsr = 0.0272 * (fwi**1.77)

        ffmc_out.append(ffmc); dmc_out.append(dmc); dc_out.append(dc)
        isi_out.append(isi); bui_out.append(bui); fwi_out.append(fwi)
        dsr_out.append(dsr)

        ffmc_prev, dmc_prev, dc_prev = ffmc, dmc, dc

    out = df.assign(
        ffmc=ffmc_out, dmc=dmc_out, dc=dc_out,
        isi=isi_out, bui=bui_out, fwi=fwi_out, dsr=dsr_out,
    )
    return out
