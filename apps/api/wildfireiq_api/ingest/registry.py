"""Central registry of every ingest job, by name."""

from __future__ import annotations

from .base import IngestJob
from .bcem_evac import BCEMEvacuationJob
from .climatedata_projections import ClimateDataProjectionsJob
from .cwfis_fwi import CWFISFWIDailyJob
from .databc_fires_current import DataBCFiresCurrentJob
from .databc_fires_historical import DataBCFiresHistoricalJob
from .derived_fires_unified import DerivedFiresUnifiedJob
from .derived_fwi import DerivedFWIStationsJob
from .derived_seasonal_metrics import DerivedSeasonalMetricsJob
from .eccc_climate import ECCCClimateBulkJob
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
        ECCCClimateBulkJob(),
        CWFISFWIDailyJob(),
        DerivedFWIStationsJob(),
        GeoMetAQHIRealtimeJob(),
        WAQIKamloopsJob(),
        FireWorkSmokeForecastJob(),
        BCEMEvacuationJob(),
        ClimateDataProjectionsJob(),
        DerivedFiresUnifiedJob(),
        DerivedSeasonalMetricsJob(),
    ]
    return {j.name: j for j in instances}


def scheduled_jobs() -> list[IngestJob]:
    """Jobs that should run on a recurring schedule (have a cadence)."""
    return [j for j in all_jobs().values() if j.cadence]


def bootstrap_jobs() -> list[IngestJob]:
    """One-shot bootstrap jobs (cadence is None)."""
    return [j for j in all_jobs().values() if j.cadence is None]
