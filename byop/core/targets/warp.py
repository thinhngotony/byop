"""Warp target: safe manual-paste guidance until its endpoint schema is documented."""
from __future__ import annotations

import ipaddress
import shutil
import socket
import tomllib
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import tomli_w

from ..config import ProviderConfig

DEFAULT_SETTINGS_PATH = Path.home() / ".warp" / "settings.toml"
WARP_APP = Path("/Applications/Warp.app")
SCHEMA_LIMITATION = (
    "Warp's custom endpoint TOML schema is undocumented and unverified. "
    "Paste the values below into Warp Settings > AI > Custom inference endpoint. "
    "byop will not guess endpoint keys or modify settings.toml."
)


def validate_warp_endpoint(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Warp endpoints must be public HTTPS URLs (https://...).")
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host.lower() in {"localhost", "localhost.localdomain"}:
            raise ValueError("Warp endpoints must be public; localhost is unsupported.") from None
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError:
            infos = []
        if infos and all(ipaddress.ip_address(item[4][0]).is_private for item in infos):
            raise ValueError("Warp endpoints must resolve to a public address; local/private hosts are unsupported.") from None
    else:
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Warp endpoints must resolve to a public address; local/private hosts are unsupported.")


class WarpTarget:
    name = "warp"
    display_name = "Warp"

    def __init__(self, settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.settings_path = Path(settings_path)

    def is_installed(self) -> bool:
        return WARP_APP.exists() or shutil.which("warp") is not None or self.settings_path.parent.exists()

    def install(self, log: Callable[[str], None] = print) -> None:
        if shutil.which("brew"):
            log("Warp is not installed. Install it with: brew install --cask warp")
        else:
            log("Install Warp from https://www.warp.dev/download, then re-run byop.")

    @staticmethod
    def _read(path: Path) -> dict:
        if not path.exists():
            return {}
        with path.open("rb") as handle:
            return tomllib.load(handle)

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(data), encoding="utf-8")

    @staticmethod
    def _manual_values(provider: ProviderConfig) -> str:
        models = ", ".join(model.name for model in provider.models)
        return (f"Provider name: {provider.provider_name}\nEndpoint URL: {provider.normalized_api_url()}\n"
                f"Models: {models}\nAPI key: [REDACTED — paste your key into Warp; byop never prints it]")

    def configure(self, provider: ProviderConfig, *, dry_run: bool = False,
                  use_keychain: bool = True, use_env: bool = False,
                  conflict_action: str | None = None,
                  log: Callable[[str], None] = print) -> None:
        errors = provider.validate()
        if errors:
            raise ValueError("\n".join(errors))
        validate_warp_endpoint(provider.api_url)
        if conflict_action == "append":
            raise ValueError("Warp supports one active custom endpoint; --conflict append is not supported. Use replace or skip.")
        # ponytail: undocumented Warp endpoint schema is the ceiling; upgrade to file writes after official schema/client verification.
        log(SCHEMA_LIMITATION)
        log(self._manual_values(provider))
        if dry_run:
            log("Dry run: no Warp settings, keychain, or secret writes performed.")
        else:
            log("Warp: manual step required — paste values above.")

    def current_provider_names(self) -> list[str]:
        return []

    def export_config(self) -> dict:
        self._read(self.settings_path)
        return {self.name: {"config_path": str(self.settings_path), "providers": {}}}

    def load_settings(self) -> dict:
        return self._read(self.settings_path)

    def write_settings(self, data: dict) -> None:
        self._write(self.settings_path, data)
