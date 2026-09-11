"""Owner control: who owns this deployment, and how the owner steers it.

Read this first, because it sets expectations honestly.

WHAT THIS CANNOT DO
Nothing in software stops somebody who has both the source code and root on
the machine. They can delete this file, comment out the middleware, or run an
older commit. Any claim otherwise is theatre: a "secret dependency" gets
vendored, an obfuscated check gets patched, a licence check gets stubbed. So
this module does not pretend to be a lock against the host.

WHAT THIS DOES DO, and it is the part that matters
Nobody can *forge the owner's instructions*. Control commands are signed with
an Ed25519 private key that exists only on the owner's own machine; this file
carries the public half. Someone with the server can stop obeying a command,
but they cannot mint one, cannot alter one, and cannot replay an old one to
undo a newer one. Combined with several independent delivery routes, that
gives the owner a say from anywhere, and gives the owner evidence when
somebody has interfered.

THE COMMANDS
A command is one compact line: base64url(payload) + "." + base64url(signature).
The payload is small, readable JSON:

    {"v": 1, "state": "paused", "message": "...",
     "issued_at": "2026-09-11T05:00:00Z", "nonce": "…"}

`state` is one of:
  running   normal service
  readonly  reads work; writes (POST/PUT/PATCH/DELETE on /api/*) are refused
  paused    every /api/* route refuses, except the two below

`/healthz` and `/api/ownership` are never blocked, so a paused deployment can
still be diagnosed — and so the owner can confirm from a phone that the pause
landed.

WHERE COMMANDS COME FROM (all three are checked; the newest valid one wins)
  1. `data/runtime/control.json` — scp a file, or use the CLI on the box
  2. `WILDFIREIQ_CONTROL` env var — break-glass with no filesystem write
  3. `OWNER_CONTROL_URL` — a URL the owner controls (a gist, their own
     domain), polled every few minutes, so the owner can flip state without
     shell access at all

FAIL-OPEN, ON PURPOSE
No command, an unreadable command, a bad signature, an unreachable URL: the
deployment keeps running and the problem is logged loudly. A control system
that fails closed is a control system that eventually locks out its owner,
which is the opposite of the point.

ROLLBACK PROTECTION
The highest `issued_at` ever accepted is remembered in
`data/runtime/control_seen.json`. An older command is refused, so a captured
"running" command cannot be replayed to undo a later "paused". Anyone with
the box can delete that file; that is expected, and it is logged.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .paths import DATA_ROOT

log = structlog.get_logger("owner")

# ── owner identity ───────────────────────────────────────────────────────
#
# The public half of the owner's signing key. The private half lives only on
# the owner's machine (`~/.wildfireiq/owner_ed25519`, mode 0600) and is never
# in this repository.
#
# Changing these two lines is how ownership would transfer. `/api/ownership`
# reports the fingerprint, so comparing what a deployment says against
# `scripts/owner.py whoami` is how the owner checks it is still theirs.
OWNER_NAME: Final[str] = "Deeparsh Singh Dang"
OWNER_PUBLIC_KEY_B64: Final[str] = "pttrY-NjChcESOHEdEGYkZo6syhsDcc_lfYmd3NUMpA"

RUNTIME_ROOT: Final[Path] = DATA_ROOT / "runtime"
CONTROL_PATH: Final[Path] = RUNTIME_ROOT / "control.json"
SEEN_PATH: Final[Path] = RUNTIME_ROOT / "control_seen.json"
LOCAL_STATE_PATH: Final[Path] = RUNTIME_ROOT / "control_local.json"
OWNER_STATE_PATH: Final[Path] = RUNTIME_ROOT / "owner.json"

State = Literal["running", "readonly", "paused"]
VALID_STATES: Final[frozenset[str]] = frozenset({"running", "readonly", "paused"})

#: Prefixes that answer even when the deployment is paused.
#:
#: `/api/ownership` has to include its subpaths, not just the exact path: the
#: route that applies a command lives under it, and blocking that would mean a
#: pause could not be lifted over HTTP. A kill switch that cannot be switched
#: back is a way to lock yourself out of your own deployment.
ALWAYS_OPEN: Final[tuple[str, ...]] = ("/healthz", "/api/ownership")


#: Ed25519 public keys are exactly this long. Checking it turns a mistyped
#: key into a clear "invalid" rather than a plausible-looking fingerprint that
#: then fails every signature check for no visible reason.
_ED25519_PUBLIC_KEY_BYTES: Final[int] = 32


def _b64d(s: str) -> bytes:
    """Strict base64url. `validate=True` matters: without it Python quietly
    discards characters outside the alphabet, so garbage decodes to something
    instead of raising."""
    padded = (s + "=" * (-len(s) % 4)).encode()
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def key_fingerprint(public_key_b64: str | None = None) -> str:
    """A short, human-comparable fingerprint of the owner's public key."""
    public_key_b64 = public_key_b64 or OWNER_PUBLIC_KEY_B64
    from hashlib import sha256

    try:
        raw = _b64d(public_key_b64)
    except Exception:
        return "invalid"
    if len(raw) != _ED25519_PUBLIC_KEY_BYTES:
        return "invalid"
    digest = sha256(raw).hexdigest()
    return ":".join(digest[i : i + 4] for i in range(0, 16, 4))


# ── a command ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Command:
    state: State
    message: str
    issued_at: datetime
    source: str
    nonce: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "message": self.message,
            "issued_at": self.issued_at.isoformat(),
            "source": self.source,
        }


def verify(token: str, *, source: str, public_key_b64: str | None = None) -> Command:
    """Parse and verify one signed command. Raises ValueError if not the owner's."""
    public_key_b64 = public_key_b64 or OWNER_PUBLIC_KEY_B64
    token = token.strip()
    if "." not in token:
        raise ValueError("not a command: expected payload.signature")
    payload_b64, sig_b64 = token.rsplit(".", 1)
    try:
        payload_raw = _b64d(payload_b64)
        signature = _b64d(sig_b64)
    except Exception as exc:
        raise ValueError("command is not valid base64url") from exc

    try:
        Ed25519PublicKey.from_public_bytes(_b64d(public_key_b64)).verify(signature, payload_raw)
    except InvalidSignature as exc:
        raise ValueError("signature is not the owner's") from exc
    except Exception as exc:
        raise ValueError(f"cannot check signature: {exc}") from exc

    try:
        payload = json.loads(payload_raw)
    except ValueError as exc:
        raise ValueError("signed payload is not JSON") from exc

    state = payload.get("state")
    if state not in VALID_STATES:
        raise ValueError(f"unknown state {state!r}")
    try:
        issued_at = datetime.fromisoformat(str(payload["issued_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("issued_at is missing or unparseable") from exc
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)

    return Command(
        state=state,  # type: ignore[arg-type]
        message=str(payload.get("message") or ""),
        issued_at=issued_at,
        source=source,
        nonce=str(payload.get("nonce") or ""),
    )


# ── the live state ───────────────────────────────────────────────────────


@dataclass
class Health:
    """What /api/ownership reports. Deliberately readable at a glance."""

    owner: str = OWNER_NAME
    fingerprint: str = ""
    state: State = "running"
    message: str = ""
    command_source: str = "none"
    command_issued_at: str | None = None
    problems: list[str] = field(default_factory=list)


class OwnerControl:
    """Holds the current command and answers "may this request proceed?"."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._command: Command | None = None
        self._problems: list[str] = []
        self._loaded = False
        #: Last token fetched from OWNER_CONTROL_URL, if that is configured.
        self._remote_token: str = ""
        #: State set with the admin token rather than a signature. Weaker, and
        #: kept separate so it is always clear which channel is in force.
        self._local: Command | None = None

    # ── loading ──────────────────────────────────────────────────────────

    def _candidates(self) -> list[tuple[str, str]]:
        """Every place a command might be, as (source, token) pairs."""
        import os

        found: list[tuple[str, str]] = []
        if CONTROL_PATH.exists():
            try:
                raw = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
                token = raw.get("command") if isinstance(raw, dict) else raw
                if isinstance(token, str) and token.strip():
                    found.append(("file", token))
            except (OSError, ValueError) as exc:
                self._problems.append(f"{CONTROL_PATH.name} could not be read: {exc}")
        env_token = os.environ.get("WILDFIREIQ_CONTROL", "").strip()
        if env_token:
            found.append(("env", env_token))
        if self._remote_token:
            found.append(("url", self._remote_token))
        return found

    async def refresh_remote(self, url: str, *, timeout_s: float = 10.0) -> None:
        """Fetch the command from a URL the owner controls, then reload.

        Deliberately tolerant: a gist that is down, renamed or rate-limited
        must not change how the deployment behaves. The fetched text is only
        ever trusted after the signature check in `verify`, so the URL does
        not have to be private or authenticated -- a public gist is fine.
        """
        if not url:
            return
        import httpx

        try:
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text.strip()
        except Exception as exc:
            log.info("owner.remote_unreachable", url=url, error=str(exc))
            return
        # Accept a bare command or a {"command": "..."} document.
        token = text
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                token = str(parsed.get("command") or "")
            except ValueError:
                token = ""
        if token and token != self._remote_token:
            self._remote_token = token
            log.info("owner.remote_fetched", url=url)
        self.reload()

    def _highest_seen(self) -> datetime | None:
        try:
            raw = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
            return datetime.fromisoformat(str(raw["issued_at"]))
        except (OSError, ValueError, KeyError):
            return None

    def _remember(self, at: datetime) -> None:
        try:
            SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            SEEN_PATH.write_text(json.dumps({"issued_at": at.isoformat()}) + "\n", encoding="utf-8")
        except OSError as exc:
            self._problems.append(f"could not record the command timestamp: {exc}")

    def reload(self) -> None:
        """Re-read every source and adopt the newest valid command."""
        with self._lock:
            self._loaded = True
            self._problems = []
            best: Command | None = None
            for source, token in self._candidates():
                try:
                    cmd = verify(token, source=source)
                except ValueError as exc:
                    # Loud, because a rejected command is either tampering or
                    # a mistake, and both need a person to look.
                    self._problems.append(f"command from {source} rejected: {exc}")
                    log.warning("owner.command_rejected", source=source, reason=str(exc))
                    continue
                if best is None or cmd.issued_at > best.issued_at:
                    best = cmd

            floor = self._highest_seen()
            if best is not None and floor is not None and best.issued_at < floor:
                self._problems.append(
                    "a command older than one already seen was refused (possible rollback)"
                )
                log.warning(
                    "owner.rollback_refused",
                    offered=best.issued_at.isoformat(),
                    already_seen=floor.isoformat(),
                )
                # Keep whatever is already in force. Falling back to "no
                # command" here would hand the replay exactly the result it
                # was replayed for. Deleting the control file is still a clean
                # way out, and that needs access to the machine.
                best = self._command

            if best is not None:
                self._remember(best.issued_at)
                if self._command is None or best.issued_at != self._command.issued_at:
                    log.info(
                        "owner.command_accepted",
                        state=best.state,
                        source=best.source,
                        issued_at=best.issued_at.isoformat(),
                    )
            self._command = best
            self._local = self._load_local()

    def _load_local(self) -> Command | None:
        """The admin-token state, which survives a restart like a command does."""
        try:
            raw = json.loads(LOCAL_STATE_PATH.read_text(encoding="utf-8"))
            state = raw["state"]
            if state not in VALID_STATES:
                return None
            at = datetime.fromisoformat(str(raw["set_at"]))
            if at.tzinfo is None:
                at = at.replace(tzinfo=UTC)
            return Command(
                state=state,
                message=str(raw.get("message") or ""),
                issued_at=at,
                source="admin-token",
            )
        except (OSError, ValueError, KeyError):
            return None

    def set_local_state(self, state: State, message: str = "") -> None:
        """Set the state with the admin token. A newer signed command wins."""
        now = datetime.now(UTC)
        with self._lock:
            self._loaded = True
            self._local = Command(state=state, message=message, issued_at=now, source="admin-token")
            try:
                LOCAL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                LOCAL_STATE_PATH.write_text(
                    json.dumps(
                        {"state": state, "message": message, "set_at": now.isoformat()}, indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                self._problems.append(f"could not save the state: {exc}")
        log.info("owner.state_set_with_token", state=state)

    def _effective(self) -> Command | None:
        """Whichever instruction is most recent, signed or admin-token.

        "The last thing the owner said wins" is the rule a person expects, and
        it means neither channel can strand the other: a signed pause overrides
        an older token resume, and a token resume overrides an older signed
        pause. The signed channel is the one nobody else can forge; the token
        channel is the convenient one.
        """
        if not self._loaded:
            self.reload()
        candidates = [c for c in (self._command, self._local) if c is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.issued_at)

    def adopt(self, token: str, *, source: str) -> Command:
        """Verify and adopt one command immediately. Raises ValueError if invalid."""
        cmd = verify(token, source=source)
        with self._lock:
            # Mark as loaded, or the next read would call reload() and discard
            # the command that was just accepted.
            self._loaded = True
            floor = self._highest_seen()
            if floor is not None and cmd.issued_at < floor:
                raise ValueError("this command is older than one already applied")
            self._remember(cmd.issued_at)
            self._command = cmd
        log.info("owner.command_accepted", state=cmd.state, source=source)
        return cmd

    # ── asking ───────────────────────────────────────────────────────────

    @property
    def state(self) -> State:
        current = self._effective()
        return current.state if current else "running"

    def blocks(self, path: str, method: str) -> str | None:
        """The message to refuse with, or None to let the request through."""
        if not path.startswith("/api/"):
            return None
        if any(path == open_path or path.startswith(open_path + "/") for open_path in ALWAYS_OPEN):
            return None
        state = self.state
        if state == "running":
            return None
        if state == "readonly" and method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return None
        default = (
            "This deployment is paused by its owner."
            if state == "paused"
            else "This deployment is read-only by its owner."
        )
        current = self._effective()
        return current.message if current and current.message else default

    def health(self) -> Health:
        current = self._effective()
        h = Health(
            fingerprint=key_fingerprint(),
            state=self.state,
            message=current.message if current else "",
            command_source=current.source if current else "none",
            command_issued_at=(current.issued_at.isoformat() if current else None),
            problems=list(self._problems),
        )
        return h

    def reset_for_tests(self) -> None:
        with self._lock:
            self._command = None
            self._local = None
            self._remote_token = ""
            self._problems = []
            self._loaded = True


control = OwnerControl()


# ── the admin token ──────────────────────────────────────────────────────
#
# Separate from the signing key, and much weaker on purpose: it is a shared
# secret for day-to-day work (saving API keys, pausing from the UI), stored on
# the server, so anyone who can read the server's files can read it. The
# signing key is what nobody else can obtain.


def admin_token(configured: str = "") -> str:
    """The admin token: the configured one, else a generated one on disk.

    Nobody has to set anything. On first boot, when nothing is configured, a
    random token is generated, saved to `data/runtime/owner.json` (which git
    ignores) and logged once. That way a deployment is protected by default,
    with no .env file anywhere, and the owner can read the token off their own
    server with `make admin-token`.
    """
    if configured.strip():
        return configured.strip()
    try:
        raw = json.loads(OWNER_STATE_PATH.read_text(encoding="utf-8"))
        token = str(raw.get("admin_token") or "")
        if token:
            return token
    except (OSError, ValueError):
        pass

    token = secrets.token_urlsafe(24)
    try:
        OWNER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        OWNER_STATE_PATH.write_text(
            json.dumps(
                {"admin_token": token, "created_at": datetime.now(UTC).isoformat()}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        OWNER_STATE_PATH.chmod(0o600)
        log.info("owner.admin_token_generated", path=str(OWNER_STATE_PATH))
    except OSError as exc:
        # A read-only data directory: keep the token in memory for this
        # process rather than leaving the API unprotected.
        log.warning("owner.admin_token_not_saved", error=str(exc))
    return token
