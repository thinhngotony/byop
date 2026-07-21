"""Detect and parse pasted provider JSON.

Used by the interactive wizard: when the first prompt is a multi-line blob
that looks like JSON, parse it into a :class:`ProviderConfig` instead of
asking each field one by one.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import ModelConfig, ProviderConfig

# Match the provider's JSON shape — must be multi-line AND contain a brace.
_PASTE_HINT = re.compile(r"\{[\s\S]*\}")


def looks_like_provider_paste(text: str) -> bool:
    """True if ``text`` looks like the user's provider JSON rather than a one-field answer."""
    stripped = text.strip()
    if "\n" not in stripped:
        return False
    if not _PASTE_HINT.search(stripped):
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _coerce_model(raw: dict[str, Any]) -> ModelConfig:
    """Normalize a per-model dict into a ModelConfig.

    Accepts either ``name`` or ``id`` as the model id; ``max_tokens`` or
    ``context_window``; ``max_output_tokens`` or ``max_tokens_out``.
    """
    name = raw.get("name") or raw.get("id")
    if not name:
        raise ValueError(f"model entry missing 'name' (or 'id'): {raw!r}")
    max_tokens = raw.get("max_tokens", raw.get("context_window", 128000))
    max_output_tokens = raw.get(
        "max_output_tokens", raw.get("max_tokens_out", 32000)
    )
    display = raw.get("display_name")
    reasoning = raw.get("reasoning_effort")
    caps_raw = raw.get("capabilities")
    capabilities: dict[str, Any] = (
        dict(caps_raw) if isinstance(caps_raw, dict) else {}
    )
    return ModelConfig(
        name=name,
        display_name=display,
        max_tokens=int(max_tokens),
        max_output_tokens=int(max_output_tokens),
        reasoning_effort=reasoning,
        capabilities=capabilities,
    )


# Field names the user must supply before we can actually configure anything.
REQUIRED_KEYS = ("provider_name", "api_url", "api_key", "models")


def parse_provider_paste(text: str) -> tuple[ProviderConfig, list[str]]:
    """Parse a pasted JSON provider description.

    Returns ``(ProviderConfig, missing_fields)``. The config has placeholder
    values for any missing field so callers can identify which fields to
    prompt for. ``missing_fields`` is empty when the paste was complete.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse pasted JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Pasted content must be a JSON object.")

    missing: list[str] = []
    provider_name = data.get("provider_name") or data.get("name")
    if not provider_name:
        missing.append("provider_name")

    api_url = data.get("api_url") or data.get("apiUrl")
    if not api_url:
        missing.append("api_url")

    api_key = data.get("api_key") or data.get("apiKey")
    if not api_key:
        missing.append("api_key")

    raw_models = data.get("models")
    models: list[ModelConfig]
    if not isinstance(raw_models, list) or not raw_models:
        missing.append("models")
        models = [ModelConfig(name="placeholder")]
    else:
        models = [_coerce_model(m) for m in raw_models if isinstance(m, dict)]
        if not models:
            missing.append("models")

    cfg = ProviderConfig(
        provider_name=provider_name or "PlaceholderProvider",
        api_url=api_url or "https://example.invalid/v1",
        api_key=api_key or "sk-placeholder-key",
        models=models,
    )
    return cfg, missing


__all__ = ["looks_like_provider_paste", "parse_provider_paste"]
