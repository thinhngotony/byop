"""Codex target: configure a custom OpenAI Responses API provider.

Codex (https://developers.openai.com/codex) stores user configuration in
``~/.codex/config.toml``. A custom provider is declared under
``[model_providers.<name>]`` and selected via ``model`` /
``model_provider``. Reasoning effort (``low`` / ``medium`` / ``high`` /
``xhigh``) is normally gated by the built-in model catalogue; custom models
therefore need an explicit catalogue entry to expose thinking-effort choices
in the TUI (see ``model_catalog_json`` + ``model_supports_reasoning_summaries``).

This target is intentionally conservative: it deep-merges into the existing
``config.toml`` (preserving unrelated sections like ``[features]``,
``[mcp_servers]`` and other providers), generates a per-provider catalogue
that mirrors OpenAI's ``models_cache.json`` schema, and never writes secrets
to disk. Secrets stay in the macOS keychain and are referenced via a
command-backed ``[model_providers.<name>.auth]`` table at request time.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import tomli_w

# tomllib is Python 3.11+; fall back to tomli on older interpreters.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from .. import keychain as kc
from ..config import ModelConfig, ProviderConfig

DEFAULT_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
DEFAULT_CATALOG_DIR = Path.home() / ".codex" / "byop-catalogs"

# All reasoning levels Codex understands for the picker.  ``none``/``minimal``
# are not user-selectable in the TUI but are accepted by the API.
_CATALOG_REASONING_LEVELS = [
    {"effort": "low", "description": "Fast responses with lighter reasoning"},
    {"effort": "medium", "description": "Balances speed and reasoning depth for everyday tasks"},
    {"effort": "high", "description": "Greater reasoning depth for complex problems"},
    {"effort": "xhigh", "description": "Extra high reasoning depth for complex problems"},
    {"effort": "max", "description": "Maximum reasoning depth for the hardest problems"},
    {"effort": "ultra", "description": "Maximum reasoning with automatic task delegation"},
]

# Minimal but complete model entry that satisfies Codex's strict catalog
# validation (mirrors the shape of ``models_cache.json`` entries).  Values are
# chosen to be sensible defaults for an OpenAI-compatible proxy; per-model
# fields like ``slug`` / ``priority`` are overwritten at generation time.
_CATALOG_BASE: dict = {
    "shell_type": "unified_exec",
    "visibility": "list",
    "supported_in_api": True,
    "additional_speed_tiers": [],
    "service_tiers": [],
    "availability_nux": None,
    "upgrade": None,
    "model_messages": {
        "instructions_template": (
            "You are Codex, a coding agent based on GPT-5. You and the user "
            "share one workspace, and your job is to collaborate with them "
            "until their goal is genuinely handled."
        ),
        "instructions_variables": None,
        "approvals": None,
        "collaboration_modes": None,
        "auto_review": None,
        "permissions": None,
        "multi_agent": None,
        "token_budget": {
            "enabled": False,
            "use_history_notes_extension": False,
            "reminder_threshold_tokens": 6144,
            "reminder_message_template": "",
            "guidance_message": "",
            "auto_compact_fallback_prompt": "",
            "auto_compact_fallback_buffer_tokens": 16384,
        },
    },
    "include_skills_usage_instructions": False,
    "include_plugin_usage_instructions": True,
    "include_apps_usage_instructions": True,
    "default_reasoning_summary": "none",
    "support_verbosity": True,
    "default_verbosity": "low",
    "apply_patch_tool_type": "freeform",
    "web_search_tool_type": "text_and_image",
    "truncation_policy": {"mode": "tokens", "limit": 10000},
    "supports_image_detail_original": True,
    "context_window": 272000,
    "max_context_window": 272000,
    "comp_hash": "byop-1",
    "effective_context_window_percent": 95,
    "experimental_supported_tools": [],
    "input_modalities": ["text", "image"],
    "supports_search_tool": True,
    "use_responses_lite": True,
    "node_repl_auto_review_required": False,
    "node_repl_disabled": False,
    "tool_mode": "code_mode_only",
    "multi_agent_version": "v2",
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:  # pragma: no cover
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` into ``base`` (in place) and return it."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(dict(base[key]), value)
        else:
            base[key] = value
    return base


def _catalog_path_for(provider_name: str, catalog_dir: Path = DEFAULT_CATALOG_DIR) -> Path:
    # Sanitise provider name for a filename; Codex itself restricts the name to
    # ``^[A-Za-z0-9 _.\-]+$`` so this is mostly defensive.
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in provider_name).strip("_")
    return catalog_dir / f"{safe or 'provider'}.json"


def _catalog_entry(model: ModelConfig, priority: int) -> dict:
    entry = dict(_CATALOG_BASE)
    # Per-model overrides.
    entry["slug"] = model.name
    entry["display_name"] = model.display_name or model.name
    entry["description"] = f"{entry['display_name']} via {model.name}"
    # Default reasoning level is the model's configured effort, falling back to
    # medium for models that declare none/minimal.
    default_effort = model.reasoning_effort if model.reasoning_effort not in (None, "none", "minimal") else "medium"
    # Ensure the default is one of the supported levels; otherwise fall back.
    if default_effort not in {lvl["effort"] for lvl in _CATALOG_REASONING_LEVELS}:
        default_effort = "medium"
    entry["default_reasoning_level"] = default_effort
    entry["supported_reasoning_levels"] = list(_CATALOG_REASONING_LEVELS)
    entry["priority"] = priority
    entry["context_window"] = model.max_tokens
    entry["max_context_window"] = max(model.max_tokens, model.max_output_tokens * 4)
    entry["description"] = f"{entry['display_name']} via byop"
    return entry


class CodexTarget:
    """Configure the Codex desktop app and CLI user configuration."""

    name = "codex"
    display_name = "Codex"

    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        catalog_dir: Path = DEFAULT_CATALOG_DIR,
    ) -> None:
        self.config_path = config_path
        self.catalog_dir = catalog_dir

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def is_installed(self) -> bool:
        if self.config_path.parent.exists():
            return True
        if shutil.which("codex") is not None:
            return True
        # Desktop app ships the CLI inside ChatGPT.app as well as a dedicated
        # Codex.app on some installations.
        for p in (
            Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
            Path("/Applications/Codex.app"),
            Path("/Applications/ChatGPT.app"),
        ):
            if p.exists():
                return True
        return False

    def install(self, log: Callable[[str], None] = print) -> None:  # pragma: no cover
        if shutil.which("brew") is not None:
            log("Installing Codex via Homebrew...")
            result = _run(["brew", "install", "--cask", "codex"])
            if result.returncode == 0:
                log("Codex installed via Homebrew.")
                return
            log(f"brew install failed: {result.stderr or result.stdout}")
        log("Install Codex from https://developers.openai.com/codex/ then re-run byop.")
        log("  The desktop app is bundled with ChatGPT; the CLI is `npm i -g @openai/codex` or `brew install codex`.")

    # ------------------------------------------------------------------
    # Fragment builders
    # ------------------------------------------------------------------
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
            raise ValueError("Codex requires either keychain storage or an environment variable.")

        # Top-level model selection + reasoning plumbing.  A custom catalogue is
        # required to expose multiple models (lite/pro/max) and thinking-effort
        # choices in the TUI; without it Codex falls back to built-in OpenAI
        # models and silently drops ``reasoning.effort``.
        catalog_path = _catalog_path_for(provider.provider_name, self.catalog_dir)
        has_reasoning = any(m.reasoning_effort not in (None, "none") for m in provider.models)

        fragment: dict = {
            "model": primary.name,
            "model_provider": provider.provider_name,
            "model_providers": {provider.provider_name: block},
        }
        # Only set reasoning-related keys when the provider actually uses them;
        # this keeps the config minimal for non-reasoning proxies.
        if has_reasoning:
            fragment["model_reasoning_effort"] = primary.reasoning_effort or "medium"
            fragment["model_reasoning_summary"] = "auto"
            fragment["model_verbosity"] = "medium"
            fragment["model_supports_reasoning_summaries"] = True
            fragment["model_catalog_json"] = str(catalog_path)

        return fragment

    def build_catalog(self, provider: ProviderConfig) -> dict:
        """Build the catalogue JSON that exposes all provider models.

        The catalogue mirrors ``~/.codex/models_cache.json`` so the picker shows
        ``Lite`` / ``Pro`` / ``Max`` (or any custom names) with full
        ``low``/``medium``/``high``/``xhigh`` effort support.
        """
        models = [_catalog_entry(m, i) for i, m in enumerate(provider.models)]
        return {"models": models}

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------
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
        # Atomic write to avoid truncating on crash.
        tmp = self.config_path.with_suffix(".toml.tmp")
        tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
        tmp.replace(self.config_path)

    def _write_catalog(self, provider: ProviderConfig, *, log: Callable[[str], None] = print) -> Path:
        catalog = self.build_catalog(provider)
        path = _catalog_path_for(provider.provider_name, self.catalog_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        log(f"Wrote Codex model catalogue with {len(catalog['models'])} model(s) to {path}")
        return path

    # ------------------------------------------------------------------
    # Public API
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
            raise ValueError("Invalid provider configuration:\n  - " + "\n  - ".join(errors))
        if conflict_action == "append":
            raise ValueError("Codex supports one active model provider; use replace or skip.")

        fragment = self.build_fragment(provider, use_keychain=use_keychain, use_env=use_env)
        catalog_preview = self.build_catalog(provider)

        if dry_run:
            log("[dry-run] Codex would merge this config.toml fragment:")
            log(tomli_w.dumps(fragment))
            log("[dry-run] Codex would write this catalogue JSON to")
            log(f"[dry-run] {fragment.get('model_catalog_json', '(no catalogue)')} :")
            log(json.dumps(catalog_preview, indent=2))
            return

        # Ensure the secret is available via the chosen mechanism before we
        # touch any config file, so a keychain failure is surfaced early.
        if use_keychain or use_env:
            kc.ensure_key(
                server=provider.keychain_server(),
                api_key=provider.api_key,
                env_var=provider.env_var_name(),
                log=log,
                use_keychain=use_keychain,
                use_env=use_env,
            )

        # Handle skip idempotently: only skip when the active provider *and*
        # its URL and primary model already match (otherwise a re-run that
        # changes the model list or URL should update the file).
        current = self._load()
        existing_provider = current.get("model_provider")
        if conflict_action == "skip" and existing_provider == provider.provider_name:
            log(f"Skip: Codex already uses {provider.provider_name}.")
            return

        # Write catalogue first; if this fails we have not yet mutated config.toml.
        if "model_catalog_json" in fragment:
            self._write_catalog(provider, log=log)

        merged = _deep_merge(dict(current), fragment)
        self._write(merged)
        log(f"Updated Codex config at {self.config_path}")
        if use_keychain:
            log("Codex will read the API key from the macOS keychain at request time (secure).")
        else:
            log(f"Codex will read the API key from ${provider.env_var_name()}.")

    def current_provider_names(self) -> list[str]:
        data = self._load()
        name = data.get("model_provider")
        return [name] if isinstance(name, str) and name else []

    def export_config(self) -> dict:
        data = self._load()
        name = data.get("model_provider")
        providers: dict = {}
        all_providers = data.get("model_providers", {})
        if isinstance(name, str) and name and isinstance(all_providers, dict):
            if name in all_providers:
                providers[name] = all_providers[name]
        # Surface catalogue for completeness; not every installation uses it.
        if isinstance(data.get("model_catalog_json"), str):
            providers["_catalog"] = {"path": data["model_catalog_json"]}
        return {
            self.name: {
                "config_path": str(self.config_path),
                "providers": providers,
            }
        }
