"""Secure API key injection for Zed providers.

Zed reads OpenAI-compatible provider keys from the macOS login keychain
(``security``) keyed by the provider's ``api_url`` as the server and
``Bearer`` as the account, or from the environment variable derived from the
provider name (``<PROVIDER_NAME_UPPER_SNAKE>_API_KEY``).

We prefer the keychain because it keeps the secret out of shell history and
dotfiles, but we also support writing the env var to a profile as a fallback.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

LOGIN_KEYCHAIN = str(Path.home() / "Library" / "Keychains" / "login.keychain-db")

# `security delete-internet-password` / `security find-internet-password`
# exit with code 44 when the requested entry does not exist. That's an
# expected, recoverable condition we treat as a no-op everywhere.
_SECURITY_ITEM_NOT_FOUND = 44


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def keychain_has(server: str, account: str = "Bearer") -> bool:
    """Return True if a matching keychain entry already exists.

    Exits 44 ("item not found") from ``security`` is mapped to False; every
    other failure is propagated so callers hear about a locked keychain or
    permission denied instead of silently being told the entry is missing.
    """

    res = _run(
        ["security", "find-internet-password", "-s", server, "-a", account]
    )
    if res.returncode == 0:
        return True
    if res.returncode == _SECURITY_ITEM_NOT_FOUND:
        return False
    raise RuntimeError(
        f"Keychain lookup failed (exit {res.returncode}):\n"
        + (res.stderr or "")
    )


def security_command_ref(server: str, account: str = "Bearer") -> str:
    """Build the ``!security find-internet-password ...`` shell-out string.

    Targets embed this verbatim in their settings JSON for the ``apiKey``
    field, so the editor reads the secret at request time without ever
    persisting plaintext.

    The ``server`` and ``account`` values are shell-quoted with
    :func:`shlex.quote` to prevent injection when the editor interprets
    the ``!command`` reference.
    """
    return (
        f"!security find-internet-password"
        f" -s {shlex.quote(server)}"
        f" -a {shlex.quote(account)}"
        f" -w"
    )


def keychain_get(server: str, account: str = "Bearer") -> str | None:
    """Return the stored secret, or ``None`` if not present."""

    res = _run(
        ["security", "find-internet-password", "-s", server, "-a", account, "-w"]
    )
    if res.returncode == 0:
        return res.stdout.strip() or None
    if res.returncode == _SECURITY_ITEM_NOT_FOUND:
        return None
    raise RuntimeError(
        f"Keychain read failed (exit {res.returncode}):\n"
        + (res.stderr or "")
    )


def keychain_set(server: str, api_key: str, account: str = "Bearer") -> None:
    """Store (or replace) the API key in the login keychain.

    Uses ``-U`` (update) so the operation is atomic: if the entry exists it
    is updated in place; if it does not exist ``-U`` is silently ignored and
    the entry is created.  This avoids the old delete-then-add sequence
    that could lose the existing key if the add failed.
    """
    cmd = [
        "security",
        "add-internet-password",
        "-U",
        "-a",
        account,
        "-s",
        server,
        "-w",
        api_key,
        LOGIN_KEYCHAIN,
    ]
    res = _run(cmd)
    if res.returncode != 0:
        raise RuntimeError(
            "Failed to store API key in keychain:\n" + (res.stderr or "")
        )


def keychain_delete(server: str, account: str = "Bearer") -> None:
    """Remove the keychain entry if it exists.

    ``security delete-internet-password`` exits 0 if the entry was removed
    and a non-fatal "item not found" code (44) if there was nothing to
    delete. Any other failure is propagated so callers learn about real
    keychain problems (locked keychain, permission denied).
    """
    res = _run(["security", "delete-internet-password", "-s", server, "-a", account])
    if res.returncode not in (0, _SECURITY_ITEM_NOT_FOUND):
        raise RuntimeError(
            "Failed to remove keychain entry:\n" + (res.stderr or "")
        )


def env_var_export_line(env_var: str, api_key: str) -> str:
    return f'export {env_var}="{api_key}"'


def profile_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / ".zshrc",
        home / ".zprofile",
        home / ".bash_profile",
        home / ".bashrc",
        home / ".profile",
    ]


def find_env_in_profiles(env_var: str) -> Path | None:
    """Return the first profile file that already exports ``env_var``."""

    marker = f"export {env_var}="
    for path in profile_candidates():
        if path.exists():
            try:
                if marker in path.read_text(encoding="utf-8", errors="ignore"):
                    return path
            except OSError:
                continue
    return None


def write_env_to_profile(
    env_var: str, api_key: str, profile: Path | None = None
) -> Path:
    """Append the env var export to a shell profile (default: ``~/.zshrc``)."""

    target = profile or (Path.home() / ".zshrc")
    line = env_var_export_line(env_var, api_key)
    existed = find_env_in_profiles(env_var)
    if existed == target:
        # Already present in the chosen profile; do not duplicate.
        existing = target.read_text(encoding="utf-8", errors="ignore")
        if line in existing:
            return target
    with target.open("a", encoding="utf-8") as fh:
        fh.write("\n# Added by byop for custom LLM provider\n")
        fh.write(line + "\n")
    return target


def ensure_key(
    server: str,
    api_key: str,
    env_var: str,
    log: Callable[[str], None] = print,
    use_keychain: bool = True,
    use_env: bool = False,
) -> list[str]:
    """Store the API key via keychain and/or env var.

    Returns a list of human-readable notes about what was done.
    """

    notes: list[str] = []
    if use_keychain:
        keychain_set(server, api_key)
        log(f"Stored API key in login keychain (server={server}).")
        notes.append(f"keychain:{server}")
    if use_env:
        path = write_env_to_profile(env_var, api_key)
        log(f"Exported {env_var} in {path}.")
        notes.append(f"env:{path}")
    if not notes:
        raise RuntimeError("No key storage method selected.")
    return notes
