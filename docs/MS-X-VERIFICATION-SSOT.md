# MS-X Verification SSOT — Advanced CAS Compute Integration

**Repo:** `cas-service`
**Date:** 2026-02-24
**Status:** cas-service complete, PePeRS integration pending
**Branch:** `main` (pushed)
**HEAD:** `a6780bc`

---

## 1. What Was Built (Factual)

### Slice A — Compute Foundation
- **`POST /compute`** endpoint with full request validation
- **`Capability`** enum: `validate`, `compute`, `remote`
- **`ComputeRequest`** / **`ComputeResult`** dataclasses
- **`/engines`** response extended with `capabilities` array per engine
- `/validate` **unchanged** (backward compatible)

### Slice B — GapEngine MVP
- **`cas_service/engines/gap_engine.py`** (273 LOC)
- 3 allowlisted templates: `group_order`, `is_abelian`, `center_size`
- Input sanitization: blocks `Exec`, `IO_`, `Process`, semicolons, newlines
- Subprocess execution with configurable timeout and 64KB output cap
- Capability: `[compute]` (not validate — GAP is not a LaTeX validator)

### Slice C — Wizard/Setup/Verify
- **`_gap.py`**: GAP setup step with apt auto-install
- **`_sage.py`**: SageMath detection only (info step, always passes)
- **`_wolframalpha.py`**: env detection for `CAS_WOLFRAMALPHA_APPID`
- **`_verify.py`**: now shows capabilities column + `/compute` smoke test
- **`_service.py`**: documents `CAS_GAP_PATH`, `CAS_WOLFRAMALPHA_APPID`, `CAS_SAGE_PATH`
- `cas-setup engines` now reports 6 engines (was 3)
- `cas-setup` full setup now runs 9 steps (was 6)

### Slice D — WolframAlpha Engine
- **`cas_service/engines/wolframalpha_engine.py`** (225 LOC)
- 3 templates: `evaluate`, `solve`, `simplify`
- Feature-gated: enabled only when `CAS_WOLFRAMALPHA_APPID` is set
- Capability: `[compute, remote]`
- `/engines` shows `availability_reason: "missing CAS_WOLFRAMALPHA_APPID"` when disabled
- **Not** part of `/validate` consensus (by design)
- Error mapping: `AUTH_ERROR`, `NETWORK_ERROR`, `TIMEOUT`, `QUERY_FAILED`, `NO_RESULT`

### Slice E — Sage-Ready Runtime
- **`cas_service/runtime/executor.py`** (240 LOC)
- `SubprocessExecutor`: sync `run()` + async `submit()`/`wait()`
- `Job` dataclass with lifecycle: pending → running → completed/failed/timeout/cancelled
- Thread-safe job registry with eviction
- Output caps, configurable timeout, command-not-found handling
- **Purpose**: future SageEngine plugs in here without redesigning `/compute`

---

## 2. Test Evidence

| Test File | Count | What It Tests |
|-----------|-------|---------------|
| `test_compute_api.py` | 16 | /compute validation, capability checks, backward compat |
| `test_gap_engine.py` | 25 | Templates, input sanitization, subprocess mock, HTTP integration |
| `test_wolframalpha_engine.py` | 21 | API mock, error codes, HTTP integration, availability reason |
| `test_runtime_executor.py` | 19 | Sync/async exec, timeout, output cap, job lifecycle, eviction |
| `test_setup_wizard.py` | 84 | All setup steps (pre-existing + updated counts) |
| **Total** | **165** | **All pass** |

```
$ uv run pytest tests/ -q
165 passed in 15.67s
```

---

## 3. API Contract (Verifiable)

### `GET /engines` Response
```json
{
  "engines": [
    {"name": "sympy", "available": true, "capabilities": ["validate"], "description": "..."},
    {"name": "maxima", "available": true, "capabilities": ["validate"], "description": "..."},
    {"name": "matlab", "available": false, "capabilities": ["validate"], "description": "..."},
    {"name": "gap", "available": false, "capabilities": ["compute"], "description": "..."},
    {"name": "wolframalpha", "available": false, "capabilities": ["compute", "remote"],
     "availability_reason": "missing CAS_WOLFRAMALPHA_APPID", "description": "..."}
  ]
}
```

### `POST /compute` Request
```json
{
  "engine": "gap",
  "task_type": "template",
  "template": "group_order",
  "inputs": {"group_expr": "SymmetricGroup(4)"},
  "timeout_s": 5
}
```

### `POST /compute` Response (success)
```json
{
  "engine": "gap",
  "success": true,
  "time_ms": 120,
  "result": {"value": "24"},
  "stdout": "24\n",
  "stderr": "",
  "error": null,
  "error_code": null
}
```

### Error Codes (structured)
| Code | When |
|------|------|
| `INVALID_REQUEST` | Missing/invalid fields |
| `UNKNOWN_ENGINE` | Engine not in registry |
| `NOT_IMPLEMENTED` | Engine lacks compute capability |
| `ENGINE_UNAVAILABLE` | Engine binary/key missing |
| `UNKNOWN_TEMPLATE` | Template not in allowlist |
| `MISSING_INPUT` | Required template input missing |
| `INVALID_INPUT` | Input fails sanitization |
| `TIMEOUT` | Subprocess/API exceeded timeout |
| `ENGINE_ERROR` | Nonzero exit code |
| `AUTH_ERROR` | WA invalid AppID |
| `NETWORK_ERROR` | WA network failure |
| `QUERY_FAILED` | WA could not interpret query |
| `NO_RESULT` | WA returned no usable result |
| `REMOTE_ERROR` | WA HTTP error |

---

## 4. File Inventory

### New Files (this milestone)
| File | LOC | Slice |
|------|-----|-------|
| `cas_service/engines/gap_engine.py` | 273 | B |
| `cas_service/engines/wolframalpha_engine.py` | 225 | D |
| `cas_service/runtime/__init__.py` | 0 | E |
| `cas_service/runtime/executor.py` | 240 | E |
| `cas_service/setup/_gap.py` | 87 | C |
| `cas_service/setup/_sage.py` | 62 | C |
| `cas_service/setup/_wolframalpha.py` | 42 | C |
| `tests/test_compute_api.py` | 304 | A |
| `tests/test_gap_engine.py` | 308 | B |
| `tests/test_wolframalpha_engine.py` | 369 | D |
| `tests/test_runtime_executor.py` | 164 | E |
| **Total new** | **2074** | |

### Modified Files
| File | Slice | What Changed |
|------|-------|-------------|
| `cas_service/engines/base.py` | A | +Capability, +ComputeRequest, +ComputeResult, +compute(), +capabilities |
| `cas_service/main.py` | A,B,D | +/compute route, +GAP/WA registration, +availability_reason in /engines |
| `cas_service/setup/main.py` | C | +GAP/Sage/WA steps, 9 steps total |
| `cas_service/setup/_verify.py` | C | +capabilities column, +/compute smoke test |
| `cas_service/setup/_service.py` | C | +new env vars in foreground guidance |
| `cas-service.service` | C | +GAP/WA/Sage env placeholders |
| `tests/test_setup_wizard.py` | C | Updated step count assertions |
| `README.md` | A,C | +/compute docs, +engine table, +env vars |

---

## 5. Environment Variables

| Variable | Default | Engine | Required |
|----------|---------|--------|----------|
| `CAS_GAP_PATH` | `gap` | GAP | No (searches PATH) |
| `CAS_GAP_TIMEOUT` | `10` | GAP | No |
| `CAS_WOLFRAMALPHA_APPID` | (empty) | WolframAlpha | Only if using WA |
| `CAS_WOLFRAMALPHA_TIMEOUT` | `10` | WolframAlpha | No |

---

## 6. Security Constraints

- **No arbitrary script execution** — template-only compute
- GAP input sanitization blocks: `Exec`, `IO_`, `Process`, `Runtime`, `System`, file I/O functions
- Semicolons and newlines rejected in GAP inputs
- Input length capped at 200 chars
- Subprocess output capped at 64KB
- WolframAlpha AppID never logged or exposed in API responses
- `cas-service.service` has new env vars as comments (no secrets inline)

---

## 7. Commit History (Milestone)

```
a6780bc docs: update execution log — all cas-service slices complete (A-E)
49aa6d7 feat(cas-service): add Sage-ready runtime executor model
472a030 feat(cas-service): add WolframAlphaEngine optional remote compute
9b4d87f docs: update execution log — Slices A+B+C complete
3d9e531 docs: update README with compute engines and env vars
fd80c0a feat(cas-service): extend setup wizard for GAP, Sage, WolframAlpha
d291b2f feat(cas-service): add GapEngine MVP with template-based compute
8677030 feat(cas-service): add /compute endpoint and capability-based engine model
```

---

## 8. What Is NOT Done (Remaining in Milestone)

| Item | Repo | Status |
|------|------|--------|
| PePeRS P1: CAS client + capability discovery | PePeRS | Not started |
| PePeRS P2: Routing algebra tasks to /compute | PePeRS | Not started |
| PePeRS WA fallback (feature-gated) | PePeRS | Not started |
| SageEngine implementation | cas-service | Future (runtime ready) |
| `/jobs` async endpoints | cas-service | Optional/future (executor ready) |

---

## 9. Cross-Verification Checklist

For Codex/Gemini reviewers — verify these claims:

- [ ] `uv run pytest tests/ -q` → 165 passed
- [ ] `GET /engines` returns 5 engines with capabilities array
- [ ] `POST /compute` with unknown engine → 422 `UNKNOWN_ENGINE`
- [ ] `POST /compute` with validate-only engine → 400 `NOT_IMPLEMENTED`
- [ ] `POST /compute` with `engine=gap` + valid template → 200 (mocked or real)
- [ ] `POST /validate` → unchanged behavior (backward compatible)
- [ ] `cas_service/engines/gap_engine.py` rejects `Exec("ls")` input → `INVALID_INPUT`
- [ ] WA engine `is_available()` returns False when APPID empty
- [ ] `/engines` includes `availability_reason` for WA when disabled
- [ ] `SubprocessExecutor.run(["sleep", "10"], timeout_s=1)` → `timed_out=True`
- [ ] No secrets in `cas-service.service` (all env values are placeholders)
- [ ] No `import gap` or `import wolframalpha` (stdlib only, subprocess-based)
