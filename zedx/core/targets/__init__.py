"""Target subpackage for zedx."""

from .base import Target, configure_all, detect_installed
from .py import PyTarget
from .registry import ALL_TARGETS, available_targets
from .zed import ZedTarget

__all__ = [
    "Target",
    "configure_all",
    "detect_installed",
    "PyTarget",
    "ZedTarget",
    "ALL_TARGETS",
    "available_targets",
]
