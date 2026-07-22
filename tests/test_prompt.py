"""Tests for byop.core.prompt — primarily the ESC-byte sanitizer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core import prompt


def test_strip_escape_chars_removes_esc_bytes():
    """Bare ESC bytes (\x1b) — what the terminal delivers on the ESC key —
    must be stripped. This is the regression we hit when the user accidentally
    hits ESC during the JSON-paste prompt and the prompt echoed ^[^[^[^[^[.
    """
    assert prompt._strip_escape_chars("hello") == "hello"
    assert prompt._strip_escape_chars("\x1b\x1b\x1b\x1b\x1b") == ""
    assert prompt._strip_escape_chars("a\x1bb\x1bc") == "abc"
    # Caret-notation rendering shouldn't appear because we strip at byte
    # level, but the ANSI sequences CSI A/B/C/D (arrow keys) also start with
    # ESC and are equally meaningless as wizard answers.
    assert prompt._strip_escape_chars("\x1b[A\x1b[B") == "[A[B"


def test_strip_escape_chars_does_not_touch_legitimate_text():
    """Letters, digits, slashes, braces — all preserved."""
    payload = '{"name": "HyberOrbit", "url": "https://api.example.com/v1"}'
    assert prompt._strip_escape_chars(payload) == payload
