"""Abuse and spend controls for the assistant endpoint.

Every other endpoint in this backend reads a parquet file off local disk.
Cost is CPU, the worst case is a slow response, and nothing an anonymous
caller does can produce a bill. `/api/assistant/chat` is the first
endpoint where that stops being true: each request spends real money at a
third-party API, and the platform has no accounts to attribute it to.

So the endpoint gets what the others do not need — three independent
limits, each answering a different failure:

* **Per-caller rate limits** stop one person, or one broken script,
  monopolising it.
* **A rolling 24-hour spend ceiling** stops a distributed burst, or a
  genuinely popular day, from emptying the account. It is the backstop
  that does not care who is calling.
* **A concurrency cap** stops a burst from opening fifty simultaneous
  upstream connections, which would be slow for everyone and might get
  the key rate-limited at OpenRouter instead.

All three are in-process, matching the rest of this backend: one uvicorn
process, no Redis. A multi-process deployment would need shared state,
and that is noted where it matters rather than pretended away.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

#: Callers we have seen recently. Bounded so a spray of distinct source
#: addresses cannot grow the table without limit.
_MAX_TRACKED_CALLERS = 4096

HOUR_S = 3600.0
DAY_S = 86_400.0


@dataclass(frozen=True, slots=True)
class Verdict:
    """Whether a request may proceed, and what to tell the caller if not."""

    allowed: bool
    reason: str | None = None
    retry_after_s: int | None = None


class AssistantGuard:
    """Rate, spend, and concurrency limits for one process."""

    def __init__(
        self,
        *,
        per_minute: int,
        per_hour: int,
        daily_cost_limit_usd: float,
        max_concurrent: int,
    ) -> None:
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.daily_cost_limit_usd = daily_cost_limit_usd
        self.max_concurrent = max_concurrent

        self._lock = threading.Lock()
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._spend: deque[tuple[float, float]] = deque()  # (when, usd)
        self._in_flight = 0

    # ── Admission ───────────────────────────────────────────────────

    def check(self, caller: str, *, now: float | None = None) -> Verdict:
        """Decide whether `caller` may ask a question right now.

        Spend is checked before rate, because a spent-out account is a
        different message from "you are asking too fast" and the caller
        should not be told to retry in a minute when the answer is no for
        the rest of the day.
        """
        now = now if now is not None else time.monotonic()

        with self._lock:
            self._expire(now)

            spent = sum(usd for _, usd in self._spend)
            if spent >= self.daily_cost_limit_usd:
                oldest = self._spend[0][0] if self._spend else now
                retry = max(1, int(DAY_S - (now - oldest)))
                log.warning("assistant.guard.spend_exhausted", spent_usd=round(spent, 4))
                return Verdict(
                    False,
                    "The assistant has reached its daily budget on this deployment. "
                    "It will be available again within 24 hours.",
                    retry,
                )

            if self._in_flight >= self.max_concurrent:
                return Verdict(
                    False,
                    "The assistant is handling as many questions as it can at once. "
                    "Try again in a few seconds.",
                    5,
                )

            history = self._requests[caller]
            recent_minute = sum(1 for t in history if now - t < 60.0)
            if recent_minute >= self.per_minute:
                return Verdict(
                    False,
                    f"That is more than {self.per_minute} questions a minute. Give it a moment.",
                    60,
                )
            if len(history) >= self.per_hour:
                return Verdict(
                    False,
                    f"That is more than {self.per_hour} questions an hour from this "
                    "connection. Try again later.",
                    int(HOUR_S - (now - history[0])) + 1,
                )

            history.append(now)
            self._prune_callers()
            return Verdict(True)

    def _expire(self, now: float) -> None:
        """Drop everything outside its window. Caller holds the lock."""
        for caller, history in list(self._requests.items()):
            while history and now - history[0] > HOUR_S:
                history.popleft()
            if not history:
                del self._requests[caller]
        while self._spend and now - self._spend[0][0] > DAY_S:
            self._spend.popleft()

    def _prune_callers(self) -> None:
        """Bound the caller table. Caller holds the lock.

        Evicting the least recently active is safe: their history has
        already aged, so at worst someone gets a fresh allowance sooner
        than they strictly should — which is the right way for a limiter
        under memory pressure to fail.
        """
        if len(self._requests) <= _MAX_TRACKED_CALLERS:
            return
        oldest = sorted(self._requests, key=lambda c: self._requests[c][-1])
        for caller in oldest[: len(self._requests) - _MAX_TRACKED_CALLERS]:
            del self._requests[caller]

    # ── Concurrency ─────────────────────────────────────────────────

    def enter(self) -> None:
        with self._lock:
            self._in_flight += 1

    def leave(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    # ── Spend ───────────────────────────────────────────────────────

    def record_spend(self, usd: float, *, now: float | None = None) -> None:
        """Book what a completed run actually cost.

        Recorded after the fact, from OpenRouter's own reported charge, so
        the ceiling can be overshot by at most the runs already in flight
        — bounded by `max_concurrent` times the cost of one answer.
        """
        if usd <= 0:
            return
        now = now if now is not None else time.monotonic()
        with self._lock:
            self._spend.append((now, usd))
            self._expire(now)

    def snapshot(self) -> dict[str, float | int]:
        """Current state, for the health endpoint."""
        with self._lock:
            self._expire(time.monotonic())
            return {
                "spent_24h_usd": round(sum(usd for _, usd in self._spend), 4),
                "daily_cost_limit_usd": self.daily_cost_limit_usd,
                "runs_24h": len(self._spend),
                "in_flight": self._in_flight,
                "callers_tracked": len(self._requests),
                "per_minute": self.per_minute,
                "per_hour": self.per_hour,
            }

    def reset(self) -> None:
        """Clear all state. Used by tests."""
        with self._lock:
            self._requests.clear()
            self._spend.clear()
            self._in_flight = 0


_guard: AssistantGuard | None = None


def get_guard() -> AssistantGuard:
    """The process-wide guard, built from settings on first use."""
    global _guard
    if _guard is None:
        from ..settings import get_settings

        settings = get_settings()
        _guard = AssistantGuard(
            per_minute=settings.assistant_rate_per_minute,
            per_hour=settings.assistant_rate_per_hour,
            daily_cost_limit_usd=settings.assistant_daily_cost_limit_usd,
            max_concurrent=settings.assistant_max_concurrent,
        )
    return _guard


def reset_guard() -> None:
    """Drop the singleton so settings are re-read. Used by tests."""
    global _guard
    _guard = None


def caller_id(forwarded_for: str | None, client_host: str | None) -> str:
    """Identify a caller for rate limiting.

    `X-Forwarded-For` is trusted when present because the intended
    deployment is behind a single reverse proxy, which is the only thing
    that can set it there. Directly exposed, the header is caller-supplied
    and spoofable — which is exactly why the spend ceiling exists and does
    not consult it.
    """
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first[:64]
    return (client_host or "unknown")[:64]
