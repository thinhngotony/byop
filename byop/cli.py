"""byop command-line interface.

Subcommand structure (since v2.0.0):

  byop                          # status dashboard (or wizard on first run)
  byop status                   # same as bare `byop` — read-only dashboard
  byop apply [flags]            # sync active profile to selected targets
  byop profile {list,use,new,edit,delete,export}
  byop doctor                   # drift detection
  byop export-config [flags]    # dump current target settings as JSON

Backwards compatibility: the top-level flags (``--provider``, ``--api-url``,
``--model``, ``--target``, ``--config-file``, ``--export-config``, etc.) still
work — they're routed to ``apply`` / ``export-config`` automatically. So
existing scripts and CI pipelines keep running unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

from .core import default_model_capabilities, prompt, wizard
from .core.config import ModelConfig, ProviderConfig
from .core.conflict import resolve_conflict_action, supports_append
from .core.paste import parse_provider_paste


# ===========================================================================
# Argument parser
# ===========================================================================
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

    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    # ---- status (default) ------------------------------------------------
    sub.add_parser(
        "status",
        help="Show the current profile + per-target state (read-only).",
        description="Read-only dashboard. Same as running `byop` with no "
        "subcommand. Does not modify any files.",
    )

    # ---- apply -----------------------------------------------------------
    apply_p = sub.add_parser(
        "apply",
        help="Sync the active profile to one or more targets.",
        description="Apply the active profile to selected targets. The wizard "
        "is shown when no profile exists yet, or when --provider/--api-url/"
        "--api-key/--model are not provided.",
    )
    _add_apply_args(apply_p)

    # ---- profile ---------------------------------------------------------
    prof_p = sub.add_parser(
        "profile",
        help="Manage saved provider profiles.",
        description="List, switch, create, edit, delete, or export saved "
        "provider profiles.",
    )
    prof_sub = prof_p.add_subparsers(dest="profile_command", metavar="CMD")
    prof_sub.add_parser("list", help="List all saved profiles (active first).")
    prof_sub.add_parser("new", help="Create a new profile (interactive).")
    prof_sub.add_parser("edit", help="Edit the active profile (interactive).")
    prof_sub.add_parser("export", help="Print the active profile as JSON.")

    use_p = prof_sub.add_parser("use", help="Switch the active profile.")
    use_p.add_argument("name", help="Profile name to activate.")

    del_p = prof_sub.add_parser("delete", help="Delete a saved profile.")
    del_p.add_argument("name", help="Profile name to delete.")

    # ---- doctor ----------------------------------------------------------
    sub.add_parser(
        "doctor",
        help="Detect drift between the active profile and current targets.",
        description="Compares the active profile against each target's "
        "actual settings.json / models.json and reports drift. Read-only.",
    )

    # ---- export-config ---------------------------------------------------
    exp_p = sub.add_parser(
        "export-config",
        help="Print the current byop-managed configuration for each target.",
    )
    _add_apply_args(exp_p)  # shares --target / --export-provider
    exp_p.add_argument(
        "--export-provider",
        default=None,
        help="Only include this provider name across targets.",
    )

    return p


def _add_apply_args(p: argparse.ArgumentParser) -> None:
    """Args shared between ``apply`` and ``export-config``."""
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
        help="What to do when the provider name already exists on a target.",
    )
    # Non-interactive provider options (apply only)
    g = p.add_argument_group("provider (non-interactive mode)")
    g.add_argument("--provider", help="Provider name, e.g. 'MyProvider'")
    g.add_argument("--api-url", help="API base URL, e.g. https://.../v1")
    g.add_argument("--api-key", help="API key for the provider")
    g.add_argument(
        "--model", action="append", default=[],
        help="Model ID (repeatable). First becomes the default.",
    )
    g.add_argument("--model-name", help="Single model ID (legacy alias).")
    g.add_argument("--model-display", help="Display name for models.")
    g.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
    )
    g.add_argument("--max-tokens", type=int, default=128000)
    g.add_argument("--max-output-tokens", type=int, default=32000)
    g.add_argument("--images", action="store_true")
    g.add_argument("--interleaved-reasoning", action="store_true")
    g.add_argument("--max-tokens-parameter", action="store_true")
    g.add_argument("--default-agent", action="store_true")
    g.add_argument("--inline-assistant", action="store_true")
    g.add_argument("--commit-message", action="store_true")
    g.add_argument("--thread-summary", action="store_true")
    g.add_argument("--edit-predictions", action="store_true")


# ===========================================================================
# Top-level dispatch
# ===========================================================================
def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except KeyboardInterrupt:
        prompt.warn("Cancelled.")
        return 130


def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    argv = _inject_default_subcommand(argv)
    args = parser.parse_args(argv)

    # No subcommand: route based on legacy flags vs. fresh user.
    if args.command is None:
        return _route_bare(parser, args)
    return _dispatch(parser, args)


def _inject_default_subcommand(argv: list[str] | None) -> list[str]:
    """Prepend ``apply`` when no subcommand is present.

    Lets the legacy top-level-flag UX (``byop --provider P --api-url ...``)
    keep working without requiring users to type ``byop apply ...``.
    """
    if argv is None:
        argv = []
    # Help/version short-circuit: leave argv alone so the global help shows.
    if any(t in argv for t in ("-h", "--help", "--version")):
        return list(argv)
    known = {"status", "apply", "profile", "doctor", "export-config"}
    for tok in argv:
        if tok in known:
            return list(argv)
        if tok == "--":
            return list(argv)
    if not argv:
        return list(argv)
    return ["apply"] + list(argv)


def _dispatch(parser, args) -> int:
    if args.command == "status":
        return _run_status()
    if args.command == "apply":
        return _run_apply(args)
    if args.command == "profile":
        return _run_profile(args)
    if args.command == "doctor":
        return _run_doctor()
    if args.command == "export-config":
        return _run_export(args)
    parser.error(f"Unknown command: {args.command}")
    return 2  # unreachable


def _route_bare(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Decide what to do when `byop` is run with no subcommand.

    Backwards compatibility: if any of the legacy apply flags are set
    (``--provider``, ``--api-url``, ``--api-key``, ``--model``, ``--target``,
    ``--config-file``, ``--export-config``, etc.), route to ``apply``.

    Otherwise: show status dashboard if a profile exists, else launch the
    first-run wizard.
    """
    # When no subcommand was given, the apply-only attributes are missing.
    # Use getattr with defaults — true means "user passed a legacy apply flag".
    legacy_apply_args = (
        getattr(args, "provider", None)
        or getattr(args, "api_url", None)
        or getattr(args, "api_key", None)
        or getattr(args, "model", None)
        or getattr(args, "model_name", None)
        or getattr(args, "target", None)
        or getattr(args, "config_file", None) is not None
        or getattr(args, "export_config", False)
        or getattr(args, "dry_run", False)
        or getattr(args, "skip_install", False)
        or getattr(args, "env_key", False)
        or getattr(args, "no_keychain", False)
        or getattr(args, "conflict", None) is not None
    )
    if legacy_apply_args:
        # Inject 'apply' so _run_apply's parser path runs.
        return _run_apply(args)
    return _run_default_landing()


def _run_default_landing() -> int:
    """The bare ``byop`` experience: status if configured, wizard if not."""
    from .core import profiles as prof

    if prof.profile_exists(prof.get_active_profile_name()):
        return _run_status()
    prompt.header("byop — Custom LLM provider setup")
    prompt.info("No saved profile found — let's create one.")
    return _run_first_run_wizard()


def _run_first_run_wizard() -> int:
    """First-run path: wizard collects provider, saves a profile, applies it."""
    from .core import profiles as prof

    provider, prefs = wizard.run_wizard()
    profile_name = prof.DEFAULT_PROFILE_NAME
    api_key = provider.api_key
    profile = prof.profile_from_provider(provider, name=profile_name)
    # Save the secret to keychain so the profile's api_key_ref == "keychain"
    # resolves at apply time.
    if prefs["use_keychain"]:
        from .core import keychain as kc

        kc.keychain_set(provider.keychain_server(), api_key)
    prof.save_profile(profile, api_key=api_key)
    prompt.success(f"Saved profile {profile_name!r}.")

    # Continue with apply flow using the same provider.
    args = _make_args_for_apply(profile, api_key, prefs)
    return _run_apply(args)


def _make_args_for_apply(profile, api_key, prefs):
    """Build an argparse.Namespace for ``_run_apply`` from a Profile."""
    primary = profile.models[0] if profile.models else None
    args = argparse.Namespace(
        settings=Path.home() / ".config" / "zed" / "settings.json",
        dry_run=False,
        no_keychain=not prefs.get("use_keychain", True),
        env_key=prefs.get("use_env", False),
        skip_install=False,
        target=[],
        config_file=None,
        conflict=None,
        provider=profile.provider_name,
        api_url=profile.api_url,
        api_key=api_key,
        model=[m.name for m in profile.models],
        model_name=None,
        model_display=primary.display_name if primary else None,
        reasoning_effort=primary.reasoning_effort if primary else None,
        max_tokens=primary.max_tokens if primary else 128000,
        max_output_tokens=primary.max_output_tokens if primary else 32000,
        images=bool(primary and primary.capabilities.get("images")),
        interleaved_reasoning=bool(
            primary and primary.capabilities.get("interleaved_reasoning")
        ),
        max_tokens_parameter=bool(
            primary and primary.capabilities.get("max_tokens_parameter")
        ),
        default_agent=profile.set_default_agent,
        inline_assistant=profile.set_inline_assistant,
        commit_message=profile.set_commit_message,
        thread_summary=profile.set_thread_summary,
        edit_predictions=profile.use_edit_predictions,
        export_config=False,
        export_provider=None,
    )
    return args


# ===========================================================================
# status / apply / profile / doctor / export-config
# ===========================================================================
def _run_status() -> int:
    """Print a status dashboard for the active profile + each target."""
    from .core import profiles as prof
    from .core.targets import available_targets

    if not prof.profile_exists(prof.get_active_profile_name()):
        prompt.warn("No active profile. Run `byop profile new` or just `byop`.")
        return 0

    profile = prof.load_profile()
    targets = available_targets(settings_path=Path.home() / ".config" / "zed" / "settings.json")

    prompt.header("byop — Bring Your Own Provider")
    prompt.info(f"Profile: [bold]{profile.name}[/bold]  ({profile.provider_name})")
    prompt.info(f"API URL: {profile.api_url}")
    prompt.info(f"Key:     {profile.api_key_ref}{':' + profile.env_var if profile.env_var else ''}")
    model_names = [m.name for m in profile.models]
    primary = model_names[0] if model_names else "(none)"
    prompt.info(f"Models:  {len(model_names)} ({primary}{' default' if len(model_names) > 1 else ''})")

    prompt.header("Targets")
    for target in targets:
        names = target.current_provider_names()
        installed = target.is_installed()
        if not installed:
            status = "[dim](not installed)[/dim]"
        elif profile.provider_name in names:
            status = "[green]✓ configured[/green]"
        else:
            status = "[yellow]! not configured for this profile[/yellow]"
        prompt.info(f"  {target.display_name:<22} {status}")

    prompt.header("Next steps")
    prompt.info("  [bold]byop apply[/bold]               sync this profile to all targets")
    prompt.info("  [bold]byop profile list[/bold]         show saved profiles")
    prompt.info("  [bold]byop profile edit[/bold]         edit the active profile")
    prompt.info("  [bold]byop doctor[/bold]               detect drift")
    prompt.info("  [bold]byop export-config[/bold]        dump current settings as JSON")
    return 0


def _run_apply(args: argparse.Namespace) -> int:
    """Sync a provider to selected targets — the renamed default behavior."""
    # Backwards-compat: ``byop --export-config`` (no subcommand) used to be a
    # top-level flag. The apply subparser doesn't declare it; default it.
    if getattr(args, "export_config", False):
        return _run_export(args)

    # Resolve provider either from --config-file, from CLI flags, from the
    # active profile (in that order), or fall through to the wizard.
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
            )
            return 2
        non_interactive = True
        use_keychain = not args.no_keychain
        use_env = args.env_key
        api_key = provider.api_key
    else:
        non_interactive_args = any(
            [args.provider, args.api_url, args.api_key, args.model, args.model_name]
        )
        if non_interactive_args:
            if not (args.provider and args.api_url and args.api_key):
                prompt.error(
                    "Non-interactive mode requires --provider, --api-url and "
                    "--api-key."
                )
                return 2
            provider = _provider_from_args(args)
            use_keychain = not args.no_keychain
            use_env = args.env_key
            api_key = provider.api_key
            non_interactive = True
        else:
            # Interactive path. Prefer loading the active profile to pre-fill
            # so the user doesn't re-enter provider/api_url/models.
            from .core import profiles as prof

            prefill: ProviderConfig | None = None
            if prof.profile_exists(prof.get_active_profile_name()):
                saved = prof.load_profile()
                prefill = saved.to_provider_config()
                api_key = ""
                prompt.header("byop — Custom LLM provider setup")
                prompt.info(
                    f"Loaded saved profile [bold]{saved.name}[/bold] "
                    f"({saved.provider_name}). Press Enter to keep each field."
                )
            else:
                api_key = ""

            collected, prefs = wizard.run_wizard(prefill=prefill)
            provider = collected
            use_keychain = prefs["use_keychain"] and not args.no_keychain
            use_env = prefs["use_env"] or args.env_key

    if not use_keychain and not use_env:
        use_env = True

    # ---- Persist as profile (if the user provided values via flags, save
    # a profile so the next `byop apply` is a one-keystroke experience).
    from .core import profiles as prof

    profile_name = prof.get_active_profile_name()
    profile = prof.profile_from_provider(
        provider, name=profile_name,
        api_key_ref="keychain" if use_keychain else f"env:{provider.env_var_name()}",
    )
    if prof.profile_exists(profile_name):
        prof.save_profile(profile, allow_overwrite=True, api_key=api_key)
    else:
        prof.save_profile(profile, api_key=api_key)
    # Keep the secret in the keychain for `api_key_ref == "keychain"`.
    if use_keychain and api_key:
        from .core import keychain as kc
        kc.keychain_set(provider.keychain_server(), api_key)

    # ---- Select targets --------------------------------------------------
    targets = _select_targets(args, provider)
    if not targets:
        prompt.warn("No target applications selected. Nothing to do.")
        return 0

    if non_interactive and args.conflict == "prompt":
        prompt.error(
            "--conflict prompt requires an interactive TTY. "
            "Pass --conflict replace|skip|append for non-interactive runs."
        )
        return 2
    cli_flag = args.conflict if args.conflict and args.conflict != "prompt" else None

    def _pick(target) -> str:
        if cli_flag == "append" and not supports_append(target.name):
            raise _ConflictRejected(
                f"--conflict append is not supported for {target.display_name} "
                f"(only py/omp accept multi-provider entries). "
                f"Use --conflict replace or --conflict skip."
            )
        existing_names = target.current_provider_names()
        has_collision = (
            bool(existing_names) and provider.provider_name in existing_names
        )
        decided = resolve_conflict_action(
            target.name,
            has_collision=has_collision,
            interactive=not non_interactive,
            conflict_flag=cli_flag,
        )
        if decided is None:
            # Interactive + collision; prompt below.
            pass
        if decided is not None:
            return decided.value
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


def _run_profile(args: argparse.Namespace) -> int:
    """Dispatch `byop profile ...` subcommands."""
    from .core import profiles as prof

    cmd = args.profile_command
    if cmd == "list":
        names = prof.list_profiles()
        active = prof.get_active_profile_name()
        if not names:
            prompt.info("No saved profiles. Run `byop profile new`.")
            return 0
        prompt.header("Saved profiles")
        for name in names:
            marker = "*" if name == active else " "
            prompt.info(f"  {marker} {name}")
        return 0

    if cmd == "use":
        if not prof.profile_exists(args.name):
            prompt.error(f"Profile {args.name!r} does not exist.")
            return 2
        prof.set_active_profile_name(args.name)
        prompt.success(f"Active profile: {args.name}")
        return 0

    if cmd == "new":
        return _profile_new_interactive()

    if cmd == "edit":
        return _profile_edit_interactive()

    if cmd == "delete":
        try:
            prof.delete_profile(args.name)
        except prof.ProfileNotFound as exc:
            prompt.error(str(exc))
            return 2
        prompt.success(f"Deleted profile {args.name!r}.")
        return 0

    if cmd == "export":
        try:
            p = prof.load_profile()
        except prof.ProfileNotFound as exc:
            prompt.error(str(exc))
            return 2
        sys.stdout.write(json.dumps(p.to_toml(), indent=2) + "\n")
        return 0

    prompt.error(
        "`byop profile` needs a subcommand: list | new | edit | use | delete | export"
    )
    return 2


def _profile_new_interactive() -> int:
    """Walk the user through creating a new saved profile."""
    from .core import profiles as prof

    name = prompt.ask("Profile name", default=prof.DEFAULT_PROFILE_NAME)
    if prof.profile_exists(name):
        prompt.error(f"Profile {name!r} already exists. Use `byop profile edit {name}`.")
        return 2

    prefill: ProviderConfig | None = None
    if prof.profile_exists(prof.DEFAULT_PROFILE_NAME):
        saved = prof.load_profile(prof.DEFAULT_PROFILE_NAME)
        prefill = saved.to_provider_config()
    collected, prefs = wizard.run_wizard(prefill=prefill)
    profile = prof.profile_from_provider(collected, name=name)
    if prefs["use_keychain"]:
        from .core import keychain as kc
        kc.keychain_set(collected.keychain_server(), collected.api_key)
    prof.save_profile(profile, api_key=collected.api_key)
    prompt.success(f"Saved profile {name!r}.")
    return 0


def _profile_edit_interactive() -> int:
    """Re-run the wizard pre-filled with the active profile."""
    from .core import profiles as prof

    name = prof.get_active_profile_name()
    if not prof.profile_exists(name):
        prompt.error("No active profile to edit. Run `byop profile new`.")
        return 2
    saved = prof.load_profile(name)
    collected, prefs = wizard.run_wizard(prefill=saved.to_provider_config())
    profile = prof.profile_from_provider(collected, name=name)
    if prefs["use_keychain"]:
        from .core import keychain as kc
        kc.keychain_set(collected.keychain_server(), collected.api_key)
    prof.save_profile(profile, allow_overwrite=True, api_key=collected.api_key)
    prompt.success(f"Updated profile {name!r}.")
    return 0


def _run_doctor() -> int:
    """Detect drift between the active profile and each target's actual config."""
    from .core import profiles as prof
    from .core.targets import available_targets

    if not prof.profile_exists(prof.get_active_profile_name()):
        prompt.warn("No active profile to check against.")
        return 0
    saved = prof.load_profile()
    targets = available_targets(settings_path=Path.home() / ".config" / "zed" / "settings.json")

    issues = 0
    prompt.header("byop doctor")
    for target in targets:
        if not target.is_installed():
            continue
        names = target.current_provider_names()
        if saved.provider_name not in names:
            prompt.warn(
                f"{target.display_name}: provider {saved.provider_name!r} "
                f"not configured. Run `byop apply --target {target.name}`."
            )
            issues += 1
            continue
        prompt.success(
            f"{target.display_name}: provider {saved.provider_name!r} configured."
        )
    if issues == 0:
        prompt.success("No drift detected.")
        return 0
    return 1


def _run_export(args: argparse.Namespace) -> int:
    """Print the byop-managed slice of every target's settings as JSON."""
    from .core.targets import available_targets

    all_targets = available_targets(settings_path=args.settings)
    by_name = {t.name: t for t in all_targets}

    if args.target:
        chosen = [by_name[n] for n in args.target if n in by_name]
    else:
        chosen = list(all_targets)

    out: dict = {}
    for target in chosen:
        try:
            snapshot = target.export_config()
        except RuntimeError as exc:
            prompt.error(f"{target.display_name}: {exc}")
            return 1
        if args.export_provider:
            entry = snapshot.get(target.name, {})
            providers = entry.get("providers", {}) or {}
            filtered = {
                k: v for k, v in providers.items() if k == args.export_provider
            }
            if filtered:
                entry = {**entry, "providers": filtered}
                snapshot = {target.name: entry}
            else:
                continue
        out.update(snapshot)

    sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


# ===========================================================================
# Helpers (shared between subcommands)
# ===========================================================================
class _ConflictRejected(Exception):
    """Raised when a --conflict value is incompatible with a target."""


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
    if not models and args.model_name:
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


def _select_targets(args, provider: ProviderConfig | None) -> list:
    from .core.targets import available_targets, detect_installed

    all_targets = available_targets(settings_path=args.settings)
    by_name = {t.name: t for t in all_targets}

    if args.target:
        return [by_name[n] for n in args.target if n in by_name]

    installed = detect_installed(all_targets)
    installed_names = {t.name for t in installed}

    non_interactive_args = any(
        [args.provider, args.api_url, args.api_key, args.model, args.model_name]
    )
    if non_interactive_args or args.config_file is not None:
        if installed:
            return installed
        if not args.skip_install:
            return all_targets
        return []

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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
