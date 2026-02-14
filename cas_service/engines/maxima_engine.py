"""Maxima CAS engine — subprocess wrapper for formula validation."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time

from cas_service.engines.base import BaseEngine, EngineResult

logger = logging.getLogger(__name__)

# LaTeX → Maxima syntax conversion table
_LATEX_TO_MAXIMA = [
    # Fractions: \frac{a}{b} → (a)/(b)
    (r"\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
     r"(\1)/(\2)"),
    # Square root: \sqrt{x} → sqrt(x)
    (r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)"),
    # Nth root: \sqrt[n]{x} → x^(1/n)
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
    # Log/exp
    (r"\\ln", "log"),
    (r"\\log", "log"),
    (r"\\exp", "exp"),
    # Greek letters
    (r"\\alpha", "%alpha"),
    (r"\\beta", "%beta"),
    (r"\\gamma", "%gamma"),
    (r"\\delta", "%delta"),
    (r"\\epsilon", "%epsilon"),
    (r"\\theta", "%theta"),
    (r"\\lambda", "%lambda"),
    (r"\\mu", "%mu"),
    (r"\\nu", "%nu"),
    (r"\\pi", "%pi"),
    (r"\\sigma", "%sigma"),
    (r"\\tau", "%tau"),
    (r"\\omega", "%omega"),
    (r"\\phi", "%phi"),
    (r"\\psi", "%psi"),
    (r"\\rho", "%rho"),
    (r"\\xi", "%xi"),
    (r"\\zeta", "%zeta"),
    # Infinity
    (r"\\infty", "inf"),
    # Superscripts: x^{n} → x^n (remove braces)
    (r"\^\{([^{}]*)\}", r"^(\1)"),
    # Subscripts: x_{i} → x_i (remove braces)
    (r"_\{([^{}]*)\}", r"_\1"),
    # Summation: \sum_{i=a}^{b} → sum(..., i, a, b) handled separately
    # Remaining backslashes
    (r"\\", ""),
]


def _latex_to_maxima(latex: str) -> str:
    """Convert preprocessed LaTeX to Maxima syntax."""
    result = latex
    for pattern, replacement in _LATEX_TO_MAXIMA:
        result = re.sub(pattern, replacement, result)
    return result.strip()


class MaximaEngine(BaseEngine):
    """Validate LaTeX formulas using Maxima subprocess."""

    name = "maxima"

    def __init__(
        self,
        maxima_path: str = "/usr/bin/maxima",
        timeout: int = 10,
    ) -> None:
        self.maxima_path = maxima_path
        self.timeout = timeout

    def validate(self, latex: str) -> EngineResult:
        start = time.time()
        try:
            maxima_expr = _latex_to_maxima(latex)
            if not maxima_expr:
                return EngineResult(
                    engine=self.name, success=False,
                    error="empty expression after conversion",
                    time_ms=int((time.time() - start) * 1000),
                )

            is_equation = self._is_equation(maxima_expr)

            if is_equation:
                parts = maxima_expr.split("=", 1)
                lhs, rhs = parts[0].strip(), parts[1].strip()
                cmd = f"ratsimp({lhs} - ({rhs}));"
            else:
                cmd = f"ratsimp({maxima_expr});"

            output = self._run_maxima(cmd)

            if is_equation:
                is_valid = output.strip() == "0"
                simplified = output.strip()
            else:
                is_valid = True
                simplified = output.strip()

            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name,
                success=True,
                is_valid=is_valid,
                simplified=simplified,
                original_parsed=maxima_expr,
                time_ms=elapsed,
            )

        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name, success=False,
                error="timeout", time_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name, success=False,
                error=f"maxima error: {e}", time_ms=elapsed,
            )

    def _run_maxima(self, command: str) -> str:
        """Execute a Maxima command and return cleaned output."""
        result = subprocess.run(
            [self.maxima_path, "--very-quiet", "--batch-string", command],
            capture_output=True, text=True, timeout=self.timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"non-zero exit ({result.returncode}): {stderr}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("no output")

        # Maxima outputs lines like "(%o1) result" — extract the result
        lines = output.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            # Skip empty and input echo lines
            if not line or line.startswith("(%i"):
                continue
            # Remove output label like (%o1)
            match = re.match(r"\(%o\d+\)\s*(.*)", line)
            if match:
                return match.group(1).strip()
            return line
        raise RuntimeError("no parseable output")

    def _is_equation(self, expr: str) -> bool:
        """Check for standalone = in Maxima expression."""
        return bool(re.search(r"(?<![<>!:])=(?!=)", expr))

    def is_available(self) -> bool:
        return shutil.which(self.maxima_path) is not None

    def get_version(self) -> str:
        try:
            result = subprocess.run(
                [self.maxima_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip().split("\n")[0]
        except Exception:
            return "unknown"
