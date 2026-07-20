"""End-to-end smoke test for the CLI entry point (targets mocked)."""

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
