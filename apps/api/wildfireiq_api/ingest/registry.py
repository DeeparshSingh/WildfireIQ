"""Central registry of every ingest job, by name."""

from __future__ import annotations

from .base import IngestJob
from .bcem_evac import BCEMEvacuationJob
from .climatedata_projections import ClimateDataProjectionsJob
from .cwfis_fwi import CWFISFWIDailyJob
from .databc_fires_current import DataBCFiresCurrentJob
from .databc_fires_historical import DataBCFiresHistoricalJob
from .derived_fwi import DerivedFWIStationsJob
from .derived_region_weather import DerivedRegionWeatherJob
from .derived_risk_features import DerivedRiskFeaturesJob
from .derived_seasonal_metrics import DerivedSeasonalMetricsJob
from .firework_smoke import FireWorkSmokeForecastJob
from .firms_hotspots import FIRMSHotspotsJob
from .geomet_aqhi import GeoMetAQHIRealtimeJob
from .open_meteo import OpenMeteoArchiveBootstrapJob, OpenMeteoKamloopsJob
from .open_meteo_aq import OpenMeteoAQArchiveJob, OpenMeteoAQHourlyJob
from .waqi import WAQIKamloopsJob


def all_jobs() -> dict[str, IngestJob]:
    """Return every ingest job, keyed by `.name`."""
    instances: list[IngestJob] = [
        DataBCFiresCurrentJob(),
        FIRMSHotspotsJob(),
        DataBCFiresHistoricalJob(),
        OpenMeteoKamloopsJob(),
        OpenMeteoArchiveBootstrapJob(),
        OpenMeteoAQHourlyJob(),
        OpenMeteoAQArchiveJob(),
        CWFISFWIDailyJob(),
        DerivedFWIStationsJob(),
        GeoMetAQHIRealtimeJob(),
        WAQIKamloopsJob(),
        FireWorkSmokeForecastJob(),
        BCEMEvacuationJob(),
        ClimateDataProjectionsJob(),
        DerivedRegionWeatherJob(),
        DerivedSeasonalMetricsJob(),
        DerivedRiskFeaturesJob(),
    ]
    return {j.name: j for j in instances}


def scheduled_jobs() -> list[IngestJob]:
    """Jobs that should run on a recurring schedule (have a cadence)."""
    return [j for j in all_jobs().values() if j.cadence]


def bootstrap_jobs() -> list[IngestJob]:
    """One-shot bootstrap jobs (cadence is None)."""
    return [j for j in all_jobs().values() if j.cadence is None]


def with_dependents(jobs: list[IngestJob]) -> list[IngestJob]:
    """Add every recurring job that reads the output of one already selected.

    Freshness is judged per job, which on its own is not enough: a derived job
    can look fresh while the inputs it reads are being rebuilt in the same
    pass, leaving its output older than its sources. Whenever a job runs, so
    must everything downstream of it.
    """
    selected = {j.name: j for j in jobs}

    changed = True
    while changed:
        changed = False
        for job in scheduled_jobs():
            if job.name in selected:
                continue
            if any(dep in selected for dep in job.depends_on):
                selected[job.name] = job
                changed = True

    return list(selected.values())


def dependency_waves(jobs: list[IngestJob]) -> list[list[IngestJob]]:
    """Group `jobs` into waves that can each run fully in parallel.

    Wave 0 holds everything with no unmet dependency inside the selection;
    wave 1 holds jobs whose dependencies all landed in wave 0, and so on.
    Dependencies on jobs outside the selection (a bootstrap, or a job that
    is already fresh) are treated as satisfied.

    Raises ValueError on an unknown dependency name or a cycle, so a typo
    surfaces at startup rather than as silently reordered data.
    """
    known = all_jobs()
    for j in jobs:
        for dep in j.depends_on:
            if dep not in known:
                raise ValueError(f"job {j.name!r} depends on unknown job {dep!r}")

    pending = {j.name: j for j in jobs}
    waves: list[list[IngestJob]] = []
    settled: set[str] = set()

    while pending:
        ready = [
            j
            for j in pending.values()
            if all(dep in settled or dep not in pending for dep in j.depends_on)
        ]
        if not ready:
            raise ValueError(f"dependency cycle among ingest jobs: {sorted(pending)}")
        ready.sort(key=lambda j: j.name)
        waves.append(ready)
        for j in ready:
            settled.add(j.name)
            del pending[j.name]

    return waves
