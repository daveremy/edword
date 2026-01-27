"""FastMCP server exposing edword editorial analysis tools.

Provides 8 tools for AI assistants to query manuscript indices
and check text for consistency.
"""

import os
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP

from ..common import EdwordError, IndexVersionMismatch
from ..config import find_config, load_config, EdwordConfig
from ..discovery import discover_project, get_book_by_name
from ..index.storage import IndexStorage
from ..query import (
    query_character,
    query_timeline,
    query_location,
    query_artifact,
    query_world,
    query_search,
)
from ..check import check_text

# Cached config to avoid repeated disk reads
_cached_config: Optional[EdwordConfig] = None


def get_project_root(override_root: Optional[str] = None) -> Path:
    """Get project root, respecting override > env var > auto-discover.

    Args:
        override_root: Explicit project root path (highest priority)

    Returns:
        Path to project root

    Raises:
        ValueError: If no project root can be determined
    """
    if override_root:
        return Path(override_root).resolve()

    env_root = os.environ.get("EDWORD_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    config_path = find_config()
    if config_path:
        return config_path.parent

    raise ValueError(
        "No project root found. Set EDWORD_PROJECT_ROOT or run from a "
        "directory with edword.yaml"
    )


def get_config(override_root: Optional[str] = None) -> EdwordConfig:
    """Get config, respecting override > env var > auto-discover.

    Caches config after first load to avoid repeated disk reads.

    Args:
        override_root: Explicit project root path

    Returns:
        EdwordConfig instance
    """
    global _cached_config

    # If override provided, don't use cache (explicit path takes precedence)
    if override_root:
        root = Path(override_root).resolve()
        config_path = find_config(root)
        return load_config(config_path)

    # Use cache for default case
    if _cached_config is not None:
        return _cached_config

    config_path = find_config()
    _cached_config = load_config(config_path)
    return _cached_config


def handle_error(e: Exception) -> dict[str, Any]:
    """Convert exceptions to MCP-friendly error dict.

    Args:
        e: Exception to convert

    Returns:
        Dict with error info, safe for JSON serialization
    """
    if isinstance(e, IndexVersionMismatch):
        return {
            "error": True,
            "error_type": "IndexVersionMismatch",
            "message": "Edword has been upgraded with improved analysis capabilities.",
            "needs_rebuild": True,
            "book": e.book_id,
            "index_version": e.index_version,
            "current_version": e.current_version,
            "action": f"Run 'edword index build --book {e.book_id}' to rebuild",
        }
    return {
        "error": True,
        "error_type": type(e).__name__,
        "message": str(e),
    }


# Create the MCP server
mcp = FastMCP(
    name="edword",
    instructions="Editorial analysis tools for manuscript consistency checking. Query character facts, timeline events, locations, artifacts, and world-building details. Check text for contradictions against indexed facts.",
)


@mcp.tool
def edword_query_character(
    name: str,
    book: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Look up character facts, relationships, and appearances.

    Search the manuscript index for a character by name. Returns their
    canonical name, aliases, facts (age, appearance, etc.), and relationships.

    Args:
        name: Character name to search for (canonical or alias)
        book: Book name (optional, defaults to first book)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Character data or error dict
    """
    try:
        root = get_project_root(project_root)
        return query_character(root, name, book)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_query_timeline(
    book: Optional[str] = None,
    chapter_range: Optional[str] = None,
    limit: Optional[int] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Get timeline events from the manuscript index.

    Returns events in chronological order, optionally filtered by chapter range.

    Args:
        book: Book name (optional, defaults to first book)
        chapter_range: Chapter range like "1-5" or "1,3,7" (optional)
        limit: Maximum number of events to return (optional)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Timeline events or error dict
    """
    try:
        root = get_project_root(project_root)
        return query_timeline(root, book, chapter_range, limit)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_query_location(
    name: str,
    book: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Look up location details from the manuscript index.

    Search for a location by name. Returns description, characters present,
    and narrative significance.

    Args:
        name: Location name to search for
        book: Book name (optional, defaults to first book)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Location data or error dict
    """
    try:
        root = get_project_root(project_root)
        return query_location(root, name, book)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_query_artifact(
    name: str,
    book: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Look up significant items or artifacts from the manuscript index.

    Search for objects, items, or artifacts that have narrative significance.

    Args:
        name: Artifact/item name to search for
        book: Book name (optional, defaults to first book)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Artifact data or error dict
    """
    try:
        root = get_project_root(project_root)
        return query_artifact(root, name, book)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_query_world(
    term: str,
    book: Optional[str] = None,
    as_of_chapter: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Search world-building facts and terminology.

    Find world facts and terminology entries matching a search term.
    Can filter to show only facts established up to a certain chapter.

    Args:
        term: Term or concept to search for
        book: Book name (optional, defaults to first book)
        as_of_chapter: Only show facts from this chapter or earlier (optional)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Matching world facts and terminology, or error dict
    """
    try:
        root = get_project_root(project_root)
        return query_world(root, term, book, as_of_chapter)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_query_search(
    query: str,
    book: Optional[str] = None,
    limit: Optional[int] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Search across all index dimensions.

    Performs a cross-dimensional search across characters, locations,
    events, artifacts, world facts, and terminology.

    Args:
        query: Search query string
        book: Book name (optional, defaults to first book)
        limit: Maximum results per dimension (optional)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Matching entries from all dimensions, or error dict
    """
    try:
        root = get_project_root(project_root)
        return query_search(root, query, book, limit)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_check_text(
    text: str,
    book: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Check if text contradicts indexed facts.

    Compares new text against the manuscript index to detect inconsistencies.
    Currently checks character ages and physical traits (eye color, hair color).

    Args:
        text: Text to check for consistency
        book: Book name (optional, defaults to first book)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Conflict report or error dict. Structure:
        {
            "has_conflicts": bool,
            "conflicts": [...],
            "characters_checked": int,
            "text_length": int,
            "book": str
        }
    """
    try:
        root = get_project_root(project_root)
        return check_text(root, text, book)
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_verify_finding(
    finding_message: str,
    finding_location: str,
    book: Optional[str] = None,
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Verify a specific finding using Chain-of-Verification (CoVe).

    Runs a 4-step verification process to determine if a finding is real or
    a false positive:
    1. Load relevant manuscript evidence
    2. Generate verification questions
    3. Answer questions independently
    4. Synthesize final verdict

    Args:
        finding_message: The finding message to verify
        finding_location: Location in manuscript (e.g., "Chapters: 8, 11b")
        book: Book name (optional, defaults to first book)
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Verification result with verdict, confidence, and explanation.
        Verdicts: confirmed (real issue), dismissed (false positive), uncertain
    """
    from ..passes.verifier import CoVeVerifier
    from ..passes.base import Finding, Severity

    try:
        config = get_config(project_root)
        root = config.project_root or Path.cwd()
        project = discover_project(root)

        # Resolve book
        selected_book = get_book_by_name(project, book) if book else (
            project.books[0] if project.books else None
        )
        if not selected_book:
            msg = f"Book '{book}' not found" if book else "No books found"
            return {"error": True, "message": msg}

        # Resolve model from config
        resolved_model = getattr(config.llm, 'recursive_model', None) or config.llm.model or "sonnet"

        verifier = CoVeVerifier(provider=config.llm.provider, model=resolved_model)
        finding = Finding(severity=Severity.ERROR, message=finding_message, location=finding_location)
        result = verifier.verify(finding, selected_book)

        return {
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "questions_asked": len(result.questions),
            "evidence_excerpt": result.evidence_excerpt[:200] if result.evidence_excerpt else "",
            "book": selected_book.name,
        }
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


@mcp.tool
def edword_index_status(
    project_root: Optional[str] = None,
) -> dict[str, Any]:
    """Get index status including staleness check.

    Returns information about the project and its index, including
    which books are indexed and whether any chapters are stale.

    Args:
        project_root: Project root path (optional, uses env/auto-discover)

    Returns:
        Index status information:
        {
            "project_root": str,
            "project_name": str,
            "books": [
                {
                    "book_id": str,
                    "chapters_indexed": int,
                    "has_accumulated": bool,
                    "stale": bool,
                    "size_bytes": int
                }
            ],
            "total_chapters": int
        }
    """
    try:
        config = get_config(project_root)
        root = config.project_root or Path.cwd()

        # Discover project structure
        project = discover_project(root)

        # Initialize storage with configured index path
        storage = IndexStorage(root, str(config.paths.index))
        stats = storage.get_stats()

        # Build enhanced book info with staleness check
        books_info = []
        for book_stat in stats.get("books", []):
            book_id = book_stat["book_id"]

            # Find the book in project structure
            book_info_struct = get_book_by_name(project, book_id)

            # Check staleness: compare index timestamp vs chapter file mtime
            stale = False
            if book_info_struct and book_stat.get("has_accumulated"):
                acc_index = storage.load_accumulated_index(book_id)
                if acc_index and acc_index.last_updated:
                    index_timestamp = acc_index.last_updated.timestamp()
                    for chapter_path in book_info_struct.chapters:
                        if chapter_path.exists():
                            if chapter_path.stat().st_mtime > index_timestamp:
                                stale = True
                                break

            books_info.append({
                "book_id": book_id,
                "chapters_indexed": len(book_stat.get("chapters", [])),
                "has_accumulated": book_stat.get("has_accumulated", False),
                "stale": stale,
                "size_bytes": book_stat.get("size_bytes", 0),
            })

        return {
            "project_root": str(root),
            "project_name": config.project_name,
            "books": books_info,
            "total_chapters": stats.get("total_chapters", 0),
        }
    except EdwordError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)


def create_server() -> FastMCP:
    """Create and return the FastMCP server instance.

    Returns:
        Configured FastMCP server with all edword tools registered
    """
    return mcp


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
