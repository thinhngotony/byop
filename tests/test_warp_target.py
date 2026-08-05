from unittest import mock

import pytest

from byop.core.config import ModelConfig, ProviderConfig
from byop.core.targets.warp import WarpTarget, validate_warp_endpoint


def provider(url="https://api.example.com/v1"):
    return ProviderConfig("Demo", url, "secret-key-123", [ModelConfig("model")])


def test_detection_from_temp_settings(tmp_path):
    with mock.patch("byop.core.targets.warp.WARP_APP", tmp_path / "Warp.app"), mock.patch("byop.core.targets.warp.shutil.which", return_value=None):
        assert WarpTarget(tmp_path / ".warp" / "settings.toml").is_installed() is False
        (tmp_path / ".warp").mkdir()
        assert WarpTarget(tmp_path / ".warp" / "settings.toml").is_installed() is True

def test_dry_run_redacts_key_and_does_not_write(tmp_path):
    path = tmp_path / ".warp" / "settings.toml"
    logs = []
    WarpTarget(path).configure(provider(), dry_run=True, log=logs.append)
    assert not path.exists()
    output = "\n".join(logs)
    assert "REDACTED" in output
    assert "secret-key-123" not in output


def test_unknown_schema_refuses_write(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[unrelated]\nvalue = "keep"\n')
    logs = []
    WarpTarget(path).configure(provider(), log=logs.append)
    assert "value = \"keep\"" in path.read_text()
    assert any("manual step required" in item for item in logs)


def test_append_rejected(tmp_path):
    with pytest.raises(ValueError, match="append"):
        WarpTarget(tmp_path / "settings.toml").configure(provider(), conflict_action="append", log=lambda _: None)


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://localhost/v1", "https://127.0.0.1/v1"])
def test_endpoint_must_be_public_https(url):
    with pytest.raises(ValueError):
        validate_warp_endpoint(url)


def test_toml_round_trip_preserves_unrelated_tables(tmp_path):
    path = tmp_path / "settings.toml"
    target = WarpTarget(path)
    data = {"general": {"theme": "dark"}, "telemetry": {"enabled": False}}
    target.write_settings(data)
    assert target.load_settings() == data
