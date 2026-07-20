"""Tests for Zed install/upgrade detection (subprocess mocked)."""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core import zed as zedmod


def test_has_brew_true():
    with mock.patch.object(zedmod.shutil, "which", return_value="/opt/homebrew/bin/brew"):
        assert zedmod.has_brew() is True


def test_has_brew_false():
    with mock.patch.object(zedmod.shutil, "which", return_value=None):
        assert zedmod.has_brew() is False


def _result(returncode=0, stdout="", stderr=""):
    class R:
        pass

    r = R()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_is_installed_true():
    with mock.patch.object(zedmod, "is_installed", return_value=True):
        assert zedmod.is_installed() is True


def test_is_installed_false():
    with mock.patch.object(zedmod, "is_installed", return_value=False):
        assert zedmod.is_installed() is False


def test_installed_version_parses():
    with mock.patch.object(zedmod, "installed_version", return_value="1.11.3"):
        assert zedmod.installed_version() == "1.11.3"


def test_brew_installed_true():
    with mock.patch.object(zedmod, "has_brew", return_value=True), \
         mock.patch.object(zedmod, "_run") as run:
        run.return_value.returncode = 0
        assert zedmod.brew_installed() is True


def test_brew_installed_false():
    with mock.patch.object(zedmod, "has_brew", return_value=True), \
         mock.patch.object(zedmod, "_run") as run:
        run.return_value.returncode = 1
        assert zedmod.brew_installed() is False


def test_install_via_brew_when_missing():
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

    with mock.patch.object(zedmod, "has_brew", return_value=True), \
         mock.patch.object(zedmod, "is_installed", return_value=False), \
         mock.patch.object(zedmod, "brew_installed", return_value=False), \
         mock.patch.object(zedmod, "_run", _run):
        zedmod.install(log=lambda m: None)
    assert any(c[0:3] == ["brew", "install", "--cask"] for c in calls)


def test_upgrade_already_up_to_date_is_ok():
    with mock.patch.object(zedmod, "has_brew", return_value=True), \
         mock.patch.object(zedmod, "brew_installed", return_value=True), \
         mock.patch.object(zedmod, "_run",
                           return_value=_result(1, "already up-to-date")):
        # Should not raise.
        zedmod.upgrade(log=lambda m: None)


def test_latest_release_tag_parses_json():
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"tag_name": "v9.9.9"}'

    with mock.patch("urllib.request.urlopen", return_value=_Resp()), \
         mock.patch("urllib.request.Request") as req:
        assert zedmod.latest_release_tag() == "v9.9.9"
        # The request must identify itself with a User-Agent.
        assert req.call_args.kwargs.get("headers", {}).get("User-Agent")


def test_install_via_download_fallback(tmp_path):
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

    tmp = mock.MagicMock()
    tmp.TemporaryDirectory.return_value.__enter__.return_value = str(tmp_path)

    with mock.patch.object(zedmod, "has_brew", return_value=False), \
         mock.patch.object(zedmod, "is_installed", return_value=False), \
         mock.patch.object(zedmod, "ZED_APP") as zapp, \
         mock.patch.object(zedmod, "ZED_CLI") as zcli, \
         mock.patch.object(zedmod, "_run", _run), \
         mock.patch.object(zedmod, "tempfile", tmp), \
         mock.patch.object(zedmod, "latest_release_tag",
                           return_value="v1.11.3"), \
         mock.patch("urllib.request.urlretrieve") as urlretrieve:
        zapp.exists.return_value = False
        zcli.exists.return_value = False
        urlretrieve.return_value = None
        zedmod._install_via_download(log=lambda m: None)

    assert any(c[0] == "hdiutil" for c in calls)
    assert any(c[0] == "cp" for c in calls)

