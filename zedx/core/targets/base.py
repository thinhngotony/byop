"""Target abstraction for applications zedx can configure.

A *target* is any AI-coding application (Zed, py.dev, a future Claude Code
integration, ...) that can be wired to a custom OpenAI-compatible provider.

Each target exposes:

* ``name`` / ``display_name`` — identifiers and a human label.
* ``is_installed()`` — whether the app is present on this machine.
* ``install(log)`` — install or upgrade the app to the latest version.
* ``configure(provider, ...)`` — write the provider config for that app.
* ``current_provider_names()`` — providers already configured (for UX).

This indirection keeps the CLI thin and makes adding a new app (e.g. Claude
Code) a matter of implementing one module and registering it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from ..config import ProviderConfig


@runtime_checkable
class Target(Protocol):
    """Interface every configurable application target implements."""

    name: str
    display_name: str

    def is_installed(self) -> bool: ...

    def install(self, log: Callable[[str], None] = print) -> None: ...

    def configure(
        self,
        provider: ProviderConfig,
        *,
        dry_run: bool = False,
        use_keychain: bool = True,
        use_env: bool = False,
        log: Callable[[str], None] = print,
    ) -> None: ...

    def current_provider_names(self) -> list[str]: ...


def detect_installed(targets: list[Target]) -> list[Target]:
    """Return the subset of ``targets`` that are installed."""

    return [t for t in targets if t.is_installed()]


def configure_all(
    targets: list[Target],
    provider: ProviderConfig,
    *,
    dry_run: bool = False,
    use_keychain: bool = True,
    use_env: bool = False,
    log: Callable[[str], None] = print,
) -> None:
    """Configure every target in ``targets`` with ``provider``."""

    for target in targets:
        label = target.display_name
        log(f"--- Configuring {label} ---")
        target.configure(
            provider,
            dry_run=dry_run,
            use_keychain=use_keychain,
            use_env=use_env,
            log=log,
        )
