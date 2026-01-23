"""Base classes for analysis passes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class Severity(Enum):
    """Finding severity levels."""
    ERROR = "error"      # Must fix - breaks continuity/consistency
    WARNING = "warning"  # Should fix - quality issue
    INFO = "info"        # Suggestion - could improve


@dataclass
class Finding:
    """A single finding from an analysis pass."""
    severity: Severity
    message: str
    location: Optional[str] = None  # e.g., "Chapter 8, line 42"
    context: Optional[str] = None   # Relevant text snippet
    suggestion: Optional[str] = None  # How to fix

    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}] {self.message}"]
        if self.location:
            parts.append(f"  Location: {self.location}")
        if self.context:
            # Truncate long context
            ctx = self.context[:200] + "..." if len(self.context) > 200 else self.context
            parts.append(f"  Context: {ctx}")
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(parts)


@dataclass
class PassResult:
    """Result of running an analysis pass."""
    pass_name: str
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None  # If pass failed to run

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def infos(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == Severity.INFO]

    @property
    def success(self) -> bool:
        return self.error is None

    def summary(self) -> str:
        if self.error:
            return f"{self.pass_name}: FAILED - {self.error}"
        return (
            f"{self.pass_name}: {len(self.errors)} errors, "
            f"{len(self.warnings)} warnings, {len(self.infos)} info"
        )


class BasePass(ABC):
    """Base class for all analysis passes."""

    name: str = "base"
    description: str = "Base analysis pass"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the pass.

        Args:
            config: Pass-specific configuration from edword.yaml
        """
        self.config = config or {}

    @abstractmethod
    def run(
        self,
        manuscript: str,
        codex: Optional[str] = None,
        **kwargs
    ) -> PassResult:
        """
        Run the analysis pass.

        Args:
            manuscript: Compiled manuscript text
            codex: Optional compiled codex text
            **kwargs: Additional pass-specific arguments

        Returns:
            PassResult with findings
        """
        pass

    def _create_result(self) -> PassResult:
        """Create an empty result for this pass."""
        return PassResult(pass_name=self.name)
