"""XDG-aware config dir resolution for byop.

On macOS the default is ``~/.config/byop/`` (matching what ``gh`` and most
modern CLIs do, and what the install.sh script and README already document).
Users who set ``XDG_CONFIG_HOME`` get the standard XDG layout, and a
``BYOP_CONFIG_DIR`` override beats both for tests and power users.

The directory and its ``profiles/`` subdirectory are created lazily by
:func:`ensure_config_dir` so callers don't have to think about it.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "byop"


def config_dir() -> Path:
    """Return the directory where byop stores its config and profiles.

    Precedence: ``BYOP_CONFIG_DIR`` > ``XDG_CONFIG_HOME`` > platform default.
    """
    override = os.environ.get("BYOP_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir(APP_NAME, appauthor=False, roaming=True))


def profiles_dir() -> Path:
    """Directory holding one ``.toml`` file per saved profile."""
    return config_dir() / "profiles"


def config_path() -> Path:
    """Path to the user-global ``config.toml`` (settings + active profile)."""
    return config_dir() / "config.toml"


def ensure_config_dir() -> Path:
    """Create ``config_dir()`` and ``profiles_dir()`` if they don't exist.

    Returns the config dir so callers can chain.
    """
    profiles_dir().mkdir(parents=True, exist_ok=True)
    return config_dir()
