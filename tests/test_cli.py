"""End-to-end smoke test for the CLI entry point (targets mocked)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop import cli


def test_cli_dry_run_non_interactive(monkeypatch):
    calls = {"install": 0, "configure": 0}

    class FakeTarget:
        name = "zed"
        display_name = "Zed"

        def is_installed(self):
            return True

        def install(self, log=print):
            calls["install"] += 1

        def configure(self, provider, **kwargs):
            calls["configure"] += 1
            calls["kwargs"] = kwargs

        def current_provider_names(self):
            return []  # No collision -> per-target _pick returns default policy.

    import byop.core.targets as tmod

    monkeypatch.setattr(tmod, "available_targets", lambda settings_path=None: [FakeTarget()])
    monkeypatch.setattr(tmod, "detect_installed", lambda targets: targets)

    rc = cli.main(
        [
            "--provider", "P",
            "--api-url", "https://api.example.com/v1",
            "--api-key", "sk-x",
            "--model", "m1",
            "--dry-run",
        ]
    )

    assert rc == 0
    assert calls["install"] == 1
    assert calls["configure"] == 1


def test_cli_non_interactive_requires_provider(monkeypatch, capsys):
    rc = cli.main(["--api-url", "https://api.example.com/v1"])
    assert rc == 2


def test_cli_config_file_path(monkeypatch, tmp_path):
    cfg = tmp_path / "provider.json"
    cfg.write_text(json.dumps({
        "provider_name": "P",
        "api_url": "https://api.example.com/v1",
        "api_key": "sk-x",
        "models": [{"name": "m1"}],
    }))
    called = {"configure": 0, "install": 0}

    class FT:
        name = "zed"
        display_name = "Zed"
        existing = []

        def is_installed(self):
            return True

        def install(self, log=print):
            called["install"] += 1

        def configure(self, provider, **kw):
            called["configure"] += 1

        def current_provider_names(self):
            return list(self.existing)

    import byop.core.targets as tmod

    monkeypatch.setattr(tmod, "available_targets", lambda settings_path=None: [FT()])
    monkeypatch.setattr(tmod, "detect_installed", lambda targets: targets)

    rc = cli.main(["--config-file", str(cfg), "--dry-run"])
    assert rc == 0
    assert called["configure"] == 1


def test_cli_target_choices_include_omp_and_claude():
    """The --target flag must accept the new options without a parse error."""
    parser = cli.build_parser()
    # Argparse rejects unknown choices; if the list isn't updated, this errors.
    for action in parser._actions:
        if "--target" in str(action.option_strings):
            assert "omp" in action.choices
            assert "claude" in action.choices
            assert "opencode" in action.choices
            return
    raise AssertionError("--target action not found")


def test_cli_runs_only_opencode_target(monkeypatch, tmp_path):
    """`--target opencode` must route through OpencodeTarget.configure end-to-end."""
    from byop.core.targets.opencode import OpencodeTarget

    target = OpencodeTarget(config_path=tmp_path / "opencode.json")
    seen = {"calls": 0}

    real_configure = target.configure

    def _track(provider, **kw):
        seen["calls"] += 1
        return real_configure(provider, **kw)

    target.configure = _track  # type: ignore[assignment]

    import byop.core.targets as tmod
    monkeypatch.setattr(tmod, "available_targets", lambda settings_path=None: [target])
    monkeypatch.setattr(tmod, "detect_installed", lambda targets: targets)
    monkeypatch.setattr("byop.core.targets.opencode.kc.keychain_has", lambda *a, **k: True)
    monkeypatch.setattr("byop.core.targets.opencode.kc.ensure_key", lambda *a, **k: ["k:x"])

    rc = cli.main([
        "--provider", "P",
        "--api-url", "https://api.example.com/v1",
        "--api-key", "sk-12345678",
        "--model", "m1",
        "--target", "opencode",
    ])

    assert rc == 0
    assert seen["calls"] == 1
    data = json.loads((tmp_path / "opencode.json").read_text())
    assert "P" in data["provider"]


def test_cli_conflict_flag_passed_to_configure(monkeypatch, tmp_path):
    """--conflict skip must be threaded into ZedTarget.configure(...)."""
    cfg = tmp_path / "provider.json"
    cfg.write_text(json.dumps({
        "provider_name": "P",
        "api_url": "https://api.example.com/v1",
        "api_key": "sk-x",
        "models": [{"name": "m1"}],
    }))
    captured = {}

    class FT:
        name = "zed"
        display_name = "Zed"
        existing = ["P"]

        def is_installed(self):
            return True

        def install(self, log=print):
            pass

        def configure(self, provider, **kw):
            captured["conflict_action"] = kw.get("conflict_action")

        def current_provider_names(self):
            return list(self.existing)

    import byop.core.targets as tmod

    monkeypatch.setattr(tmod, "available_targets", lambda settings_path=None: [FT()])
    monkeypatch.setattr(tmod, "detect_installed", lambda targets: targets)

    rc = cli.main([
        "--config-file", str(cfg),
        "--conflict", "skip",
        "--dry-run",
    ])
    assert rc == 0
    assert captured["conflict_action"] == "skip"


def test_cli_config_file_missing_key_rejected(monkeypatch, tmp_path):
    cfg = tmp_path / "provider.json"
    cfg.write_text(json.dumps({
        "provider_name": "P",
        "api_url": "https://api.example.com/v1",
        "models": [{"name": "m1"}],
    }))
    rc = cli.main(["--config-file", str(cfg), "--target", "zed"])
    # api_key missing -> CLI exits 2.
    assert rc == 2


def test_cli_conflict_prompt_in_non_interactive_rejected(monkeypatch, tmp_path, capsys):
    """--conflict prompt is meaningless without a TTY and must exit 2."""
    cfg = tmp_path / "provider.json"
    cfg.write_text(json.dumps({
        "provider_name": "P",
        "api_url": "https://api.example.com/v1",
        "api_key": "sk-x",
        "models": [{"name": "m1"}],
    }))

    class FT:
        name = "zed"
        display_name = "Zed"

        def is_installed(self):
            return True

        def install(self, log=print):
            pass

        def configure(self, provider, **kw):
            pass

        def current_provider_names(self):
            return []

    import byop.core.targets as tmod

    monkeypatch.setattr(tmod, "available_targets", lambda settings_path=None: [FT()])
    monkeypatch.setattr(tmod, "detect_installed", lambda targets: targets)

    rc = cli.main(["--config-file", str(cfg), "--conflict", "prompt", "--dry-run"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "--conflict prompt requires an interactive TTY" in captured.err


def test_cli_conflict_append_against_single_provider_rejected(monkeypatch, tmp_path, capsys):
    """--conflict append must refuse zed/claude (single-provider targets)."""
    cfg = tmp_path / "provider.json"
    cfg.write_text(json.dumps({
        "provider_name": "P",
        "api_url": "https://api.example.com/v1",
        "api_key": "sk-x",
        "models": [{"name": "m1"}],
    }))

    class FT:
        name = "zed"
        display_name = "Zed"
        existing = ["P"]

        def is_installed(self):
            return True

        def install(self, log=print):
            pass

        def configure(self, provider, **kw):
            pass

        def current_provider_names(self):
            return list(self.existing)

    import byop.core.targets as tmod

    monkeypatch.setattr(tmod, "available_targets", lambda settings_path=None: [FT()])
    monkeypatch.setattr(tmod, "detect_installed", lambda targets: targets)

    rc = cli.main([
        "--config-file", str(cfg),
        "--conflict", "append",
        "--target", "zed",
        "--dry-run",
    ])
    assert rc == 2
    captured = capsys.readouterr()
    assert "append is not supported for" in captured.err


def test_cli_ctrl_c_exits_cleanly(monkeypatch, capsys):
    """Ctrl+C during the interactive wizard prints cancellation, not a traceback."""
    def raise_keyboard_interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.wizard, "run_wizard", raise_keyboard_interrupt)

    rc = cli.main([])

    assert rc == 130
    assert "Cancelled." in capsys.readouterr().out
