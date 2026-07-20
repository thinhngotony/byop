"""Tests for JSONC parsing/serialization and settings merge/write."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core import settings as sett


def test_loads_strips_line_comments():
    text = '{\n  // a comment\n  "a": 1\n}'
    assert sett.loads(text) == {"a": 1}


def test_loads_strips_block_comments():
    text = '{\n  /* block\n comment */ "a": 1\n}'
    assert sett.loads(text) == {"a": 1}


def test_loads_keeps_urls_in_strings():
    text = '{"url": "https://x.com/v1"}'
    assert sett.loads(text)["url"] == "https://x.com/v1"


def test_loads_handles_trailing_comma():
    text = '{\n  "a": 1,\n  "b": 2,\n}'
    assert sett.loads(text) == {"a": 1, "b": 2}


def test_loads_keeps_comment_like_in_key():
    text = '{"https://x": 1}'
    assert sett.loads(text) == {"https://x": 1}


def test_load_path_missing_returns_empty():
    assert sett.load_path(Path("/nonexistent/settings.json")) == {}


def test_merge_deep():
    base = {"language_models": {"openai_compatible": {"A": {"x": 1}}}}
    update = {"language_models": {"openai_compatible": {"B": {"y": 2}}}}
    merged = sett.merge(base, update)
    assert merged["language_models"]["openai_compatible"]["A"] == {"x": 1}
    assert merged["language_models"]["openai_compatible"]["B"] == {"y": 2}
    # base not mutated
    assert "B" not in base["language_models"]["openai_compatible"]


def test_merge_overrides_scalar():
    base = {"agent": {"default_model": {"model": "old"}}}
    update = {"agent": {"default_model": {"model": "new"}}}
    merged = sett.merge(base, update)
    assert merged["agent"]["default_model"]["model"] == "new"


def test_write_and_reload_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        data = {"a": 1, "b": {"c": [1, 2, 3]}}
        sett.write_path(path, data)
        assert path.exists()
        assert sett.load_path(path) == data


def test_write_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "dir" / "settings.json"
        sett.write_path(path, {"x": 1})
        assert path.exists()
