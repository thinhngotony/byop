"""Tests for the Claude Code target."""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core.config import ModelConfig, ProviderConfig
from byop.core.targets.claude import ClaudeTarget


# ----------------------------------------------------------------------
# Install/detection (T7)
# ----------------------------------------------------------------------
def _result(returncode=0, stdout="", stderr=""):
    class R:
        pass
    r = R()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_install_via_brew_when_present():
    calls = []

    def _run(cmd, *a, **k):
        calls.append(cmd)
        r = _result()
        return r

    with mock.patch(
        "byop.core.targets.claude.shutil.which",
        side_effect=lambda n: "/opt/homebrew/bin/brew" if n == "brew" else None,
    ), mock.patch("byop.core.targets.claude._run", _run):
        ClaudeTarget().install(log=lambda m: None)
    assert any(c[:4] == ["brew", "install", "--cask", "claude-code"] for c in calls)


def test_install_falls_back_to_npm():
    calls = []

    def _run(cmd, *a, **k):
        calls.append(cmd)
        return _result()

    def which(name):
        return "/usr/local/bin/npm" if name == "npm" else None

    with mock.patch("byop.core.targets.claude.shutil.which", which), \
         mock.patch("byop.core.targets.claude._run", _run):
        ClaudeTarget().install(log=lambda m: None)
    assert any("npm" in c and "install" in c and "-g" in c for c in calls)


# ----------------------------------------------------------------------
# build_fragment + configure (T8)
# ----------------------------------------------------------------------
def _provider(**over):
    base = {
        "provider_name": "HyberOrbit",
        "api_url": "https://api.example.com/v1/",
        "api_key": "sk-12345678",
        "models": [
            ModelConfig(name="hy3", max_tokens=250000, max_output_tokens=32000)
        ],
    }
    base.update(over)
    return ProviderConfig(**base)


def test_build_fragment_shape():
    frag = ClaudeTarget().build_fragment(_provider())
    assert frag["provider"] == "HyberOrbit"
    # Trailing slash normalized away.
    assert frag["apiBaseUrl"] == "https://api.example.com/v1"
    assert frag["model"] == "hy3"
    assert frag["models"][0]["id"] == "hy3"
    assert frag["models"][0]["context_window"] == 250000


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS keychain required")
def test_configure_writes_settings_json_with_keychain_command(tmp_path):
    """Keychain `!command` is the default apiKey reference when entry exists."""
    settings = tmp_path / "settings.json"
    target = ClaudeTarget(settings_path=settings)
    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.claude.kc.keychain_has", return_value=True):
        target.configure(_provider(), log=lambda m: None)
    data = json.loads(settings.read_text())
    assert data["provider"] == "HyberOrbit"
    assert data["apiBaseUrl"] == "https://api.example.com/v1"
    assert data["apiKey"].startswith("!security find-internet-password")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS keychain required")
def test_configure_writes_literal_key_when_no_keychain_entry(tmp_path):
    settings = tmp_path / "settings.json"
    target = ClaudeTarget(settings_path=settings)
    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.claude.kc.keychain_has", return_value=False):
        target.configure(_provider(), log=lambda m: None)
    data = json.loads(settings.read_text())
    assert data["apiKey"] == "sk-12345678"


def test_configure_skip_when_settings_already_match(tmp_path):
    """Idempotent re-run with conflict_action='skip' and matching settings = no-op."""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "provider": "HyberOrbit",
        "apiBaseUrl": "https://api.example.com/v1",
        "model": "hy3",
        "models": [{"id": "hy3", "context_window": 250000, "max_tokens": 32000}],
        "apiKey": "!security find-internet-password -s x -a Bearer -w",
    }))
    target = ClaudeTarget(settings_path=settings)
    writes = {"count": 0}
    real_write = target._write

    def tracking(data):
        writes["count"] += 1
        return real_write(data)

    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.claude.kc.ensure_key",
                    return_value=["k"]) as ek, \
         mock.patch.object(target, "_write", tracking):
        target.configure(_provider(), conflict_action="skip", log=lambda m: None)
    assert writes["count"] == 0
    ek.assert_called_once()


def test_current_provider_names_when_present(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"provider": "HyberOrbit"}))
    target = ClaudeTarget(settings_path=settings)
    assert target.current_provider_names() == ["HyberOrbit"]


def test_current_provider_names_when_absent(tmp_path):
    settings = tmp_path / "settings.json"  # doesn't exist
    target = ClaudeTarget(settings_path=settings)
    assert target.current_provider_names() == []
