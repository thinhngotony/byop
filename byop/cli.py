#!/usr/bin/env python3
"""byop command-line interface.

Two modes:

* Interactive (default, no args): a guided wizard that collects the provider
  details, installs/upgrades Zed, and configures everything.
* Non-interactive (flags): supply provider details via options for scripting
  and CI. Multiple ``--model`` entries are supported.

Examples
--------
    byop                                   # interactive wizard
    byop --provider MyProvider \
         --api-url https://api.example.com/v1 \
         --api-key sk-xxx \
         --model hy3 --model hy3-mini \
         --inline-assistant --default-agent
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

from .core import default_model_capabilities, prompt, wizard
from .core.config import ModelConfig, ProviderConfig
from .core.conflict import resolve_conflict_action, supports_append
from .core.paste import parse_provider_paste


def _build_model(name: str, display: str | None, reasoning: str | None,
                 max_tokens: int, max_out: int, images: bool,
                 interleaved: bool, max_param: bool) -> ModelConfig:
    caps = default_model_capabilities()
    caps["images"] = images
    caps["interleaved_reasoning"] = interleaved
    caps["max_tokens_parameter"] = max_param
    return ModelConfig(
        name=name,
        display_name=display,
        max_tokens=max_tokens,
        max_output_tokens=max_out,
        reasoning_effort=reasoning,
        capabilities=caps,
    )


def _provider_from_args(args: argparse.Namespace) -> ProviderConfig:
    models: list[ModelConfig] = []
    for m in args.model:
        models.append(_build_model(
            name=m,
            display=args.model_display,
            reasoning=args.reasoning_effort,
            max_tokens=args.max_tokens,
            max_out=args.max_output_tokens,
            images=args.images,
            interleaved=args.interleaved_reasoning,
            max_param=args.max_tokens_parameter,
        ))
    if not models:
        # Fall back to a single model from --model-name if provided.
        if args.model_name:
            models.append(_build_model(
                name=args.model_name,
                display=args.model_display,
                reasoning=args.reasoning_effort,
                max_tokens=args.max_tokens,
                max_out=args.max_output_tokens,
                images=args.images,
                interleaved=args.interleaved_reasoning,
                max_param=args.max_tokens_parameter,
            ))
    if not models:
        raise SystemExit(
            "No model specified. Use --model NAME (repeatable) or --model-name."
        )
    return ProviderConfig(
        provider_name=args.provider,
        api_url=args.api_url,
        api_key=args.api_key,
        models=models,
        set_default_agent=args.default_agent,
        set_inline_assistant=args.inline_assistant,
        set_commit_message=args.commit_message,
        set_thread_summary=args.thread_summary,
        use_edit_predictions=args.edit_predictions,
    )


class _ConflictRejected(Exception):
    """Raised when a --conflict value is incompatible with a target.

    Always maps to CLI exit code 2 (user error). Caught by main() and turned
    into a printed error and an early abort before the rest of the targets
    run with stale state.
    """


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="byop",
        description="Interactively set up a custom LLM provider for Zed, "
        "py.dev, and other AI coding tools.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_pkg_version('byop')}",
    )
    p.add_argument(
        "--settings",
        type=Path,
        default=Path.home() / ".config" / "zed" / "settings.json",
        help="Path to Zed settings.json (default: ~/.config/zed/settings.json)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying anything.",
    )
    p.add_argument(
        "--no-keychain",
        action="store_true",
        help="Do not write the API key to the macOS keychain.",
    )
    p.add_argument(
        "--env-key",
        action="store_true",
        help="Also export the API key as a shell environment variable.",
    )
    p.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not install/upgrade any app (configure settings only).",
    )
    p.add_argument(
        "--target",
        action="append",
        default=[],
        choices=["zed", "py", "omp", "claude", "opencode"],
        help="Restrict to specific target(s): zed, py, omp, claude, opencode "
        "(repeatable). Defaults to all detected/installed apps.",
    )
    p.add_argument(
        "--config-file",
        type=Path,
        help="Path to a JSON file with provider fields (provider_name, "
        "api_url, api_key, models). Overrides --provider/--api-url/...",
    )
    p.add_argument(
        "--conflict",
        choices=["replace", "skip", "append", "prompt"],
        default=None,
        help="What to do when the provider name already exists on a target. "
        "Default: prompt interactively; replace for zed/claude, append for "
        "py/omp in non-interactive mode.",
    )

    # Non-interactive provider options.
    g = p.add_argument_group("provider (non-interactive mode)")
    g.add_argument("--provider", help="Provider name, e.g. 'MyProvider'")
    g.add_argument("--api-url", help="API base URL, e.g. https://.../v1")
    g.add_argument("--api-key", help="API key for the provider")
    g.add_argument(
        "--model",
        action="append",
        default=[],
        help="Model ID (repeatable). First becomes the default.",
    )
    g.add_argument("--model-name", help="Single model ID (legacy alias).")
    g.add_argument("--model-display", help="Display name for models.")
    g.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        help="Default reasoning effort for models.",
    )
    g.add_argument("--max-tokens", type=int, default=128000)
    g.add_argument("--max-output-tokens", type=int, default=32000)
    g.add_argument("--images", action="store_true", help="Model supports images.")
    g.add_argument(
        "--interleaved-reasoning",
        action="store_true",
        help="Model streams thinking in reasoning_content.",
    )
    g.add_argument(
        "--max-tokens-parameter",
        action="store_true",
        help="Endpoint expects max_tokens (not max_completion_tokens).",
    )
    g.add_argument("--default-agent", action="store_true",
                   help="Set as default Agent model.")
    g.add_argument("--inline-assistant", action="store_true",
                   help="Set as Inline Assistant model.")
    g.add_argument("--commit-message", action="store_true",
                   help="Use for Git commit messages.")
    g.add_argument("--thread-summary", action="store_true",
                   help="Use for thread summaries.")
    g.add_argument("--edit-predictions", action="store_true",
                   help="Enable Edit Predictions with this provider.")

    return p


def _select_targets(args, provider: ProviderConfig | None) -> list:
    """Resolve which targets to configure based on detection + user choice.

    ``provider`` is only needed for the interactive wizard path so we can show
    already-configured providers; it may be ``None`` in non-interactive mode.
    """
    from .core.targets import available_targets, detect_installed

    all_targets = available_targets(settings_path=args.settings)
    by_name = {t.name: t for t in all_targets}

    # Explicit --target restriction.
    if args.target:
        chosen = [by_name[n] for n in args.target if n in by_name]
        return chosen

    installed = detect_installed(all_targets)
    installed_names = {t.name for t in installed}
    missing = [t for t in all_targets if t.name not in installed_names]

    if not installed and not missing:
        return []

    # Non-interactive (flags or --config-file): configure all detected/installed apps.
    non_interactive_args = any(
        [args.provider, args.api_url, args.api_key, args.model, args.model_name]
    )
    if non_interactive_args or args.config_file is not None:
        if installed:
            return installed
        # Nothing installed but non-interactive: configure the missing ones too
        # only if the user explicitly wants install (not skip-install).
        if not args.skip_install:
            return all_targets
        return []

    # Interactive: ask the user.
    prompt.header("Target applications")
    prompt.info(
        "byop can configure the following AI coding tools with this provider."
    )
    selected: list = []
    for target in all_targets:
        is_inst = target.name in installed_names
        label = f"{target.display_name} (installed)" if is_inst \
            else f"{target.display_name} (not installed)"
        prompt.info(f"  - {label}")
        if is_inst:
            if prompt.confirm(f"Configure {target.display_name}?", default=True):
                selected.append(target)
        else:
            if prompt.confirm(
                f"Install and configure {target.display_name}?", default=False
            ):
                selected.append(target)
    return selected


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except KeyboardInterrupt:
        prompt.warn("Cancelled.")
        return 130


def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ---- Resolve provider -----------------------------------------------
    non_interactive = False
    provider: ProviderConfig | None = None

    if args.config_file is not None:
        try:
            raw = args.config_file.read_text(encoding="utf-8")
        except OSError as exc:
            prompt.error(f"Could not read --config-file: {exc}")
            return 2
        try:
            provider, missing = parse_provider_paste(raw)
        except ValueError as exc:
            prompt.error(str(exc))
            return 2
        if missing:
            prompt.error(
                "--config-file is missing required fields: "
                + ", ".join(missing)
                + ". Provide them via --provider/--api-url/--api-key/--model "
                + "flags, or re-run byop without --config-file to fill them "
                + "in interactively."
            )
            return 2
        non_interactive = True
        use_keychain = not args.no_keychain
        use_env = args.env_key
    else:
        non_interactive = any(
            [args.provider, args.api_url, args.api_key, args.model, args.model_name]
        )
        if non_interactive:
            if not (args.provider and args.api_url and args.api_key):
                prompt.error(
                    "Non-interactive mode requires --provider, --api-url and "
                    "--api-key."
                )
                return 2
            provider = _provider_from_args(args)
            use_keychain = not args.no_keychain
            use_env = args.env_key
        else:
            provider, prefs = wizard.run_wizard()
            use_keychain = prefs["use_keychain"] and not args.no_keychain
            use_env = prefs["use_env"] or args.env_key

    # At least one storage method must be active. Zed reads either the
    # keychain or the ``<PROVIDER>_API_KEY`` env var, and py.dev requires the
    # env var. Prefer the env var as the fallback so non-interactive/CI runs
    # don't trigger a keychain prompt.
    if not use_keychain and not use_env:
        use_env = True

    targets = _select_targets(args, provider if not non_interactive else None)
    if not targets:
        prompt.warn("No target applications selected. Nothing to do.")
        return 0

    # ---- Per-target conflict resolution ----------------------------------
    # CLI override for the conflict action: replace/skip/append/prompt.
    # 'prompt' is meaningful only when stdin is a TTY; otherwise it would
    # silently downgrade to the target's default. Catch that here so the
    # user gets an actionable error rather than a surprise auto-replace.
    if non_interactive and args.conflict == "prompt":
        prompt.error(
            "--conflict prompt requires an interactive TTY. "
            "Pass --conflict replace|skip|append for non-interactive runs."
        )
        return 2
    cli_flag = args.conflict if args.conflict and args.conflict != "prompt" else None

    def _pick(target) -> str:
        """Resolve the conflict action for one target, prompting if needed."""
        # Only py/omp support multiple concurrent providers; refuse --conflict
        # append against single-provider targets (zed/claude) so the user
        # gets a clear error instead of a silent overwrite.
        if cli_flag == "append" and not supports_append(target.name):
            raise _ConflictRejected(
                f"--conflict append is not supported for {target.display_name} "
                f"(only py/omp accept multi-provider entries). "
                f"Use --conflict replace or --conflict skip."
            )
        existing_names = target.current_provider_names()
        has_collision = bool(existing_names) and provider.provider_name in existing_names
        decided = resolve_conflict_action(
            target.name,
            has_collision=has_collision,
            interactive=not non_interactive,
            conflict_flag=cli_flag,
        )
        if decided is not None:
            return decided.value
        # Interactive + collision + no CLI override: ask the user.
        options = ["replace", "skip"]
        if supports_append(target.name):
            options.append("append")
        return prompt.choose_action(target.display_name, options, default="replace")

    success = True
    for target in targets:
        try:
            conflict_action = _pick(target)

            if not args.skip_install:
                target.install(log=prompt.info)
            target.configure(
                provider,
                dry_run=args.dry_run,
                use_keychain=use_keychain,
                use_env=use_env,
                conflict_action=conflict_action,
                log=prompt.info,
            )
        except ValueError as exc:
            prompt.error(f"{target.display_name}: {exc}")
            success = False
        except RuntimeError as exc:
            prompt.error(f"{target.display_name}: {exc}")
            success = False
        except _ConflictRejected as exc:
            prompt.error(str(exc))
            return 2

    if args.dry_run:
        prompt.success("Dry run complete. No changes were made.")
        return 0 if success else 1

    if success:
        prompt.success("Configuration complete!")
        prompt.info(
            "Restart the configured applications (or reload their settings) "
            "for changes to take effect."
        )
        if use_env:
            prompt.warn(
                "An environment variable was added to your shell profile; open "
                "a new terminal or 'source' it before launching the apps."
            )
    return 0 if success else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
