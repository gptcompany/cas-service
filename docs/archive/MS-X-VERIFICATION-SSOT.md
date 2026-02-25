# Milestone GSD — Advanced CAS Compute Integration (PePeRS + cas-service)

Date: 2026-02-23  
Status: Draft (implementation-ready)  
Mode: Single source of truth for cross-repo work (`cas-service` + `PePeRS`)

## Purpose

This document captures validated findings, architectural decisions, scope, and an implementation plan for extending `cas-service` beyond formula validation and integrating the new capabilities into `PePeRS`.

Primary target:
- Add `GAP` support (high-value, low redundancy)
- Prepare a production-grade runtime path for `SageMath`
- Add optional `WolframAlpha` backend (remote/oracle, not default consensus)
- Update `PePeRS` to discover and route to the new capabilities

## Context Summary

Current state:
- `PePeRS` is the broader tool/pipeline (discovery, LLM analysis, extraction, RAG, orchestration).
- This repo (`cas-service`) is the CAS validation/calculation backend only.

Why this milestone:
- The current CAS stack is good for generic formula validation.
- It is weak for noncommutative / algebra-computational workflows where `GAP` is a much better fit.
- `SageMath` can be valuable, but should be introduced on top of a stronger runtime/executor model.

## Validated Findings

### F1. `cas-service` scope is formula validation (not full PePeRS)

Verified in this repo:
- HTTP endpoints: `/validate`, `/health`, `/status`, `/engines` (`cas_service/main.py`)
- Engines currently registered: `sympy`, `maxima`, `matlab` (`cas_service/main.py`)
- LaTeX preprocessing pipeline exists (`cas_service/preprocessing.py`)
- Engine abstraction is validate-only (`cas_service/engines/base.py`)

Implication:
- Discovery/RAG/LLM/extraction claims belong to `PePeRS`, not this repo.

### F2. Current `cas-service` does not include `GAP`, `SageMath`, or `WolframAlpha`

Verified:
- No `gap` engine
- No `sage` engine
- No `wolframalpha` engine
- No `/compute` endpoint

Implication:
- New engine integration requires both API extension and runtime model changes.

### F3. Wizard/setup is tightly coupled to existing engines

Verified in setup wizard:
- Hardcoded engine steps for `SymPy`, `Maxima`, `MATLAB` (`cas_service/setup/main.py`)
- Verify step checks `/health` and `/engines` only (`cas_service/setup/_verify.py`)
- Service deployment step and unit file expose only current env vars (`cas_service/setup/_service.py`, `cas-service.service`)

Implication:
- Engine additions require wizard + verify + service configuration updates.

### F4. Redundancy profile of candidate engines

Assessment:
- `SymPy + Maxima (+MATLAB)` have useful overlap for formula validation consensus.
- `GAP` adds materially new capability (low redundancy to current stack).
- `SageMath` overlaps partially as validator, but adds value as a general compute platform.
- `WolframAlpha` is a remote oracle/service; useful as optional fallback, not core local compute.

### F5. SageMath should influence runtime design now

Assessment:
- Adding Sage as a simple per-request subprocess later can force painful refactors.
- A Sage-ready runtime model (timeouts, isolation, jobs/executor) should be designed now.
- This should not block an earlier `GAP` MVP release.

## Decision Record (for this milestone)

### D1. Introduce capability-based engine model

Engine capabilities will be exposed and used for routing:
- `validate`
- `compute`
- `remote` (optional marker for external APIs like WolframAlpha)

### D2. Preserve backward compatibility for `/validate`

`POST /validate` remains unchanged in behavior and payloads.

### D3. Add `POST /compute` for structured engine-specific tasks

`/compute` becomes the entry point for `GAP`, future `Sage`, and optional `WolframAlpha`.

### D4. Implement `GAP` before `SageMath`

Reason:
- Higher immediate value for algebra-focused workflows
- Lower integration complexity than a full production-grade Sage engine

### D5. Make `WolframAlpha` optional and non-default

Reason:
- External dependency (API key, network, rate limits)
- Should not be part of default `/validate` consensus path

### D6. Design runtime Sage-ready now, but phase actual Sage engine

Reason:
- Avoid rework
- Keep milestone deliverable practical

## GSD (Goal / Scope / Done)

## Goal

Extend `cas-service` from formula validator to capability-based CAS compute backend, starting with `GAP`, while preparing a production-grade path for `SageMath`, and integrate the new capabilities into `PePeRS`.

## Scope (In)

- `cas-service`
- New `/compute` endpoint
- Capability metadata on `/engines`
- `GapEngine` MVP (template-only)
- Wizard/setup/service updates for new engines
- Optional `WolframAlpha` integration (feature-gated)
- `PePeRS` client/routing updates to use `/engines` and `/compute`

## Scope (Out)

- `Magma` integration
- Arbitrary script execution in MVP (untrusted)
- Full cohomology-specific libraries/workflows in first release
- Non-CAS PePeRS features (discovery/RAG/extraction) unless needed for routing integration

## Done (Milestone Definition)

- `cas-service` exposes stable `/compute`
- `GAP` integrated and visible via `/engines`
- Wizard/setup/verify updated for new engine model
- `PePeRS` uses `/engines` and routes at least one path to `/compute`
- `/validate` remains backward compatible
- Tests pass in both repos for touched paths
- Docs updated

## Target Architecture — `cas-service`

### API Endpoints

Keep:
- `POST /validate` (existing formula validation)
- `GET /health`
- `GET /status`
- `GET /engines` (extended)

Add:
- `POST /compute` (sync, template-only MVP)

Future (Sage-grade runtime phase):
- `POST /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/cancel` (optional)

### Engine Interface Evolution

Current:
- `validate(latex) -> EngineResult`

Target:
- `validate(latex) -> EngineResult` (unchanged)
- `compute(request) -> ComputeResult` (optional; unsupported engines return explicit not supported)
- capability introspection per engine

### Runtime/Safety Model (MVP)

- Template-only tasks (`task_type=template`)
- Allowlisted templates per engine
- Per-request timeout
- Output size limits
- Structured JSON errors
- No arbitrary script execution for untrusted mode

## API Proposal (MVP)

### `POST /compute` Request

```json
{
  "engine": "gap",
  "task_type": "template",
  "template": "group_order",
  "inputs": {
    "group_expr": "SymmetricGroup(4)"
  },
  "timeout_s": 5
}
```

### `POST /compute` Response

```json
{
  "engine": "gap",
  "success": true,
  "time_ms": 120,
  "result": {
    "value": "24"
  },
  "stdout": "24\n",
  "stderr": "",
  "error": null
}
```

### `GET /engines` Response (Extended)

```json
{
  "engines": [
    {
      "name": "sympy",
      "available": true,
      "capabilities": ["validate"],
      "description": "..."
    },
    {
      "name": "gap",
      "available": true,
      "capabilities": ["compute"],
      "description": "..."
    },
    {
      "name": "wolframalpha",
      "available": false,
      "capabilities": ["compute", "remote"],
      "availability_reason": "missing CAS_WOLFRAMALPHA_APPID"
    }
  ]
}
```

## Implementation Plan (Slices)

## Slice A — Foundation (`cas-service`)

### Goal

Add capability-based compute support without breaking existing validation flows.

### Scope

- Extend `BaseEngine`
- Add `ComputeResult`
- Add `POST /compute`
- Extend `/engines` payload with capabilities
- Maintain full backward compatibility for `/validate`

### Tasks

- Update `cas_service/engines/base.py`
- Introduce `ComputeResult` dataclass
- Add optional `compute()` to base engine abstraction
- Add capability introspection method/property
- Implement `POST /compute` in `cas_service/main.py`
- Add request validation for `engine`, `task_type`, `template`, `inputs`, `timeout_s`
- Add structured error codes (`INVALID_REQUEST`, `UNKNOWN_ENGINE`, `NOT_IMPLEMENTED`)
- Extend `/engines` response to include `capabilities`

### Done

- `/validate` unchanged and working
- `/compute` returns JSON (including explicit unsupported)
- `/engines` includes capability data for existing engines

## Slice B — `GapEngine` MVP (`cas-service`)

### Goal

Add the first compute-oriented engine with meaningful new algebra capability.

### Scope

- New `GapEngine`
- Registry integration
- Template-only compute execution
- Timeout + output caps
- 2-3 allowlisted templates

### Suggested Templates (MVP)

- `group_order`
- `character_table_basic`
- `matrix_group_check`

Alternative if simpler for MVP:
- `group_order`
- `is_group_expr_valid`
- `small_group_info`

### Tasks

- Add `cas_service/engines/gap_engine.py`
- Implement GAP availability detection
- Implement subprocess execution wrapper with timeout
- Add stdout/stderr size limits
- Add template compiler (inputs -> GAP code)
- Parse results into structured `result`
- Register `gap` in `cas_service/main.py`
- Expose capabilities `["compute"]`

### Done

- `GET /engines` lists `gap`
- `POST /compute` works for valid GAP templates
- Invalid template/input returns clear error
- Timeout and engine failures return structured JSON

## Slice C — Wizard / Setup / Verify / Service (`cas-service`)

### Goal

Align setup and operations with new engine model.

### Scope

- New GAP setup step
- Sage/WA detection or prep steps
- Verify smoke test for `/compute`
- Service env documentation updates

### Tasks

- Add `cas_service/setup/_gap.py`
- Add `cas_service/setup/_sage.py` (detection/info only OK for this milestone)
- Add `cas_service/setup/_wolframalpha.py` (APPID/env detection only OK initially)
- Update `cas_service/setup/main.py` to include new steps
- Update `cas_service/setup/_verify.py`:
- check `/health`
- check `/engines`
- optionally run lightweight `/compute` smoke test for available compute engine(s)
- Update `cas_service/setup/_service.py` env guidance:
- `CAS_GAP_PATH`
- `CAS_SAGE_PATH` or future runtime URL
- `CAS_WOLFRAMALPHA_APPID` (document as secret)
- Update `cas-service.service` with placeholders/comments (no secrets)
- Update `README.md`

### Done

- `cas-setup engines` reports GAP/Sage/WA status (detection/prep is enough for Sage/WA in this milestone)
- `cas-setup verify` can validate compute support when available
- Service/docs reflect new configuration paths

## Slice D — `WolframAlphaEngine` Optional (`cas-service`)

### Goal

Add a remote engine fallback/oracle without coupling it to default validation consensus.

### Scope

- Optional engine enabled by env (`CAS_WOLFRAMALPHA_APPID`)
- Remote API handling
- Capability metadata `["compute", "remote"]`

### Tasks

- Add `cas_service/engines/wolframalpha_engine.py`
- Implement availability check based on APPID presence
- Implement limited query/template modes (avoid generic raw proxy initially)
- Map API/network/rate-limit errors
- Register engine and expose availability reason when unavailable

### Done

- `/engines` shows `wolframalpha` with availability reason if disabled
- `/compute` with `engine=wolframalpha` works when configured
- WA not used by default in `/validate` consensus

## Slice E — Sage-Ready Runtime (Production-Grade Foundation)

### Goal

Prepare runtime/executor model suitable for a future `SageEngine` without blocking GAP delivery.

### Scope

- Job/executor abstraction
- Async path for long-running tasks
- Timeouts/cancellation/output caps/isolation

### Tasks

- Define executor interface (sync + async compatible)
- Add internal job registry and lifecycle model
- (Optional in this milestone) add `/jobs` endpoints
- Implement process isolation/timeouts/output caps
- Define how `SageEngine` will attach to this runtime

### Done

- Runtime model can support long-running compute tasks
- Adding `SageEngine` later does not require redesigning `/compute`

## Changes Required in `PePeRS` (Yes — Cross-Repo Work)

`cas-service` changes alone are not enough. `PePeRS` must be updated to discover and route to the new capabilities.

## `PePeRS` — Required Changes

### P1. CAS Client / Capability Discovery

- Add `GET /engines` client support
- Add `POST /compute` client support
- Cache capabilities and refresh on startup / periodic invalidation

### P2. Routing / Planner Logic

- Route formula validation tasks to `POST /validate`
- Route algebra-structured tasks to `POST /compute` (`gap` first if available)
- Use `WolframAlpha` only as optional fallback (feature-flagged)
- Preserve existing behavior when `/compute` or `gap` unavailable

### P3. Template Payload Generation

- Map planner/LLM outputs to allowlisted compute templates
- Avoid arbitrary script generation in MVP
- Handle unmappable tasks with fallback or explicit “not supported”

### P4. UX / Observability

- Report engine used (`sympy`, `maxima`, `gap`, `sage`, `wolframalpha`)
- Log timing/error metrics for engine selection tuning
- Add feature flags for optional engines/fallbacks

### P5. Testing

- Mock `cas-service` `/engines`, `/validate`, `/compute`
- Test routing decisions (validate vs compute)
- Test fallback path (local compute unavailable -> WA optional)

## Cross-Repo Dependencies and Execution Order

Recommended order:

1. `cas-service` Slice A (foundation `/compute`)
2. `cas-service` Slice B (`GapEngine` MVP)
3. `cas-service` Slice C (wizard/setup/verify/service updates)
4. `PePeRS` capability discovery + `/compute` client
5. `PePeRS` routing for GAP templates
6. `cas-service` Slice D (`WolframAlpha` optional)
7. `PePeRS` WA fallback (feature-gated)
8. `cas-service` Slice E (Sage-ready runtime foundation)
9. `SageEngine` implementation on top of runtime

## Risks and Mitigations

### Risks

- Scope creep (`GAP + Sage + WA + wizard + PePeRS` in one milestone)
- Security issues if arbitrary compute execution is enabled too early
- Fragile parsing of engine outputs (especially GAP/WA)
- Setup wizard complexity / UX overload
- Runtime instability if heavy engines are added without isolation

### Mitigations

- Template-only compute MVP
- Capability-driven rollout
- WA feature-gated and not default consensus
- Phase Sage runtime foundation before full Sage engine
- Add smoke tests and mocked integration tests early

## Non-Functional Requirements (Minimum)

- Backward compatibility: `/validate` unchanged
- Security: no arbitrary script execution in MVP
- Reliability: timeout and output limits on `compute`
- Observability: engine selection + duration + errors logged
- Setup UX: wizard reports availability and missing config clearly

## File Impact Map — `cas-service`

Likely modifications:
- `cas_service/engines/base.py`
- `cas_service/main.py`
- `README.md`
- `cas_service/setup/main.py`
- `cas_service/setup/_verify.py`
- `cas_service/setup/_service.py`
- `cas-service.service`

Likely new files:
- `cas_service/engines/gap_engine.py`
- `cas_service/engines/wolframalpha_engine.py`
- `cas_service/setup/_gap.py`
- `cas_service/setup/_sage.py`
- `cas_service/setup/_wolframalpha.py`
- new tests under `tests/`

## Claude Code Implementation Prompts

### Prompt A — `cas-service` (Slices A+B+C)

```text
Implement Milestone MS-X Slice A+B+C in cas-service.

Goal:
- Add POST /compute endpoint for capability-based CAS engines
- Add GapEngine (template-only MVP)
- Extend /engines response with capabilities
- Update setup wizard and service docs/unit for GAP and future Sage/WA support
- Keep POST /validate fully backward compatible

Constraints:
- Preserve current engine validate() behavior
- Template-only compute execution (no arbitrary script execution yet)
- Timeouts and output size limits required
- Add tests for /compute and GapEngine
- Update README and setup wizard verification flow

Files likely impacted:
- cas_service/main.py
- cas_service/engines/base.py
- cas_service/engines/gap_engine.py (new)
- cas_service/setup/main.py
- cas_service/setup/_verify.py
- cas_service/setup/_service.py
- cas-service.service
- README.md
- tests/*

Deliverables:
- Working /compute endpoint
- GAP engine registration and availability reporting
- Wizard step for GAP
- Updated /engines capability output
- Tests passing
```

### Prompt B — `PePeRS` (integration changes)

```text
Implement PePeRS integration for new cas-service compute capabilities.

Goal:
- Add client support for GET /engines and POST /compute
- Add routing logic: formula validation -> /validate, algebra-structured tasks -> /compute (gap)
- Feature-gate WolframAlpha fallback if remote engine available
- Preserve current behavior when /compute is unavailable

Requirements:
- Capability discovery and caching
- Engine-aware routing
- Template-based compute payload generation
- Integration tests with mocked cas-service responses

Deliverables:
- Updated CAS client
- Routing/planner changes
- Tests for validate vs compute path
- Config flags for optional WA fallback
```

## Open Questions (to resolve before/while implementing)

- Which 2-3 GAP templates provide the best immediate value for PePeRS use cases?
- Should `POST /compute` be sync-only in Slice A/B, or include async scaffolding immediately?
- Do we want `WolframAlpha` in this milestone or move it to a follow-up after GAP + PePeRS routing?
- What is the first `PePeRS` planner signal used to classify “formula validation” vs “algebra-structured compute”?

## Suggested First Execution Step (Pragmatic)

Start with:
- `cas-service` Slice A (foundation `/compute` + capabilities)

Reason:
- Unblocks all other work
- Low risk
- Keeps backward compatibility
- Makes the `PePeRS` integration contract concrete

## Step-by-Step Execution Playbook (Claude Code + GSD, Resumable)

This section is optimized for resuming work after rate limits or session interruptions.

## 1. Session Start Checklist (Resume-Safe)

Run at the beginning of each Claude Code session in the target repo.

### 1.1 Confirm repo and branch

- `pwd`
- `git status --short`
- `git branch --show-current`

Recommended branch names:
- `feat/ms-x-cas-compute-foundation`
- `feat/ms-x-gap-engine-mvp`
- `feat/ms-x-wizard-compute`
- `feat/ms-x-pepers-cas-compute-routing`

### 1.2 Open this milestone document first

- `docs/MS-X-VERIFICATION-SSOT.md`

### 1.3 Restore last checkpoint

Use the latest completed marker from Section 7 (Implementation Plan) and this Playbook's checkpoint log (Section 8 below).

## 2. GSD Operating Loop (per Slice)

Use this exact loop for each slice.

### 2.1 Goal (G)

Tell Claude Code the single slice goal only (avoid combining multiple slices unless explicitly intended).

Example:
- "Implement Slice A only: `/compute` endpoint + capability model, keep `/validate` backward compatible."

### 2.2 Scope (S)

Constrain files and behavior.

Example constraints:
- no arbitrary script execution
- template-only compute
- no changes to `/validate` payloads
- add tests for touched API paths

### 2.3 Done (D)

Define pass criteria before coding.

Example:
- `/compute` returns JSON
- `/engines` exposes capabilities
- tests pass
- README updated for new endpoint

### 2.4 Execute

Ask Claude Code to implement exactly the slice.

### 2.5 Validate

Minimum local checks after each slice:
- `pytest`
- manual smoke test for touched endpoint(s)
- `git diff --stat`

Optional (if configured in repo later):
- `~/.claude/templates/validation/scaffold.sh . general` (first-time only)
- `/validate quick`
- `confidence-gate` on summary/diff

### 2.6 Commit + Handoff Note

Commit at slice boundaries with a short structured message and update the checkpoint log.

Suggested commit format:
- `feat(cas-service): add compute endpoint foundation`
- `feat(cas-service): add gap engine template mvp`
- `feat(cas-service): extend setup wizard for compute engines`
- `feat(pepers): route algebra tasks to cas-service compute`

## 3. Step-by-Step Implementation Sequence (Cross-Repo)

## Step 1 — `cas-service` Slice A (Foundation)

### Goal

Add capability-based compute support without adding new compute engines yet.

### Files (expected)

- `cas_service/engines/base.py`
- `cas_service/main.py`
- `README.md`
- tests under `tests/`

### Deliverables

- `ComputeResult` abstraction
- optional `compute()` support in engine interface
- `POST /compute` endpoint
- `/engines` capability metadata
- backward-compatible `/validate`

### Claude Code prompt (copy/paste)

```text
Implement Slice A only in cas-service.

Goal:
- Add a capability-based compute foundation
- Add POST /compute endpoint
- Extend GET /engines with capabilities
- Keep POST /validate fully backward compatible

Constraints:
- No GAP/Sage/WA engine implementation yet
- Template-only request schema accepted, but unsupported engines may return NOT_IMPLEMENTED
- Add tests for /compute error handling and /engines capabilities output
- Update README minimally for new endpoint

Done when:
- /compute returns structured JSON errors/success responses
- /engines includes capabilities for existing engines
- /validate behavior is unchanged
- pytest passes
```

### Validation checklist

- `pytest`
- start service and test:
- `curl -s http://localhost:8769/engines | jq .`
- `curl -s -X POST http://localhost:8769/compute -H 'Content-Type: application/json' -d '{}' | jq .`

### Checkpoint marker

- `A-DONE` when endpoint + capability model + tests are in place

## Step 2 — `cas-service` Slice B (`GapEngine` MVP)

### Goal

Add `GapEngine` with template-only compute execution.

### Files (expected)

- `cas_service/engines/gap_engine.py` (new)
- `cas_service/main.py`
- tests
- `README.md`

### Deliverables

- GAP availability detection
- template allowlist
- subprocess timeout and output caps
- structured result parsing
- `/engines` exposes `gap`

### Claude Code prompt (copy/paste)

```text
Implement Slice B only in cas-service.

Prerequisite:
- Assume Slice A is already implemented.

Goal:
- Add GapEngine template-only MVP via POST /compute

Constraints:
- No arbitrary script execution
- Add timeout and stdout/stderr size limits
- Provide 2-3 allowlisted templates (start with group_order + one more simple template)
- Return structured JSON errors for invalid templates/inputs
- Add tests for GapEngine and /compute gap path

Done when:
- gap appears in GET /engines
- valid gap template compute requests succeed (or show unavailable cleanly if GAP missing)
- invalid requests fail with clear codes
- pytest passes
```

### Validation checklist

- `pytest`
- `curl -s http://localhost:8769/engines | jq .`
- `curl -s -X POST http://localhost:8769/compute -H 'Content-Type: application/json' -d '{"engine":"gap","task_type":"template","template":"group_order","inputs":{"group_expr":"SymmetricGroup(4)"}}' | jq .`

### Checkpoint marker

- `B-DONE` when GAP template compute is working end-to-end

## Step 3 — `cas-service` Slice C (Wizard / Verify / Service)

### Goal

Bring setup/deployment tooling in sync with the new engine model.

### Files (expected)

- `cas_service/setup/main.py`
- `cas_service/setup/_verify.py`
- `cas_service/setup/_service.py`
- `cas_service/setup/_gap.py` (new)
- `cas_service/setup/_sage.py` (new, detection/prep)
- `cas_service/setup/_wolframalpha.py` (new, env detection)
- `cas-service.service`
- `README.md`

### Deliverables

- GAP setup step
- Sage/WA detection/prep steps
- `/compute` smoke test in verify step (best effort)
- service env guidance for new engines

### Claude Code prompt (copy/paste)

```text
Implement Slice C only in cas-service.

Prerequisites:
- Assume Slice A and Slice B are already implemented.

Goal:
- Update setup wizard, verification flow, and service docs/unit for compute-capable engines

Constraints:
- GAP step should be functional
- Sage and WolframAlpha steps may be detection/info-only in this slice
- Verify step should smoke-test /compute only when a compute engine is available
- Do not hardcode secrets in cas-service.service

Done when:
- cas-setup engines reports GAP/Sage/WA statuses
- cas-setup verify checks /health, /engines, and compute smoke test when possible
- README and service env docs are updated
- pytest passes
```

### Validation checklist

- `pytest`
- `uv run cas-setup engines`
- `uv run cas-setup verify`

### Checkpoint marker

- `C-DONE` when wizard and verify flow reflect compute engines

## Step 4 — `PePeRS` Integration Phase 1 (Client + Capability Discovery)

### Goal

Teach PePeRS to discover CAS capabilities and call `/compute`.

### Deliverables

- `GET /engines` client support
- `POST /compute` client support
- capability cache/refresh
- preserve fallback to existing `/validate` path

### Claude Code prompt (copy/paste)

```text
Implement PePeRS integration Phase 1 in the PePeRS repo.

Goal:
- Add cas-service client support for GET /engines and POST /compute
- Cache capabilities and preserve backward compatibility with validate-only cas-service instances

Constraints:
- Do not change planner routing behavior yet beyond safe no-op capability discovery
- Add integration tests with mocked cas-service responses

Done when:
- PePeRS can discover engine capabilities
- PePeRS can call /compute via client abstraction
- Existing validate flows still work when /compute is absent
```

### Checkpoint marker

- `P1-DONE`

## Step 5 — `PePeRS` Integration Phase 2 (Routing to GAP)

### Goal

Route algebra-structured tasks to `/compute` with template payloads.

### Deliverables

- routing logic (`validate` vs `compute`)
- template payload generation (allowlist)
- optional WA fallback flag hook (no implementation dependency yet)

### Claude Code prompt (copy/paste)

```text
Implement PePeRS integration Phase 2 in the PePeRS repo.

Prerequisite:
- Phase 1 client/capability discovery is complete.

Goal:
- Route formula validation tasks to /validate
- Route algebra-structured tasks to /compute using gap templates

Constraints:
- Template-only payload generation (no arbitrary scripts)
- Preserve current behavior when gap or /compute is unavailable
- Add routing tests and fallback tests

Done when:
- At least one real algebra task path uses gap /compute
- Formula paths still use /validate
- Tests pass
```

### Checkpoint marker

- `P2-DONE`

## Step 6 — Optional `WolframAlpha` Slice D (`cas-service` + PePeRS follow-up)

### Goal

Add feature-gated remote oracle fallback.

### Deliverables

- `WolframAlphaEngine` in `cas-service`
- APPID env-based availability
- PePeRS feature-gated fallback path

### Checkpoint markers

- `D-WA-CAS-DONE`
- `D-WA-PEPERS-DONE`

## Step 7 — Sage-Ready Runtime (Slice E)

### Goal

Introduce executor/job model before full `SageEngine`.

### Deliverables

- runtime/executor abstraction
- optional jobs endpoints
- isolation + timeout + output caps
- documented path for future `SageEngine`

### Checkpoint marker

- `E-RUNTIME-DONE`

## 4. Resume Protocol (When Rate Limit Resets)

When you come back, do this in order:

1. Open `docs/MS-X-VERIFICATION-SSOT.md`
2. Find the latest checkpoint marker in Section 8 (Execution Log Template)
3. Resume from the next step in Section 3
4. Paste the corresponding Claude Code prompt for that step
5. Ask Claude Code to update the same document with:
- completed checkpoint marker
- date/time
- what changed
- blockers/open questions

Suggested resume prompt to Claude Code:

```text
Resume milestone MS-X from checkpoint <LAST_CHECKPOINT> using docs/MS-X-VERIFICATION-SSOT.md.

Instructions:
- Read the milestone document first
- Continue from the next step in the Step-by-Step Execution Playbook
- Follow GSD (Goal/Scope/Done) for the next slice only
- Update the checkpoint log in the same document when finished
- Keep changes narrowly scoped and backward compatible
```

## 5. Handoff Template (Paste into Claude Code at Session Start)

Use this when resuming after interruption:

```text
Handoff for MS-X (Advanced CAS Compute Integration):

Repo: <cas-service or PePeRS>
Milestone doc: docs/MS-X-VERIFICATION-SSOT.md
Last checkpoint: <A-DONE | B-DONE | C-DONE | P1-DONE | P2-DONE | ...>
Next step: <Step # and slice name>

What is already done:
- <bullet>
- <bullet>

What remains in this step:
- <bullet>
- <bullet>

Constraints:
- <bullet>
- <bullet>

Validation to run:
- pytest
- <other checks>
```

## 6. Minimal Validation Matrix (Per Step)

- Slice A: API contract + backward compatibility
- Slice B: GAP compute path + error handling + timeout behavior
- Slice C: wizard output + verify step + docs/service env guidance
- PePeRS P1: client compatibility with validate-only and compute-capable cas-service
- PePeRS P2: routing correctness and fallback behavior
- WA Slice D: feature-gated remote path; no regression to local paths
- Sage Runtime Slice E: executor stability and timeout/isolation behavior

## 7. Scope Guardrails (Important)

To keep implementation tractable:

- Do not add arbitrary script execution before template-only compute works
- Do not block GAP MVP on full Sage integration
- Do not make WA part of default `/validate` consensus
- Do not couple PePeRS routing to one specific engine name without capability checks
- Keep `/validate` payload/response compatibility intact

## 8. Execution Log Template (Update This In-Place During Work)

Append entries under this section as you progress.

Template:

```md
### YYYY-MM-DD HH:MM — <Repo> — <Slice/Phase>
- Checkpoint: <A-DONE | B-DONE | C-DONE | P1-DONE | P2-DONE | ...>
- Changes:
  - <short bullet>
  - <short bullet>
- Validation:
  - <pytest / smoke tests>
- Open questions/blockers:
  - <if any>
- Next step:
  - <next planned step>
```

### 2026-02-23 21:37 — cas-service — Slice A (Foundation)
- Checkpoint: A-DONE
- Changes:
  - `ComputeRequest`, `ComputeResult`, `Capability` enum in `engines/base.py`
  - `POST /compute` endpoint with full request validation in `main.py`
  - `/engines` now includes `capabilities` per engine
  - 16 new tests in `tests/test_compute_api.py`
- Validation:
  - pytest 125/125 pass
- Next step: Slice B

### 2026-02-23 21:45 — cas-service — Slice B (GapEngine MVP)
- Checkpoint: B-DONE
- Changes:
  - `cas_service/engines/gap_engine.py`: 3 templates (group_order, is_abelian, center_size)
  - Input sanitization, subprocess timeout, output caps (64KB)
  - GAP registered in engine registry
  - 25 new tests in `tests/test_gap_engine.py`
- Validation:
  - pytest 125/125 pass
- Next step: Slice C

### 2026-02-23 22:00 — cas-service — Slice C (Wizard/Setup/Verify)
- Checkpoint: C-DONE
- Changes:
  - `_gap.py`: GAP setup step with auto-install on apt
  - `_sage.py`: SageMath detection (info-only)
  - `_wolframalpha.py`: WolframAlpha env detection
  - `_verify.py`: capabilities column + /compute smoke test
  - `_service.py`: new env vars documented
  - `main.py`: 9 steps (was 6), engine subcommand includes new engines
  - README fully updated with compute engines and env vars
- Validation:
  - pytest 125/125 pass
- Next step: Step 4 — PePeRS Integration Phase 1 (or Slice D WolframAlpha)

### 2026-02-24 — cas-service — Slice D (WolframAlpha)
- Checkpoint: D-WA-CAS-DONE
- Changes:
  - `cas_service/engines/wolframalpha_engine.py`: 3 templates (evaluate, solve, simplify)
  - Feature-gated via CAS_WOLFRAMALPHA_APPID env
  - `/engines` shows availability_reason when disabled
  - Not part of /validate consensus
  - 21 new tests in `tests/test_wolframalpha_engine.py`
- Validation:
  - pytest 146/146 pass
- Next step: Slice E

### 2026-02-24 — cas-service — Slice E (Sage-Ready Runtime)
- Checkpoint: E-RUNTIME-DONE
- Changes:
  - `cas_service/runtime/executor.py`: SubprocessExecutor (sync + async)
  - Job lifecycle: pending/running/completed/failed/cancelled/timeout
  - Output caps, eviction, thread-safe job registry
  - 19 new tests in `tests/test_runtime_executor.py`
- Validation:
  - pytest 165/165 pass
- Next step: PePeRS Integration (Step 4 P1 + Step 5 P2)

## 9. Suggested Next Action (Immediate)

All 5 cas-service slices complete (A+B+C+D+E). Remaining work:

If resuming in `PePeRS`, start with:
- **Step 4 / P1** (CAS client + capability discovery)
- **Step 5 / P2** (Routing algebra tasks to /compute)
