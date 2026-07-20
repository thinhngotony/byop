"""Tests for keychain/env key injection (subprocess mocked)."""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core import keychain as kc


def _fake_run(returncode=0, stdout="", stderr=""):
    def _run(cmd, *a, **k):
        class R:
            pass

        r = R()
        r.returncode = returncode
        r.stdout = stdout
        r.stderr = stderr
        return r

    return _run


def test_keychain_has_true():
    with mock.patch.object(kc, "_run", _fake_run(0)):
        assert kc.keychain_has("https://x/v1") is True


def test_keychain_has_false():
    with mock.patch.object(kc, "_run", _fake_run(1)):
        assert kc.keychain_has("https://x/v1") is False


def test_keychain_get_returns_secret():
    with mock.patch.object(kc, "_run", _fake_run(0, "sk-abc\n")):
        assert kc.keychain_get("https://x/v1") == "sk-abc"


def test_keychain_set_calls_add_and_delete():
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

    with mock.patch.object(kc, "_run", _run):
        kc.keychain_set("https://x/v1", "sk-abc")
    # delete then add must both be issued
    delete = [c for c in calls if c[0:2] == ["security", "delete-internet-password"]]
    add = [c for c in calls if c[0:2] == ["security", "add-internet-password"]]
    assert delete and add
    assert "sk-abc" in add[0]
    assert "https://x/v1" in add[0]


def test_keychain_set_raises_on_failure():
    with mock.patch.object(kc, "_run", _fake_run(1, "", "denied")):
        try:
            kc.keychain_set("https://x/v1", "sk-abc")
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass


def test_env_export_line():
    assert kc.env_var_export_line("MY_PROV_API_KEY", "sk-1") == \
        'export MY_PROV_API_KEY="sk-1"'


def test_find_env_in_profiles(tmp_path, monkeypatch):
    prof = tmp_path / ".zshrc"
    prof.write_text('export MYPROV_API_KEY="sk-x"\n')
    monkeypatch.setattr(kc, "profile_candidates", lambda: [prof])
    assert kc.find_env_in_profiles("MYPROV_API_KEY") == prof


def test_write_env_appends_once(tmp_path, monkeypatch):
    prof = tmp_path / ".zshrc"
    prof.write_text("# header\n")
    monkeypatch.setattr(kc, "profile_candidates", lambda: [prof])
    kc.write_env_to_profile("PROV_API_KEY", "sk-1", profile=prof)
    content = prof.read_text()
    assert content.count('export PROV_API_KEY="sk-1"') == 1
    # second write to same profile doesn't duplicate
    kc.write_env_to_profile("PROV_API_KEY", "sk-1", profile=prof)
    assert prof.read_text().count('export PROV_API_KEY="sk-1"') == 1


def test_ensure_key_keychain_only(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "LOGIN_KEYCHAIN", str(tmp_path / "keychain"))
    stored = {}

    def _run(cmd, *a, **k):
        if cmd[0:2] == ["security", "add-internet-password"]:
            stored["server"] = cmd[cmd.index("-s") + 1]
            stored["key"] = cmd[cmd.index("-w") + 1]

        class R:
            pass

        r = R()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with mock.patch.object(kc, "_run", _run):
        notes = kc.ensure_key("https://x/v1", "sk-1", "PROV_API_KEY")
    assert "keychain:https://x/v1" in notes
    assert stored["key"] == "sk-1"
