"""Analysis passes for editorial review."""

from typing import List, Dict, Any, Optional

from .base import BasePass, Finding, PassResult, Severity
from ..config import EdwordConfig, get_pass_config
from ..index.schema import AccumulatedIndex

__all__ = ["BasePass", "Finding", "PassResult", "Severity", "run_passes", "get_pass"]

# Registry of available passes
_PASS_REGISTRY: Dict[str, type] = {}


def register_pass(pass_class: type) -> type:
    """Decorator to register a pass class."""
    _PASS_REGISTRY[pass_class.name] = pass_class
    return pass_class


def get_pass(name: str) -> Optional[type]:
    """Get a pass class by name."""
    return _PASS_REGISTRY.get(name)


def list_passes() -> List[str]:
    """List all registered pass names."""
    return list(_PASS_REGISTRY.keys())


def run_passes(
    pass_names: List[str],
    manuscript: str,
    codex: Optional[str] = None,
    config: Optional[EdwordConfig] = None,
    verbose: bool = False,
    index: Optional[AccumulatedIndex] = None,
) -> List[PassResult]:
    """
    Run multiple analysis passes.

    Args:
        pass_names: Names of passes to run
        manuscript: Compiled manuscript text
        codex: Optional compiled codex text
        config: Edword configuration
        verbose: Show verbose output
        index: Optional accumulated index for index-based passes

    Returns:
        List of PassResult objects
    """
    results = []

    for name in pass_names:
        pass_class = get_pass(name)

        if pass_class is None:
            # Pass not found - create error result
            result = PassResult(pass_name=name, error=f"Pass '{name}' not found")
            results.append(result)
            continue

        # Get pass-specific config
        pass_config = {}
        if config:
            pc = get_pass_config(config, name)
            pass_config = pc.options

        # Instantiate and run the pass
        try:
            pass_instance = pass_class(config=pass_config)

            if verbose:
                import sys
                print(f"Running pass: {name}...", file=sys.stderr)

            result = pass_instance.run(
                manuscript=manuscript,
                codex=codex,
                config=config,
                verbose=verbose,
                index=index,
            )
            results.append(result)

        except Exception as e:
            result = PassResult(pass_name=name, error=str(e))
            results.append(result)

    return results


# Import passes to trigger registration
# These imports are at the bottom to avoid circular imports
try:
    from . import continuity
except ImportError:
    pass  # Pass not yet implemented

try:
    from . import codex_validation
except ImportError:
    pass  # Pass not yet implemented

try:
    from . import character_codex
except ImportError:
    pass  # Pass not yet implemented

try:
    from . import continuity_index
except ImportError:
    pass  # Pass not yet implemented

try:
    from . import codex_validation_index
except ImportError:
    pass  # Pass not yet implemented
