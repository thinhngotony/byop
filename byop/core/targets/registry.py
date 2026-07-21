"""Registry of configurable application targets.

Add a new application by implementing a target module and listing it here.
"""

from __future__ import annotations

from pathlib import Path

from .base import Target
from .claude import ClaudeTarget
from .omp import OmpTarget
from .py import PyTarget
from .zed import ZedTarget

# Targets that are fully implemented and offered to the user.
ALL_TARGETS: list[type[Target]] = [ZedTarget, PyTarget, ClaudeTarget, OmpTarget]


def available_targets(settings_path: Path | None = None) -> list[Target]:
    """Instantiate every registered target with its default paths.

    ``settings_path`` (if given) is forwarded to targets that accept a
    settings file (currently Zed) so callers can override the location.
    """
    targets: list[Target] = []
    for cls in ALL_TARGETS:
        if cls is ZedTarget and settings_path is not None:
            targets.append(cls(settings_path=settings_path))
        else:
            targets.append(cls())
    return targets
