"""Oh My Pi (omp) target.

omp (https://omp.sh) is a fork of py.dev by can1357; it shares the same
``~/.pi/agent/models.json`` provider schema but lives at ``~/.omp``. We
subclass :class:`PyTarget` so the models.json fragment logic stays in one
place — if the two projects ever diverge, lift this into a standalone class.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .py import PyTarget

DEFAULT_MODELS_PATH = Path.home() / ".omp" / "agent" / "models.json"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class OmpTarget(PyTarget):
    name = "omp"
    display_name = "Oh My Pi (omp)"

    def __init__(self, models_path: Path | None = None) -> None:
        super().__init__(models_path=models_path or DEFAULT_MODELS_PATH)

    # ------------------------------------------------------------------
    def is_installed(self) -> bool:
        return (
            self.models_path.parent.parent.exists()
            or shutil.which("omp") is not None
        )

    def install(self, log: Callable[[str], None] = print) -> None:
        if shutil.which("brew") is not None:
            log("Installing omp via Homebrew...")
            res = _run(["brew", "install", "can1357/tap/omp"])
            if res.returncode == 0:
                log("omp installed via Homebrew.")
                return
            log(
                f"brew install failed: {res.stderr or res.stdout}; "
                f"falling back to the published installer."
            )

        log("Installing omp via published installer (https://omp.sh/install)...")
        res = _run(["bash", "-c", "curl -fsSL https://omp.sh/install | sh"])
        if res.returncode == 0:
            log("omp installed via published script.")
            return

        if shutil.which("bun") is not None:
            log("Falling back to bun...")
            res = _run(["bun", "install", "-g", "@oh-my-pi/pi-coding-agent"])
            if res.returncode != 0:
                raise RuntimeError(
                    "omp install via bun failed:\n"
                    + (res.stderr or res.stdout)
                )
            log("omp installed via bun.")
            return

        raise RuntimeError(
            "Could not install omp. Try one of:\n"
            "  brew install can1357/tap/omp\n"
            "  curl -fsSL https://omp.sh/install | sh\n"
            "  bun install -g @oh-my-pi/pi-coding-agent"
        )
