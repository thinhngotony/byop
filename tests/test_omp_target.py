"""Tests for the Oh My Pi (omp) target."""

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core.config import ModelConfig, ProviderConfig
from byop.core.targets import available_targets
from byop.core.targets.omp import OmpTarget
from byop.core.targets.py import PyTarget


def _provider(**over):
    base = {
        "provider_name": "HyberOrbit",
        "api_url": "https://api.example.com/v1/",
        "api_key": "sk-12345678",
        "models": [ModelConfig(name="hy3")],
    }
    base.update(over)
    return ProviderConfig(**base)


def test_omp_default_path():
    """OmpTarget defaults to ~/.omp/agent/models.json, NOT py.dev's path."""
    target = OmpTarget()
    assert target.models_path == Path.home() / ".omp" / "agent" / "models.json"
    # Sanity check it is distinct from PyTarget's default.
    assert target.models_path != PyTarget().models_path


def test_omp_is_py_target_subclass():
    """Subclass so the models.json fragment logic stays DRY."""
    assert issubclass(OmpTarget, PyTarget)


def test_omp_configure_writes_to_omp_path(tmp_path):
    models = tmp_path / "models.json"
    target = OmpTarget(models_path=models)
    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.py.kc.keychain_has", return_value=True):
        target.configure(_provider(), log=lambda m: None)
    data = json.loads(models.read_text())
    assert "HyberOrbit" in data["providers"]
    # Inherited from PyTarget — the apiKey is a keychain shell-out.
    assert data["providers"]["HyberOrbit"]["apiKey"].startswith("!security")


def test_omp_install_via_brew_when_present():
    calls = []

    def _run(cmd, *a, **k):
        calls.append(cmd)

        class R:
            pass
        r = R()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with mock.patch(
        "byop.core.targets.omp.shutil.which",
        side_effect=lambda n: "/opt/homebrew/bin/brew" if n == "brew" else None,
    ), mock.patch("byop.core.targets.omp._run", _run):
        OmpTarget().install(log=lambda m: None)
    assert any(c[:3] == ["brew", "install", "can1357/tap/omp"] for c in calls)


def test_omp_registered_with_default_registry():
    """OmpTarget must be in ALL_TARGETS after the registry update."""
    targets = available_targets()
    names = {t.__class__.__name__ for t in targets}
    assert "OmpTarget" in names
    assert "ClaudeTarget" in names
    assert "PyTarget" in names
    assert "ZedTarget" in names


def test_omp_detect_installed_uses_PATH_or_dir():
    """is_installed is True when ~/.omp/ exists OR `omp` is on PATH."""
    import shutil

    with mock.patch.object(OmpTarget, "__init__", lambda self, models_path=None: None):
        target = OmpTarget.__new__(OmpTarget)
        target.models_path = Path("/tmp/whatever/models.json")
        with mock.patch.object(Path, "exists", return_value=True):
            assert target.is_installed() is True
        with mock.patch.object(Path, "exists", return_value=False), \
             mock.patch.object(shutil, "which", return_value="/usr/local/bin/omp"):
            assert target.is_installed() is True
        with mock.patch.object(Path, "exists", return_value=False), \
             mock.patch.object(shutil, "which", return_value=None):
            assert target.is_installed() is False
