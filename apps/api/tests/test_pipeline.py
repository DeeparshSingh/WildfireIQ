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
    with_dependents,
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


# ─── Widening a partial selection ────────────────────────────────────


def test_a_fresh_derived_job_is_pulled_in_when_its_input_reruns() -> None:
    """The bug this guards: on a real cold start every source was stale except
    `derived_risk_features`, which had run 24 minutes earlier. It was skipped
    while the region weather archives it reads were rebuilt, leaving the
    feature matrix older than its own inputs."""
    stale = [j for j in scheduled_jobs() if j.name != "derived_risk_features"]
    selected = with_dependents(stale)
    assert "derived_risk_features" in {j.name for j in selected}


def test_widening_is_transitive() -> None:
    """region weather → risk features is two hops from the Kamloops archive."""
    archive = all_jobs()["open_meteo_archive_kamloops"]
    selected = {j.name for j in with_dependents([archive])}
    assert "derived_region_weather" in selected
    assert "derived_risk_features" in selected


def test_widening_adds_nothing_when_the_selection_is_already_closed() -> None:
    jobs = scheduled_jobs()
    assert {j.name for j in with_dependents(jobs)} == {j.name for j in jobs}

    leaf = all_jobs()["derived_risk_features"]
    assert {j.name for j in with_dependents([leaf])} == {"derived_risk_features"}


def test_widened_selection_still_forms_valid_waves() -> None:
    stale = [j for j in scheduled_jobs() if j.name != "derived_risk_features"]
    waves = dependency_waves(with_dependents(stale))
    wave_of = {j.name: i for i, w in enumerate(waves) for j in w}
    assert wave_of["derived_risk_features"] > wave_of["derived_region_weather"]
    assert wave_of["derived_region_weather"] > wave_of["open_meteo_archive_kamloops"]


def test_the_two_heavy_archive_pulls_never_share_a_wave() -> None:
    """Both issue the same 27-year query against Open-Meteo's archive host.
    Running them together earned an HTTP 429 and silently lost two regions."""
    waves = dependency_waves(scheduled_jobs())
    wave_of = {j.name: i for i, w in enumerate(waves) for j in w}
    assert wave_of["derived_region_weather"] != wave_of["open_meteo_archive_kamloops"]


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


# ─── Raw snapshot retention ──────────────────────────────────────────


def test_every_recurring_job_caps_its_raw_snapshots() -> None:
    """Unbounded raw snapshots filled 1.3 GB in four months of running:
    bcem_evac writes a GeoJSON every 5 minutes and nothing pruned it."""
    for job in scheduled_jobs():
        assert job.raw_retention is not None, f"{job.name} keeps raw forever"
        assert job.raw_retention >= 1


def test_prune_raw_keeps_the_newest_and_handles_both_shapes(tmp_path) -> None:
    import os

    from wildfireiq_api.ingest import base

    monkey = tmp_path / "raw"
    original = base.RAW_ROOT
    base.RAW_ROOT = monkey
    try:
        job = all_jobs()["bcem_evac"]
        job.raw_retention = 3
        d = monkey / job.name
        d.mkdir(parents=True)

        # Five flat snapshots plus five directory snapshots, oldest first.
        for i in range(5):
            f = d / f"snap{i}.geojson"
            f.write_text("{}")
            os.utime(f, (1_700_000_000 + i, 1_700_000_000 + i))
        for i in range(5):
            sub = d / f"dir{i}"
            sub.mkdir()
            (sub / "part.csv").write_text("a,b")
            os.utime(sub, (1_700_000_100 + i, 1_700_000_100 + i))

        removed = job.prune_raw()
        left = sorted(p.name for p in d.iterdir())
        assert removed == 7
        assert left == ["dir2", "dir3", "dir4"], left
        assert (d / "dir4" / "part.csv").exists(), "kept snapshot lost its contents"
        assert job.prune_raw() == 0, "pruning twice should be a no-op"
    finally:
        # all_jobs() builds fresh instances per call, so the retention override
        # above dies with this one; only RAW_ROOT needs restoring.
        base.RAW_ROOT = original


def test_prune_raw_is_a_no_op_when_retention_is_disabled(tmp_path) -> None:
    from wildfireiq_api.ingest import base

    original = base.RAW_ROOT
    base.RAW_ROOT = tmp_path / "raw"
    try:
        job = all_jobs()["eccc_climate_kamloops"]
        assert job.raw_retention is None
        d = base.RAW_ROOT / job.name
        d.mkdir(parents=True)
        for year in range(1999, 2027):
            (d / f"{year}.csv").write_text("x")
        assert job.prune_raw() == 0
        assert len(list(d.iterdir())) == 28
    finally:
        base.RAW_ROOT = original
