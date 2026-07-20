"""py.dev (Pi) target: wires a provider into ~/.pi/agent/models.json."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from .. import keychain as kc
from ..config import ProviderConfig

AGENT_DIR = Path.home() / ".pi" / "agent"
MODELS_PATH = AGENT_DIR / "models.json"


class PyTarget:
    """Configures py.dev (the 'Pi' coding agent) with a custom provider.

    py.dev reads ``~/.pi/agent/models.json`` (JSON, not JSONC). Per Pi's
    credential resolution order, an ``apiKey`` value in ``models.json`` may be:

    * a literal key (works, but stores the secret in plaintext),
    * ``"$ENV_VAR"`` (requires the variable in Pi's process environment),
    * ``"!command"`` (executed and its stdout used as the key).

    In our experience Pi 0.80.x does **not** resolve custom provider keys from
    ``~/.pi/agent/auth.json``, and ``$ENV_VAR`` only works if the variable is
    present when Pi starts (which is not guaranteed for GUI launches). The
    most robust, secure option is therefore a ``!command`` that reads the key
    from the macOS login keychain — the same keychain entry Zed's setup writes
    (server = api_url, account = ``Bearer``). This keeps the secret out of any
    config file and works for both terminal and GUI launches.

    If no keychain entry exists we fall back to embedding the literal key in
    ``models.json`` so the provider still works.
    """

    name = "py"
    display_name = "py.dev (Pi)"

    def __init__(self, models_path: Path = MODELS_PATH) -> None:
        self.models_path = models_path

    # ------------------------------------------------------------------
    def is_installed(self) -> bool:
        return shutil.which("pi") is not None or (Path.home() / ".pi").exists()

    def install(self, log: Callable[[str], None] = print) -> None:
        if shutil.which("brew") is not None:
            log("Installing py.dev via Homebrew...")
            import subprocess

            res = subprocess.run(
                ["brew", "install", "--cask", "pi"],
                capture_output=True, text=True, check=False,
            )
            if res.returncode != 0:
                raise RuntimeError(
                    "Homebrew install of pi failed:\n" + (res.stderr or res.stdout)
                )
            log("py.dev installed via Homebrew.")
            return
        log(
            "Homebrew not found. Install py.dev from https://pi.dev "
            "and re-run zedx."
        )

    # ------------------------------------------------------------------
    def _api_key_ref(self, provider: ProviderConfig) -> str:
        """Return the ``apiKey`` value to write for Pi.

        Prefer a keychain ``!command`` read (secure, launch-independent).
        Fall back to the literal key if no keychain entry is present.
        """

        server = provider.keychain_server()
        account = "Bearer"
        if kc.keychain_has(server, account):
            return (
                f"!security find-internet-password -s {server} "
                f"-a {account} -w"
            )
        return provider.api_key

    # ------------------------------------------------------------------
    def _model_entry(self, model) -> dict:
        entry = {
            "id": model.name,
            "name": model.display_name or model.name,
            "contextWindow": model.max_tokens,
            "maxTokens": model.max_output_tokens,
            "input": ["text", "image"] if model.capabilities.get("images") else ["text"],
        }
        if model.reasoning_effort or model.capabilities.get("interleaved_reasoning"):
            entry["reasoning"] = True
            if model.reasoning_effort and model.reasoning_effort != "none":
                entry["thinkingLevelMap"] = {
                    "minimal": None,
                    "low": None,
                    "medium": None,
                    "high": model.reasoning_effort,
                    "xhigh": None,
                    "max": None,
                }
        return entry

    def build_fragment(self, provider: ProviderConfig) -> dict:
        provider_block: dict = {
            "baseUrl": provider.normalized_api_url(),
            "api": "openai-completions",
            "apiKey": self._api_key_ref(provider),
            "authHeader": True,
        }
        any_max_tokens_param = any(
            m.capabilities.get("max_tokens_parameter") for m in provider.models
        )
        any_reasoning = any(
            (m.reasoning_effort and m.reasoning_effort != "none")
            or m.capabilities.get("interleaved_reasoning")
            for m in provider.models
        )
        compat: dict = {}
        if any_max_tokens_param:
            compat["maxTokensField"] = "max_tokens"
        if any_reasoning:
            compat["supportsReasoningEffort"] = True
        if compat:
            provider_block["compat"] = compat

        provider_block["models"] = [self._model_entry(m) for m in provider.models]
        return {"providers": {provider.provider_name: provider_block}}

    # ------------------------------------------------------------------
    def configure(
        self,
        provider: ProviderConfig,
        *,
        dry_run: bool = False,
        use_keychain: bool = True,
        use_env: bool = False,
        log: Callable[[str], None] = print,
    ) -> None:
        errors = provider.validate()
        if errors:
            raise ValueError("Invalid provider configuration:\n  - " +
                             "\n  - ".join(errors))

        fragment = self.build_fragment(provider)

        if dry_run:
            log("[dry-run] py.dev would write the following models.json fragment:")
            log(json.dumps(fragment, indent=2))
            return

        # Merge into models.json preserving other providers.
        self.models_path.parent.mkdir(parents=True, exist_ok=True)
        current = self._load()
        providers = current.setdefault("providers", {})
        providers[provider.provider_name] = fragment["providers"][
            provider.provider_name
        ]
        self._write(current)
        log(f"Updated py.dev models at {self.models_path}")
        if fragment["providers"][provider.provider_name]["apiKey"].startswith("!"):
            log("API key is read from the macOS keychain at runtime (secure).")
        else:
            log(
                "Warning: API key is embedded in models.json in plaintext "
                "(no keychain entry was found)."
            )

    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if not self.models_path.exists():
            return {}
        try:
            return json.loads(self.models_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Could not parse {self.models_path}: {exc}"
            ) from exc

    def _write(self, data: dict) -> None:
        self.models_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def current_provider_names(self) -> list[str]:
        data = self._load()
        block = data.get("providers", {})
        return list(block.keys()) if isinstance(block, dict) else []
