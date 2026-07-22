"""OpenCode target: wires a custom OpenAI-compatible provider into OpenCode.

OpenCode (https://opencode.ai) stores its configuration at
``~/.config/opencode/opencode.json`` (or ``opencode.jsonc``). Providers live
under the top-level ``provider`` key, keyed by a user-chosen name. A custom
OpenAI-compatible provider is described with:

* ``npm`` — the AI SDK package; we use ``@ai-sdk/openai-compatible``.
* ``name`` — display name.
* ``options.baseURL`` — the API base URL.
* ``options.apiKey`` — the API key (we mirror the py.dev pattern and prefer a
  ``!security find-internet-password`` shell-out so the secret stays in the
  keychain rather than on disk in plaintext).
* ``models`` — a map of model id -> per-model capabilities.

OpenCode supports multiple named providers, so we offer replace / skip /
append conflict resolution (same as py.dev / omp).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .. import keychain as kc
from ..config import ModelConfig, ProviderConfig

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.json"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class OpencodeTarget:
    """Configures OpenCode with a custom OpenAI-compatible provider."""

    name = "opencode"
    display_name = "OpenCode"

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = config_path

    # ------------------------------------------------------------------
    def is_installed(self) -> bool:
        return self.config_path.parent.exists() or shutil.which("opencode") is not None

    def install(self, log: Callable[[str], None] = print) -> None:
        if shutil.which("brew") is not None:
            log("Installing OpenCode via Homebrew...")
            res = _run(["brew", "install", "--cask", "opencode"])
            if res.returncode == 0:
                log("OpenCode installed via Homebrew.")
                return
            log(
                f"brew install failed: {res.stderr or res.stdout}; "
                f"falling back to the published installer."
            )
        log("Install OpenCode with one of:")
        log("  brew install --cask opencode")
        log("  curl -fsSL https://opencode.ai/install | sh")
        log("then re-run byop.")

    # ------------------------------------------------------------------
    def _api_key_ref(self, provider: ProviderConfig) -> str:
        """Return the apiKey value to embed in opencode.json.

        Prefer a keychain ``!command`` read so the secret stays out of any
        config file. Fall back to the literal key if no keychain entry
        exists.
        """
        server = provider.keychain_server()
        if kc.keychain_has(server):
            return kc.security_command_ref(server)
        return provider.api_key

    def _model_entry(self, model: ModelConfig) -> dict:
        entry: dict = {
            "name": model.display_name or model.name,
            "tool_call": True,
            "temperature": True,
            "attachment": model.capabilities.get("images", False),
        }
        if model.reasoning_effort and model.reasoning_effort != "none":
            entry["reasoning"] = True
        if model.capabilities.get("interleaved_reasoning"):
            entry["interleaved"] = {"field": "reasoning_content"}
        return entry

    def build_fragment(self, provider: ProviderConfig) -> dict:
        provider_block: dict = {
            "name": provider.provider_name,
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": provider.normalized_api_url(),
                "apiKey": self._api_key_ref(provider),
            },
            "models": {
                m.name: self._model_entry(m) for m in provider.models
            },
        }
        return {"provider": {provider.provider_name: provider_block}}

    # ------------------------------------------------------------------
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

        if dry_run:
            fragment = self.build_fragment(provider)
            log("[dry-run] OpenCode would write the following opencode.json fragment:")
            log(json.dumps(fragment, indent=2))
            return

        existing = self._load()
        existing_providers = existing.get("provider") or {}
        name_to_write = provider.provider_name
        if provider.provider_name in existing_providers:
            if conflict_action == "skip":
                log(
                    f"Skip: OpenCode already has {provider.provider_name}; "
                    f"leaving {self.config_path} untouched."
                )
                if use_keychain:
                    kc.ensure_key(
                        server=provider.keychain_server(),
                        api_key=provider.api_key,
                        env_var=provider.env_var_name(),
                        log=log,
                        use_keychain=True,
                        use_env=use_env,
                    )
                return
            if conflict_action == "append":
                i = 2
                while f"{provider.provider_name}_{i}" in existing_providers:
                    i += 1
                name_to_write = f"{provider.provider_name}_{i}"
                log(
                    f"Append: OpenCode already has {provider.provider_name}; "
                    f"writing under {name_to_write}."
                )

        if use_keychain:
            kc.ensure_key(
                server=provider.keychain_server(),
                api_key=provider.api_key,
                env_var=provider.env_var_name(),
                log=log,
                use_keychain=True,
                use_env=use_env,
            )

        fragment = self.build_fragment(provider)
        # If conflict resolution renamed the entry, rewrite its key in-place.
        new_block = fragment["provider"][provider.provider_name]
        if name_to_write != provider.provider_name:
            fragment = {"provider": {name_to_write: new_block}}

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        current = self._load()
        providers = current.setdefault("provider", {})
        providers[name_to_write] = new_block
        self._write(current)
        log(f"Updated OpenCode config at {self.config_path}")
        if new_block["options"]["apiKey"].startswith("!"):
            log("API key is read from the macOS keychain at runtime (secure).")
        else:
            log(
                "Warning: --no-keychain was set, so the API key is embedded in "
                "opencode.json in plaintext. Prefer removing --no-keychain so "
                "the key is read from the macOS keychain instead."
            )

    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Could not parse {self.config_path}: {exc}"
            ) from exc

    def _write(self, data: dict) -> None:
        self.config_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def current_provider_names(self) -> list[str]:
        data = self._load()
        block = data.get("provider", {})
        return list(block.keys()) if isinstance(block, dict) else []

    def export_config(self) -> dict:
        """Return the byop-managed slice of opencode.json (top-level ``provider``)."""
        data = self._load()
        providers = data.get("provider", {})
        return {
            self.name: {
                "config_path": str(self.config_path),
                "providers": dict(providers) if isinstance(providers, dict) else {},
            }
        }
