"""Base engine abstraction for CAS validation and compute."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Capability(str, Enum):
    """Engine capability markers."""

    VALIDATE = "validate"
    COMPUTE = "compute"
    REMOTE = "remote"


@dataclass
class EngineResult:
    """Result from a single CAS engine validation."""

    engine: str
    success: bool
    is_valid: bool | None = None
    simplified: str | None = None
    original_parsed: str | None = None
    error: str | None = None
    time_ms: int = 0


@dataclass
class ComputeRequest:
    """Structured compute request for capability-based engines."""

    engine: str
    task_type: str
    template: str
    inputs: dict[str, str] = field(default_factory=dict)
    timeout_s: int = 5


@dataclass
class ComputeResult:
    """Result from a CAS compute operation."""

    engine: str
    success: bool
    time_ms: int = 0
    result: dict | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    error_code: str | None = None


class BaseEngine(ABC):
    """Abstract base class for CAS engines."""

    name: str = "base"

    @abstractmethod
    def validate(self, latex: str) -> EngineResult:
        """Validate a preprocessed LaTeX formula."""
        ...

    def compute(self, request: ComputeRequest) -> ComputeResult:
        """Execute a compute task. Override in engines that support compute."""
        return ComputeResult(
            engine=self.name,
            success=False,
            error=f"Engine '{self.name}' does not support compute",
            error_code="NOT_IMPLEMENTED",
        )

    def is_available(self) -> bool:
        """Check if this engine is available on the system."""
        return True

    def get_version(self) -> str:
        """Return engine version string."""
        return "unknown"

    @property
    def capabilities(self) -> list[Capability]:
        """Return list of capabilities this engine supports."""
        return [Capability.VALIDATE]
