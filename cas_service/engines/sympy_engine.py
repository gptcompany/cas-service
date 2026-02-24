"""SymPy CAS engine — parse_latex + simplify validation."""

from __future__ import annotations

import logging
import signal
import threading
import time

from cas_service.engines.base import BaseEngine, EngineResult

logger = logging.getLogger(__name__)


class _Timeout(Exception):
    pass


def _timeout_handler(signum: int, frame: object) -> None:
    raise _Timeout()


def _in_main_thread() -> bool:
    """Check if current thread is the main thread (signal only works there)."""
    return threading.current_thread() is threading.main_thread()


class SympyEngine(BaseEngine):
    """Validate LaTeX formulas using SymPy's parse_latex and simplify."""

    name = "sympy"

    def __init__(self, timeout: int = 5) -> None:
        self.timeout = timeout

    def validate(self, latex: str) -> EngineResult:
        start = time.time()
        try:
            expr = self._parse(latex)
            original = str(expr)
            simplified, is_valid = self._evaluate(expr, latex)
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name,
                success=True,
                is_valid=is_valid,
                simplified=str(simplified),
                original_parsed=original,
                time_ms=elapsed,
            )
        except _Timeout:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name, success=False,
                error="timeout", time_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return EngineResult(
                engine=self.name, success=False,
                error=f"parse failed: {e}", time_ms=elapsed,
            )

    def _parse(self, latex: str) -> object:
        """Parse LaTeX with ANTLR backend, fallback to Lark."""
        if _in_main_thread():
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(self.timeout)
        try:
            from sympy.parsing.latex import parse_latex
            try:
                return parse_latex(latex)
            except Exception:
                return parse_latex(latex, backend="lark")
        finally:
            if _in_main_thread():
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    def _evaluate(self, expr: object, latex: str) -> tuple[object, bool]:
        """Simplify expression. For equations, check lhs == rhs."""
        import sympy

        if _in_main_thread():
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(self.timeout)
        try:
            if isinstance(expr, sympy.Eq):
                diff = sympy.simplify(expr.lhs - expr.rhs)
                return diff, diff == 0
            elif self._is_equation_str(latex):
                parts = self._split_equation(latex)
                if parts:
                    from sympy.parsing.latex import parse_latex
                    lhs = parse_latex(parts[0])
                    rhs = parse_latex(parts[1])
                    diff = sympy.simplify(lhs - rhs)
                    return diff, diff == 0
            simplified = sympy.simplify(expr)
            return simplified, True
        finally:
            if _in_main_thread():
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    def _is_equation_str(self, latex: str) -> bool:
        """Check if latex contains a standalone = sign (not <=, >=, !=)."""
        import re
        return bool(re.search(r"(?<![<>!\\])=(?!=)", latex))

    def _split_equation(self, latex: str) -> tuple[str, str] | None:
        """Split on standalone = sign."""
        import re
        match = re.search(r"(?<![<>!\\])=(?!=)", latex)
        if match:
            lhs = latex[:match.start()].strip()
            rhs = latex[match.end():].strip()
            if lhs and rhs:
                return lhs, rhs
        return None

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
