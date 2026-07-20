"""Interactive prompt helpers for zedx.

Uses `rich` for a polished experience when available, and degrades gracefully
to plain stdlib input/output otherwise so the tool works in minimal CI shells.
"""

from __future__ import annotations

import getpass
import sys

try:  # pragma: no cover - optional dependency
    from rich.console import Console
    from rich.prompt import Confirm, IntPrompt, Prompt

    _HAS_RICH = True
except Exception:  # pragma: no cover
    _HAS_RICH = False

_PROMPT_PREFIX = "› "


def _console() -> Console:
    return Console()


def ask(prompt: str, default: str = "", allow_empty: bool = False) -> str:
    if _HAS_RICH:
        val = Prompt.ask(_PROMPT_PREFIX + prompt, default=default)
    else:
        suffix = f" [{default}]" if default else ""
        val = input(f"{_PROMPT_PREFIX}{prompt}{suffix}: ").strip()
        if not val and default:
            val = default
    if not allow_empty and not val:
        # Retry once for critical fields.
        return ask(prompt, default=default, allow_empty=allow_empty)
    return val


def ask_secret(prompt: str) -> str:
    if _HAS_RICH:
        return Prompt.ask(_PROMPT_PREFIX + prompt, password=True)
    return getpass.getpass(f"{_PROMPT_PREFIX}{prompt}: ")


def ask_int(prompt: str, default: int) -> int:
    if _HAS_RICH:
        return IntPrompt.ask(_PROMPT_PREFIX + prompt, default=default)
    raw = input(f"{_PROMPT_PREFIX}{prompt} [{default}]: ").strip()
    return int(raw) if raw else default


def confirm(prompt: str, default: bool = False) -> bool:
    if _HAS_RICH:
        return Confirm.ask(_PROMPT_PREFIX + prompt, default=default)
    raw = input(f"{_PROMPT_PREFIX}{prompt} (y/N): ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


def choose(prompt: str, options: list[str], default_index: int = 0) -> str:
    if _HAS_RICH:
        from rich.prompt import Prompt as _P

        display = "\n".join(
            f"  {i+1}. {opt}" for i, opt in enumerate(options)
        )
        _console().print(display)
        val = _P.ask(
            _PROMPT_PREFIX + prompt,
            choices=[str(i + 1) for i in range(len(options))],
            default=str(default_index + 1),
        )
        return options[int(val) - 1]
    print(_PROMPT_PREFIX + prompt)
    for i, opt in enumerate(options):
        print(f"  {i+1}. {opt}")
    raw = input(f"Select [1-{len(options)}] [{default_index+1}]: ").strip()
    idx = int(raw) - 1 if raw else default_index
    return options[idx]


def header(title: str) -> None:
    if _HAS_RICH:
        _console().rule(title)
    else:
        print(f"\n=== {title} ===")


def info(message: str) -> None:
    if _HAS_RICH:
        _console().print(f"[cyan]{message}[/cyan]")
    else:
        print(message)


def success(message: str) -> None:
    if _HAS_RICH:
        _console().print(f"[green]✓[/green] {message}")
    else:
        print(f"✓ {message}")


def warn(message: str) -> None:
    if _HAS_RICH:
        _console().print(f"[yellow]![/yellow] {message}")
    else:
        print(f"! {message}")


def error(message: str) -> None:
    if _HAS_RICH:
        Console(stderr=True).print(f"[red]✗ {message}[/red]")
    else:
        print(f"✗ {message}", file=sys.stderr)
