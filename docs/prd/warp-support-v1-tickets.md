# Warp support v1 implementation tickets

Source: `docs/prd/warp-support-v1-prd.md` (reviewed PRD). Scope is P0 only; no commits, pushes, or PRs during implementation.

## Dependency order and ownership

| Ticket | Priority | P0 acceptance coverage | Depends on | Assignment |
|---|---|---|---|---|
| WARP-E2E | P0 | Temp-settings/macOS smoke: detect installed Warp, report version/path, exercise dry-run and redacted manual-paste output without live settings/keychain | None | Dev, then QA |
| WARP-1 | P0 | Discovery and registry; target protocol integration; CLI selection | None | Dev |
| WARP-2 | P0 | Safe documented/general TOML read/merge/write, unrelated-table preservation, manual-paste output and redaction, no undocumented endpoint writes | WARP-1 | Dev |
| WARP-3 | P0 | Conflict behavior and public HTTPS/private endpoint validation | WARP-1, WARP-2 | Dev |
| WARP-4 | P0 | README/security/limitations and exact verification commands | WARP-1–3 | Dev |
| WARP-5 | P0 | Deterministic tests and full verification plus temp-settings smoke | WARP-1–4 | Dev, then QA |

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
