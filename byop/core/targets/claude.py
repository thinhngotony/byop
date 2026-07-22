"""Claude Code target: wires a provider into ~/.claude/settings.json."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .. import keychain as kc
from ..config import ProviderConfig

DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class ClaudeTarget:
    name = "claude"
    display_name = "Claude Code"

    def __init__(self, settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.settings_path = settings_path

    # ------------------------------------------------------------------
    # Install / detection
    # ------------------------------------------------------------------
    def is_installed(self) -> bool:
        return (
            self.settings_path.parent.exists()
            or shutil.which("claude") is not None
        )

    def install(self, log: Callable[[str], None] = print) -> None:
        if shutil.which("brew") is not None:
            log("Installing Claude Code via Homebrew...")
            res = _run(["brew", "install", "--cask", "claude-code"])
            if res.returncode == 0:
                log("Claude Code installed via Homebrew.")
                return
            log(f"brew install failed: {res.stderr or res.stdout}; trying npm.")

        if shutil.which("npm") is not None:
            log("Installing Claude Code via npm...")
            res = _run(["npm", "install", "-g", "@anthropic-ai/claude-code"])
            if res.returncode == 0:
                log("Claude Code installed via npm.")
                return
            log(f"npm install failed: {res.stderr or res.stdout}; falling back to curl.")

        log("Install Claude Code with one of:")
        log("  brew install --cask claude-code")
        log("  npm install -g @anthropic-ai/claude-code")
        log("  curl -fsSL https://claude.ai/install.sh | sh")

    # ------------------------------------------------------------------
    # Provider fragment + keychain-aware apiKey ref
    # ------------------------------------------------------------------
    def _api_key_ref(self, provider: ProviderConfig) -> str:
        """Return the apiKey value to embed — prefer a keychain `!command`.

        Mirrors PyTarget: the keychain `!security find-internet-password ...`
        shell-out reads the secret at request time, so settings.json holds no
        plaintext. Falls back to the literal key when no entry exists
        (e.g. --no-keychain was passed by the caller).
        """
        server = provider.keychain_server()
        if kc.keychain_has(server):
            return kc.security_command_ref(server)
        return provider.api_key

    def build_fragment(self, provider: ProviderConfig) -> dict:
        primary = provider.models[0]
        return {
            "provider": provider.provider_name,
            "apiBaseUrl": provider.normalized_api_url(),
            "apiKey": self._api_key_ref(provider),
            "models": [
                {
                    "id": m.name,
                    "context_window": m.max_tokens,
                    "max_tokens": m.max_output_tokens,
                }
                for m in provider.models
            ],
            "model": primary.name,
        }

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if not self.settings_path.exists():
            return {}
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Could not parse {self.settings_path}: {exc}"
            ) from exc

    def _write(self, data: dict) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def configure(
        self,
        provider: ProviderConfig,
        *,
        dry_run: bool = False,
        use_keychain: bool = True,
        use_env: bool = False,
        conflict_action: str | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        errors = provider.validate()
        if errors:
            raise ValueError(
                "Invalid provider configuration:\n  - "
                + "\n  - ".join(errors)
            )

        fragment = self.build_fragment(provider)

        if dry_run:
            log(
                "[dry-run] Claude Code would write the following settings "
                "fragment:"
            )
            log(json.dumps(fragment, indent=2))
            return

        # Skip on idempotent re-run: existing entry already points at this
        # provider and api_url. Still ensure the keychain (cheap and idempotent).
        if conflict_action == "skip":
            existing = self._load()
            same = (
                existing.get("provider") == provider.provider_name
                and existing.get("apiBaseUrl") == provider.normalized_api_url()
            )
            if same:
                kc.ensure_key(
                    server=provider.keychain_server(),
                    api_key=provider.api_key,
                    env_var=provider.env_var_name(),
                    log=log,
                    use_keychain=use_keychain,
                    use_env=use_env,
                )
                log(
                    f"Skip: Claude Code already has {provider.provider_name} "
                    f"with the same api_url."
                )
                return

        # Default path: ensure the keychain entry, then write the fragment.
        # Shallow merge at root preserves unknown keys.
        kc.ensure_key(
            server=provider.keychain_server(),
            api_key=provider.api_key,
            env_var=provider.env_var_name(),
            log=log,
            use_keychain=use_keychain,
            use_env=use_env,
        )
        current = self._load()
        merged = {**current, **fragment}
        self._write(merged)
        log(f"Updated Claude Code settings at {self.settings_path}")

    def current_provider_names(self) -> list[str]:
        data = self._load()
        name = data.get("provider")
        return [name] if isinstance(name, str) and name else []

    def export_config(self) -> dict:
        """Return the byop-managed slice of Claude Code's ``settings.json``.

        Claude Code is single-provider — there's at most one active provider,
        so we surface it under the same ``providers`` key as multi-provider
        targets, keyed by ``provider`` (or ``""`` if not set).
        """
        data = self._load()
        providers: dict = {}
        name = data.get("provider")
        if isinstance(name, str) and name:
            providers[name] = {
                "provider": name,
                "apiBaseUrl": data.get("apiBaseUrl"),
                "apiKey": data.get("apiKey"),
                "model": data.get("model"),
            }
        return {
            self.name: {
                "config_path": str(self.settings_path),
                "providers": providers,
            }
        }

