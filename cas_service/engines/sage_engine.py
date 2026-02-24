"""SageMath engine — validate + compute via SubprocessExecutor."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
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
# LaTeX → Sage expression conversion
# ---------------------------------------------------------------------------

_LATEX_TO_SAGE: list[tuple[str, str]] = [
    (r"\\frac\{([^}]+)\}\{([^}]+)\}", r"((\1)/(\2))"),
    (r"\\sqrt\[([^\]]+)\]\{([^}]+)\}", r"(\2)^(1/(\1))"),
    (r"\\sqrt\{([^}]+)\}", r"sqrt(\1)"),
    (r"\\sin", "sin"),
    (r"\\cos", "cos"),
    (r"\\tan", "tan"),
    (r"\\arcsin", "arcsin"),
    (r"\\arccos", "arccos"),
    (r"\\arctan", "arctan"),
    (r"\\ln", "log"),
    (r"\\log", "log"),
    (r"\\exp", "exp"),
    (r"\\pi", "pi"),
    (r"\\infty", "oo"),
    (r"\\alpha", "alpha"),
    (r"\\beta", "beta"),
    (r"\\gamma", "gamma"),
    (r"\\theta", "theta"),
    (r"\\phi", "phi"),
    (r"\\cdot", "*"),
    (r"\\times", "*"),
    (r"\\div", "/"),
    (r"\^{([^}]+)}", r"^(\1)"),
    (r"\\left", ""),
    (r"\\right", ""),
    (r"\\,", " "),
    (r"\\;", " "),
    (r"\\!", ""),
    (r"\\quad", " "),
]

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
    """Safety check on a Sage input value."""
    if not value or len(value) > 500:
        return False
    if _BLOCKED_PATTERNS.search(value):
        return False
    if "\x00" in value:
        return False
    return True


def _latex_to_sage(latex: str) -> str:
    """Convert preprocessed LaTeX to a Sage-compatible expression string."""
    result = latex
    for pattern, replacement in _LATEX_TO_SAGE:
        result = re.sub(pattern, replacement, result)
    # Implicit multiplication: 2x → 2*x, )( → )*(
    result = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", result)
    result = re.sub(r"\)(\()", r")*\1", result)
    result = re.sub(r"\)([a-zA-Z])", r")*\1", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Sage script templates (executed via `sage --python`)
# ---------------------------------------------------------------------------

_SAGE_VALIDATE_SCRIPT = """\
import json, sys, base64
from sage.all import *
var('x y z t a b c n k m p q r s u v w')
_lcl = {str(v): v for v in [x,y,z,t,a,b,c,n,k,m,p,q,r,s,u,v,w]}
data = json.loads(base64.b64decode(sys.stdin.read().strip()).decode())
expr_str = data['expression']
is_equation = data.get('is_equation', False)
try:
    if is_equation:
        parts = expr_str.split('==')
        if len(parts) != 2:
            raise ValueError('Expected exactly one == in equation')
        lhs = sage_eval(parts[0].strip(), locals=_lcl)
        rhs = sage_eval(parts[1].strip(), locals=_lcl)
        diff_expr = simplify(lhs - rhs)
        is_valid = bool(diff_expr == 0)
        simplified = str(simplify(lhs)) + ' == ' + str(simplify(rhs))
        parsed = str(lhs) + ' == ' + str(rhs)
    else:
        expr = sage_eval(expr_str, locals=_lcl)
        simplified = str(simplify(expr))
        parsed = str(expr)
        is_valid = True
    print('SAGE_VALID:' + ('1' if is_valid else '0'))
    print('SAGE_SIMPLIFIED:' + simplified)
    print('SAGE_PARSED:' + parsed)
except Exception as e:
    print('SAGE_VALID:0')
    print('SAGE_ERROR:' + str(e))
"""

_SAGE_COMPUTE_SCRIPT = """\
import json, sys, base64
from sage.all import *
var('x y z t a b c n k m p q r s u v w')
_lcl = {str(v): v for v in [x,y,z,t,a,b,c,n,k,m,p,q,r,s,u,v,w]}
data = json.loads(base64.b64decode(sys.stdin.read().strip()).decode())
task = data['task']
inputs = data['inputs']
def _out(val):
    print('SAGE_RESULT:' + str(val).replace('\\n', ' '))
try:
    if task == 'evaluate':
        _out(sage_eval(inputs['expression'], locals=_lcl))
    elif task == 'simplify':
        expr = sage_eval(inputs['expression'], locals=_lcl)
        _out(simplify(expr))
    elif task == 'solve':
        expr = sage_eval(inputs['equation'], locals=_lcl)
        v = _lcl.get(inputs.get('variable', 'x'), x)
        _out(solve(expr, v))
    elif task == 'factor':
        expr = sage_eval(inputs['expression'], locals=_lcl)
        _out(factor(expr))
    elif task == 'integrate':
        expr = sage_eval(inputs['expression'], locals=_lcl)
        v = _lcl.get(inputs.get('variable', 'x'), x)
        _out(integrate(expr, v))
    elif task == 'differentiate':
        expr = sage_eval(inputs['expression'], locals=_lcl)
        v = _lcl.get(inputs.get('variable', 'x'), x)
        _out(diff(expr, v))
    elif task == 'matrix_rank':
        m = sage_eval(inputs['matrix'], locals=_lcl)
        if hasattr(m, 'rank'):
            _out(m.rank())
        else:
            _out(matrix(m).rank())
    elif task == 'latex_to_sage':
        _out(sage_eval(inputs['expression'], locals=_lcl))
    elif task == 'group_order':
        g = sage_eval(inputs['group_expr'], locals=_lcl)
        _out(g.order())
    elif task == 'is_abelian':
        g = sage_eval(inputs['group_expr'], locals=_lcl)
        _out(g.is_abelian())
    elif task == 'center_size':
        g = sage_eval(inputs['group_expr'], locals=_lcl)
        _out(g.center().order())
    else:
        print('SAGE_ERROR:Unknown task: ' + task)
except Exception as e:
    print('SAGE_ERROR:' + str(e))
"""


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "evaluate": {
        "required_inputs": ["expression"],
        "description": "Evaluate a mathematical expression",
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
    "matrix_rank": {
        "required_inputs": ["matrix"],
        "description": "Compute the rank of a matrix",
    },
    "latex_to_sage": {
        "required_inputs": ["expression"],
        "description": "Parse LaTeX and return Sage representation",
    },
    "group_order": {
        "required_inputs": ["group_expr"],
        "description": "Compute the order (size) of a group",
    },
    "is_abelian": {
        "required_inputs": ["group_expr"],
        "description": "Check if a group is abelian",
    },
    "center_size": {
        "required_inputs": ["group_expr"],
        "description": "Compute the size of the center of a group",
    },
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SageEngine(BaseEngine):
    """SageMath symbolic computation engine — validate + compute via subprocess."""

    name = "sage"

    def __init__(
        self,
        sage_path: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.sage_path = sage_path or os.environ.get("CAS_SAGE_PATH", "sage")
        self.timeout = timeout
        self._executor = SubprocessExecutor(
            default_timeout=timeout, max_output=64 * 1024,
        )
        self._available: bool | None = None
        self._version: str = "unknown"

    # -- validate ----------------------------------------------------------

    def validate(self, latex: str) -> EngineResult:
        start = time.time()

        if not self.is_available():
            return EngineResult(
                engine=self.name,
                success=False,
                error="SageMath binary not found",
                time_ms=int((time.time() - start) * 1000),
            )

        sage_expr = _latex_to_sage(latex)
        if not _validate_input(sage_expr):
            return EngineResult(
                engine=self.name,
                success=False,
                error="Expression rejected by input validation",
                time_ms=int((time.time() - start) * 1000),
            )

        # Detect equations: single = (not ==) → convert to ==
        is_equation = False
        if "=" in sage_expr:
            # Already ==
            if "==" in sage_expr:
                is_equation = True
            # Single = but not <=, >=, !=
            elif re.search(r"(?<![<>!=])=(?!=)", sage_expr):
                sage_expr = re.sub(r"(?<![<>!=])=(?!=)", "==", sage_expr)
                is_equation = True

        payload = json.dumps({
            "expression": sage_expr,
            "is_equation": is_equation,
        })
        encoded = base64.b64encode(payload.encode()).decode()

        result = self._executor.run(
            [self.sage_path, "--python", "-c", _SAGE_VALIDATE_SCRIPT],
            input_data=encoded,
            timeout_s=self.timeout,
        )

        elapsed = int((time.time() - start) * 1000)
        return self._parse_validate_output(result.stdout, result.stderr, elapsed, result)

    def _parse_validate_output(
        self, stdout: str, stderr: str, elapsed: int, exec_result: Any,
    ) -> EngineResult:
        """Parse tagged output from the Sage validate script."""
        if exec_result.timed_out:
            return EngineResult(
                engine=self.name,
                success=False,
                error=f"SageMath timed out after {self.timeout}s",
                time_ms=elapsed,
            )

        if exec_result.returncode != 0:
            return EngineResult(
                engine=self.name,
                success=False,
                error=f"SageMath exited with code {exec_result.returncode}",
                time_ms=elapsed,
            )

        tags = _parse_tags(stdout)

        if "SAGE_ERROR" in tags:
            return EngineResult(
                engine=self.name,
                success=False,
                error=tags["SAGE_ERROR"],
                time_ms=elapsed,
            )

        is_valid = tags.get("SAGE_VALID") == "1"
        return EngineResult(
            engine=self.name,
            success=True,
            is_valid=is_valid,
            simplified=tags.get("SAGE_SIMPLIFIED"),
            original_parsed=tags.get("SAGE_PARSED"),
            time_ms=elapsed,
        )

    # -- compute -----------------------------------------------------------

    def compute(self, request: ComputeRequest) -> ComputeResult:
        start = time.time()

        if not self.is_available():
            return ComputeResult(
                engine=self.name,
                success=False,
                error="SageMath binary not found",
                error_code="ENGINE_UNAVAILABLE",
                time_ms=int((time.time() - start) * 1000),
            )

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
        missing = [
            k for k in tmpl["required_inputs"] if k not in request.inputs
        ]
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

        payload = json.dumps({
            "task": request.template,
            "inputs": request.inputs,
        })
        encoded = base64.b64encode(payload.encode()).decode()

        timeout_s = min(request.timeout_s, self.timeout)
        result = self._executor.run(
            [self.sage_path, "--python", "-c", _SAGE_COMPUTE_SCRIPT],
            input_data=encoded,
            timeout_s=timeout_s,
        )

        elapsed = int((time.time() - start) * 1000)
        return self._parse_compute_output(result, elapsed)

    def _parse_compute_output(
        self, exec_result: Any, elapsed: int,
    ) -> ComputeResult:
        """Parse tagged output from the Sage compute script."""
        if exec_result.timed_out:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error=f"SageMath timed out after {self.timeout}s",
                error_code="TIMEOUT",
            )

        if exec_result.returncode != 0:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                error=f"SageMath exited with code {exec_result.returncode}",
                error_code="ENGINE_ERROR",
            )

        tags = _parse_tags(exec_result.stdout)

        if "SAGE_ERROR" in tags:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                error=tags["SAGE_ERROR"],
                error_code="ENGINE_ERROR",
            )

        value = tags.get("SAGE_RESULT", "")
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
        if self._available is not None:
            return self._available
        self._available = shutil.which(self.sage_path) is not None
        if self._available:
            self._detect_version()
        return self._available

    def _detect_version(self) -> None:
        try:
            result = self._executor.run(
                [self.sage_path, "--version"],
                timeout_s=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Output: "SageMath version 9.5, ..."
                self._version = result.stdout.strip().split("\n")[0]
        except Exception:
            pass

    def get_version(self) -> str:
        if self._available is None:
            self.is_available()
        return self._version

    @property
    def availability_reason(self) -> str | None:
        """Return reason if unavailable, None if available."""
        if not self.is_available():
            return f"sage binary not found at '{self.sage_path}'"
        return None

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
    """Extract SAGE_*:value tagged lines from stdout."""
    tags: dict[str, str] = {}
    for line in stdout.splitlines():
        if line.startswith("SAGE_"):
            colon = line.index(":")
            key = line[:colon]
            value = line[colon + 1:]
            tags[key] = value
    return tags
