# byop

[![CI](https://github.com/thinhngotony/byop/actions/workflows/ci.yml/badge.svg)](https://github.com/thinhngotony/byop/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**byop** (**B**ring **Y**our **O**wn **P**rovider) is a production-ready,
interactive CLI that wires a **custom OpenAI-compatible LLM provider** — the
endpoint is yours to supply — into your AI coding tools, starting with
[Zed](https://zed.dev) and [py.dev (Pi)](https://pi.dev), with a single
command.

## Why

Self-hosting or using a third-party OpenAI-compatible gateway (e.g. a private
`/v1` endpoint) means repeating the same fiddly setup in every tool: install the
app, find the right config file, get the provider schema right, and store the
API key somewhere safe. `byop` does all of that for you, consistently, and never
writes your secret to disk in plaintext.

## Features

- **Multi-target** — detects which AI coding tools are installed and asks which
  to configure. Missing apps can be installed for you on the spot.
- **Always up to date** — upgrades each selected app to the latest stable
  release before configuring.
- **One provider, many tools** — configure Zed and py.dev from the same input.
- **Non-destructive** — merges into each app's config, preserving your existing
  settings and comments.
- **Idempotent** — safe to re-run: merging refreshes provider settings, while the
  `agent` / `inline_assistant` / `edit_predictions` blocks are updated to the
  currently selected provider on each run (they are not appended).
- **Secure by default** — API keys live in the macOS login keychain (Zed) or are
  read from the keychain at runtime (py.dev); never plaintext in config files.
- **Scriptable** — full non-interactive flag mode for CI and dotfiles.
- **Extensible** — adding a new tool (e.g. Claude Code) is one module + one line
  in a registry.

## Supported targets

| Target | Config file | Install |
| --- | --- | --- |
| `zed` (Zed) | `~/.config/zed/settings.json` | Homebrew cask / direct download |
| `py` (py.dev / Pi) | `~/.pi/agent/models.json` | Homebrew cask |
| `omp` (oh-my-pi / Oh My Pi) | `~/.omp/agent/models.json` | `brew install can1357/tap/omp` / `curl -fsSL https://omp.sh/install | sh` |
| `claude` (Claude Code) | `~/.claude/settings.json` | `brew install --cask claude-code` / `npm i -g @anthropic-ai/claude-code` / `curl -fsSL https://claude.ai/install.sh | sh` |

> Platform: **macOS**. The keychain integration is macOS-specific; the
> architecture is built so other platforms/tools can be added behind the same
> `Target` interface.

## Installation

### One command (recommended)

```bash
curl -sfS https://byop.hyberorbit.com/install | sh
```

This installs the `byop` command (via [pipx](https://pipx.pypa.io) when
available, pinned to the latest release). Requires macOS and Python 3.11+;
Homebrew is used to install any missing prerequisites.

> Prefer to read before you run? Inspect the script first:
> `curl -sfS https://byop.hyberorbit.com/install`

### From source

```bash
git clone https://github.com/thinhngotony/byop.git
cd byop
python3 -m pip install -e ".[dev]"      # includes test/lint/type tooling
```

### With pipx (from GitHub)

```bash
pipx install "git+https://github.com/thinhngotony/byop.git"
```

## Usage

### Interactive (recommended)

```bash
byop
```

You are guided through provider details, then `byop` detects your installed
tools and asks which to configure:

```
=== byop — Custom LLM provider setup ===
› Provider name (e.g. 'MyProvider'): MyProvider
› API base URL (e.g. 'https://api.example.com/v1'): https://api.example.com/v1
› API key: ********************************
...

=== Target applications ===
  - Zed (installed)
  - py.dev (Pi) (installed)
› Configure Zed? [y/n] (y):
› Configure py.dev (Pi)? [y/n] (y):
```

### Non-interactive (scripting / CI)

```bash
byop \
  --provider "MyProvider" \
  --api-url "https://api.example.com/v1" \
  --api-key "sk-xxxx" \
  --model my-model \
  --inline-assistant --default-agent
```

| Flag | Purpose |
| --- | --- |
| `--target {zed,py,omp,claude}` | Configure only the named target(s); repeatable. Defaults to all detected apps. |
| `--config-file PATH` | Path to a JSON file with provider fields (`provider_name`, `api_url`, `api_key`, `models`). Overrides per-flag values. Useful for scripts and re-runs. |
| `--conflict {replace,skip,append,prompt}` | What to do when a provider with the same name already exists on a target. Default: prompt interactively; `replace` for zed/claude, `append` for py/omp in non-interactive mode. |
| `--settings PATH` | Override the Zed settings path (default `~/.config/zed/settings.json`). |
| `--dry-run` | Print the configuration fragments that *would* be written; change nothing. |
| `--no-keychain` | Skip the macOS keychain (falls back to an embedded key — less secure). |
| `--env-key` | Also export the key as a shell environment variable. |
| `--skip-install` | Configure settings only; do not install/upgrade any app. |

Repeat `--model` for multiple models; the **first** becomes the default for
features that take a single model.

## What it writes

For a provider `MyProvider` with model `my-model`:

**Zed** (`~/.config/zed/settings.json`):

```json
{
  "language_models": {
    "openai_compatible": {
      "MyProvider": {
        "api_url": "https://api.example.com/v1",
        "available_models": [
          { "name": "my-model", "max_tokens": 128000, "max_output_tokens": 32000 }
        ]
      }
    }
  },
  "agent": {
    "default_model":          { "provider": "MyProvider", "model": "my-model" },
    "inline_assistant_model": { "provider": "MyProvider", "model": "my-model" }
  }
}
```

**py.dev** (`~/.pi/agent/models.json`):

```json
{
  "providers": {
    "MyProvider": {
      "baseUrl": "https://api.example.com/v1",
      "api": "openai-completions",
      "apiKey": "!security find-internet-password -s https://api.example.com/v1 -a Bearer -w",
      "authHeader": true,
      "models": [
        { "id": "my-model", "name": "my-model", "contextWindow": 128000,
          "maxTokens": 32000, "input": ["text"] }
      ]
    }
  }
}
```

The py.dev `apiKey` is a `!command` that reads the secret from the macOS
keychain **at request time**, so the key is never stored in `models.json`. If no
keychain entry exists, `byop` falls back to embedding the key inline (with a
warning).

## Security

- **Zed**: the API key is written to the **macOS login keychain** keyed by the
  provider `api_url` (account `Bearer`) — the same entry Zed itself uses. It is
  never written to `settings.json` or shell history.
- **py.dev**: the key is read from that same keychain entry via a `!command`
  reference, so `models.json` contains no secret.
- The `--env-key` option appends a single `export` line to `~/.zshrc` (or
  another detected profile) and refuses to duplicate it on re-runs.
- No credentials are sent over the network by `byop` itself; it only writes
  local config files and keychain entries.

## Conflict resolution

If a provider with the same name already exists on a target, `byop` asks you
what to do:

- **replace** — overwrite the existing entry. For Zed and Claude Code this also
  switches the active default model to the new one.
- **skip** — leave the file untouched (idempotent re-run). The macOS keychain
  entry is still ensured.
- **append** — write under `<ProviderName>_2`, `<ProviderName>_3`, … so the new
  provider lives alongside the existing one. Only available for targets that
  support multiple concurrent providers (py.dev, omp).

For non-interactive / scripted runs, pass `--conflict replace|skip|append`
to skip the prompt. The default in non-interactive mode is `replace` for
Zed/Claude Code and `append` for py.dev/omp.

The wizard's first prompt also accepts a pasted JSON block. If your provider
description is already in a file, you can pipe it: `pbpaste | xargs -0 byop`
isn't right, but `byop` will detect any multi-line JSON shape and skip the
per-field prompts. See `--config-file` for the scripted equivalent.

## Behavioral notes

A few choices `byop` makes for you, so they aren't surprising:

- **Edit Predictions (`edit_predictions`)** — when enabled, `byop` writes
  `"mode": "eager"` and `"allow_data_collection": "no"`. `eager` means Zed
  *auto-accepts* completions from your provider (no manual confirm step); switch
  it to `"on"|"off"` or remove the block if you'd rather review each suggestion.
  `allow_data_collection: "no"` opts out of any edit-telemetry sharing.
- **First model is the default** — wherever a single model is required (Agent,
  Inline Assistant, commit messages, thread summaries), the **first** model you
  configure is used.
- **Re-running overwrites feature blocks** — `agent`, `inline_assistant_model`,
  and `edit_predictions` are set to the currently selected provider on every
  run. They are merged, not appended, so stale provider references are replaced.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| py.dev: "No API key found" | Ensure the keychain entry exists (`byop` writes it) or re-run `byop --target py`. |
| Zed: "provider not configured" | Restart Zed after configuration; the model must be listed under `language_models.openai_compatible`. |
| Tool not detected | Pass `--target zed`/`--target py` explicitly, or install the app and re-run. |
| Dry run shows nothing | You disabled all targets; re-run and answer the target prompts, or pass `--target`. |

## Architecture

```
byop/
├── cli.py                 # argparse entry point, interactive/non-interactive
├── core/
│   ├── config.py          # ProviderConfig model + validation + Zed fragments
│   ├── settings.py        # JSONC-aware read/merge/write for Zed
│   ├── keychain.py        # macOS keychain + env-var key storage
│   ├── zed.py             # Zed install/upgrade (brew + direct download)
│   ├── wizard.py          # interactive prompts (accepts pasted JSON)
│   ├── prompt.py          # rich-based prompts (stdlib fallback)
│   ├── conflict.py        # ConflictAction enum + resolve_conflict_action()
│   ├── paste.py           # detect/parse pasted provider JSON
│   ├── apply.py           # legacy Zed helper (delegates to targets)
│   └── targets/           # one module per app
│       ├── base.py        # Target protocol
│       ├── zed.py         # ZedTarget
│       ├── py.py          # PyTarget (py.dev)
│       ├── claude.py      # ClaudeTarget (Claude Code)
│       ├── omp.py         # OmpTarget (subclass of PyTarget)
│       └── registry.py    # ALL_TARGETS + extension point
└── tests/                 # unit + integration (pytest)
```

## Adding a new target

Implement a class with the `Target` interface
(`is_installed`, `install`, `configure`, `current_provider_names`) in
`byop/core/targets/<name>.py`, then register it in
`byop/core/targets/registry.py::ALL_TARGETS`. The CLI automatically detects it,
asks whether to configure/install it, and wires the provider through your
`configure` method.

## Roadmap

The multi-target architecture is the point: `byop` is built to wire *any* tool
that accepts an OpenAI-compatible endpoint. Today the shipped targets are:

- **Zed** (`zed`) — fully implemented.
- **py.dev / Pi** (`py`) — fully implemented.
- **Claude Code** (`claude`) — fully implemented.
- **Oh My Pi / omp** (`omp`) — fully implemented.

If you want to add another target, the registry is the only place to touch.
- **Hermes / OpenCode** and other agent CLIs that consume `models.json`-style
  provider configs.

Contributions adding a target are a single module + one registry line.

## Development

```bash
python3 -m pip install -e ".[dev]"
pytest                 # unit + integration tests
ruff check byop tests # lint
mypy byop              # type check
```

CI (`.github/workflows/ci.yml`) runs lint, type-check, and tests on macOS
across Python 3.11–3.13, then builds distribution artifacts.

## License

MIT — see [LICENSE](LICENSE).
