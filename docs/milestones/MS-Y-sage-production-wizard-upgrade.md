# Milestone MS-Y — SageMath Production Engine + Wizard Production-Grade

Date: 2026-02-24
Status: Draft
Depends on: MS-X (complete)

## Context

MS-X delivered 5 engines (SymPy, Maxima, MATLAB, GAP, WolframAlpha), all now active.
The runtime executor is built but unused. The wizard installs/detects engines but
does not handle interactive configuration (custom paths, API keys).

This milestone adds SageMath as the 6th engine (the most capable single CAS), upgrades
the wizard to production quality, and ensures the service is reliable enough for
paid use.

## Current State (Verified 2026-02-24)

| Engine | Available | Version | Capabilities | Config |
|--------|:---------:|---------|:------------:|--------|
| SymPy | Yes | 1.14.0 | validate | Auto (pip) |
| Maxima | Yes | 5.45.1 | validate | `/usr/bin/maxima` |
| MATLAB | Yes | R2025b | validate | `/media/sam/3TB-WDC/matlab2025/bin/matlab` |
| GAP | Yes | 4.11.1 | compute | `/usr/bin/gap` |
| WolframAlpha | Yes | v2-api | compute, remote | `CAS_WOLFRAMALPHA_APPID` (SSOT .env) |
| **SageMath** | **No** | - | - | Not installed |

SageMath 9.5 available via `apt install sagemath` (~2GB installed).
Disk space: 505GB free on /media/sam/1TB.

## Goal

1. Add SageMath as a full-capability engine (validate + compute) using the runtime executor
2. Upgrade the setup wizard to production quality: interactive config for all engines
3. Ensure service reliability for paid deployment

## Scope (In)

### S1. SageEngine (validate + compute)
- New `cas_service/engines/sage_engine.py`
- Uses `SubprocessExecutor` from `cas_service/runtime/executor.py`
- Validate: parse LaTeX → Sage symbolic expression → validate
- Compute: template-based (like GAP) + freeform expression evaluation
- Capabilities: `[validate, compute]`
- Subprocess via `sage -c "code"` with timeout and output caps
- Templates:
  - `evaluate` — evaluate expression
  - `simplify` — simplify expression
  - `solve` — solve equation
  - `factor` — factor polynomial
  - `integrate` — symbolic integration
  - `differentiate` — symbolic differentiation
  - `matrix_rank` — compute matrix rank
  - `latex_to_sage` — parse LaTeX, return Sage representation

### S2. Wizard Production Upgrade
- **Every engine** must support interactive configuration via wizard:
  - Path prompt (MATLAB, GAP, Sage, Maxima)
  - API key prompt (WolframAlpha) — secure input, no echo
  - Auto-detection of common install locations
  - Verify step for each engine individually
- Wizard stores config to a local `.env` file (project-level, not SSOT)
- Wizard generates/updates `cas-service.service` with detected paths
- `cas-setup engines` shows full status table with paths and versions
- `cas-setup verify` runs smoke tests for ALL engine types (validate + compute)
- `cas-setup configure` — new subcommand to re-configure engine paths/keys

### S3. Service Hardening
- Graceful handling of engine startup failures (service starts even if some engines unavailable)
- `/engines` response includes `version` field for each engine
- `/health` includes engine count and availability summary
- Request logging with engine selection, duration, success/fail
- Rate limiting consideration (document, not necessarily implement in MVP)

## Scope (Out)

- Async `/jobs` endpoints (executor supports it, but not exposed via HTTP yet)
- SageMath Docker isolation (future — subprocess is sufficient for now)
- Custom user-defined templates (admin-only feature, not this milestone)
- Billing/metering infrastructure
- PePeRS integration (separate milestone)

## Done Criteria

- [ ] SageMath engine registered, available, and functional via `/compute` and `/validate`
- [ ] At least 5 Sage templates work end-to-end with real Sage subprocess
- [ ] Sage uses `SubprocessExecutor` (not raw subprocess)
- [ ] Wizard interactively configures ALL engine paths and API keys
- [ ] Wizard writes config to `.env` or systemd env file
- [ ] `cas-setup verify` smoke-tests all available engines (validate AND compute)
- [ ] `cas-setup configure` subcommand exists
- [ ] All 6 engines shown in `/engines` with versions
- [ ] Service starts cleanly even if some engines are unavailable
- [ ] Tests pass (existing + new SageEngine tests + wizard config tests)
- [ ] README updated

## Implementation Plan (Slices)

### Slice 1 — SageEngine Core

**Goal:** SageMath validate + compute via subprocess.

**Files:**
- `cas_service/engines/sage_engine.py` (new)
- `cas_service/main.py` (register engine)
- `tests/test_sage_engine.py` (new)

**Tasks:**
- Implement `SageEngine(BaseEngine)` with `sage -c` subprocess
- Wire to `SubprocessExecutor` for isolation/timeout
- Implement `validate()`: LaTeX → Sage expression → valid/invalid
- Implement `compute()` with template allowlist
- Capabilities: `[validate, compute]`
- Detect Sage availability and version
- Register in `_init_engines()`
- Add env vars: `CAS_SAGE_PATH`, `CAS_SAGE_TIMEOUT`
- Tests: unit (mocked subprocess) + integration (real Sage if available)

**Done:** Sage appears in `/engines`, `/validate` and `/compute` work.

### Slice 2 — Wizard Interactive Configuration

**Goal:** Every engine configurable interactively.

**Files:**
- `cas_service/setup/_matlab.py` (add path prompt)
- `cas_service/setup/_gap.py` (add path prompt)
- `cas_service/setup/_sage.py` (upgrade from detection to full setup)
- `cas_service/setup/_wolframalpha.py` (add API key prompt)
- `cas_service/setup/_maxima.py` (add path prompt if non-standard)
- `cas_service/setup/_config.py` (new — config file read/write)
- `cas_service/setup/main.py` (add `configure` subcommand)
- `tests/test_setup_wizard.py` (update)

**Tasks:**
- Add `_config.py` module: read/write `.env` in project root
- Each engine step: add interactive path/key prompt in `install()`
- MATLAB step: search common paths + prompt for custom
- GAP step: auto-install + prompt for custom path
- Sage step: auto-install + prompt + version check
- WolframAlpha step: secure API key input (questionary password prompt)
- Maxima step: verify default, prompt if not found
- `configure` subcommand: re-runs config prompts for selected engines
- Wizard writes to `.env` file (dotenvx format)
- `verify` step upgraded to test validate AND compute per engine
- Update `cas-setup engines` output to show path/config source

**Done:** `cas-setup` fully configures all 6 engines interactively.

### Slice 3 — Service Hardening + /engines Upgrade

**Goal:** Production reliability.

**Files:**
- `cas_service/main.py`
- `cas_service/engines/base.py` (optional: add `availability_reason` to base)
- `tests/test_compute_api.py` (update)

**Tasks:**
- `_init_engines()`: catch exceptions per engine, log warning, continue
- `/engines` response: add `version` field
- `/health` response: add `engines_available` count
- Add `availability_reason` property to `BaseEngine` (default None)
- All engines: implement `availability_reason` if missing
- Request logging: engine name, duration, success, error code
- Tests for partial engine failure (service starts if 1 engine crashes)

**Done:** Service is resilient, `/engines` is fully informative.

### Slice 4 — Documentation + Final Verification

**Goal:** README, API docs, deploy guide.

**Files:**
- `README.md`
- `docs/MS-Y-VERIFICATION-SSOT.md` (new)

**Tasks:**
- Update README with all 6 engines, full env var table, wizard guide
- Add deploy guide section (systemd + env config)
- Write verification SSOT doc
- Run full test suite
- Smoke test all 6 engines (real data)

**Done:** Docs complete, all tests pass, all engines verified.

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| SageMath startup slow (~2-5s cold) | High latency on first request | Pre-warm on startup, document cold-start |
| SageMath apt package old (9.5 vs latest 10.x) | Missing features | Use conservative API, document version |
| SageMath install large (~2GB) | Disk/bandwidth | Document size, make optional |
| LaTeX → Sage parsing fragile | Validation errors | Robust error handling, fallback to SymPy |
| Wizard config overwrites user .env | Data loss | Backup before write, dotenvx encryption |

## Environment Variables (Complete)

| Variable | Default | Engine | Description |
|----------|---------|--------|-------------|
| `CAS_PORT` | `8769` | - | HTTP listen port |
| `CAS_SYMPY_TIMEOUT` | `5` | SymPy | Parse/simplify timeout (s) |
| `CAS_MAXIMA_PATH` | `/usr/bin/maxima` | Maxima | Binary path |
| `CAS_MAXIMA_TIMEOUT` | `10` | Maxima | Subprocess timeout (s) |
| `CAS_MATLAB_PATH` | `matlab` | MATLAB | Binary path |
| `CAS_MATLAB_TIMEOUT` | `30` | MATLAB | Subprocess timeout (s) |
| `CAS_GAP_PATH` | `gap` | GAP | Binary path |
| `CAS_GAP_TIMEOUT` | `10` | GAP | Subprocess timeout (s) |
| `CAS_SAGE_PATH` | `sage` | SageMath | Binary path |
| `CAS_SAGE_TIMEOUT` | `30` | SageMath | Subprocess timeout (s) |
| `CAS_WOLFRAMALPHA_APPID` | - | WolframAlpha | API key (secret) |
| `CAS_WOLFRAMALPHA_TIMEOUT` | `10` | WolframAlpha | Request timeout (s) |
| `CAS_LOG_LEVEL` | `INFO` | - | Logging level |

## Execution Order

1. **Slice 1** — SageEngine (biggest new code)
2. **Slice 2** — Wizard upgrade (touches many files)
3. **Slice 3** — Service hardening (smaller, focused)
4. **Slice 4** — Documentation

## Suggested First Step

Install SageMath: `sudo apt install sagemath`
Then implement Slice 1 (SageEngine core).
