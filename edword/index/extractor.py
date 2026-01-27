"""Chapter fact extractor using LLM.

Extracts structured facts from a single chapter using delta extraction:
- Only extracts facts from the current chapter
- Optionally receives entity list for pronoun resolution
- Returns validated ChapterIndex
"""

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

from ..prompts import render_prompt
from ..llm import call_model, extract_index, ProviderTimeout, RateLimitError
from .schema import ChapterIndex, EntityList, INDEX_SCHEMA_VERSION, ExtractionMetadata
from .. import __version__ as edword_version

# Timeout retry settings
MAX_TIMEOUT_RETRIES = 2
TIMEOUT_BACKOFF_SECONDS = [30, 60]  # Wait times between retries
from .validation import (
    validate_with_retry,
    coerce_to_schema,
    IndexValidationError,
)


@dataclass
class ExtractionConfig:
    """Configuration for chapter extraction."""
    provider: str = "claude"
    model: str = "haiku"
    max_retries: int = 3
    timeout: int = 120
    verbose: bool = False


@dataclass
class TimingStats:
    """Timing breakdown for extraction phases."""
    file_read_ms: float = 0.0
    prompt_render_ms: float = 0.0
    llm_calls_ms: float = 0.0  # Total time in LLM calls (including retries)
    llm_call_count: int = 0    # Number of LLM calls made
    parse_validate_ms: float = 0.0
    total_ms: float = 0.0

    def __str__(self) -> str:
        return (
            f"total={self.total_ms:.0f}ms | "
            f"llm={self.llm_calls_ms:.0f}ms ({self.llm_call_count} calls) | "
            f"parse/validate={self.parse_validate_ms:.0f}ms | "
            f"file={self.file_read_ms:.0f}ms | "
            f"prompt={self.prompt_render_ms:.0f}ms"
        )


@dataclass
class ExtractionResult:
    """Result of chapter extraction."""
    success: bool
    index: Optional[ChapterIndex] = None
    error: Optional[str] = None
    retries_used: int = 0
    raw_response: Optional[str] = None
    timing: Optional[TimingStats] = None


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of file contents."""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def extract_chapter(
    chapter_path: Path,
    book_id: str,
    chapter_id: str,
    entity_list: Optional[EntityList] = None,
    config: Optional[ExtractionConfig] = None,
    on_retry: Optional[Callable[[int, list[str]], None]] = None,
) -> ExtractionResult:
    """Extract facts from a single chapter file.

    Args:
        chapter_path: Path to the chapter markdown file
        book_id: Book identifier (e.g., "book1")
        chapter_id: Chapter identifier (e.g., "chapter-01")
        entity_list: Optional entity list from previous chapters for pronoun resolution
        config: Extraction configuration
        on_retry: Optional callback for retry events (attempt, errors)

    Returns:
        ExtractionResult with ChapterIndex if successful
    """
    config = config or ExtractionConfig()
    timing = TimingStats()
    total_start = time.perf_counter()

    # Read chapter content
    if not chapter_path.exists():
        return ExtractionResult(
            success=False,
            error=f"Chapter file not found: {chapter_path}"
        )

    file_start = time.perf_counter()
    try:
        chapter_text = chapter_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try with a more permissive encoding
        try:
            chapter_text = chapter_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ExtractionResult(
                success=False,
                error=f"Failed to read chapter file (encoding): {e}"
            )
    except PermissionError:
        return ExtractionResult(
            success=False,
            error=f"Permission denied reading chapter file: {chapter_path}"
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error=f"Failed to read chapter file: {e}"
        )

    try:
        source_hash = compute_file_hash(chapter_path)
    except Exception as e:
        return ExtractionResult(
            success=False,
            error=f"Failed to compute file hash: {e}"
        )
    timing.file_read_ms = (time.perf_counter() - file_start) * 1000

    # Format entity list for prompt
    entity_text = entity_list.to_text() if entity_list else "(No entities from previous chapters)"

    # Build prompt
    prompt_start = time.perf_counter()
    try:
        prompt = render_prompt(
            "extract_chapter",
            chapter_text=chapter_text,
            entity_list=entity_text,
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error=f"Failed to render prompt: {e}"
        )
    timing.prompt_render_ms = (time.perf_counter() - prompt_start) * 1000

    # Track retries and LLM timing
    retries_used = 0
    raw_response = None

    def call_llm(p: str) -> str:
        nonlocal raw_response

        for attempt in range(MAX_TIMEOUT_RETRIES + 1):
            llm_start = time.perf_counter()
            try:
                response = call_model(
                    config.provider,
                    p,
                    model=config.model,
                    timeout=config.timeout,
                    use_cache=False,  # Don't cache extraction calls
                )
                timing.llm_calls_ms += (time.perf_counter() - llm_start) * 1000
                timing.llm_call_count += 1
                raw_response = response
                return response
            except ProviderTimeout:
                timing.llm_calls_ms += (time.perf_counter() - llm_start) * 1000
                timing.llm_call_count += 1
                if attempt < MAX_TIMEOUT_RETRIES:
                    wait_time = TIMEOUT_BACKOFF_SECONDS[attempt]
                    if config.verbose:
                        print(f"  Timeout, retrying in {wait_time}s (attempt {attempt + 2}/{MAX_TIMEOUT_RETRIES + 1})...")
                    time.sleep(wait_time)
                else:
                    raise  # Re-raise after all retries exhausted
            except RateLimitError:
                timing.llm_calls_ms += (time.perf_counter() - llm_start) * 1000
                timing.llm_call_count += 1
                raise  # Always re-raise rate limit errors (don't retry)

        # Loop always returns (success) or raises (timeout/rate limit)
        # This is unreachable but satisfies type checker
        assert False, "Unreachable"

    def parse_response(response: str) -> dict:
        """Parse LLM response to dict, extracting from tags."""
        result = extract_index(response)

        if not result.success:
            # Only try fallback if tag was NOT found (not if JSON was invalid)
            # If tag was found but JSON invalid, don't risk grabbing wrong snippet
            if not result.tag_found:
                from ..llm.parsing import fallback_json_extraction
                fallback = fallback_json_extraction(response)
                if fallback.success and isinstance(fallback.data, dict):
                    data = fallback.data
                else:
                    raise ValueError(result.error or "Failed to extract JSON from response")
            else:
                # Tag was found but JSON was invalid - don't fallback
                raise ValueError(result.error or "Tagged JSON was invalid")
        else:
            data = result.data

        # Apply coercion to fix common issues
        data = coerce_to_schema(data)

        # Add metadata that LLM doesn't provide
        data["book"] = book_id
        data["chapter"] = chapter_id
        data["source_path"] = str(chapter_path)
        data["source_hash"] = source_hash
        data["extracted_at"] = datetime.now().isoformat()
        data["schema_version"] = INDEX_SCHEMA_VERSION
        data["extraction_metadata"] = {
            "provider": config.provider,
            "model": config.model,
            "edword_version": edword_version,
        }

        return data

    def track_retry(attempt: int, errors: list[str]):
        nonlocal retries_used
        retries_used = attempt
        if on_retry:
            on_retry(attempt, errors)
        if config.verbose:
            print(f"  Retry {attempt}: {errors[0] if errors else 'unknown error'}")

    try:
        # Use validation with retry (timing is tracked via call_llm wrapper)
        validate_start = time.perf_counter()
        index = validate_with_retry(
            call_llm=call_llm,
            initial_prompt=prompt,
            parse_response=parse_response,
            model=ChapterIndex,
            max_retries=config.max_retries,
            on_retry=track_retry,
        )
        # Parse/validate time = total time minus LLM time
        total_validate_time = (time.perf_counter() - validate_start) * 1000
        timing.parse_validate_ms = total_validate_time - timing.llm_calls_ms
        timing.total_ms = (time.perf_counter() - total_start) * 1000

        if config.verbose:
            print(f"  Timing: {timing}")

        return ExtractionResult(
            success=True,
            index=index,
            retries_used=retries_used,
            raw_response=raw_response,
            timing=timing,
        )

    except RateLimitError:
        # Re-raise rate limit errors so caller can halt
        raise
    except IndexValidationError as e:
        timing.total_ms = (time.perf_counter() - total_start) * 1000
        return ExtractionResult(
            success=False,
            error=f"Validation failed after {config.max_retries + 1} attempts: {e.errors[0] if e.errors else str(e)}",
            retries_used=retries_used,
            raw_response=raw_response,
            timing=timing,
        )
    except Exception as e:
        timing.total_ms = (time.perf_counter() - total_start) * 1000
        return ExtractionResult(
            success=False,
            error=str(e),
            retries_used=retries_used,
            raw_response=raw_response,
            timing=timing,
        )


def extract_chapter_simple(
    chapter_text: str,
    book_id: str,
    chapter_id: str,
    source_path: str = "",
    entity_list: Optional[EntityList] = None,
    config: Optional[ExtractionConfig] = None,
) -> ExtractionResult:
    """Extract facts from chapter text (simpler interface for testing).

    Like extract_chapter but takes text directly instead of path.
    """
    config = config or ExtractionConfig()

    # Compute hash of text
    source_hash = hashlib.sha256(chapter_text.encode()).hexdigest()[:16]

    # Format entity list for prompt
    entity_text = entity_list.to_text() if entity_list else "(No entities from previous chapters)"

    # Build prompt
    try:
        prompt = render_prompt(
            "extract_chapter",
            chapter_text=chapter_text,
            entity_list=entity_text,
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error=f"Failed to render prompt: {e}"
        )

    raw_response = None
    retries_used = 0

    def call_llm(p: str) -> str:
        nonlocal raw_response
        response = call_model(
            config.provider,
            p,
            model=config.model,
            timeout=config.timeout,
            use_cache=False,
        )
        raw_response = response
        return response

    def parse_response(response: str) -> dict:
        result = extract_index(response)

        if not result.success:
            # Only try fallback if tag was NOT found
            if not result.tag_found:
                from ..llm.parsing import fallback_json_extraction
                fallback = fallback_json_extraction(response)
                if fallback.success and isinstance(fallback.data, dict):
                    data = fallback.data
                else:
                    raise ValueError(result.error or "Failed to extract JSON")
            else:
                raise ValueError(result.error or "Tagged JSON was invalid")
        else:
            data = result.data

        data = coerce_to_schema(data)
        data["book"] = book_id
        data["chapter"] = chapter_id
        data["source_path"] = source_path
        data["source_hash"] = source_hash
        data["extracted_at"] = datetime.now().isoformat()
        data["schema_version"] = INDEX_SCHEMA_VERSION
        data["extraction_metadata"] = {
            "provider": config.provider,
            "model": config.model,
            "edword_version": edword_version,
        }

        return data

    def track_retry(attempt: int, errors: list[str]):
        nonlocal retries_used
        retries_used = attempt

    try:
        index = validate_with_retry(
            call_llm=call_llm,
            initial_prompt=prompt,
            parse_response=parse_response,
            model=ChapterIndex,
            max_retries=config.max_retries,
            on_retry=track_retry,
        )

        return ExtractionResult(
            success=True,
            index=index,
            retries_used=retries_used,
            raw_response=raw_response,
        )

    except IndexValidationError as e:
        return ExtractionResult(
            success=False,
            error=str(e),
            retries_used=retries_used,
            raw_response=raw_response,
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error=str(e),
            retries_used=retries_used,
            raw_response=raw_response,
        )
