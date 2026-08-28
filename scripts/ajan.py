"""Faz 2 terminal arayüzü — ajanı metin komutuyla sürer.

    python scripts/ajan.py "Not defterini aç ve içine bugünün tarihini yaz"
    python scripts/ajan.py            # etkileşimli

Arayüz Faz 5'te gelecek; bu, döngüyü tek başına doğrulamak için.
Her an Esc'ye üç kez basarak durdurabilirsin.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows konsolu varsayılan olarak cp1254/cp437 kullanıyor ve modelin Türkçe
# yanıtı `ı` karakterinde UnicodeEncodeError ile düşüyor. Türkçe konuşan bir
# uygulamada bu isteğe bağlı bir ayar değil.
for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")

from backend import config  # noqa: E402
from backend.agent.dispatch import ToolOutcome  # noqa: E402
from backend.agent.loop import Agent, Turn  # noqa: E402
from backend.computer.capture import ScreenCapture  # noqa: E402
from backend.computer.displays import enumerate_displays, set_dpi_awareness  # noqa: E402
from backend.safety.killswitch import Aborted, KillSwitch  # noqa: E402

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"


def _short(payload: dict) -> str:
    parts = []
    for key in ("coordinate", "start_coordinate", "text", "scroll_direction",
                "scroll_amount", "region", "duration", "index", "repeat"):
        if key in payload:
            value = payload[key]
            if isinstance(value, str) and len(value) > 40:
                value = value[:37] + "..."
            parts.append(f"{key}={value!r}")
    return " ".join(parts)


def make_turn() -> Turn:
    return Turn(
        on_text=lambda t: print(t, end="", flush=True),
        on_thinking=lambda t: print(f"{DIM}  ~ {t.strip()[:160]}{RESET}", flush=True),
        on_action=lambda name, payload: print(
            f"{DIM}  > {name} {_short(payload)}{RESET}", flush=True
        ),
        on_result=lambda name, outcome: (
            print(f"{DIM}    ! {outcome.content}{RESET}", flush=True)
            if outcome.is_error
            else None
        ),
    )


def ask_approval(name: str, detail: str, reason: str) -> bool:
    """Terminalde onay ister. Faz 5'te bunun yerini arayüzdeki modal alacak."""
    print(f"\n{BOLD}[APPROVAL NEEDED]{RESET} {name} — {reason}")
    for line in detail.splitlines():
        print(f"  {line}")
    try:
        answer = input(f"{BOLD}Run it? (y/N) {RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("  declined")
        return False
    approved = answer in {"e", "evet", "y", "yes"}
    print("  approved" if approved else "  declined")
    return approved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instruction", nargs="*", help="the instruction; interactive when empty")
    parser.add_argument("--max-steps", type=int, default=60)
    args = parser.parse_args()

    try:
        cfg = config.Config.load()
    except RuntimeError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 1

    set_dpi_awareness()
    displays = enumerate_displays()

    with ScreenCapture(displays) as capture, KillSwitch(
        on_trigger=lambda: print(f"\n{BOLD}[DURDURULDU]{RESET}", flush=True)
    ) as kill:
        agent = Agent.create(cfg, displays, capture, kill, approve=ask_approval)
        print(f"{len(displays)} displays. Esc x3 to stop.\n")

        instructions = [" ".join(args.instruction)] if args.instruction else None
        while True:
            if instructions is not None:
                if not instructions:
                    return 0
                instruction = instructions.pop(0)
                print(f"{BOLD}> {instruction}{RESET}")
            else:
                try:
                    instruction = input(f"{BOLD}> {RESET}").strip()
                except (EOFError, KeyboardInterrupt):
                    return 0
                if not instruction:
                    continue
                if instruction in {"cik", "çık", "exit", "quit"}:
                    agent.dispatcher.shutdown()
                    return 0

            try:
                agent.run(instruction, make_turn(), max_steps=args.max_steps)
                print()
                open_terminals = agent.dispatcher.terminals.names()
                if open_terminals:
                    print(f"{DIM}  open terminals: {', '.join(open_terminals)}{RESET}")
            except Aborted as exc:
                print(f"\n{exc}")
            except Exception as exc:
                print(f"\nHATA: {type(exc).__name__}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
