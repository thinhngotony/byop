"""Codex target: configure a custom OpenAI Responses API provider."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import tomli_w

from .. import keychain as kc
from ..config import ProviderConfig

DEFAULT_CONFIG_PATH = Path.home() / ".codex" / "config.toml"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class CodexTarget:
    """Configure the Codex desktop app and CLI user configuration."""

    name = "codex"
    display_name = "Codex"

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = config_path

    def is_installed(self) -> bool:
        return (
            self.config_path.parent.exists()
            or shutil.which("codex") is not None
            or Path("/Applications/Codex.app").exists()
        )

    def install(self, log: Callable[[str], None] = print) -> None:
        if shutil.which("brew") is not None:
            log("Installing Codex via Homebrew...")
            result = _run(["brew", "install", "--cask", "codex"])
            if result.returncode == 0:
                log("Codex installed via Homebrew.")
                return
            log(f"brew install failed: {result.stderr or result.stdout}")
        log("Install Codex from https://openai.com/codex/ then re-run byop.")

    def build_fragment(
        self,
        provider: ProviderConfig,
        *,
        use_keychain: bool = True,
        use_env: bool = False,
    ) -> dict:
        """Return the Codex TOML fragment without exposing the API key."""
        primary = provider.models[0]
        block: dict = {
            "name": provider.provider_name,
            "base_url": provider.normalized_api_url(),
            "wire_api": "responses",
        }
        if use_keychain:
            block["auth"] = {
                "command": "security",
                "args": [
                    "find-internet-password",
                    "-s",
                    provider.keychain_server(),
                    "-a",
                    "Bearer",
                    "-w",
                ],
                "timeout_ms": 5000,
                "refresh_interval_ms": 300000,
            }
        elif use_env:
            block["env_key"] = provider.env_var_name()
        else:
            raise ValueError(
                "Codex requires either keychain storage or an environment variable."
            )
        return {
            "model": primary.name,
            "model_provider": provider.provider_name,
            "model_providers": {provider.provider_name: block},
        }

    def _load(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            with self.config_path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(f"Could not parse {self.config_path}: {exc}") from exc
        return data

    def _write(self, data: dict) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(tomli_w.dumps(data), encoding="utf-8")

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
            raise ValueError("Invalid provider configuration:\n  - " + "\n  - ".join(errors))
        if conflict_action == "append":
            raise ValueError("Codex supports one active model provider; use replace or skip.")

        if dry_run:
            fragment = self.build_fragment(
                provider, use_keychain=use_keychain, use_env=use_env
            )
            log("[dry-run] Codex would merge this config.toml fragment:")
            log(tomli_w.dumps(fragment))
            return

        if use_keychain:
            kc.ensure_key(
                server=provider.keychain_server(),
                api_key=provider.api_key,
                env_var=provider.env_var_name(),
                log=log,
                use_keychain=True,
                use_env=False,
            )
        fragment = self.build_fragment(
            provider, use_keychain=use_keychain, use_env=use_env
        )

        current = self._load()
        existing_provider = current.get("model_provider")
        if conflict_action == "skip" and existing_provider == provider.provider_name:
            log(f"Skip: Codex already uses {provider.provider_name}.")
            return

        merged = {**current, **fragment}
        self._write(merged)
        log(f"Updated Codex config at {self.config_path}")
        if use_keychain:
            log("Codex will read the API key from the macOS keychain at request time.")
        else:
            log(f"Codex will read the API key from ${provider.env_var_name()}.")

    def current_provider_names(self) -> list[str]:
        data = self._load()
        name = data.get("model_provider")
        return [name] if isinstance(name, str) and name else []

    def export_config(self) -> dict:
        data = self._load()
        name = data.get("model_provider")
        providers = {}
        all_providers = data.get("model_providers", {})
        if isinstance(name, str) and name and isinstance(all_providers, dict):
            if name in all_providers:
                providers[name] = all_providers[name]
        return {
            self.name: {
                "config_path": str(self.config_path),
                "providers": providers,
            }
        }
