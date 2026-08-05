# Warp support v1 PRD

## Problem

`byop` configures custom OpenAI-compatible providers for several coding tools but not Warp. Warp supports custom inference endpoints through its local settings and secure credential storage. Users need one repeatable `byop` flow to prepare Warp with the same provider and model data.

## Evidence and constraints

- Warp's official custom inference documentation requires a public HTTPS OpenAI-compatible endpoint, but the endpoint-key schema used by the installed client is not a stable documented TOML surface.
- Warp's official settings documentation identifies `~/.warp/settings.toml` as the editable settings file.
- The installed machine has Warp `0.2026.07.29.09.05.02` at `/Applications/Warp.app`; current user settings are at `~/.warp/settings.toml`.
- **Schema ceiling:** v1 MUST NOT guess or write undocumented custom-endpoint keys. The endpoint URL, model, and API key are emitted as exact manual-paste values (with the API key redacted in displayed/exported output); users paste them into Warp's documented UI. The target may safely read/write only documented/general TOML settings needed for its managed metadata and must preserve unrelated tables.
- Tests and smoke verification MUST use a temporary settings path and MUST NOT mutate the user's live Warp settings or macOS keychain. No GUI experiment or disposable endpoint is a release blocker.

## Secure-storage automation objective (P1 dependency)

Warp source evidence identifies the intended credential model as `ApiKeys { custom_endpoints: Vec<CustomEndpoint> }` stored under the secure-storage key `AiApiKeys`. Each `CustomEndpoint` contains `name`, `url`, `api_key`, `models` (including `name`, `alias`, and UUID `config_key`), and a schema enum of `openai_chat_completions`, `openai_responses`, or `anthropic_messages`. Warp's model picker consumes these entries. This source shape is evidence of the logical model, not by itself a supported machine-write contract.

**Machine evidence and blocker (2026-08-05):** installed Warp is `/Applications/Warp.app`, bundle id `dev.warp.Warp-Stable`, version `0.2026.07.29.09.05.02`, executable `Contents/MacOS/stable`, and settings file `~/.warp/settings.toml` (owner `tony:staff`, mode `0644`). Metadata-only login-keychain inspection found generic-password records with service `dev.warp.Warp-Stable`: `User` is a 4215-byte hex-encoded JSON authentication-token blob (`id_token`, `refresh_token`, `expiration_time`), and `FileBasedMcpCredentials` is a 3-byte record. Neither is `AiApiKeys`; no service/account/encoding contract for `AiApiKeys` was found. Secret bytes were not exposed and no records were written. The installed app's `settings_schema.json` does not establish the private secure-blob contract.

Automation is **NO-SHIP**. It MUST remain unsupported unless a documented or empirically round-tripped OS secure-storage contract identifies the exact `AiApiKeys` account, encoding, ownership, and atomic backup/read-modify-write/restore behavior. The current records MUST NOT be repurposed. This is private Warp Rust-internal/secure-storage reverse engineering, not a supported Warp CLI/API. The manual-paste branch remains the supported behavior.

Before any future write, Warp MUST be quit; the raw whole `AiApiKeys` blob MUST be backed up and restoration proven. Any read-modify-write MUST preserve `google`, `anthropic`, `openai`, `open_router`, and every other existing custom endpoint; a fresh replacement blob is prohibited. If mapping cannot be established without extracting a secret, the result is a blocker and no automation claim may ship.

The candidate service/account observations are hypotheses only and must not be written.

## Dry-run and safety gates

The known CLI bug where profile and keychain persistence occurs before the dry-run guard is a release blocker. The guard MUST run before profile saves, keychain writes, environment/profile persistence, settings writes, or any other secret-bearing side effect. Regression tests MUST assert that dry-run leaves isolated profile/config/keychain mocks untouched.

All tests and automation experiments MUST use an isolated temporary `HOME`, config directory, and keychain mock/backup. Live settings, secure storage, and unrelated Warp credentials MUST remain untouched unless the user receives an explicit confirmation prompt after the disposable round trip and chooses to proceed. No plaintext secret may appear in dry-run, exported, or diagnostic output.

## Success metrics

1. `byop --target warp --dry-run` safely reports the intended Warp operation without writing a secret or corrupting settings.
2. Warp is detected when the app, `warp` executable, or `~/.warp` settings directory exists.
3. The target is registered, selectable, exported, documented, and covered by deterministic tests.
4. On this Mac, the verification command demonstrates the installed Warp version, settings path, and whether the installed client exposes a machine-writable endpoint schema. Unsupported/unknown schema is reported explicitly, not silently misconfigured.

## Scope

### P0 — approved manual-paste branch

 - Add a `WarpTarget` implementing the existing `Target` protocol.
 - Discover `~/.warp/settings.toml`, safely read/write only documented/general TOML settings, preserve unrelated tables, and use `tomli-w` plus stdlib `tomllib` for deterministic load/merge/write.
 - Detect Warp via app bundle, executable, or settings directory; provide existing Homebrew/direct-install guidance without an installer.
 - Add `warp` to CLI target choices and existing conflict handling. Use replace/skip and reject append for the single managed metadata section.
 - Emit exact manual-paste endpoint URL/model/API-key values, with API key redacted in output/export; never write undocumented endpoint keys.
 - Add deterministic tests for detection, TOML preservation, dry-run, conflicts, endpoint validation, manual-paste output, and no undocumented writes.
 - Update README with setup, manual-paste limitation, security, and verification commands.
 - Run repository verification and macOS smoke against temporary settings only; never alter live settings or keychain.

### Deferred/P1
 - Automatic GUI interaction with Warp Settings.
 - Writing custom endpoint keys until the installed client or official schema documents them; this is the explicit upgrade path beyond manual paste.
 - Any unattended configuration claim without the model-picker and prompt evidence above.
## Verification procedure

1. Record Warp version: `defaults read /Applications/Warp.app/Contents/Info CFBundleShortVersionString`.
2. Create a temporary Warp settings file/path and exercise detection, dry-run, TOML preservation, and manual-paste output against it.
3. Confirm output contains exact URL/model instructions but redacts the API key, and confirm no undocumented endpoint keys are written.
4. Confirm live `~/.warp/settings.toml` and macOS keychain are untouched. GUI configuration and a disposable public endpoint are optional manual follow-up, not release gates.

## Current branch decision

On 2026-08-05, the empirical endpoint-schema experiment was not available and no live settings or keychain state was changed. The approved v1 branch is therefore manual paste: Warp support may ship for detection, safe general TOML handling, and exact redacted paste instructions, while undocumented endpoint-key writes remain explicitly unsupported.

## User stories and acceptance criteria

### WARP-1: Target discovery and registry

- [ ] `WarpTarget.name == "warp"` and display name is `Warp`.
- [ ] Default path is `~/.warp/settings.toml`.
- [ ] `available_targets()` includes Warp and CLI accepts `--target warp`.
- [ ] Detection works for app bundle, executable, and settings directory.

### WARP-2: Safe settings integration

- [ ] Existing TOML parses and unrelated sections survive a write.
- [ ] Documented/general settings are represented in one clearly named managed section; endpoint URL/model/API-key values are manual-paste output, and no undocumented endpoint keys are written.

### WARP-3: UX and security

- [ ] Conflict `skip` is idempotent; `replace` updates the managed endpoint; `append` is rejected with a clear message.
- [ ] Public HTTPS endpoint validation prevents known-local/private URLs before any write.
- [ ] README documents Warp setup, limitations, and exact verification commands.

### WARP-4: Verification

- [ ] Machine smoke command confirms Warp bundle/version and exercises dry-run against a temporary config without touching live settings/keychain.

## Risks

- Warp may change its settings schema without compatibility guarantees.
- Warp custom endpoint requests transit Warp's backend; users must understand the data-routing implication.
- Writing a guessed key into settings could be ignored or damage user configuration, so unknown schema is a hard stop.
