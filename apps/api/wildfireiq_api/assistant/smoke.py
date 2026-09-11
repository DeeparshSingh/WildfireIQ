"""One live assistant call, printed as a trace. `make assistant-smoke`.

Everything else about the assistant is tested offline against a scripted
model, so this is the only thing in the repo that spends real credit. It
makes exactly one request and prints what the harness did with it: which
tools ran, what they returned, what the model said, and what OpenRouter
actually charged.

    make assistant-smoke
    make assistant-smoke Q="are there fires near Merritt?"
"""

from __future__ import annotations

import asyncio
import sys

from ..settings import get_settings
from .harness import ChatRequest, availability, run_conversation

DEFAULT_QUESTION = "What's the wildfire risk near Kamloops today, and is the air safe?"

DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def main(question: str) -> int:
    state = availability()
    if not state["enabled"]:
        print("Assistant disabled (ASSISTANT_ENABLED=false).", file=sys.stderr)
        return 1
    if not state["configured"]:
        print(
            "No OpenRouter key in the runtime key store — enter one in the app's Settings panel first.",
            file=sys.stderr,
        )
        return 1

    print(f"{DIM}model {state['model']} · {state['tools']} tools{RESET}")
    print(f"{BOLD}> {question}{RESET}\n")

    answering = False
    async for event in run_conversation(
        ChatRequest(messages=[{"role": "user", "content": question}]),
        settings=get_settings(),
    ):
        match event.name:
            case "safety":
                print(f"{DIM}[safety] {event.data['message']}{RESET}\n")
            case "tool_call":
                print(f"{DIM}→ {event.data['name']}({event.data['arguments']}){RESET}")
            case "tool_result":
                mark = "ok" if event.data["ok"] else "FAILED"
                detail = event.data.get("error") or event.data.get("summary") or ""
                print(f"{DIM}  {mark} {event.data['duration_ms']} ms · {detail}{RESET}")
            case "effect":
                print(f"{DIM}⇒ ui: {event.data}{RESET}")
            case "step_end":
                if note := event.data.get("note"):
                    print(f"{DIM}  plan: {note}{RESET}")
            case "token":
                if not answering:
                    print()
                    answering = True
                print(event.data["text"], end="", flush=True)
            case "sources":
                for source in event.data["sources"]:
                    print(f"\n{DIM}  source: {source['source']}{RESET}", end="")
            case "usage":
                data = event.data
                print(
                    f"\n\n{DIM}{data['prompt_tokens']} in / {data['completion_tokens']} out · "
                    f"${data['cost_usd']:.6f} · {data['tool_calls']} tool calls · "
                    f"{data['duration_ms'] / 1000:.1f} s{RESET}"
                )
            case "error":
                print(f"\nERROR: {event.data['message']}", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    argument = " ".join(sys.argv[1:]).strip()
    raise SystemExit(asyncio.run(main(argument or DEFAULT_QUESTION)))
