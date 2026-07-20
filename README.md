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

> Platform: **macOS**. The keychain integration is macOS-specific; the
> architecture is built so other platforms/tools can be added behind the same
> `Target` interface.

## Installation

```bash
git clone https://github.com/thinhngotony/byop.git
cd byop
python3 -m pip install -e ".[dev]"      # includes test/lint/type tooling
```

This installs the `byop` command. Requires Python 3.11+.

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
| `--target {zed,py}` | Configure only the named target(s); repeatable. Defaults to all detected apps. |
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
│   ├── wizard.py          # interactive prompts
│   ├── prompt.py          # rich-based prompts (stdlib fallback)
│   ├── apply.py           # legacy Zed helper (delegates to targets)
│   └── targets/           # one module per app
│       ├── base.py        # Target protocol
│       ├── zed.py         # ZedTarget
│       ├── py.py          # PyTarget (py.dev)
│       └── registry.py    # ALL_TARGETS + extension point
└── tests/                 # unit + integration (pytest)
```

## Adding a new target (e.g. Claude Code)

Implement a class with the `Target` interface
(`is_installed`, `install`, `configure`, `current_provider_names`) in
`byop/core/targets/<name>.py`, then register it in
`byop/core/targets/registry.py::ALL_TARGETS`. The CLI automatically detects it,
asks whether to configure/install it, and wires the provider through your
`configure` method. A commented `ClaudeTarget` template is already present in
the registry.

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
