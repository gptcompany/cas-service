# Final Repo Handoff (2026-02-24)

## Scope

This handoff documents the final stabilized state of `cas-service` after:

- WolframAlpha AppID override bug fix
- MATLAB compute hardening (no `eval` in `evaluate`)
- setup wizard port/URL centralization
- coverage expansion (API / preprocessing / MATLAB error paths)
- setup wizard alignment for MATLAB detection via `PATH`
- setup wizard robustness improvements (cancel handling, Sage external-drive discovery)

## Branch / Status

- Branch: `feat/docker-support`
- Remote tracking: `origin/feat/docker-support`
- Working tree (tracked files): clean at time of handoff
- Untracked local-only artifact: `.claude-flow/`

## Key Recent Commits

- `f8d603c` fix: align setup wizard matlab detection with PATH
- `dcb8f7e` test: expand coverage and harden preprocessing paths
- `79ec599` chore: update lockfile and project planning
- `5142074` test: cover setup config helpers and preserve empty values
- `10e16bd` refactor: centralize cas port url and remove matlab eval
- `cde787b` fix: harden wa appid override and matlab eval input

## Final Validation Snapshot

Executed locally (with MATLAB available via `PATH`):

- `ruff check .` ✅
- `ruff format --check .` ✅
- `pytest -q -ra` ✅
- `pytest --cov=cas_service --cov-report=term-missing:skip-covered -q` ✅
- `pytest --collect-only -q` → `294` tests collected

### Coverage (final)

- Total: `82%` (`1701` statements, `302` missed)
- `cas_service/main.py`: `88%`
- `cas_service/engines/matlab_engine.py`: `91%`
- `cas_service/preprocessing.py`: `96%`
- `cas_service/engines/wolframalpha_engine.py`: `91%`
- `cas_service/setup/_matlab.py`: `84%`
- `cas_service/setup/_sage.py`: `26%`
- `cas_service/setup/_service.py`: `70%`
- `cas_service/setup/_verify.py`: `62%`

## Setup Wizard Cross-Check (final)

### Fixed / aligned

1. MATLAB setup step now supports:
- `CAS_MATLAB_PATH` as absolute path **or** command name (e.g. `matlab`)
- discovery via `PATH` (`shutil.which("matlab")`)
- custom user input `"matlab"` in wizard prompt
- verification of command names (not only absolute paths)

2. MATLAB discovery improved for external-drive layouts:
- added `/media/.../apps/matlab*/bin/matlab` patterns

3. Sage discovery improved for external-drive layouts:
- added `/media/.../sage`, `/media/.../sagemath*/sage`, `/media/.../apps/sage*/sage`, `/media/.../SageMath*/sage`

4. Wizard interaction robustness:
- explicit cancel handling for `ServiceStep` mode selection
- explicit cancel handling in `run_steps()` confirm and retry/skip/abort prompts

### Already aligned before final pass

- `VerifyStep` uses centralized `get_service_url()` (no hardcoded `localhost:8769`)
- setup config helpers centralize `CAS_PORT` resolution and service URL generation

## Environment Notes (MATLAB)

Tests that gate on `shutil.which("matlab")` require MATLAB on `PATH`.

Validated local setup:

- real binary: `/media/sam/3TB-WDC/matlab2025/bin/matlab`
- symlink: `~/.local/bin/matlab -> /media/sam/3TB-WDC/matlab2025/bin/matlab`

`.env` local runtime config was also aligned to the real path (local only / not part of repo state).

## Residual Gaps (non-blocking)

- `cas_service/setup/_sage.py`, `cas_service/setup/_verify.py`, `cas_service/setup/_wolframalpha.py` still have lower coverage than core runtime modules.
- `_WA_API_URL` default remains hardcoded but is now overrideable via `CAS_WOLFRAMALPHA_API_URL`.
- `.claude/validation/config.json` is absent, so the external ValidationOrchestrator skill cannot run in this repo without scaffolding.

## Suggested Next Steps (optional)

1. Add dedicated unit tests for `SageStep.install()` auto-install branches (apt/brew failure/success with tighter mocks)
2. Add tests for `VerifyStep` smoke methods with mocked `urlopen` request URL assertions (`get_service_url()`)
3. Add docs snippet for MATLAB PATH requirement in README deployment/setup section
