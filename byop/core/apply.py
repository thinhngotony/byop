"""End-to-end configuration orchestration for byop.

This module now delegates to the :mod:`byop.core.targets` abstractions. The
legacy :func:`apply_provider` / :func:`build_settings_update` helpers are kept
for backward compatibility (and the existing test-suite) but simply wrap the
:class:`ZedTarget`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import ProviderConfig
from .targets.zed import ZedTarget

DEFAULT_SETTINGS_PATH = Path.home() / ".config" / "zed" / "settings.json"


def default_model_capabilities() -> dict[str, bool]:
    """Sensible default capabilities for an OpenAI-compatible chat model."""

    return {
        "tools": True,
        "images": False,
        "parallel_tool_calls": False,
        "prompt_cache_key": False,
        "chat_completions": True,
        "interleaved_reasoning": False,
        "max_tokens_parameter": False,
    }


def build_settings_update(provider: ProviderConfig) -> dict[str, object]:
    """Build the full Zed settings.json fragment for a provider."""

    return ZedTarget().build_fragment(provider)


def apply_provider(
    provider: ProviderConfig,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    log: Callable[[str], None] = print,
    dry_run: bool = False,
    use_keychain: bool | None = None,
    use_env: bool | None = None,
) -> dict[str, object]:
    """Apply a provider configuration to Zed (legacy helper).

    Prefer using :class:`ZedTarget` / :func:`byop.core.targets.configure_all`
    for new code. This wraps :class:`ZedTarget` so existing callers and tests
    keep working.
    """

    target = ZedTarget(settings_path=settings_path)
    target.configure(
        provider,
        dry_run=dry_run,
        use_keychain=use_keychain if use_keychain is not None else True,
        use_env=use_env if use_env is not None else False,
        log=log,
    )
    return target.build_fragment(provider)


def current_provider_names(settings_path: Path = DEFAULT_SETTINGS_PATH) -> list[str]:
    """Return provider names already configured under openai_compatible."""

    return ZedTarget(settings_path=settings_path).current_provider_names()
