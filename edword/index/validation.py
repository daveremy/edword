"""Schema validation with retry logic for LLM-extracted indices.

Validates JSON data against Pydantic models with helpful error messages
and optional retry capability for when LLM output doesn't match schema.
"""

from typing import TypeVar, Type, Optional, Callable, Any
from dataclasses import dataclass, field
from pydantic import BaseModel

from .schema import ChapterIndex


T = TypeVar("T", bound=BaseModel)


@dataclass
class ValidationResult:
    """Result of schema validation."""
    success: bool
    data: Optional[T] = None  # Validated Pydantic model if success
    errors: list[str] = field(default_factory=list)  # List of validation errors if failed
    raw_data: Optional[dict] = None  # Original data that was validated


class IndexValidationError(Exception):
    """Schema validation failed after all retries."""
    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


def validate_json(
    data: dict,
    model: Type[T],
) -> ValidationResult:
    """Validate JSON data against a Pydantic model.

    Args:
        data: Dictionary to validate
        model: Pydantic model class to validate against

    Returns:
        ValidationResult with validated model or errors
    """
    try:
        validated = model.model_validate(data)
        return ValidationResult(
            success=True,
            data=validated,
            raw_data=data,
        )
    except Exception as e:
        # Extract useful error messages
        errors = _extract_validation_errors(e)
        return ValidationResult(
            success=False,
            errors=errors,
            raw_data=data,
        )


def validate_chapter_index(data: dict) -> ValidationResult:
    """Validate data as a ChapterIndex.

    Convenience wrapper for validate_json with ChapterIndex model.
    """
    return validate_json(data, ChapterIndex)


def _extract_validation_errors(error: Exception) -> list[str]:
    """Extract human-readable error messages from validation exception."""
    errors = []

    # Check if it's a Pydantic ValidationError (has callable .errors() method)
    if hasattr(error, 'errors') and callable(getattr(error, 'errors', None)):
        try:
            for err in error.errors():
                loc = " -> ".join(str(l) for l in err['loc'])
                msg = err['msg']
                errors.append(f"{loc}: {msg}")
        except (TypeError, KeyError, AttributeError):
            # Fallback if .errors() doesn't return expected format
            errors.append(str(error))
    else:
        errors.append(str(error))

    return errors


def format_validation_errors(errors: list[str]) -> str:
    """Format validation errors for inclusion in retry prompt."""
    if not errors:
        return "Unknown validation error"

    lines = ["The JSON output had the following validation errors:"]
    for i, err in enumerate(errors, 1):
        lines.append(f"  {i}. {err}")
    lines.append("\nPlease fix these issues and output valid JSON.")

    return "\n".join(lines)


def validate_with_retry(
    call_llm: Callable[[str], str],
    initial_prompt: str,
    parse_response: Callable[[str], dict],
    model: Type[T],
    max_retries: int = 3,
    on_retry: Optional[Callable[[int, list[str]], None]] = None,
) -> T:
    """Validate LLM output with automatic retry on validation failure.

    Args:
        call_llm: Function that takes a prompt and returns LLM response
        initial_prompt: The initial prompt to send
        parse_response: Function to parse LLM response into dict
        model: Pydantic model to validate against
        max_retries: Maximum number of retry attempts
        on_retry: Optional callback called before each retry with (attempt, errors)

    Returns:
        Validated Pydantic model

    Raises:
        IndexValidationError: If validation fails after all retries
        ValueError: If max_retries is negative
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be non-negative, got {max_retries}")

    prompt = initial_prompt
    all_errors = []

    for attempt in range(max_retries + 1):
        # Call LLM
        response = call_llm(prompt)

        # Parse response to dict
        try:
            data = parse_response(response)
        except Exception as e:
            errors = [f"Failed to parse response: {e}"]
            all_errors.extend(errors)

            if attempt < max_retries:
                if on_retry:
                    on_retry(attempt + 1, errors)
                prompt = _build_retry_prompt(initial_prompt, errors)
                continue
            else:
                raise IndexValidationError(
                    f"Failed to parse LLM response after {max_retries + 1} attempts",
                    all_errors
                )

        # Validate against schema
        result = validate_json(data, model)

        if result.success:
            return result.data

        # Validation failed
        all_errors.extend(result.errors)

        if attempt < max_retries:
            if on_retry:
                on_retry(attempt + 1, result.errors)
            prompt = _build_retry_prompt(initial_prompt, result.errors)
        else:
            raise IndexValidationError(
                f"Schema validation failed after {max_retries + 1} attempts",
                all_errors
            )

    # Should never reach here
    raise IndexValidationError("Unexpected error in retry loop", all_errors)


def _build_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    """Build a retry prompt that includes validation errors."""
    error_text = format_validation_errors(errors)

    return f"""{original_prompt}

---

IMPORTANT: Your previous response had validation errors:

{error_text}

Please output valid JSON that matches the schema exactly."""


def coerce_to_schema(data: Any) -> dict:
    """Attempt to coerce common issues in LLM output to match schema.

    This handles common mistakes like:
    - Missing required fields (adds empty defaults)
    - Non-list fields that should be lists (wraps in list)
    - Missing pov_scene subfields (adds defaults)

    Note: This is a best-effort function. Validation should still be used.
    Returns a new dict; does not mutate the input.

    Raises:
        ValueError: If data is not a dict (LLM returned wrong type)
    """
    # Reject non-dict input - let retry loop handle it
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict from LLM, got {type(data).__name__}")

    # Work on a shallow copy to avoid mutating the original
    result = dict(data)

    # Ensure required top-level fields exist
    defaults = {
        "characters": [],
        "timeline": [],
        "locations": [],
        "artifacts": [],
        "world_facts": [],
        "terminology": [],
        "narrative": [],
        "pov_scene": {},
    }

    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    # Ensure pov_scene has required structure
    pov_defaults = {
        "tense": "past",
        "voice": "third_limited",
        "scene_breaks": [],
    }
    if isinstance(result.get("pov_scene"), dict):
        # Copy and fill in defaults
        result["pov_scene"] = dict(result["pov_scene"])
        for key, default in pov_defaults.items():
            if key not in result["pov_scene"]:
                result["pov_scene"][key] = default
    else:
        # Not a dict (null, list, string, etc.) - replace with defaults
        result["pov_scene"] = pov_defaults.copy()

    # Coerce list items
    for key in ["characters", "timeline", "locations", "artifacts", "world_facts", "terminology", "narrative"]:
        if key in result and not isinstance(result[key], list):
            # Wrap single item in list, or empty list for None
            result[key] = [] if result[key] is None else [result[key]]

    return result
