"""Zed target: wires a provider into Zed's settings.json + keychain."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import keychain as kc
from .. import settings as sett
from .. import zed as zedmod
from ..config import ProviderConfig

DEFAULT_SETTINGS_PATH = Path.home() / ".config" / "zed" / "settings.json"


class ZedTarget:
    name = "zed"
    display_name = "Zed"

    def __init__(self, settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.settings_path = settings_path

    # ------------------------------------------------------------------
    def is_installed(self) -> bool:
        return zedmod.is_installed()

    def install(self, log: Callable[[str], None] = print) -> None:
        zedmod.install(log=log)

    # ------------------------------------------------------------------
    def build_fragment(self, provider: ProviderConfig) -> dict:
        language_models = sett.merge(
            {}, {"openai_compatible": provider.language_models_block()}
        )
        fragment: dict = {"language_models": language_models}

        agent = provider.agent_block()
        if agent:
            fragment["agent"] = agent

        ep = provider.edit_predictions_block()
        if ep:
            fragment["edit_predictions"] = ep

        return fragment

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
            raise ValueError("Invalid provider configuration:\n  - " +
                             "\n  - ".join(errors))

        fragment = self.build_fragment(provider)

        if dry_run:
            log("[dry-run] Zed would write the following settings fragment:")
            log(sett.dumps(fragment))
            log(
                f"[dry-run] Zed would store key for server="
                f"{provider.keychain_server()}"
            )
            return

        # When the caller chose 'skip' and there's an existing provider entry
        # with the *same* api_url, treat the run as a no-op (the merge would
        # produce an identical fragment anyway). We still ensure the keychain
        # entry — that's a maintenance step, not a state change.
        #
        # Note: 'skip' is taken only when the existing entry already points at
        # the same provider name AND api_url. If the name matches but the url
        # has changed (e.g. an api endpoint migration) we fall through and
        # let the merge path update api_url in place — preserving the user
        # expectation that 'skip' means "idempotent re-run".
        if conflict_action == "skip":
            existing = sett.load_path(self.settings_path)
            existing_block = (
                existing.get("language_models", {})
                .get("openai_compatible", {})
                .get(provider.provider_name)
            )
            if isinstance(existing_block, dict) and existing_block.get(
                "api_url"
            ) == provider.normalized_api_url():
                kc.ensure_key(
                    server=provider.keychain_server(),
                    api_key=provider.api_key,
                    env_var=provider.env_var_name(),
                    log=log,
                    use_keychain=use_keychain,
                    use_env=use_env,
                )
                log(
                    f"Skip: {provider.provider_name} already configured with "
                    f"the same api_url."
                )
                return

        current = sett.load_path(self.settings_path)
        existing_url = (
            current.get("language_models", {})
            .get("openai_compatible", {})
            .get(provider.provider_name, {})
            .get("api_url")
        )
        if (
            existing_url
            and existing_url != provider.normalized_api_url()
            and not (conflict_action == "skip")
        ):
            log(
                f"Note: {provider.provider_name} api_url changed "
                f"({existing_url} -> {provider.normalized_api_url()})."
            )
        merged = sett.merge(current, fragment)
        sett.write_path(self.settings_path, merged)
        log(f"Updated Zed settings at {self.settings_path}")

        kc.ensure_key(
            server=provider.keychain_server(),
            api_key=provider.api_key,
            env_var=provider.env_var_name(),
            log=log,
            use_keychain=use_keychain,
            use_env=use_env,
        )

    def current_provider_names(self) -> list[str]:
        data = sett.load_path(self.settings_path)
        block = data.get("language_models", {}).get("openai_compatible", {})
        return list(block.keys()) if isinstance(block, dict) else []
