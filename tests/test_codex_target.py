"""Tests for the Codex target."""

import tomllib
from pathlib import Path
from unittest import mock

import pytest

from byop.core.config import ModelConfig, ProviderConfig
from byop.core.targets.codex import CodexTarget


def _provider(**over):
    base = {
        "provider_name": "HyberOrbit",
        "api_url": "https://api.example.com/v1/",
        "api_key": "sk-12345678",
        "models": [ModelConfig(name="hy3", reasoning_effort="high")],
    }
    base.update(over)
    return ProviderConfig(**base)


def test_codex_default_path():
    assert CodexTarget().config_path == Path.home() / ".codex" / "config.toml"


def test_codex_is_installed_detects_config_parent(tmp_path):
    assert CodexTarget(tmp_path / "config.toml").is_installed() is True


def test_codex_build_fragment_uses_responses_and_env_key():
    fragment = CodexTarget().build_fragment(_provider(), use_keychain=False, use_env=True)
    assert fragment["model"] == "hy3"
    block = fragment["model_providers"]["HyberOrbit"]
    assert block["base_url"] == "https://api.example.com/v1"
    assert block["wire_api"] == "responses"
    assert block["env_key"] == "HYBERORBIT_API_KEY"
    assert _provider().api_key not in str(fragment)


def test_codex_build_fragment_uses_command_auth_without_secret():
    fragment = CodexTarget().build_fragment(_provider())
    block = fragment["model_providers"]["HyberOrbit"]
    assert block["auth"]["command"] == "security"
    assert block["auth"]["args"][-1] == "-w"
    assert "env_key" not in block
    assert "sk-12345678" not in str(fragment)


def test_codex_build_fragment_rejects_missing_credentials():
    with pytest.raises(ValueError, match="either keychain storage"):
        CodexTarget().build_fragment(_provider(), use_keychain=False, use_env=False)


def test_codex_configure_merges_and_preserves_other_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model = "old"\n[features]\njs_repl = false\n', encoding="utf-8")
    target = CodexTarget(path)
    with mock.patch("byop.core.targets.codex.kc.ensure_key"):
        target.configure(_provider(), use_keychain=False, use_env=True, log=lambda _: None)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["model"] == "hy3"
    assert data["model_provider"] == "HyberOrbit"
    assert data["features"]["js_repl"] is False


def test_codex_skip_does_not_write(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model_provider = "HyberOrbit"\n', encoding="utf-8")
    target = CodexTarget(path)
    with mock.patch.object(Path, "write_text") as write:
        target.configure(_provider(), use_keychain=False, use_env=True,
                         conflict_action="skip", log=lambda _: None)
    write.assert_not_called()


def test_codex_rejects_append(tmp_path):
    with pytest.raises(ValueError, match="one active model provider"):
        CodexTarget(tmp_path / "config.toml").configure(
            _provider(), use_keychain=False, use_env=True,
            conflict_action="append", log=lambda _: None
        )


def test_codex_current_provider_names(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model_provider = "HyberOrbit"\n', encoding="utf-8")
    assert CodexTarget(path).current_provider_names() == ["HyberOrbit"]
