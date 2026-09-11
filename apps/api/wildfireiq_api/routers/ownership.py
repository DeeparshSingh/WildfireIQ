"""Who owns this deployment, and what state the owner has put it in.

`GET /api/ownership` is deliberately public and deliberately never blocked,
even when the deployment is paused. The owner needs to be able to check, from
any phone or network, that a deployment still answers to their key and that a
pause actually landed. It reveals nothing secret: an owner name, a public key
fingerprint, and the current state.

`POST /api/ownership/command` accepts a signed command over HTTP, which is the
convenient route when the owner has the URL but not a shell. The signature is
what authorises it, not the admin token, so this endpoint is safe to leave
open: an unsigned or wrongly-signed body is refused.

`POST /api/ownership/state` is the everyday shortcut: pause or resume with the
admin token instead of a signature. It is weaker on purpose, because the token
sits on the server and anyone who can read the server's files can read it. It
exists so the owner does not need their laptop for a routine pause.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..owner import OWNER_NAME, admin_token, control
from ..settings import get_settings
from ._envelope import Envelope, Meta

router = APIRouter()


class CommandBody(BaseModel):
    """One signed command, as printed by `python scripts/owner.py pause`."""

    command: str


class StateBody(BaseModel):
    state: Literal["running", "readonly", "paused"]
    message: str = ""


@router.get("", summary="Owner, key fingerprint, and current service state")
async def ownership() -> dict[str, Any]:
    health = control.health()
    return Envelope[dict](
        data={
            "owner": health.owner,
            "key_fingerprint": health.fingerprint,
            "state": health.state,
            "message": health.message,
            "command_source": health.command_source,
            "command_issued_at": health.command_issued_at,
            "problems": health.problems,
        },
        meta=Meta(
            source="owner.control",
            attribution=OWNER_NAME,
            note=(
                "Compare key_fingerprint with `python scripts/owner.py whoami`. They should agree."
            ),
        ),
    ).model_dump(mode="json")


@router.post("/command", summary="Apply a command signed with the owner's key")
async def apply_command(body: CommandBody) -> dict[str, Any]:
    try:
        command = control.adopt(body.command, source="http")
    except ValueError as exc:
        # 403, not 401: the request was understood and refused on its merits.
        raise HTTPException(403, f"Command refused: {exc}") from exc
    return Envelope[dict](
        data={"applied": command.as_dict(), "state": control.state},
        meta=Meta(source="owner.control", attribution=OWNER_NAME),
    ).model_dump(mode="json")


@router.post("/state", summary="Pause or resume using the admin token")
async def set_state(
    body: StateBody, x_admin_token: str | None = Header(default=None)
) -> dict[str, Any]:
    expected = admin_token(get_settings().admin_token)
    if (x_admin_token or "") != expected:
        raise HTTPException(401, "The admin token did not match.")

    # Recorded as a command from the same store the signed ones use, so there
    # is one place that decides state and one place to read it from.
    control.set_local_state(body.state, body.message)
    return Envelope[dict](
        data={
            "state": control.state,
            "message": body.message,
            "set_at": datetime.now(UTC).isoformat(),
        },
        meta=Meta(
            source="owner.control",
            attribution=OWNER_NAME,
            note="Set with the admin token. A signed command overrides this.",
        ),
    ).model_dump(mode="json")
