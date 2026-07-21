"""Target subpackage for byop."""

from .base import Target, configure_all, detect_installed
from .claude import ClaudeTarget
from .omp import OmpTarget
from .py import PyTarget
from .registry import ALL_TARGETS, available_targets
from .zed import ZedTarget

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
