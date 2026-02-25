"""SymPy CAS engine — validate + compute via SubprocessExecutor.

Runs SymPy in a subprocess (same Python interpreter) to avoid
signal.SIGALRM limitations in worker threads. This makes the engine
safe for concurrent use in ThreadPoolExecutor.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import sys
import time
from typing import Any

from cas_service.engines.base import (
    BaseEngine,
    Capability,
    ComputeRequest,
    ComputeResult,
    EngineResult,
)
from cas_service.runtime.executor import SubprocessExecutor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS = re.compile(
    r"(__import__|exec\s*\(|eval\s*\(|compile\s*\(|open\s*\("
    r"|os\.|sys\.|subprocess|import\s|from\s.*import"
    r"|globals|locals|getattr|setattr|delattr"
    r"|__builtins__|__class__|__subclasses__"
    r"|Popen|system\(|popen)",
    re.IGNORECASE,
)


def _validate_input(value: str) -> bool:
    """Safety check on a SymPy input value."""
    if not value or len(value) > 500:
        return False
    if _BLOCKED_PATTERNS.search(value):
        return False
    if "\x00" in value:
        return False
    return True


# ---------------------------------------------------------------------------
# Subprocess scripts (executed via `sys.executable -c`)
# ---------------------------------------------------------------------------

_SYMPY_VALIDATE_SCRIPT = """\
import json, sys, base64
data = json.loads(base64.b64decode(sys.stdin.read().strip()).decode())
latex_str = data['latex']
try:
    from sympy.parsing.latex import parse_latex
    try:
        expr = parse_latex(latex_str)
    except Exception:
        expr = parse_latex(latex_str, backend="lark")
    import sympy
    if isinstance(expr, sympy.Eq):
        diff = sympy.simplify(expr.lhs - expr.rhs)
        is_valid = bool(diff == 0)
        simplified = str(sympy.simplify(expr.lhs)) + ' = ' + str(sympy.simplify(expr.rhs))
        parsed = str(expr.lhs) + ' = ' + str(expr.rhs)
    else:
        simplified = str(sympy.simplify(expr))
        parsed = str(expr)
        is_valid = True
    print('SYMPY_VALID:' + ('1' if is_valid else '0'))
    print('SYMPY_SIMPLIFIED:' + simplified)
    print('SYMPY_PARSED:' + parsed)
except Exception as e:
    print('SYMPY_ERROR:' + str(e))
"""

_SYMPY_COMPUTE_SCRIPT = """\
import json, sys, base64
from sympy import *
x, y, z, t, a, b, c, n, k, m = symbols('x y z t a b c n k m')
_lcl = {'x': x, 'y': y, 'z': z, 't': t, 'a': a, 'b': b, 'c': c, 'n': n, 'k': k, 'm': m}
data = json.loads(base64.b64decode(sys.stdin.read().strip()).decode())
task = data['task']
inputs = data['inputs']
def _out(val):
    print('SYMPY_RESULT:' + str(val).replace('\\n', ' '))
try:
    if task == 'evaluate':
        expr = sympify(inputs['expression'], locals=_lcl)
        _out(N(expr))
    elif task == 'simplify':
        expr = sympify(inputs['expression'], locals=_lcl)
        _out(simplify(expr))
    elif task == 'solve':
        expr = sympify(inputs['equation'], locals=_lcl)
        v = _lcl.get(inputs.get('variable', 'x'), x)
        _out(solve(expr, v))
    elif task == 'factor':
        expr = sympify(inputs['expression'], locals=_lcl)
        _out(factor(expr))
    elif task == 'integrate':
        expr = sympify(inputs['expression'], locals=_lcl)
        v = _lcl.get(inputs.get('variable', 'x'), x)
        _out(integrate(expr, v))
    elif task == 'differentiate':
        expr = sympify(inputs['expression'], locals=_lcl)
        v = _lcl.get(inputs.get('variable', 'x'), x)
        _out(diff(expr, v))
    else:
        print('SYMPY_ERROR:Unknown task: ' + task)
except Exception as e:
    print('SYMPY_ERROR:' + str(e))
"""

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "evaluate": {
        "required_inputs": ["expression"],
        "description": "Evaluate a mathematical expression numerically",
    },
    "simplify": {
        "required_inputs": ["expression"],
        "description": "Simplify a mathematical expression",
    },
    "solve": {
        "required_inputs": ["equation"],
        "optional_inputs": ["variable"],
        "description": "Solve an equation for a variable (default: x)",
    },
    "factor": {
        "required_inputs": ["expression"],
        "description": "Factor a polynomial expression",
    },
    "integrate": {
        "required_inputs": ["expression"],
        "optional_inputs": ["variable"],
        "description": "Symbolic integration (default variable: x)",
    },
    "differentiate": {
        "required_inputs": ["expression"],
        "optional_inputs": ["variable"],
        "description": "Symbolic differentiation (default variable: x)",
    },
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SympyEngine(BaseEngine):
    """Validate and compute using SymPy via subprocess isolation."""

    name = "sympy"

    def __init__(self, timeout: int = 5) -> None:
        self.timeout = timeout
        self._executor = SubprocessExecutor(
            default_timeout=timeout,
            max_output=64 * 1024,
        )

    # -- validate ----------------------------------------------------------

    def validate(self, latex: str) -> EngineResult:
        start = time.time()

        payload = json.dumps({"latex": latex})
        encoded = base64.b64encode(payload.encode()).decode()

        result = self._executor.run(
            [sys.executable, "-c", _SYMPY_VALIDATE_SCRIPT],
            input_data=encoded,
            timeout_s=self.timeout,
        )

        elapsed = int((time.time() - start) * 1000)
        return self._parse_validate_output(result, elapsed)

    def _parse_validate_output(
        self,
        exec_result: Any,
        elapsed: int,
    ) -> EngineResult:
        """Parse tagged output from the SymPy validate script."""
        if exec_result.timed_out:
            return EngineResult(
                engine=self.name,
                success=False,
                error=f"SymPy timed out after {self.timeout}s",
                time_ms=elapsed,
            )

        if exec_result.returncode != 0:
            return EngineResult(
                engine=self.name,
                success=False,
                error=f"SymPy exited with code {exec_result.returncode}",
                time_ms=elapsed,
            )

        tags = _parse_tags(exec_result.stdout)

        if "SYMPY_ERROR" in tags:
            return EngineResult(
                engine=self.name,
                success=False,
                error=tags["SYMPY_ERROR"],
                time_ms=elapsed,
            )

        is_valid = tags.get("SYMPY_VALID") == "1"
        return EngineResult(
            engine=self.name,
            success=True,
            is_valid=is_valid,
            simplified=tags.get("SYMPY_SIMPLIFIED"),
            original_parsed=tags.get("SYMPY_PARSED"),
            time_ms=elapsed,
        )

    # -- compute -----------------------------------------------------------

    def compute(self, request: ComputeRequest) -> ComputeResult:
        start = time.time()

        tmpl = _TEMPLATES.get(request.template)
        if tmpl is None:
            return ComputeResult(
                engine=self.name,
                success=False,
                error=f"Unknown template: {request.template}",
                error_code="UNKNOWN_TEMPLATE",
                time_ms=int((time.time() - start) * 1000),
            )

        # Check required inputs
        missing = [k for k in tmpl["required_inputs"] if k not in request.inputs]
        if missing:
            return ComputeResult(
                engine=self.name,
                success=False,
                error=f"Missing required inputs: {', '.join(missing)}",
                error_code="MISSING_INPUT",
                time_ms=int((time.time() - start) * 1000),
            )

        # Sanitize all inputs
        for key, value in request.inputs.items():
            if not _validate_input(value):
                return ComputeResult(
                    engine=self.name,
                    success=False,
                    error=f"Invalid input value for '{key}'",
                    error_code="INVALID_INPUT",
                    time_ms=int((time.time() - start) * 1000),
                )

        payload = json.dumps(
            {
                "task": request.template,
                "inputs": request.inputs,
            }
        )
        encoded = base64.b64encode(payload.encode()).decode()

        timeout_s = min(request.timeout_s, self.timeout)
        result = self._executor.run(
            [sys.executable, "-c", _SYMPY_COMPUTE_SCRIPT],
            input_data=encoded,
            timeout_s=timeout_s,
        )

        elapsed = int((time.time() - start) * 1000)
        return self._parse_compute_output(result, elapsed)

    def _parse_compute_output(
        self,
        exec_result: Any,
        elapsed: int,
    ) -> ComputeResult:
        """Parse tagged output from the SymPy compute script."""
        if exec_result.timed_out:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error=f"SymPy timed out after {self.timeout}s",
                error_code="TIMEOUT",
            )

        if exec_result.returncode != 0:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                error=f"SymPy exited with code {exec_result.returncode}",
                error_code="ENGINE_ERROR",
            )

        tags = _parse_tags(exec_result.stdout)

        if "SYMPY_ERROR" in tags:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                error=tags["SYMPY_ERROR"],
                error_code="ENGINE_ERROR",
            )

        value = tags.get("SYMPY_RESULT", "")
        return ComputeResult(
            engine=self.name,
            success=True,
            time_ms=elapsed,
            result={"value": value},
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
        )

    # -- availability / version --------------------------------------------

    def is_available(self) -> bool:
        try:
            import sympy  # noqa: F401

            return True
        except ImportError:
            return False

    def get_version(self) -> str:
        try:
            import sympy

            return sympy.__version__
        except ImportError:
            return "not installed"

    @property
    def capabilities(self) -> list[Capability]:
        return [Capability.VALIDATE, Capability.COMPUTE]

    @classmethod
    def available_templates(cls) -> dict[str, str]:
        """Return template name -> description mapping."""
        return {k: v["description"] for k, v in _TEMPLATES.items()}


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def _parse_tags(stdout: str) -> dict[str, str]:
    """Extract SYMPY_*:value tagged lines from stdout."""
    tags: dict[str, str] = {}
    for line in stdout.splitlines():
        if line.startswith("SYMPY_"):
            colon = line.index(":")
            key = line[:colon]
            value = line[colon + 1 :]
            tags[key] = value
    return tags
