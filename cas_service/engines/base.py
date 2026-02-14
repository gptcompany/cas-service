"""Base engine abstraction for CAS validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EngineResult:
    """Result from a single CAS engine."""

    engine: str
    success: bool
    is_valid: bool | None = None
    simplified: str | None = None
    original_parsed: str | None = None
    error: str | None = None
    time_ms: int = 0


class BaseEngine(ABC):
    """Abstract base class for CAS engines."""

    name: str = "base"

    @abstractmethod
    def validate(self, latex: str) -> EngineResult:
        """Validate a preprocessed LaTeX formula."""
        ...

    def is_available(self) -> bool:
        """Check if this engine is available on the system."""
        return True

    def get_version(self) -> str:
        """Return engine version string."""
        return "unknown"
