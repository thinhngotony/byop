"""Target subpackage for byop."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Target, configure_all, detect_installed
from .registry import ALL_TARGETS, available_targets

if TYPE_CHECKING:
    from .claude import ClaudeTarget
    from .omp import OmpTarget
    from .py import PyTarget
    from .zed import ZedTarget

# Lazy re-exports: these are only imported when accessed, so the
# macOS-only modules (claude, omp, opencode) don't blow up on Linux.
__all__ = [
    "Target",
    "configure_all",
    "detect_installed",
    "PyTarget",
    "OmpTarget",
    "ClaudeTarget",
    "ZedTarget",
    "ALL_TARGETS",
    "available_targets",
]


def __getattr__(name: str) -> object:
    if name == "PyTarget":
        from .py import PyTarget
        return PyTarget
    if name == "OmpTarget":
        from .omp import OmpTarget
        return OmpTarget
    if name == "ClaudeTarget":
        from .claude import ClaudeTarget
        return ClaudeTarget
    if name == "ZedTarget":
        from .zed import ZedTarget
        return ZedTarget
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
