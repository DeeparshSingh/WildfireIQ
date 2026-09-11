#!/usr/bin/env python3
"""The owner's command line. Runs on the owner's own machine, not the server.

This is the half of owner control that holds the private key. It never talks
to a deployment; it only prints signed commands, which the owner then delivers
by whichever route is convenient (see `apps/api/wildfireiq_api/owner.py`).

    python scripts/owner.py keygen                  # once: create the key
    python scripts/owner.py pause "Back at 6pm"     # print a signed command
    python scripts/owner.py readonly "Maintenance"
    python scripts/owner.py resume
    python scripts/owner.py verify <command>        # check one by eye
    python scripts/owner.py whoami                  # key location + fingerprint

The private key lives at ~/.wildfireiq/owner_ed25519, mode 0600, and is the
one thing that must never be committed, pasted, or copied to the server. Back
it up somewhere only you can reach; `keygen --show-private` prints it for that
purpose.

Delivering a command, easiest first:

  Remote URL (no shell needed)
      Put the command in a file the deployment can fetch, e.g. a GitHub gist,
      and point OWNER_CONTROL_URL at its raw address. Editing the gist from a
      phone is enough to pause a server.

  Straight onto the box
      python scripts/owner.py pause "…" --write control.json
      scp control.json you@server:/path/to/wildfireiq/data/runtime/control.json

  Environment variable
      WILDFIREIQ_CONTROL='<command>'   before starting the API.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

KEY_DIR = Path.home() / ".wildfireiq"
KEY_PATH = KEY_DIR / "owner_ed25519"


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def fingerprint(public_bytes: bytes) -> str:
    from hashlib import sha256

    d = sha256(public_bytes).hexdigest()
    return ":".join(d[i : i + 4] for i in range(0, 16, 4))


def load_private() -> Ed25519PrivateKey:
    if not KEY_PATH.exists():
        sys.exit(f"No signing key at {KEY_PATH}. Run:  python scripts/owner.py keygen")
    key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        sys.exit(f"{KEY_PATH} is not an Ed25519 private key.")
    return key


def cmd_keygen(args: argparse.Namespace) -> None:
    if KEY_PATH.exists() and not args.force:
        sys.exit(
            f"{KEY_PATH} already exists. Use --force to replace it, but note that every\n"
            "command signed by the old key stops being recognised, and the public key in\n"
            "apps/api/wildfireiq_api/owner.py must be updated."
        )
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    KEY_PATH.chmod(0o600)
    pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    print(f"Private key written to {KEY_PATH} (mode 0600). Back this up; it is your only copy.")
    print()
    print("Put this in apps/api/wildfireiq_api/owner.py:")
    print(f'  OWNER_PUBLIC_KEY_B64 = "{b64e(pub)}"')
    print(f"  Fingerprint: {fingerprint(pub)}")
    if args.show_private:
        print()
        print(KEY_PATH.read_text(), end="")


def sign(state: str, message: str) -> str:
    private = load_private()
    payload = {
        "v": 1,
        "state": state,
        "message": message,
        "issued_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "nonce": secrets.token_hex(8),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{b64e(raw)}.{b64e(private.sign(raw))}"


#: The subcommand a person types, and the state it means. Keeping the two
#: apart matters: "pause" reads better on a command line than "paused", and
#: the server only accepts the exact state names.
STATE_FOR = {"pause": "paused", "readonly": "readonly", "resume": "running"}


def cmd_state(args: argparse.Namespace) -> None:
    state = STATE_FOR[args.command]
    token = sign(state, getattr(args, "message", "") or "")
    if args.write:
        out = Path(args.write)
        out.write_text(json.dumps({"command": token}, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out}")
        print("Copy it to the server:")
        print(f"  scp {out} you@server:/path/to/wildfireiq/data/runtime/control.json")
    else:
        print(token)
        print(file=sys.stderr)
        print(f"state={state}  (paste this where the deployment reads it)", file=sys.stderr)


def cmd_verify(args: argparse.Namespace) -> None:
    payload_b64, _, sig_b64 = args.command.strip().rpartition(".")
    if not payload_b64:
        sys.exit("Not a command: expected payload.signature")
    raw = b64d(payload_b64)
    pub = load_private().public_key()
    try:
        pub.verify(b64d(sig_b64), raw)
    except Exception:  # noqa: BLE001
        sys.exit("REJECTED: this command was not signed by your key.")
    print("Signed by your key. Contents:")
    print(json.dumps(json.loads(raw), indent=2))


def cmd_whoami(_: argparse.Namespace) -> None:
    if not KEY_PATH.exists():
        print(f"No signing key yet. Run:  python scripts/owner.py keygen")
        return
    pub = (
        load_private()
        .public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    )
    print(f"Key file    {KEY_PATH}")
    print(f"Public key  {b64e(pub)}")
    print(f"Fingerprint {fingerprint(pub)}")
    print()
    print("Compare that fingerprint with /api/ownership on a deployment. A match")
    print("means the deployment still answers to this key and nobody has swapped it.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("keygen", help="create the owner signing key (run once)")
    g.add_argument("--force", action="store_true", help="replace an existing key")
    g.add_argument("--show-private", action="store_true", help="also print the private key, to back up")
    g.set_defaults(func=cmd_keygen)

    for name, helptext in (
        ("pause", "refuse every /api/* request"),
        ("readonly", "allow reads, refuse writes"),
        ("resume", "return to normal service"),
    ):
        s = sub.add_parser(name, help=helptext)
        if name != "resume":
            s.add_argument("message", nargs="?", default="", help="what visitors are told")
        s.add_argument("--write", metavar="FILE", help="write control.json instead of printing")
        s.set_defaults(func=cmd_state)

    v = sub.add_parser("verify", help="check a command against your key")
    v.add_argument("command")
    v.set_defaults(func=cmd_verify)

    sub.add_parser("whoami", help="key location and fingerprint").set_defaults(func=cmd_whoami)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
