# zedx

**zedx** is a production-ready, interactive CLI that wires a **custom
OpenAI-compatible LLM provider** into the [Zed](https://zed.dev) editor with a
single command.

It will:

1. **Detect which AI coding tools are installed** (Zed, py.dev, and — in the
   future — Claude Code) and ask which ones you want to configure. Missing apps
   can be installed for you on the spot.
2. Always **upgrade each selected app to the latest stable version** before
   configuring (Zed via Homebrew/download, py.dev via Homebrew).
3. Prompt you (or accept flags) for your provider details: name, base URL,
   API key, and one or more models.
4. Merge the provider into each app's configuration **without clobbering your
   existing setup**:
   - **Zed** → `~/.config/zed/settings.json` (JSONC-aware; comments preserved).
   - **py.dev (Pi)** → `~/.pi/agent/models.json` (providers block merged).
5. Securely store the API key in the **macOS login keychain** for Zed and
   export it as an environment variable (e.g. `HYBERORBIT_API_KEY`) for py.dev,
   which resolves keys from the environment.
6. Optionally enable the provider for the **Agent**, **Inline Assistant**,
   **Git commit messages**, **thread summaries**, and **Edit Predictions**.

> Platform support: **macOS** (the only platform with keychain integration
> today). The architecture is built to add more targets (e.g. Claude Code) by
> implementing a single module and registering it.

### Supported targets

| Target | Config file | Install |
| --- | --- | --- |
| `zed` (Zed) | `~/.config/zed/settings.json` | Homebrew cask / direct download |
| `py` (py.dev / Pi) | `~/.pi/agent/models.json` | Homebrew cask |

---

## Installation

```bash
git clone https://github.com/example/zedx.git
cd zedx
python3 -m pip install -e ".[dev]"      # includes test/lint tooling
```

This installs the `zedx` command.

## Usage

### Interactive (recommended)

```bash
zedx
```

You'll be guided through every step. After entering provider details, zedx
detects your installed tools and asks which to configure:

```
=== zedx — Custom LLM provider setup for Zed ===
› Provider name (e.g. 'HyberOrbit'): HyberOrbit
› API base URL (e.g. 'https://api.example.com/v1'): https://api.hyberorbit.com/v1
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
zedx \
  --provider "HyberOrbit" \
  --api-url "https://api.hyberorbit.com/v1" \
  --api-key "sk-xxxx" \
  --model hy3 --model hy3-mini \
  --inline-assistant --default-agent
```

Useful flags:

| Flag | Purpose |
| --- | --- |
| `--target {zed,py}` | Configure only the named target(s); repeatable. Defaults to all detected apps. |
| `--settings PATH` | Override the Zed settings path (default `~/.config/zed/settings.json`). |
| `--dry-run` | Print the configuration fragments that *would* be written; change nothing. |
| `--no-keychain` | Skip writing the key to the macOS keychain (falls back to an env var). |
| `--env-key` | Also export the key as a shell environment variable. |
| `--skip-install` | Configure settings only; do not install/upgrade any app. |

Repeat `--model` for multiple models; the **first** becomes the default for
features that take a single model.

## What it writes

Given a provider `HyberOrbit` with model `hy3`, zedx produces:

**Zed** (`~/.config/zed/settings.json`):

```json
{
  "language_models": {
    "openai_compatible": {
      "HyberOrbit": {
        "api_url": "https://api.hyberorbit.com/v1",
        "available_models": [
          { "name": "hy3", "max_tokens": 250000, "max_output_tokens": 32000 }
        ]
      }
    }
  },
  "agent": {
    "default_model":          { "provider": "HyberOrbit", "model": "hy3" },
    "inline_assistant_model": { "provider": "HyberOrbit", "model": "hy3" }
  }
}
```

**py.dev** (`~/.pi/agent/models.json`):

```json
{
  "providers": {
    "HyberOrbit": {
      "baseUrl": "https://api.hyberorbit.com/v1",
      "api": "openai-completions",
      "apiKey": "$HYBERORBIT_API_KEY",
      "authHeader": true,
      "models": [
        { "id": "hy3", "name": "hy3", "contextWindow": 250000,
          "maxTokens": 32000, "input": ["text"] }
      ]
    }
  }
}
```

and stores the API key in the login keychain keyed by the `api_url`.

## Security

- The API key is written to the **macOS login keychain** by default — never to
  `settings.json` or shell history.
- The `--env-key` fallback writes a single `export` line to `~/.zshrc` (or
  another detected profile) and refuses to duplicate it on re-runs.
- Zed derives the key env var name from the provider name as
  `<PROVIDER_NAME_UPPER_SNAKE>_API_KEY` (e.g. `HyberOrbit` →
  `HYBERORBIT_API_KEY`).

## Development

```bash
python3 -m pip install -e ".[dev]"
pytest                 # unit + integration tests
ruff check zedx tests # lint
mypy zedx              # type check
```

CI (`.github/workflows/ci.yml`) runs lint, type-check, and tests on
macOS across Python 3.9–3.13, then builds distribution artifacts.

## Adding a new target (e.g. Claude Code)

Implement a class with the :class:`Target` interface
(`is_installed`, `install`, `configure`, `current_provider_names`) in
`zedx/core/targets/<name>.py`, then register it in
`zedx/core/targets/registry.py::ALL_TARGETS`. The interactive CLI will
automatically detect it, ask the user whether to configure/install it, and
wire the provider through your `configure` method. A commented `ClaudeTarget`
placeholder is already present in the registry as a template.

## License

MIT — see [LICENSE](LICENSE).
