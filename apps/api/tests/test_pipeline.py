"""Ingest pipeline integrity: the job graph, its cadences, and its ordering.

Nineteen jobs feed each other through parquet files on disk. Nothing in the
runtime notices if a derived job starts reading an input that has not been
rebuilt yet, so the ordering rules live here instead: the graph must be
acyclic, every declared dependency must name a real job, and the nightly
cron times must agree with the graph they are supposed to encode.
"""

from __future__ import annotations

import pytest
from apscheduler.triggers.cron import CronTrigger

from wildfireiq_api.ingest.registry import (
    all_jobs,
    bootstrap_jobs,
    dependency_waves,
    scheduled_jobs,
)


def test_job_names_are_unique_and_registry_partitions_cleanly() -> None:
    jobs = all_jobs()
    assert len(jobs) == len(scheduled_jobs()) + len(bootstrap_jobs())
    for name, job in jobs.items():
        assert job.name == name, f"{name} keyed under a different name"
        assert job.label, f"{name} has no human-readable label"


def test_every_cadence_is_a_valid_cron_expression() -> None:
    for job in scheduled_jobs():
        assert job.cadence is not None
        CronTrigger.from_crontab(job.cadence, timezone="UTC")


def test_bootstrap_jobs_have_no_cadence() -> None:
    for job in bootstrap_jobs():
        assert job.cadence is None


# ─── The dependency graph ─────────────────────────────────────────────


def test_declared_dependencies_all_name_real_jobs() -> None:
    known = set(all_jobs())
    for job in all_jobs().values():
        for dep in job.depends_on:
            assert dep in known, f"{job.name} depends on unknown job {dep!r}"
        assert job.name not in job.depends_on, f"{job.name} depends on itself"


def test_dependency_waves_cover_every_job_exactly_once() -> None:
    jobs = scheduled_jobs()
    waves = dependency_waves(jobs)
    flat = [j.name for w in waves for j in w]
    assert sorted(flat) == sorted(j.name for j in jobs)
    assert len(flat) == len(set(flat)), "a job appears in two waves"


def test_a_dependency_never_lands_in_the_same_or_a_later_wave() -> None:
    """This is the invariant the startup catch-up relies on."""
    jobs = scheduled_jobs()
    waves = dependency_waves(jobs)
    wave_of = {j.name: i for i, w in enumerate(waves) for j in w}

    for job in jobs:
        for dep in job.depends_on:
            if dep not in wave_of:
                continue  # bootstrap, or already fresh — nothing to order
            assert wave_of[dep] < wave_of[job.name], (
                f"{job.name} (wave {wave_of[job.name]}) would run alongside or "
                f"before its input {dep} (wave {wave_of[dep]})"
            )


class _FakeJob:
    """Stand-in for an IngestJob; the wave builder only reads these two."""

    def __init__(self, name: str, depends_on: tuple[str, ...]) -> None:
        self.name = name
        self.depends_on = depends_on


def test_a_cycle_is_reported_rather_than_silently_reordered() -> None:
    # Real job names, so the failure under test is the cycle itself and not
    # the unknown-dependency check firing first.
    pair = [
        _FakeJob("derived_fires_unified", ("derived_risk_features",)),
        _FakeJob("derived_risk_features", ("derived_fires_unified",)),
    ]
    with pytest.raises(ValueError, match="cycle"):
        dependency_waves(pair)  # type: ignore[arg-type]


def test_unknown_dependency_is_rejected() -> None:
    bogus = [_FakeJob("derived_fires_unified", ("no_such_job",))]
    with pytest.raises(ValueError, match="unknown job"):
        dependency_waves(bogus)  # type: ignore[arg-type]


# ─── Cadences agree with the graph ───────────────────────────────────


def _daily_minute_of_day(cadence: str) -> int | None:
    """Minutes past midnight for a `M H * * *` cadence, else None."""
    parts = cadence.split()
    if len(parts) != 5 or parts[2:] != ["*", "*", "*"]:
        return None
    if not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[1]) * 60 + int(parts[0])


def test_nightly_derived_jobs_are_scheduled_after_their_inputs() -> None:
    """The cron times are the first line of defence; the wave ordering is the
    second. If someone retimes a job, this catches the contradiction."""
    jobs = all_jobs()
    checked = 0
    for job in scheduled_jobs():
        assert job.cadence is not None
        mine = _daily_minute_of_day(job.cadence)
        if mine is None:
            continue
        for dep in job.depends_on:
            dep_cadence = jobs[dep].cadence
            if dep_cadence is None:
                continue  # bootstrap
            theirs = _daily_minute_of_day(dep_cadence)
            if theirs is None:
                continue  # runs far more often than daily; always fresh
            assert theirs < mine, (
                f"{job.name} runs at {job.cadence} but its input {dep} runs later at {dep_cadence}"
            )
            checked += 1
    assert checked > 0, "no nightly dependency pairs were actually compared"


def test_derived_risk_features_depends_on_the_region_weather_it_reads() -> None:
    """Regression guard: the multi-region grid is only correct if every
    region's weather archive is rebuilt before the feature matrix is."""
    risk = all_jobs()["derived_risk_features"]
    assert "derived_region_weather" in risk.depends_on
    assert "open_meteo_archive_kamloops" in risk.depends_on
