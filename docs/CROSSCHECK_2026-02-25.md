# Cross-Check Document — cas-service gap fix + compute (2026-02-25)

## Purpose

This document provides a structured cross-check of all changes made on `feat/docker-support` since diverging from `main`. It is designed for external review (Codex, Gemini, or human reviewer) and contains concrete verification commands, file locations, and assertions.

---

## Branch State

- **Branch**: `feat/docker-support`
- **Commits from main**: 9 (`1a70def..de6decc`)
- **Files changed**: 34 (3539 insertions, 600 deletions)
- **Tests**: 294 collected, 294 passed, 0 failed, 2 skipped (MATLAB integration)
- **Coverage**: 82% (1701 statements, 302 missed)
- **Lint**: `ruff check .` clean
- **Format**: `ruff format --check .` clean

## Commit Chain

```
de6decc docs: add final repo handoff document with verified state
f8d603c fix: align setup wizard matlab detection with PATH
dcb8f7e test: expand coverage and harden preprocessing paths
79ec599 chore: update lockfile and project planning
5142074 test: cover setup config helpers and preserve empty values
10e16bd refactor: centralize cas port url and remove matlab eval
cde787b fix: harden wa appid override and matlab eval input
e1ebc49 fix: SymPy subprocess migration, compute templates, gap fixes
1a70def feat: add Docker support with Dockerfile, Compose, and wizard integration
```

---

## Plan Implementation Checklist

### Step 1: ExecResult.truncated

**Claim**: Added `truncated: bool = False` to ExecResult and detection logic before truncation.

**Verification**:
```bash
grep -n "truncated" cas_service/runtime/executor.py
# Expected: line ~49 "truncated: bool = False" in dataclass
# Expected: "was_truncated" logic before return in run()

grep -n "truncated" tests/test_runtime_executor.py
# Expected: TestOutputTruncation class with >=2 tests
```

**Files**: `cas_service/runtime/executor.py:49`, `tests/test_runtime_executor.py`

**Evidence**: Field present at line 49, detection at `was_truncated = len(proc.stdout) > cap or len(proc.stderr) > cap`

---

### Step 2: BaseEngine.cleanup()

**Claim**: Added no-op `cleanup()` to BaseEngine, called in main.py shutdown.

**Verification**:
```bash
grep -n "def cleanup" cas_service/engines/base.py
# Expected: line ~83

grep -n "cleanup()" cas_service/main.py
# Expected: engine.cleanup() in finally block

grep -n "cleanup" tests/test_compute_api.py
# Expected: test for default_cleanup_is_noop
```

**Files**: `cas_service/engines/base.py:83`, `cas_service/main.py:548`

**Evidence**: `base.py` has `def cleanup(self) -> None:` at line 83. `main.py` calls `engine.cleanup()` at line 548. Test at `tests/test_compute_api.py::TestBaseEngineDefaults::test_default_cleanup_is_noop`.

---

### Step 3: Sage equation regex fix

**Claim**: Changed `(?<![<>!])=(?!=)` to `(?<![<>!=])=(?!=)` to prevent `==` becoming `===`.

**Verification**:
```bash
grep -n '(?<!\[<>!=\])=(?!=)' cas_service/engines/sage_engine.py
# Expected: lines 297-298 with the CORRECTED regex including '=' in lookbehind

# Functional test:
uv run pytest tests/test_sage_engine.py -k "equation" -v
# Expected: TestEquationRegex class with tests for ==, !=, <=, single =
```

**Files**: `cas_service/engines/sage_engine.py:297-298`, `tests/test_sage_engine.py`

**Evidence**: Sage `_is_equation` logic at lines 290-299 uses `(?<![<>!=])=(?!=)`. The `=` in the lookbehind group prevents `==` from being converted to `===`.

---

### Step 4: MATLAB is_available() fix

**Claim**: Dual path handling — absolute paths use isfile+access, bare names use shutil.which.

**Verification**:
```bash
grep -n "is_available" cas_service/engines/matlab_engine.py
# Expected: os.path.isabs check, os.path.isfile + os.access for abs, shutil.which for relative

grep -n "is_available" tests/test_matlab_engine.py
# Expected: TestMatlabIsAvailable with 3+ tests
```

**Files**: `cas_service/engines/matlab_engine.py:289-294`

**Evidence**: Lines 289-294:
```python
def is_available(self) -> bool:
    if os.path.isabs(self.matlab_path):
        return os.path.isfile(self.matlab_path) and os.access(self.matlab_path, os.X_OK)
    return shutil.which(self.matlab_path) is not None
```

Tests: `test_nonexistent_absolute_path`, `test_bare_name_not_on_path`, `test_default_not_available`.

---

### Step 5: 503 NO_ENGINES on empty/unavailable engines

**Claim**: /validate returns 503 with code `NO_ENGINES` when no engines are registered or available.

**Verification**:
```bash
grep -n "NO_ENGINES" cas_service/main.py
# Expected: line ~129

uv run pytest tests/test_compute_api.py -k "no_engines or unavailable" -v
# Expected: 2 tests passing for 503 behavior
```

**Files**: `cas_service/main.py:129`, `tests/test_compute_api.py`

**Evidence**: `main.py:129` sends `NO_ENGINES` error code with 503 status. Two tests: `test_503_when_no_engines_registered` and `test_503_when_all_engines_unavailable`.

---

### Step 6: SymPy subprocess migration + 6 compute templates

**Claim**: Complete rewrite — removed signal.SIGALRM, migrated to SubprocessExecutor, added 6 compute templates.

**Verification**:
```bash
# Signal code REMOVED:
grep -c "signal" cas_service/engines/sympy_engine.py
# Expected: 1 (only in docstring mentioning the old approach)

# Subprocess approach:
grep -n "SubprocessExecutor" cas_service/engines/sympy_engine.py
# Expected: import + instantiation

# Compute templates (6):
grep "template ==" cas_service/engines/sympy_engine.py | wc -l
# OR check _SYMPY_COMPUTE_SCRIPT for: evaluate, simplify, solve, factor, integrate, differentiate

# Capabilities:
grep "COMPUTE" cas_service/engines/sympy_engine.py
# Expected: Capability.COMPUTE in capabilities property

# Input sanitization:
grep "_validate_input" cas_service/engines/sympy_engine.py
# Expected: function definition + usage in compute()

# Test count:
uv run pytest tests/test_sympy_engine.py --co -q | tail -1
# Expected: 32 tests

# All pass:
uv run pytest tests/test_sympy_engine.py -v
```

**Files**: `cas_service/engines/sympy_engine.py` (346 lines, rewritten), `tests/test_sympy_engine.py` (32 tests)

**Key assertions**:
- `signal.SIGALRM` is gone — only a docstring mention remains
- Uses `SubprocessExecutor` + `sys.executable -c` for subprocess isolation
- Scripts: `_SYMPY_VALIDATE_SCRIPT` (base64+JSON via stdin) and `_SYMPY_COMPUTE_SCRIPT`
- 6 templates: evaluate, simplify, solve, factor, integrate, differentiate
- `capabilities = [Capability.VALIDATE, Capability.COMPUTE]`
- `_validate_input()` blocks `__import__`, `exec`, `eval`, `os.`, `subprocess`, `open(`

---

### Step 7: MATLAB compute with 4 templates

**Claim**: Added compute(), 4 templates, input sanitization, str2sym replaces eval.

**Verification**:
```bash
# No eval() in generated MATLAB code:
grep -n "eval(" cas_service/engines/matlab_engine.py
# Expected: 0 matches (eval is in BLOCKED list, not in generated code)

# str2sym used instead:
grep -n "str2sym" cas_service/engines/matlab_engine.py
# Expected: line ~376 in evaluate template

# 4 templates:
grep -n '"evaluate"\|"simplify"\|"solve"\|"factor"' cas_service/engines/matlab_engine.py | head -10

# Input sanitization:
grep -n "_validate_input\|_BLOCKED_PATTERNS" cas_service/engines/matlab_engine.py

# Capabilities:
grep "COMPUTE" cas_service/engines/matlab_engine.py

# Test count:
uv run pytest tests/test_matlab_engine.py --co -q | tail -1
# Expected: 30 tests (26 unit + 2 integration skipped + 2 coverage)

# All pass (integration skipped without MATLAB):
uv run pytest tests/test_matlab_engine.py -v
```

**Files**: `cas_service/engines/matlab_engine.py` (470 lines), `tests/test_matlab_engine.py` (30 tests)

**Key assertions**:
- `eval()` completely removed from generated MATLAB code
- `evaluate` template uses `str2sym()` with `_matlab_single_quoted()` escaping
- `_BLOCKED_PATTERNS` regex blocks: system, unix, dos, perl, python, java, eval, feval, evalc, urlread, webread, fopen, delete, setenv, getenv, `!`
- `_validate_input()` rejects empty, >500 chars, null bytes, newlines, blocked patterns
- `capabilities = [Capability.VALIDATE, Capability.COMPUTE]`

---

## Security Cross-Check

### Input sanitization coverage

| Engine | Sanitizer | Blocks | Location |
|--------|-----------|--------|----------|
| SymPy | `_validate_input()` | `__import__`, `exec`, `eval`, `os.`, `subprocess`, `open(`, `compile`, null bytes | `sympy_engine.py:28-42` |
| MATLAB | `_validate_input()` | `system(`, `unix(`, `eval(`, `fopen`, `delete(`, `setenv`, `!`, null/newline | `matlab_engine.py:102-120` |
| Sage | `_validate_input()` | `import`, `exec`, `eval`, `os.`, `subprocess`, `open(`, `compile`, null bytes | `sage_engine.py:48-65` |

### MATLAB eval removal

**Before** (`main` branch): `evaluate` template used `result = eval(expr)` — arbitrary code execution risk.
**After**: Uses `expr = str2sym('escaped_input'); result = simplify(expr);` — safe symbolic parsing only.

**Verification**:
```bash
# Confirm no eval in MATLAB engine:
grep "eval(" cas_service/engines/matlab_engine.py
# Expected: only in _BLOCKED_PATTERNS (blocking eval, not using it)

# Confirm str2sym usage:
grep "str2sym" cas_service/engines/matlab_engine.py
# Expected: line 376
```

### WolframAlpha AppID override

**Issue**: `None` override was treated as "not set", but `""` (empty string) was silently passed through causing API failures.

**Verification**:
```bash
grep -n "appid" cas_service/engines/wolframalpha_engine.py | head -10
# Expected: proper None/empty handling with fallback to env var
```

---

## Coverage Per Module (final)

| Module | Coverage | Missed |
|--------|----------|--------|
| `cas_service/engines/matlab_engine.py` | 91% | 15 lines |
| `cas_service/engines/sage_engine.py` | 91% | 13 lines |
| `cas_service/engines/sympy_engine.py` | 96% | 4 lines |
| `cas_service/engines/wolframalpha_engine.py` | 91% | 9 lines |
| `cas_service/main.py` | 88% | 29 lines |
| `cas_service/preprocessing.py` | 96% | 2 lines |
| `cas_service/runtime/executor.py` | 97% | 3 lines |
| **Total** | **82%** | **302 lines** |

---

## Test Distribution

| Test file | Count | Category |
|-----------|-------|----------|
| `tests/test_compute_api.py` | 19 | API endpoint tests |
| `tests/test_main_coverage.py` | 13 | Main handler coverage |
| `tests/test_matlab_coverage.py` | 8 | MATLAB edge cases |
| `tests/test_matlab_engine.py` | 30 | MATLAB engine unit+integration |
| `tests/test_preprocessing.py` | 5 | LaTeX preprocessing |
| `tests/test_runtime_executor.py` | 21 | Subprocess executor |
| `tests/test_sage_engine.py` | 50 | Sage engine unit+integration |
| `tests/test_setup_config.py` | 12 | Setup config helpers |
| `tests/test_setup_wizard.py` | 81 | Setup wizard steps |
| `tests/test_sympy_engine.py` | 32 | SymPy engine unit+integration |
| `tests/test_wolframalpha_engine.py` | 23 | WolframAlpha engine |
| **Total** | **294** | |

---

## Verification Commands (copy-paste)

Run these to reproduce the verified state:

```bash
# 1. Lint clean
uv run ruff check .

# 2. Format clean
uv run ruff format --check .

# 3. All tests pass
uv run pytest tests/ -v

# 4. Coverage report
uv run pytest --cov=cas_service --cov-report=term-missing:skip-covered -q

# 5. Test collection count
uv run pytest --co -q | tail -1
# Expected: 294 tests collected

# 6. No signal.SIGALRM usage in SymPy engine (1 mention in docstring only)
grep -n "SIGALRM" cas_service/engines/sympy_engine.py
# Expected: only line 4 (docstring explaining why old approach was removed)

# 7. No eval() in MATLAB generated code
grep "eval(" cas_service/engines/matlab_engine.py | grep -v BLOCKED | grep -v "feval\|evalc"
# Expected: no output

# 8. str2sym present in MATLAB evaluate template
grep "str2sym" cas_service/engines/matlab_engine.py
# Expected: 1 match

# 9. Sage regex includes = in lookbehind
grep -n '<>!=' cas_service/engines/sage_engine.py
# Expected: 2 matches (lines 297 and 298)

# 10. 503 NO_ENGINES code exists
grep "NO_ENGINES" cas_service/main.py
# Expected: 1 match

# 11. cleanup() in base and called in main
grep "def cleanup" cas_service/engines/base.py && grep "cleanup()" cas_service/main.py
# Expected: both match

# 12. truncated field in ExecResult
grep "truncated.*bool" cas_service/runtime/executor.py
# Expected: 1 match
```

---

## Known Residual Gaps (non-blocking)

1. `cas_service/setup/_sage.py` coverage at 26% — install/auto-install branches untested
2. `cas_service/setup/_verify.py` coverage at 62% — smoke test methods with mocked urlopen needed
3. `cas_service/setup/_wolframalpha.py` coverage at 24% — install flow untested
4. MATLAB integration tests skipped in CI (require MATLAB on PATH)
5. `_WA_API_URL` hardcoded default (overrideable via `CAS_WOLFRAMALPHA_API_URL`)

---

## Reviewer Checklist

- [ ] All 294 tests pass (`uv run pytest tests/ -v`)
- [ ] Lint clean (`uv run ruff check .`)
- [ ] Format clean (`uv run ruff format --check .`)
- [ ] No `signal.SIGALRM` in sympy_engine.py
- [ ] No `eval()` in MATLAB generated code
- [ ] `str2sym()` used for MATLAB evaluate template
- [ ] Sage regex has `=` in lookbehind group
- [ ] 503 NO_ENGINES response implemented
- [ ] Input sanitization present in all 3 compute engines (SymPy, MATLAB, Sage)
- [ ] `cleanup()` method in BaseEngine and called in main.py shutdown
- [ ] `truncated` field in ExecResult dataclass
- [ ] SymPy uses SubprocessExecutor (not in-process signal)
- [ ] Compute templates: SymPy=6, MATLAB=4
- [ ] Coverage >= 82%
