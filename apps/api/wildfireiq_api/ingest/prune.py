"""Trim `data/raw/` to each job's retention limit.

Snapshots are pruned automatically after every run, so this exists for the
one-off case: a repo that has been ingesting for months under an older build
with no cap, or a disk that needs reclaiming now rather than at the next tick.

    make prune-raw
"""

from __future__ import annotations

from .registry import all_jobs


def main() -> None:
    total = 0
    for name, job in sorted(all_jobs().items()):
        if job.raw_retention is None:
            print(f"{name:30s} keep all")
            continue
        removed = job.prune_raw()
        total += removed
        print(f"{name:30s} keep {job.raw_retention:>3}  removed {removed}")
    print(f"\n{total} raw snapshots removed")


if __name__ == "__main__":
    main()
