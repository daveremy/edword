"""Query operations for the accumulated index."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .common import EdwordError, IndexError as CommonIndexError, load_index
from .index.schema import AccumulatedIndex

MAX_PARTIAL_MATCHES = 10


class QueryError(EdwordError):
    """Error during query operation."""

    pass


@dataclass
class EntityQueryConfig:
    """Configuration for entity name queries."""
    entity_type: str  # "character", "location", "artifact"
    name_field: str  # Field to use for name matching
    get_name: Callable[[Any], str]  # Extract primary name from entity
    get_aliases: Callable[[Any], list[str]]  # Extract alias names (empty list if none)
    format_match: Callable[[dict], dict]  # Format a partial match for display


def _load_index(project_root: Path, book: Optional[str] = None) -> tuple[AccumulatedIndex, str]:
    """Load accumulated index, using discovery for default book.

    Args:
        project_root: Project root directory
        book: Book name (optional, defaults to first book)

    Returns:
        Tuple of (AccumulatedIndex, book_id)

    Raises:
        QueryError: If no books found, book doesn't exist, or no index
    """
    try:
        return load_index(project_root, book)
    except CommonIndexError as e:
        raise QueryError(str(e)) from e


def _normalize(text: str) -> str:
    """Normalize text for matching (lowercase, stripped)."""
    return text.lower().strip()


def _parse_chapter_range(range_str: str) -> list[str]:
    """Parse '1-5' or '1,3,7' into chapter number strings.

    Handles:
    - Whitespace: "1 - 5" -> ["1", "2", "3", "4", "5"]
    - Reversed ranges: "5-1" -> ["1", "2", "3", "4", "5"]
    - Invalid input: raises ValueError with clear message

    Args:
        range_str: Chapter range string

    Returns:
        List of chapter number strings

    Raises:
        ValueError: If input is invalid
    """
    range_str = range_str.strip()
    if not range_str:
        raise ValueError("Empty chapter range")

    # Handle range: "1-5" or "5-1"
    if '-' in range_str and ',' not in range_str:
        parts = [p.strip() for p in range_str.split('-')]
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid range format: '{range_str}'. Use '1-5' or '1,3,7'")
        start, end = int(parts[0]), int(parts[1])
        if start > end:
            start, end = end, start  # Handle reversed
        return [str(i) for i in range(start, end + 1)]

    # Handle list: "1,3,7"
    parts = [p.strip() for p in range_str.split(',')]
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid chapter list: '{range_str}'. Use numbers only.")
    return parts


def _sort_matches(matches: list[dict], query: str, name_field: str = "canonical_name") -> list[dict]:
    """Sort matches: exact first, then alphabetically.

    Args:
        matches: List of match dicts
        query: Original query string
        name_field: Field to use for name comparison

    Returns:
        Sorted list
    """
    query_lower = query.lower()

    def sort_key(item: dict) -> tuple[bool, str]:
        name = item.get(name_field, item.get("name", ""))
        is_exact = _normalize(name) == query_lower
        return (not is_exact, name.lower())

    return sorted(matches, key=sort_key)


def _query_entity_by_name(
    index: AccumulatedIndex,
    name: str,
    config: EntityQueryConfig,
    book_id: str,
) -> dict[str, Any]:
    """Generic entity query by name with exact and partial matching.

    Args:
        index: The accumulated index to search
        name: Name to search for
        config: Configuration for this entity type
        book_id: Book that was queried

    Returns:
        {"found": bool, "book": str, "<entity_type>": {...} or None, "matches": [...] if multiple}
    """
    entities = getattr(index, f"{config.entity_type}s")
    query_lower = _normalize(name)

    exact_match = None
    partial_matches = []

    for entity in entities:
        entity_dict = entity.model_dump()
        primary_name = config.get_name(entity)
        aliases = config.get_aliases(entity)

        # Check primary name for exact match
        if _normalize(primary_name) == query_lower:
            exact_match = entity_dict
            break

        # Check aliases for exact match
        for alias in aliases:
            if _normalize(alias) == query_lower:
                exact_match = entity_dict
                break

        if exact_match:
            break

        # Check for partial matches
        if query_lower in _normalize(primary_name):
            partial_matches.append(entity_dict)
        elif any(query_lower in _normalize(alias) for alias in aliases):
            partial_matches.append(entity_dict)

    if exact_match:
        return {"found": True, "book": book_id, config.entity_type: exact_match}

    if partial_matches:
        sorted_matches = _sort_matches(partial_matches, name, name_field=config.name_field)
        if len(sorted_matches) == 1:
            return {"found": True, "book": book_id, config.entity_type: sorted_matches[0]}
        return {
            "found": False,
            "book": book_id,
            config.entity_type: None,
            "matches": [config.format_match(m) for m in sorted_matches[:MAX_PARTIAL_MATCHES]],
        }

    return {"found": False, "book": book_id, config.entity_type: None}


def _chapter_matches_range(chapter_id: Optional[str], range_nums: list[str]) -> bool:
    """Check if a chapter ID matches any number in the range.

    Args:
        chapter_id: e.g., "chapter-05" or "chapter-05b" (can be None)
        range_nums: e.g., ["5", "6", "7"]

    Returns:
        True if chapter number is in range
    """
    if not chapter_id:
        return False
    numbers = re.findall(r'\d+', chapter_id)
    if numbers:
        return numbers[0].lstrip('0') in range_nums or numbers[0] in range_nums
    return False


def _matches_query(query_lower: str, *fields: str) -> bool:
    """Check if any of the fields contain the query (case-insensitive)."""
    return any(query_lower in _normalize(field) for field in fields if field)


# --- Entity Query Configs ---

CHARACTER_CONFIG = EntityQueryConfig(
    entity_type="character",
    name_field="canonical_name",
    get_name=lambda c: c.canonical_name,
    get_aliases=lambda c: c.mentions,
    format_match=lambda m: {"id": m["id"], "canonical_name": m["canonical_name"]},
)

LOCATION_CONFIG = EntityQueryConfig(
    entity_type="location",
    name_field="name",
    get_name=lambda loc: loc.name or "",
    get_aliases=lambda _: [],
    format_match=lambda m: {"id": m["id"], "name": m["name"]},
)

ARTIFACT_CONFIG = EntityQueryConfig(
    entity_type="artifact",
    name_field="name",
    get_name=lambda a: a.name or "",
    get_aliases=lambda _: [],
    format_match=lambda m: {"id": m["id"], "name": m["name"]},
)


# --- Query Functions ---


def query_character(
    project_root: Path,
    name: str,
    book: Optional[str] = None,
) -> dict[str, Any]:
    """Find character by name (canonical or mention).

    Searches canonical_name and mentions list (case-insensitive).

    Args:
        project_root: Project root directory
        name: Character name to search
        book: Book name (optional)

    Returns:
        {"found": bool, "character": {...} or None, "matches": [...] if multiple}
    """
    if not name or not name.strip():
        raise QueryError("Character name cannot be empty")

    index, book_id = _load_index(project_root, book)
    return _query_entity_by_name(index, name, CHARACTER_CONFIG, book_id)


def query_timeline(
    project_root: Path,
    book: Optional[str] = None,
    chapter_range: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Get timeline events, optionally filtered by chapter range.

    Args:
        project_root: Project root directory
        book: Book name (optional)
        chapter_range: Chapter range string, e.g., "1-5" or "1,3,7"
        limit: Maximum number of events to return

    Returns:
        {
            "total_events": int,
            "events": [...]
        }
    """
    index, book_id = _load_index(project_root, book)

    events = [evt.model_dump() for evt in index.timeline]

    # Filter by chapter range if specified
    if chapter_range:
        try:
            range_nums = _parse_chapter_range(chapter_range)
        except ValueError as e:
            raise QueryError(str(e)) from e
        events = [
            evt for evt in events
            if _chapter_matches_range(evt.get("evidence", {}).get("chapter", ""), range_nums)
        ]

    # Apply limit
    if limit and limit > 0:
        events = events[:limit]

    return {
        "book": book_id,
        "total_events": len(events),
        "events": events,
    }


def query_location(
    project_root: Path,
    name: str,
    book: Optional[str] = None,
) -> dict[str, Any]:
    """Find location by name (case-insensitive).

    Args:
        project_root: Project root directory
        name: Location name to search
        book: Book name (optional)

    Returns:
        {"found": bool, "location": {...} or None, "matches": [...] if multiple}
    """
    if not name or not name.strip():
        raise QueryError("Location name cannot be empty")

    index, book_id = _load_index(project_root, book)
    return _query_entity_by_name(index, name, LOCATION_CONFIG, book_id)


def query_artifact(
    project_root: Path,
    name: str,
    book: Optional[str] = None,
) -> dict[str, Any]:
    """Find artifact/item by name (case-insensitive).

    Args:
        project_root: Project root directory
        name: Artifact name to search
        book: Book name (optional)

    Returns:
        {"found": bool, "artifact": {...} or None, "matches": [...] if multiple}
    """
    if not name or not name.strip():
        raise QueryError("Artifact name cannot be empty")

    index, book_id = _load_index(project_root, book)
    return _query_entity_by_name(index, name, ARTIFACT_CONFIG, book_id)


def _get_chapter_number(chapter_id: Optional[str]) -> Optional[int]:
    """Extract chapter number from chapter ID like 'chapter-05' -> 5."""
    if not chapter_id:
        return None
    numbers = re.findall(r'\d+', chapter_id)
    if numbers:
        return int(numbers[0])
    return None


def _is_chapter_at_or_before(chapter_id: Optional[str], as_of_chapter: int) -> bool:
    """Check if chapter_id is at or before the as_of_chapter number."""
    chapter_num = _get_chapter_number(chapter_id)
    if chapter_num is None:
        return False
    return chapter_num <= as_of_chapter


def query_world(
    project_root: Path,
    term: str,
    book: Optional[str] = None,
    as_of_chapter: Optional[str] = None,
) -> dict[str, Any]:
    """Search world_facts and terminology for a term.

    Args:
        project_root: Project root directory
        term: Term or concept to search
        book: Book name (optional)
        as_of_chapter: Only include entries from this chapter or earlier (e.g., "5" or "chapter-05")

    Returns:
        {
            "found": bool,
            "world_facts": [...],
            "terminology": [...],
            "total_matches": int
        }
    """
    if not term or not term.strip():
        raise QueryError("Search term cannot be empty")

    index, book_id = _load_index(project_root, book)
    query_lower = _normalize(term)

    # Parse as_of_chapter if provided
    as_of_num = None
    if as_of_chapter:
        as_of_num = _get_chapter_number(as_of_chapter)
        if as_of_num is None:
            # Try parsing as plain number
            try:
                as_of_num = int(as_of_chapter.strip())
            except ValueError:
                raise QueryError(f"Invalid chapter: '{as_of_chapter}'. Use a number like '5' or 'chapter-05'")

    matching_facts = []
    matching_terms = []

    # Search world facts
    for fact in index.world_facts:
        fact_text = fact.fact or ""
        if query_lower in _normalize(fact_text):
            fact_dict = fact.model_dump()
            chapter = fact_dict.get("evidence", {}).get("chapter")
            # Filter by as_of if specified
            if as_of_num is not None and not _is_chapter_at_or_before(chapter, as_of_num):
                continue
            # Add chapter to top level for easy access
            fact_dict["chapter"] = chapter
            matching_facts.append(fact_dict)

    # Search terminology
    for term_obj in index.terminology:
        term_text = term_obj.term or ""
        definition = term_obj.definition or ""
        if query_lower in _normalize(term_text) or query_lower in _normalize(definition):
            term_dict = term_obj.model_dump()
            chapter = term_dict.get("evidence", {}).get("chapter")
            # Filter by as_of if specified
            if as_of_num is not None and not _is_chapter_at_or_before(chapter, as_of_num):
                continue
            # Add chapter to top level for easy access
            term_dict["chapter"] = chapter
            matching_terms.append(term_dict)

    total = len(matching_facts) + len(matching_terms)

    result = {
        "found": total > 0,
        "book": book_id,
        "world_facts": matching_facts,
        "terminology": matching_terms,
        "total_matches": total,
    }

    if as_of_chapter:
        result["as_of_chapter"] = as_of_num

    return result


def query_search(
    project_root: Path,
    query: str,
    book: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Search specific text fields across all dimensions.

    Searches these fields (not raw JSON):
    - Characters: canonical_name, mentions
    - Locations: name, description
    - Events: event, time_ref
    - Artifacts: name
    - World facts: fact
    - Terminology: term, definition

    Args:
        project_root: Project root directory
        query: Search query
        book: Book name (optional)
        limit: Maximum results per dimension

    Returns:
        {"query": str, "characters": [...], "locations": [...], ...}
    """
    if not query or not query.strip():
        raise QueryError("Search query cannot be empty")

    index, book_id = _load_index(project_root, book)
    query_lower = _normalize(query)

    results: dict[str, list] = {
        "characters": [],
        "locations": [],
        "events": [],
        "artifacts": [],
        "world_facts": [],
        "terminology": [],
    }

    # Search characters (includes mentions as additional search fields)
    for char in index.characters:
        if _matches_query(query_lower, char.canonical_name, *char.mentions):
            results["characters"].append({
                "id": char.id,
                "canonical_name": char.canonical_name,
                "match_context": char.canonical_name,
            })

    # Search locations
    for loc in index.locations:
        if _matches_query(query_lower, loc.name, loc.description):
            results["locations"].append({
                "id": loc.id,
                "name": loc.name,
                "match_context": (loc.description or "")[:100] or loc.name,
            })

    # Search events
    for evt in index.timeline:
        if _matches_query(query_lower, evt.event, evt.time_ref):
            results["events"].append({
                "id": evt.id,
                "event": evt.event,
                "match_context": evt.event,
            })

    # Search artifacts
    for artifact in index.artifacts:
        if _matches_query(query_lower, artifact.name):
            results["artifacts"].append({
                "id": artifact.id,
                "name": artifact.name,
            })

    # Search world facts
    for fact in index.world_facts:
        if _matches_query(query_lower, fact.fact):
            category = fact.category.value if hasattr(fact.category, "value") else fact.category
            results["world_facts"].append({
                "category": category,
                "fact": fact.fact,
            })

    # Search terminology
    for term in index.terminology:
        if _matches_query(query_lower, term.term, term.definition):
            results["terminology"].append({
                "term": term.term,
                "definition": term.definition,
            })

    # Apply limit per dimension
    if limit and limit > 0:
        results = {key: val[:limit] for key, val in results.items()}

    total = sum(len(v) for v in results.values())

    return {
        "query": query,
        "book": book_id,
        **results,
        "total_matches": total,
    }
