# Warp support v1 implementation tickets

Source: `docs/prd/warp-support-v1-prd.md` (reviewed PRD). Scope is P0 manual-paste support plus a gated P1 secure-storage automation investigation; no commits, pushes, or PRs during implementation.

- **Source-verified storage only:** Warp source confirms the logical `ApiKeys.custom_endpoints` / `CustomEndpoint` model and `AiApiKeys` secure-storage key, but automation is not supported until Dev identifies and round-trips the installed build's exact OS secure-storage service/key, encoding, and ownership behavior. This is private Rust-internal reverse engineering, not a supported Warp CLI/API. Guessed records, UUIDs, schemas, or writes that could overwrite unrelated credentials are prohibited.
- **Machine evidence (2026-08-05):** Warp `0.2026.07.29.09.05.02` is installed at `/Applications/Warp.app` (bundle `dev.warp.Warp-Stable`, executable `Contents/MacOS/stable`), with settings at `~/.warp/settings.toml`. Metadata-only login-keychain inspection found generic-password records `dev.warp.Warp-Stable` / accounts `User` and `FileBasedMcpCredentials`; secret bytes were not read. These are hypotheses, not an automation contract. `User` is a candidate user namespace; `FileBasedMcpCredentials` is presumed unrelated until proven otherwise.
- **Disposable-first E2E:** Before any write Warp MUST be quit; the raw whole `AiApiKeys` blob MUST be backed up and restoration proven. Any read-modify-write must preserve `google`, `anthropic`, `openai`, `open_router`, and every existing custom endpoint; never create a fresh replacement blob. Storage experiments must use isolated temporary `HOME`/config and a disposable secure-storage backup or mock, prove write/read/model-picker round trip, and restore it before any live operation. Live automation requires explicit user confirmation; otherwise report the exact blocker and do not claim Warp active.
- **Dry-run bugfix:** The dry-run guard must precede profile save, keychain write, env/profile persistence, settings write, secure-storage write, and every other secret-bearing side effect. Regression tests must prove isolated profile/config/keychain mocks remain unchanged.
- **Secret safety:** Tests and diagnostics never mutate live settings/keychain or expose plaintext keys; exports and dry-run output redact secrets.

## Dependency order and ownership

| Ticket | Priority | P0/P1 acceptance coverage | Depends on | Assignment |
|---|---|---|---|---|
| WARP-E2E | P0 | Temp-settings/macOS smoke: detect installed Warp, report version/path, exercise dry-run and redacted manual-paste output without live settings/keychain | None | Dev, then QA |
| WARP-1 | P0 | Discovery and registry; target protocol integration; CLI selection | None | Dev |
| WARP-2 | P0 | Safe documented/general TOML read/merge/write, unrelated-table preservation, manual-paste output and redaction, no undocumented endpoint writes | WARP-1 | Dev |
| WARP-3 | P0 | Conflict behavior and public HTTPS/private endpoint validation | WARP-1, WARP-2 | Dev |
| WARP-4 | P0 | README/security/limitations and exact verification commands | WARP-1–3 | Dev |
| WARP-5 | P0 | Deterministic tests and full verification plus temp-settings smoke; dry-run regression | WARP-1–4 | Dev, then QA |
| WARP-6 | P1 | Source-verified secure-storage contract discovery and disposable round trip; safe live E2E only after confirmation | WARP-5, installed Warp evidence | Dev, then QA |

Automation WARP-6 is a hard dependency for any claim of unattended Warp configuration; failure or unknown contract leaves the supported manual-paste branch unchanged.

## WARP-6 — Secure-storage automation investigation (P1, gated)

**Objective:** Determine whether the installed Warp build provides a supported, source-confirmed OS secure-storage route for `AiApiKeys` and `custom_endpoints`, without guessing or touching unrelated credentials.

**Acceptance criteria:**
- Record exact service, account/key, encoding, schema, UUID and ownership semantics from official/client evidence; logical source evidence and service-name discovery alone are insufficient. The observed `dev.warp.Warp-Stable/User` and `dev.warp.Warp-Stable/FileBasedMcpCredentials` records remain hypotheses until mapped without exposing secrets.
- Prove an isolated read-modify-write round trip: write one disposable endpoint, verify Warp reads it and the model picker exposes it, then restore; prove `google`, `anthropic`, `openai`, `open_router`, every existing custom endpoint, and raw blob bytes/records are preserved as required. Warp must be quit for backup/write/restore, and writes must be atomic.
- Run live only after explicit user-visible confirmation; otherwise emit the exact blocker and do not claim active automation. Unknown account, encoding, ownership, or inability to safely back up/restore is a hard stop.
- Include dry-run regression evidence showing no profile/keychain/config/secure-storage writes, plus rollback evidence after a failed verification.

**Dependencies:** WARP-5 and installed Warp evidence. **Owner:** Dev investigation; QA safety review.
**Current blocker (2026-08-05):** Dev's read-only inspection confirms `dev.warp.Warp-Stable/User` is a 4215-byte hex-encoded JSON authentication-token blob (`id_token`, `refresh_token`, `expiration_time`), while `dev.warp.Warp-Stable/FileBasedMcpCredentials` is a 3-byte record. Neither is `AiApiKeys`; no service/account/encoding contract for that blob was found. No secret bytes were interpreted beyond structural classification, and nothing was written. Because a safe backup/read-modify-write/atomic restore contract is not established, automation is **NO-SHIP** and the supported manual-paste branch remains unchanged. QA must issue a binary no-ship verdict for unattended automation; Dev may proceed only with evidence discovery, not guessed writes.
**QA verdict requirement:** report two independent results: (1) manual-paste/P0 support may pass only on its existing temporary-settings and redaction evidence; (2) unattended secure-storage automation is **Fail / No-Ship** because the only observed records are authentication-token/MCP records and no `AiApiKeys` contract exists. QA must not treat the manual fallback as evidence of active Warp configuration.
## WARP-E2E — Temp-settings smoke (P0)

**Status:** READY / no GUI blocker. This ticket verifies installed Warp discovery and the manual-paste branch using temporary settings only. It MUST NOT configure Warp through GUI, mutate live `~/.warp/settings.toml`, or access/export keychain secrets.

**Acceptance criteria:**
- Report installed Warp version and default settings path.
- Exercise dry-run and manual-paste output against a temporary settings path.
- Confirm API key is redacted and no undocumented endpoint keys are written.
- Confirm live settings and keychain remain untouched.

GUI configuration and a disposable public endpoint are optional follow-up evidence, not release gates.


## WARP-1 — Target discovery and registry (P0)

**Objective:** Add `WarpTarget` using existing `Target` protocol and repository patterns.

**Acceptance criteria:**
- `WarpTarget.name == "warp"`; display name is `Warp`.
- Default settings path is `~/.warp/settings.toml`.
- `available_targets()` includes Warp and CLI accepts `--target warp`.
- Detection succeeds independently when Warp app bundle, `warp` executable, or `~/.warp` settings directory exists.
- Existing direct-install/Homebrew guidance is reused; no installer is added.

**Dependencies:** none. **Owner:** Dev. **Review gate:** QA after all implementation tickets are ready.

## WARP-2 — Safe settings integration (P0)

**Objective:** Integrate documented/general settings safely without guessing undocumented Warp endpoint TOML keys.

**Acceptance criteria:**
- Existing TOML is parsed with stdlib `tomllib`; unrelated sections survive deterministic load/merge/write using installed `tomli-w`.
- Provider/model metadata is written only in the clearly named managed general-settings section; endpoint URL/model/API-key values are emitted as exact manual-paste instructions, with API key redacted in displayed/exported output.
- No undocumented endpoint keys are ever written; output states this limitation and the upgrade path when official/client schema becomes available.
- Dry-run performs no settings, keychain, or plaintext-secret writes.

**Dependencies:** WARP-1. **Owner:** Dev.


## WARP-3 — UX, conflicts, and endpoint security (P0)

**Objective:** Apply existing conflict and endpoint-validation conventions to Warp's manual-paste flow.

**Acceptance criteria:**
- `skip` is idempotent; `replace` updates the single managed metadata section; `append` is rejected clearly.
- Public HTTPS validation rejects known-local/private endpoints before any write; Warp local/private endpoint support remains out of scope.
- No guessed undocumented endpoint keys are written.

**Dependencies:** WARP-1 and WARP-2. **Owner:** Dev.

## WARP-4 — Documentation (P0)

**Objective:** Document supported Warp flow and limitations for users and operators.

**Acceptance criteria:**
- README supported targets and flags include Warp.
- README explains setup, public HTTPS endpoint requirement, manual-paste limitation, data-routing/security implication, no-key export behavior, and conflict semantics.
- README includes exact verification commands using temporary settings only and explicitly says live settings/keychain are untouched.

**Dependencies:** WARP-1–3. **Owner:** Dev.
## WARP-5 — Tests and verification (P0)

**Objective:** Prove the complete contract without touching live Warp settings or keychain.

**Acceptance criteria:**
- Deterministic unit tests cover path detection (bundle/executable/settings), general TOML merge and unrelated-setting preservation, dry-run, conflict behavior, registry, CLI selection, endpoint rejection, manual-paste exact values, secret redaction, and no undocumented writes.
- Targeted Warp tests, Ruff, mypy, and full pytest pass.
- macOS smoke command uses a temporary Warp settings path, confirms installed Warp bundle/version, and exercises dry-run; it does not alter live settings/keychain.
- QA returns binary Approve or Request changes with exact command evidence.

**Dependencies:** WARP-1–4. **Owner:** Dev implementation; QA validation/review.

## Execution protocol

1. Manager assigns WARP-1 through WARP-5 plus WARP-E2E as one implementation slice to Dev.
2. Dev reads this tracker and the PRD, implements product/tests/docs, skips commits/pushes/PRs and skips formatters/linters/project-wide suites during development, then reports exact verification commands and a ready-for-review handoff.
3. Manager routes only the ready handoff to QA. QA edits nothing, runs required targeted/full/temp smoke commands, reviews every P0 criterion, and returns Approve or Request changes.
4. Any requested fix returns to Dev; QA re-reviews changed scope. Manager issues ship/no-ship only after QA Approve. No ship action is authorized by this ticket.
