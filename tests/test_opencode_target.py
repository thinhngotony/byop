"""Tests for the OpenCode target."""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core.config import ModelConfig, ProviderConfig
from byop.core.targets.opencode import DEFAULT_CONFIG_PATH, OpencodeTarget


def _provider(**over):
    base = {
        "provider_name": "HyberOrbit",
        "api_url": "https://api.example.com/v1/",
        "api_key": "sk-12345678",
        "models": [
            ModelConfig(
                name="hy3",
                display_name="HyberOrbit 3",
                max_tokens=250000,
                max_output_tokens=32000,
                reasoning_effort="medium",
                capabilities={"images": True, "interleaved_reasoning": True},
            )
        ],
    }
    base.update(over)
    return ProviderConfig(**base)


def test_opencode_default_path():
    target = OpencodeTarget()
    assert target.config_path == Path.home() / ".config" / "opencode" / "opencode.json"


def test_opencode_build_fragment_uses_openai_compatible_sdk():
    frag = OpencodeTarget().build_fragment(_provider())
    block = frag["provider"]["HyberOrbit"]
    assert block["npm"] == "@ai-sdk/openai-compatible"
    assert block["options"]["baseURL"] == "https://api.example.com/v1"
    # Keychain shell-out when keychain entry present.
    assert block["options"]["apiKey"].startswith("!security")
    model = block["models"]["hy3"]
    assert model["name"] == "HyberOrbit 3"
    assert model["reasoning"] is True
    assert model["interleaved"] == {"field": "reasoning_content"}


def test_opencode_falls_back_to_literal_key_when_keychain_missing():
    target = OpencodeTarget()
    with mock.patch("byop.core.targets.opencode.kc.keychain_has", return_value=False):
        frag = target.build_fragment(_provider())
    assert frag["provider"]["HyberOrbit"]["options"]["apiKey"] == "sk-12345678"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS keychain required")
def test_opencode_configure_writes_merges_preserves_other_providers(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps(
            {
                "provider": {"OtherOne": {"name": "x", "npm": "y"}},
                "permission": {"bash": "ask"},
            }
        ),
        encoding="utf-8",
    )
    target = OpencodeTarget(config_path=cfg)
    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.opencode.kc.keychain_has", return_value=True), \
         mock.patch("byop.core.targets.opencode.kc.ensure_key", return_value=["k:x"]):
        target.configure(_provider(), log=lambda m: None)
    data = json.loads(cfg.read_text())
    assert "HyberOrbit" in data["provider"]
    assert data["provider"]["OtherOne"]["name"] == "x"
    assert data["permission"]["bash"] == "ask"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS keychain required")
def test_opencode_skip_when_existing_provider(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps({"provider": {"HyberOrbit": {"name": "old"}}}), encoding="utf-8"
    )
    target = OpencodeTarget(config_path=cfg)
    writes = {"count": 0}
    real = cfg.write_text

    def _track(*a, **k):
        writes["count"] += 1
        return real(*a, **k)

    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.opencode.kc.keychain_has", return_value=True), \
         mock.patch("byop.core.targets.opencode.kc.ensure_key", return_value=["k:x"]), \
         mock.patch.object(Path, "write_text", _track):
        target.configure(_provider(), conflict_action="skip", log=lambda m: None)
    assert writes["count"] == 0
    data = json.loads(cfg.read_text())
    # Untouched on skip.
    assert data["provider"]["HyberOrbit"]["name"] == "old"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS keychain required")
def test_opencode_append_when_existing_provider(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps({"provider": {"HyberOrbit": {"name": "old"}}}), encoding="utf-8"
    )
    target = OpencodeTarget(config_path=cfg)
    with mock.patch.object(target, "install"), \
         mock.patch("byop.core.targets.opencode.kc.keychain_has", return_value=True), \
         mock.patch("byop.core.targets.opencode.kc.ensure_key", return_value=["k:x"]):
        target.configure(_provider(), conflict_action="append", log=lambda m: None)
    data = json.loads(cfg.read_text())
    assert "HyberOrbit" in data["provider"]
    assert "HyberOrbit_2" in data["provider"]


def test_opencode_current_provider_names(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps({"provider": {"HyberOrbit": {}, "OtherOne": {}}}),
        encoding="utf-8",
    )
    target = OpencodeTarget(config_path=cfg)
    assert sorted(target.current_provider_names()) == ["HyberOrbit", "OtherOne"]


def test_opencode_registered_in_default_registry():
    from byop.core.targets import available_targets

    names = {t.name for t in available_targets()}
    assert "opencode" in names
    assert DEFAULT_CONFIG_PATH.name == "opencode.json"


def test_opencode_install_via_brew_when_present():
    calls = []

    def _run(cmd, *a, **k):
        calls.append(cmd)
        r = mock.Mock(returncode=0, stdout="", stderr="")
        return r

    with mock.patch(
        "byop.core.targets.opencode.shutil.which",
        side_effect=lambda n: "/opt/homebrew/bin/brew" if n == "brew" else None,
    ), mock.patch("byop.core.targets.opencode._run", _run):
        OpencodeTarget().install(log=lambda m: None)
    assert any("brew" in c and "install" in c for c in calls)
