"""Interactive wizard that collects provider info and builds a ProviderConfig."""

from __future__ import annotations

from . import default_model_capabilities, prompt
from .config import ModelConfig, ProviderConfig


def _ask_models(provider_display: str) -> list[ModelConfig]:
    models: list[ModelConfig] = []
    prompt.header("Models")
    prompt.info(
        "Configure one or more models. The first model becomes the default "
        "for the agent and inline assistant."
    )
    while True:
        name = prompt.ask("Model ID (sent to the API, e.g. 'hy3')")
        if not name:
            if models:
                break
            prompt.warn("At least one model is required.")
            continue

        display = prompt.ask(
            "Display name (blank to reuse model ID)", default="", allow_empty=True
        )
        max_tokens = prompt.ask_int("Context window (max_tokens)", default=128000)
        max_out = prompt.ask_int(
            "Max output tokens", default=32000
        )
        reasoning: str = prompt.ask(
            "Reasoning effort (none/minimal/low/medium/high/xhigh/max, blank=off)",
            default="",
            allow_empty=True,
        )
        reasoning_value: str | None = reasoning or None
        caps = default_model_capabilities()
        if prompt.confirm("Supports image input?", default=False):
            caps["images"] = True
        if prompt.confirm("Streams thinking in a reasoning_content field?",
                          default=False):
            caps["interleaved_reasoning"] = True
        if prompt.confirm("Expects max_tokens (not max_completion_tokens)?",
                          default=False):
            caps["max_tokens_parameter"] = True

        models.append(
            ModelConfig(
                name=name,
                display_name=display or None,
                max_tokens=max_tokens,
                max_output_tokens=max_out,
                reasoning_effort=reasoning_value,
                capabilities=caps,
            )
        )
        if not prompt.confirm("Add another model?", default=False):
            break
    return models


def run_wizard() -> tuple[ProviderConfig, dict]:
    """Drive the interactive prompts.

    Returns the configured :class:`ProviderConfig` and a dict with the
    chosen key-storage preferences (``use_keychain`` / ``use_env``).
    """

    prompt.header("byop — Custom LLM provider setup for Zed")
    prompt.info(
        "This wizard installs/upgrades Zed and wires a custom "
        "OpenAI-compatible provider into it."
    )

    provider_name = prompt.ask("Provider name (e.g. 'HyberOrbit')")
    api_url = prompt.ask(
        "API base URL (e.g. 'https://api.example.com/v1')"
    )
    api_key = prompt.ask_secret("API key")

    models = _ask_models(provider_name)

    prompt.header("Feature wiring")
    prompt.info(
        "Zed can use this provider for different AI features. The first "
        "model is used where a single model is required."
    )
    set_default = prompt.confirm(
        "Set as the default Agent model?", default=True
    )
    set_inline = prompt.confirm(
        "Set as the Inline Assistant model?", default=True
    )
    set_commit = prompt.confirm(
        "Use for Git commit messages?", default=False
    )
    set_summary = prompt.confirm(
        "Use for thread summaries?", default=False
    )
    use_edit = prompt.confirm(
        "Enable Edit Predictions (autocomplete) with this provider?",
        default=False,
    )

    prompt.header("API key storage")
    use_keychain = prompt.confirm(
        "Store key in macOS login keychain? (recommended)", default=True
    )
    use_env = prompt.confirm(
        "Also export key as an environment variable in your shell profile?",
        default=not use_keychain,
    )

    provider = ProviderConfig(
        provider_name=provider_name,
        api_url=api_url,
        api_key=api_key,
        models=models,
        set_default_agent=set_default,
        set_inline_assistant=set_inline,
        set_commit_message=set_commit,
        set_thread_summary=set_summary,
        use_edit_predictions=use_edit,
    )
    return provider, {"use_keychain": use_keychain, "use_env": use_env}
