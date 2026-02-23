"""GAP engine for computational group theory via template-based compute."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
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

# Maximum stdout/stderr captured from GAP subprocess (bytes)
_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

# Each template maps to a GAP code generator function.
# Input keys are validated before code generation.

def _tmpl_group_order(inputs: dict[str, str]) -> str:
    """Compute the order of a group expression."""
    group_expr = inputs["group_expr"]
    return f"Print(Size({group_expr}));;\n"


def _tmpl_is_abelian(inputs: dict[str, str]) -> str:
    """Check if a group expression is abelian."""
    group_expr = inputs["group_expr"]
    return f"Print(IsAbelian({group_expr}));;\n"


def _tmpl_center_size(inputs: dict[str, str]) -> str:
    """Compute the size of the center of a group."""
    group_expr = inputs["group_expr"]
    return f"Print(Size(Center({group_expr})));;\n"


_TEMPLATES: dict[str, dict[str, Any]] = {
    "group_order": {
        "required_inputs": ["group_expr"],
        "generate": _tmpl_group_order,
        "description": "Compute the order (size) of a group",
    },
    "is_abelian": {
        "required_inputs": ["group_expr"],
        "generate": _tmpl_is_abelian,
        "description": "Check if a group is abelian",
    },
    "center_size": {
        "required_inputs": ["group_expr"],
        "generate": _tmpl_center_size,
        "description": "Compute the size of the center of a group",
    },
}

# Allowlisted GAP identifiers for input sanitization
_SAFE_GAP_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\("
    r"|^[0-9]+$"
    r"|^[A-Za-z_][A-Za-z0-9_, ()\[\]]*\)$"
)

# Block obvious injection attempts
_BLOCKED_PATTERNS = re.compile(
    r"(Exec|IO_|Process|Runtime|System|InputTextFile|OutputTextFile"
    r"|ReadAll|PrintTo|AppendTo|QUIT|Filename|DirectoryCurrent"
    r"|DirectoryContents|Concatenation.*Filename)",
    re.IGNORECASE,
)


def _validate_input(value: str) -> bool:
    """Basic safety check on a GAP input value."""
    if not value or len(value) > 200:
        return False
    if _BLOCKED_PATTERNS.search(value):
        return False
    # Allow common GAP expressions: function calls, numbers, identifiers
    if ";" in value or "\n" in value:
        return False
    return True


class GapEngine(BaseEngine):
    """GAP computational algebra engine — template-only compute MVP."""

    name = "gap"

    def __init__(
        self,
        gap_path: str | None = None,
        timeout: int = 10,
    ) -> None:
        self.gap_path = gap_path or os.environ.get("CAS_GAP_PATH", "gap")
        self.timeout = timeout
        self._available: bool | None = None
        self._version: str = "unknown"

    def validate(self, latex: str) -> EngineResult:
        """GAP is not a formula validator — return explicit non-support."""
        return EngineResult(
            engine=self.name,
            success=False,
            error="GAP does not support LaTeX formula validation",
        )

    def compute(self, request: ComputeRequest) -> ComputeResult:
        start = time.time()

        if not self.is_available():
            return ComputeResult(
                engine=self.name,
                success=False,
                error="GAP binary not found",
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

        # Validate required inputs
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

        # Sanitize inputs
        for key, value in request.inputs.items():
            if not _validate_input(value):
                return ComputeResult(
                    engine=self.name,
                    success=False,
                    error=f"Invalid input value for '{key}'",
                    error_code="INVALID_INPUT",
                    time_ms=int((time.time() - start) * 1000),
                )

        # Generate GAP code
        gap_code = tmpl["generate"](request.inputs)

        # Execute
        timeout_s = min(request.timeout_s, self.timeout)
        return self._run_gap(gap_code, timeout_s, start)

    def _run_gap(
        self, code: str, timeout_s: int, start: float,
    ) -> ComputeResult:
        """Execute GAP code via subprocess."""
        try:
            proc = subprocess.run(
                [self.gap_path, "-q", "-b"],
                input=code,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )

            stdout = proc.stdout[:_MAX_OUTPUT_BYTES]
            stderr = proc.stderr[:_MAX_OUTPUT_BYTES]
            elapsed = int((time.time() - start) * 1000)

            if proc.returncode != 0:
                return ComputeResult(
                    engine=self.name,
                    success=False,
                    time_ms=elapsed,
                    stdout=stdout,
                    stderr=stderr,
                    error=f"GAP exited with code {proc.returncode}",
                    error_code="ENGINE_ERROR",
                )

            # Parse output — trim whitespace, extract value
            value = stdout.strip()
            return ComputeResult(
                engine=self.name,
                success=True,
                time_ms=elapsed,
                result={"value": value},
                stdout=stdout,
                stderr=stderr,
            )

        except subprocess.TimeoutExpired:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=int((time.time() - start) * 1000),
                error=f"GAP timed out after {timeout_s}s",
                error_code="TIMEOUT",
            )
        except FileNotFoundError:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=int((time.time() - start) * 1000),
                error="GAP binary not found",
                error_code="ENGINE_UNAVAILABLE",
            )
        except Exception as exc:
            logger.exception("GAP execution error")
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=int((time.time() - start) * 1000),
                error=str(exc),
                error_code="ENGINE_ERROR",
            )

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        self._available = shutil.which(self.gap_path) is not None
        if self._available:
            self._detect_version()
        return self._available

    def _detect_version(self) -> None:
        try:
            proc = subprocess.run(
                [self.gap_path, "-q", "-b"],
                input='Print(GAPInfo.Version);;\n',
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                self._version = proc.stdout.strip()
        except Exception:
            pass

    def get_version(self) -> str:
        if self._available is None:
            self.is_available()
        return self._version

    @property
    def capabilities(self) -> list[Capability]:
        return [Capability.COMPUTE]

    @classmethod
    def available_templates(cls) -> dict[str, str]:
        """Return template name -> description mapping."""
        return {k: v["description"] for k, v in _TEMPLATES.items()}
