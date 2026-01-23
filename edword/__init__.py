"""Edword - AI-powered editorial analysis for book manuscripts."""

__version__ = "0.1.0"

from .config import EdwordConfig, load_config
from .discovery import discover_project, ProjectStructure, BookInfo
from .loaders import compile_manuscript, load_codex
from .passes import BasePass, Finding, PassResult, Severity, run_passes

__all__ = [
    "EdwordConfig",
    "load_config",
    "discover_project",
    "ProjectStructure",
    "BookInfo",
    "compile_manuscript",
    "load_codex",
    "BasePass",
    "Finding",
    "PassResult",
    "Severity",
    "run_passes",
]
