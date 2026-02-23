"""MATLAB CAS engine — subprocess wrapper for Symbolic Math Toolbox validation."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time

from cas_service.engines.base import BaseEngine, EngineResult

logger = logging.getLogger(__name__)

# LaTeX → MATLAB syntax conversion table
_LATEX_TO_MATLAB = [
    # Fractions: \frac{a}{b} → (a)/(b)
    (r"\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
     r"(\1)/(\2)"),
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
    (r"(\d)([a-zA-Z])", r"\1*\2"),      # 2x → 2*x
    (r"([a-zA-Z])(\d)", r"\1*\2"),      # x2 → x*2
    (r"\)([a-zA-Z])", r")*\1"),          # )x → )*x
    (r"([a-zA-Z])\(", r"\1*("),          # x( → x*(
]


def _latex_to_matlab(latex: str) -> str:
    """Convert preprocessed LaTeX to MATLAB symbolic syntax."""
    result = latex
    for pattern, replacement in _LATEX_TO_MATLAB:
        result = re.sub(pattern, replacement, result)
    for pattern, replacement in _IMPLICIT_MULT:
        result = re.sub(pattern, replacement, result)
    return result.strip()


class MatlabEngine(BaseEngine):
    """Validate LaTeX formulas using MATLAB Symbolic Math Toolbox."""

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
                    engine=self.name, success=False,
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
                engine=self.name, success=False,
                error=f"timeout ({self.timeout}s)", time_ms=elapsed,
            )
        except FileNotFoundError:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name, success=False,
                error="MATLAB binary not found", time_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name, success=False,
                error=f"matlab error: {e}", time_ms=elapsed,
            )

    def _run_matlab(self, code: str) -> str:
        """Execute MATLAB code via temp file and return stdout."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".m", delete=False,
        ) as f:
            f.write(code)
            temp_script = f.name

        try:
            run_cmd = f"run('{temp_script}')"
            result = subprocess.run(
                [self.matlab_path, "-batch", run_cmd],
                capture_output=True, text=True, timeout=self.timeout,
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
        return os.path.isfile(self.matlab_path)

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                [self.matlab_path, "-batch", "disp(version)"],
                capture_output=True, text=True, timeout=15,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if re.match(r"\d+\.\d+", line):
                    return f"MATLAB {line}"
            return "MATLAB (version unknown)"
        except Exception:
            return "MATLAB (unavailable)"
