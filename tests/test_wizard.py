"""Smoke test for the interactive wizard path (run_wizard).

The wizard is the default mode users hit; this drives it end-to-end with the
prompt layer mocked out so we exercise ProviderConfig assembly without a TTY.
"""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from byop.core import wizard


def _patch_wizard(ask_seq, ask_int_seq, confirm_seq, secret="sk-test123"):
    return (
        mock.patch.object(wizard.prompt, "ask", side_effect=ask_seq),
        mock.patch.object(wizard.prompt, "ask_secret", return_value=secret),
        mock.patch.object(wizard.prompt, "ask_int", side_effect=ask_int_seq),
        mock.patch.object(wizard.prompt, "confirm", side_effect=confirm_seq),
    )


def test_run_wizard_builds_provider_and_prefs():
    ask = [
        "MyProvider",                 # provider name
        "https://api.example.com/v1",  # api base url
        "my-model",                   # model id
        "",                           # display name (blank)
        "",                           # reasoning effort (blank)
    ]
    ask_int = [128000, 32000]
    confirm = [
        False,  # supports images
        False,  # interleaved reasoning
        False,  # max_tokens parameter
        False,  # add another model? -> no
        True,   # default agent
        True,   # inline assistant
        False,  # commit message
        False,  # thread summary
        False,  # edit predictions
        True,   # use keychain
        False,  # use env
    ]
    p_ask, p_secret, p_int, p_confirm = _patch_wizard(ask, ask_int, confirm)
    with p_ask, p_secret, p_int, p_confirm:
        provider, prefs = wizard.run_wizard()

    assert provider.provider_name == "MyProvider"
    assert provider.normalized_api_url() == "https://api.example.com/v1"
    assert provider.api_key == "sk-test123"
    assert len(provider.models) == 1
    assert provider.models[0].name == "my-model"
    assert provider.set_default_agent is True
    assert provider.set_inline_assistant is True
    assert provider.set_commit_message is False
    assert provider.set_thread_summary is False
    assert provider.use_edit_predictions is False
    assert prefs == {"use_keychain": True, "use_env": False}


def test_run_wizard_multiple_models():
    ask = [
        "MyProvider",
        "https://api.example.com/v1",
        "m1", "", "",   # model 1: id, display, reasoning
        "m2", "", "",   # model 2: id, display, reasoning
    ]
    ask_int = [128000, 32000, 200000, 64000]
    confirm = [
        False, False, False, True,    # model 1 caps + add another? yes
        False, False, False, False,   # model 2 caps + add another? no
        True, True, False, False, False, True, False,  # run_wizard prefs
    ]
    p_ask, p_secret, p_int, p_confirm = _patch_wizard(ask, ask_int, confirm)
    with p_ask, p_secret, p_int, p_confirm:
        provider, _ = wizard.run_wizard()

    assert [m.name for m in provider.models] == ["m1", "m2"]


def test_run_wizard_keychain_opt_out():
    ask = [
        "MyProvider",
        "https://api.example.com/v1",
        "my-model", "", "",
    ]
    ask_int = [128000, 32000]
    confirm = [
        False, False, False, False,
        True, True, False, False, False,
        False,  # use keychain? no
        True,   # use env? (default flips to True when keychain off)
    ]
    p_ask, p_secret, p_int, p_confirm = _patch_wizard(ask, ask_int, confirm)
    with p_ask, p_secret, p_int, p_confirm:
        _, prefs = wizard.run_wizard()

    assert prefs == {"use_keychain": False, "use_env": True}
