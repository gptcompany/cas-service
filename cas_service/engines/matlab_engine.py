"""MATLAB CAS engine — subprocess wrapper for Symbolic Math Toolbox validation."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

from typing import Any

from cas_service.engines.base import (
    BaseEngine,
    Capability,
    ComputeRequest,
    ComputeResult,
    EngineResult,
)

logger = logging.getLogger(__name__)

# LaTeX → MATLAB syntax conversion table
_LATEX_TO_MATLAB = [
    # Fractions: \frac{a}{b} → (a)/(b)
    (
        r"\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        r"(\1)/(\2)",
    ),
    # Square root: \sqrt{x} → sqrt(x)
    (r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)"),
    # Nth root: \sqrt[n]{x} → (x)^(1/(n))
    (r"\\sqrt\[([^]]*)\]\{([^{}]*)\}", r"(\2)^(1/(\1))"),
    # Trig functions
    (r"\\sin", "sin"),
    (r"\\cos", "cos"),
    (r"\\tan", "tan"),
    (r"\\arcsin", "asin"),
    (r"\\arccos", "acos"),
    (r"\\arctan", "atan"),
    (r"\\sinh", "sinh"),
    (r"\\cosh", "cosh"),
    (r"\\tanh", "tanh"),
    # Logarithms - MATLAB uses log for natural log, log10 for base-10
    (r"\\ln", "log"),
    (r"\\log", "log10"),
    # Exponential
    (r"\\exp", "exp"),
    # Constants - MATLAB symbolic
    (r"\\pi", "pi"),
    (r"\\e(?![a-z])", "exp(1)"),
    # Greek letters (MATLAB symbolic uses sym('alpha') etc, but single letters work)
    (r"\\alpha", "alpha"),
    (r"\\beta", "beta"),
    (r"\\gamma", "gamma"),
    (r"\\delta", "delta"),
    (r"\\epsilon", "epsilon"),
    (r"\\theta", "theta"),
    (r"\\lambda", "lambda"),
    (r"\\mu", "mu"),
    (r"\\sigma", "sigma"),
    (r"\\omega", "omega"),
    (r"\\phi", "phi"),
    # Operators
    (r"\\cdot", "*"),
    (r"\\times", "*"),
    # Superscripts: x^{n} → x^(n)
    (r"\^\{([^{}]*)\}", r"^(\1)"),
    # Subscripts: remove
    (r"_\{([^{}]*)\}", r"_\1"),
    # Clean remaining braces and backslashes
    (r"\{", "("),
    (r"\}", ")"),
    (r"\\", ""),
]

# Implicit multiplication patterns
_IMPLICIT_MULT = [
    (r"(\d)([a-zA-Z])", r"\1*\2"),  # 2x → 2*x
    (r"([a-zA-Z])(\d)", r"\1*\2"),  # x2 → x*2
    (r"\)([a-zA-Z])", r")*\1"),  # )x → )*x
    (r"([a-zA-Z])\(", r"\1*("),  # x( → x*(
]


def _latex_to_matlab(latex: str) -> str:
    """Convert preprocessed LaTeX to MATLAB symbolic syntax."""
    result = latex
    for pattern, replacement in _LATEX_TO_MATLAB:
        result = re.sub(pattern, replacement, result)
    for pattern, replacement in _IMPLICIT_MULT:
        result = re.sub(pattern, replacement, result)
    return result.strip()


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS = re.compile(
    r"(system\s*\(|unix\s*\(|dos\s*\(|perl\s*\(|python\s*\("
    r"|java\s*\(|eval\s*\(|feval\s*\(|evalc\s*\("
    r"|urlread|webread|websave|fopen|fclose|fwrite|fread"
    r"|delete\s*\(|rmdir|mkdir|movefile|copyfile"
    r"|setenv|getenv|!)",
    re.IGNORECASE,
)


def _validate_input(value: str) -> bool:
    """Safety check on a MATLAB input value."""
    if not value or len(value) > 500:
        return False
    if _BLOCKED_PATTERNS.search(value):
        return False
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        return False
    return True


def _matlab_single_quoted(value: str) -> str:
    """Return a MATLAB single-quoted string literal with embedded quotes escaped."""
    return "'" + value.replace("'", "''") + "'"


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
}


class MatlabEngine(BaseEngine):
    """Validate and compute using MATLAB Symbolic Math Toolbox."""

    name = "matlab"

    def __init__(
        self,
        matlab_path: str = "matlab",
        timeout: int = 30,
    ) -> None:
        self.matlab_path = matlab_path
        self.timeout = timeout

    def validate(self, latex: str) -> EngineResult:
        start = time.time()
        try:
            matlab_expr = _latex_to_matlab(latex)
            if not matlab_expr:
                return EngineResult(
                    engine=self.name,
                    success=False,
                    error="empty expression after conversion",
                    time_ms=int((time.time() - start) * 1000),
                )

            is_equation = self._is_equation(latex)

            if is_equation:
                parts = latex.split("=", 1)
                lhs = _latex_to_matlab(parts[0].strip())
                rhs = _latex_to_matlab(parts[1].strip())
                matlab_code = (
                    "syms x y z t real;\n"
                    f"lhs = {lhs};\n"
                    f"rhs = {rhs};\n"
                    "diff_expr = simplify(lhs - rhs);\n"
                    "disp(['MATLAB_SIMPLIFIED: ', char(diff_expr)]);\n"
                    "is_zero = isequal(diff_expr, sym(0));\n"
                    "disp(['MATLAB_IS_IDENTITY: ', num2str(is_zero)]);\n"
                )
            else:
                matlab_code = (
                    "syms x y z t real;\n"
                    f"expr = {matlab_expr};\n"
                    "simplified_expr = simplify(expr);\n"
                    "disp(['MATLAB_SIMPLIFIED: ', char(simplified_expr)]);\n"
                )

            output = self._run_matlab(matlab_code)

            simplified = None
            is_valid = None

            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("MATLAB_SIMPLIFIED:"):
                    simplified = line.replace("MATLAB_SIMPLIFIED:", "").strip()
                elif line.startswith("MATLAB_IS_IDENTITY:"):
                    val = line.replace("MATLAB_IS_IDENTITY:", "").strip()
                    is_valid = val == "1" or val.lower() == "true"

            if is_equation:
                if is_valid is None and simplified is not None:
                    is_valid = simplified == "0"
            else:
                if simplified is not None:
                    is_valid = True

            success = simplified is not None
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name,
                success=success,
                is_valid=is_valid,
                simplified=simplified,
                original_parsed=matlab_expr,
                error=None if success else "no output from MATLAB",
                time_ms=elapsed,
            )

        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name,
                success=False,
                error=f"timeout ({self.timeout}s)",
                time_ms=elapsed,
            )
        except FileNotFoundError:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name,
                success=False,
                error="MATLAB binary not found",
                time_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name,
                success=False,
                error=f"matlab error: {e}",
                time_ms=elapsed,
            )

    def _run_matlab(self, code: str) -> str:
        """Execute MATLAB code via temp file and return stdout."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".m",
            delete=False,
        ) as f:
            f.write(code)
            temp_script = f.name

        try:
            run_cmd = f"run('{temp_script}')"
            result = subprocess.run(
                [self.matlab_path, "-batch", run_cmd],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0 and not result.stdout.strip():
                stderr = result.stderr.strip()
                raise RuntimeError(
                    f"non-zero exit ({result.returncode}): {stderr[:200]}"
                )
            return result.stdout
        finally:
            os.unlink(temp_script)

    def _is_equation(self, expr: str) -> bool:
        """Check for standalone = (not == or !=)."""
        return bool(re.search(r"(?<![<>!:=])=(?!=)", expr))

    def is_available(self) -> bool:
        if os.path.isabs(self.matlab_path):
            return os.path.isfile(self.matlab_path) and os.access(
                self.matlab_path, os.X_OK
            )
        return shutil.which(self.matlab_path) is not None

    # -- compute -----------------------------------------------------------

    def compute(self, request: ComputeRequest) -> ComputeResult:
        start = time.time()

        if not self.is_available():
            return ComputeResult(
                engine=self.name,
                success=False,
                error="MATLAB binary not found",
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

        matlab_code = self._build_compute_code(request.template, request.inputs)

        try:
            output = self._run_matlab(matlab_code)
            elapsed = int((time.time() - start) * 1000)
            return self._parse_compute_output(output, elapsed)
        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - start) * 1000)
            return ComputeResult(
                engine=self.name,
                success=False,
                error=f"MATLAB timed out after {self.timeout}s",
                error_code="TIMEOUT",
                time_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return ComputeResult(
                engine=self.name,
                success=False,
                error=f"MATLAB error: {e}",
                error_code="ENGINE_ERROR",
                time_ms=elapsed,
            )

    def _build_compute_code(self, template: str, inputs: dict[str, str]) -> str:
        """Generate MATLAB script for a compute template."""
        header = "syms x y z t real;\n"

        if template == "evaluate":
            expr = inputs["expression"]
            expr_literal = _matlab_single_quoted(expr)
            return (
                header
                + f"expr = str2sym({expr_literal});\n"
                + "result = simplify(expr);\n"
                + "if isempty(symvar(result))\n"
                + "    result = vpa(result);\n"
                + "end\n"
                + "disp(['MATLAB_RESULT:', char(string(result))]);\n"
            )
        elif template == "simplify":
            expr = inputs["expression"]
            return (
                header
                + f"expr = {expr};\n"
                + "result = simplify(expr);\n"
                + "disp(['MATLAB_RESULT:', char(result)]);\n"
            )
        elif template == "solve":
            equation = inputs["equation"]
            variable = inputs.get("variable", "x")
            return (
                header
                + f"expr = {equation};\n"
                + f"result = solve(expr, {variable});\n"
                + "disp(['MATLAB_RESULT:', char(result)]);\n"
            )
        elif template == "factor":
            expr = inputs["expression"]
            return (
                header
                + f"expr = {expr};\n"
                + "result = factor(expr);\n"
                + "disp(['MATLAB_RESULT:', char(result)]);\n"
            )
        else:
            return f"disp('MATLAB_ERROR:Unknown template: {template}');\n"

    def _parse_compute_output(self, output: str, elapsed: int) -> ComputeResult:
        """Parse tagged output from MATLAB compute script."""
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("MATLAB_RESULT:"):
                value = line[len("MATLAB_RESULT:") :].strip()
                return ComputeResult(
                    engine=self.name,
                    success=True,
                    time_ms=elapsed,
                    result={"value": value},
                    stdout=output,
                )
            elif line.startswith("MATLAB_ERROR:"):
                error_msg = line[len("MATLAB_ERROR:") :].strip()
                return ComputeResult(
                    engine=self.name,
                    success=False,
                    time_ms=elapsed,
                    error=error_msg,
                    error_code="ENGINE_ERROR",
                    stdout=output,
                )

        return ComputeResult(
            engine=self.name,
            success=False,
            time_ms=elapsed,
            error="No result from MATLAB",
            error_code="ENGINE_ERROR",
            stdout=output,
        )

    # -- availability / version --------------------------------------------

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                [self.matlab_path, "-batch", "disp(version)"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if re.match(r"\d+\.\d+", line):
                    return f"MATLAB {line}"
            return "MATLAB (version unknown)"
        except Exception:
            return "MATLAB (unavailable)"

    @property
    def capabilities(self) -> list[Capability]:
        return [Capability.VALIDATE, Capability.COMPUTE]

    @classmethod
    def available_templates(cls) -> dict[str, str]:
        """Return template name -> description mapping."""
        return {k: v["description"] for k, v in _TEMPLATES.items()}
