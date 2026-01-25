# Phase 1: Query Commands Implementation Plan

## Objective

Add query commands to edword CLI so AI assistants can retrieve indexed data programmatically.

```bash
edword query character "Greg Walsh" --json
edword query timeline --json
edword query location "Cascade Labs" --json
edword query artifact "neural headset" --json
edword query world "Myriad" --json
edword query search "neural interface" --json
```

---

## Current State

- `edword query` typer group exists but has no subcommands
- Accumulated index exists at `.edword/index/{book}/accumulated.json`
- Index contains: characters, timeline, locations, artifacts, world_facts, terminology, narrative
- Schema defined in `edword/index/schema.py` with Pydantic models

---

## Implementation Plan

### 1. Create Query Module (`edword/query.py`)

New module with query functions that operate on the accumulated index.

```python
"""Query operations for the accumulated index."""

from pathlib import Path
from typing import Optional
from .index.storage import IndexStorage
from .index.schema import AccumulatedIndex
from .discovery import discover_project, get_book_by_name

def _load_index(project_root: Path, book: Optional[str] = None) -> AccumulatedIndex:
    """Load accumulated index, using discovery for default book."""
    project = discover_project(project_root)
    book_id = book or project.books[0].name if project.books else "book1"
    storage = IndexStorage(project_root)
    return storage.load_accumulated(book_id)

def _normalize(text: str) -> str:
    """Normalize text for matching (lowercase, stripped)."""
    return text.lower().strip()

def _parse_chapter_range(range_str: str) -> list[str]:
    """Parse '1-5' or '1,3,7' into chapter ID patterns.

    Returns patterns like ['chapter-01', 'chapter-02', ...] or
    just the numbers for substring matching.
    """
    # Handle range: "1-5"
    if '-' in range_str and ',' not in range_str:
        start, end = map(int, range_str.split('-'))
        return [str(i) for i in range(start, end + 1)]
    # Handle list: "1,3,7"
    return [s.strip() for s in range_str.split(',')]

def query_character(index: AccumulatedIndex, name: str) -> dict:
    """Find character by name (canonical or mention).

    Searches canonical_name and mentions list (case-insensitive).
    """

def query_timeline(
    index: AccumulatedIndex,
    chapter_range: Optional[str] = None
) -> dict:
    """Get timeline events, optionally filtered by chapter range."""

def query_location(index: AccumulatedIndex, name: str) -> dict:
    """Find location by name (case-insensitive)."""

def query_artifact(index: AccumulatedIndex, name: str) -> dict:
    """Find artifact/item by name (case-insensitive)."""

def query_world(index: AccumulatedIndex, term: str) -> dict:
    """Search world_facts and terminology for a term.

    Useful for looking up world-building details and defined terms.
    """

def query_search(index: AccumulatedIndex, query: str) -> dict:
    """Search specific text fields across all dimensions.

    Searches these fields (not raw JSON):
    - Characters: canonical_name, mentions
    - Locations: name, description
    - Events: event, time_ref
    - Artifacts: name
    - World facts: fact
    - Terminology: term, definition
    """
```

### 2. Add CLI Commands (`edword/cli.py`)

Add subcommands to the existing `query_app` typer group.

```python
@query_app.command("character")
def query_character_cmd(
    name: str = typer.Argument(..., help="Character name to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Look up character facts, relationships, and appearances."""

@query_app.command("timeline")
def query_timeline_cmd(
    book: Optional[str] = typer.Option(None, "--book", "-b"),
    chapters: Optional[str] = typer.Option(None, "--chapters", "-ch", help="Chapter range e.g. '1-5'"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Get timeline events."""

@query_app.command("location")
def query_location_cmd(
    name: str = typer.Argument(..., help="Location name to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Look up location details."""

@query_app.command("artifact")
def query_artifact_cmd(
    name: str = typer.Argument(..., help="Artifact/item name to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Look up significant items/artifacts."""

@query_app.command("world")
def query_world_cmd(
    term: str = typer.Argument(..., help="World term or concept to look up"),
    book: Optional[str] = typer.Option(None, "--book", "-b"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Look up world-building facts and terminology."""

@query_app.command("search")
def query_search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    book: Optional[str] = typer.Option(None, "--book", "-b"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Search across all index dimensions."""
```

### 3. JSON Output Structure

All query commands support `--json` flag for AI consumption.

#### Character Query Response
```json
{
  "found": true,
  "character": {
    "id": "char_greg_walsh",
    "canonical_name": "Greg Walsh",
    "mentions": ["Greg", "Dr. Walsh", "Walsh"],
    "facts": [
      {"predicate": "occupation", "value": "Senior research engineer", "confidence": "high"},
      {"predicate": "age", "value": "45", "confidence": "high"}
    ],
    "relationships": [
      {"to_id": "char_elena_walsh", "type": "spouse", "status": "former"},
      {"to_id": "char_maya_walsh", "type": "parent_of", "status": "active"}
    ],
    "state_changes": [
      {"from": "unaware of entities", "to": "aware of internal plurality"}
    ],
    "appearances": ["chapter-01", "chapter-02", "chapter-03"]
  }
}
```

#### Timeline Query Response
```json
{
  "total_events": 42,
  "events": [
    {
      "id": "evt_greg_discovers_myriad",
      "event": "Greg first becomes aware of his internal entities",
      "time_ref": "morning of Day 1",
      "chapter": "chapter-03",
      "ordering_constraints": ["before:evt_kate_appears"]
    }
  ]
}
```

#### Location Query Response
```json
{
  "found": true,
  "location": {
    "id": "loc_cascade_labs",
    "name": "Cascade Labs",
    "description": "Tech company in Seattle where Greg works",
    "characters_present": ["char_greg_walsh", "char_marcus_chen"],
    "significance": "Main workplace setting"
  }
}
```

#### Artifact Query Response
```json
{
  "found": true,
  "artifact": {
    "id": "item_neural_headset",
    "name": "Neural Interface Headset",
    "status": "prototype",
    "holder": "char_greg_walsh",
    "chapter": "chapter-05"
  }
}
```

#### World Query Response
```json
{
  "found": true,
  "world_facts": [
    {"category": "technology", "fact": "Neural interfaces allow direct brain-computer communication"}
  ],
  "terminology": [
    {"term": "Myriad", "definition": "The collective of internal entities within a person"}
  ],
  "total_matches": 2
}
```

#### Search Response
```json
{
  "query": "neural interface",
  "total_matches": 7,
  "characters": [
    {"id": "char_greg_walsh", "canonical_name": "Greg Walsh", "match_context": "works on neural interfaces"}
  ],
  "locations": [],
  "events": [
    {"id": "evt_interface_demo", "event": "Greg demonstrates neural interface prototype"}
  ],
  "artifacts": [
    {"id": "item_neural_headset", "name": "Neural Interface Headset"}
  ],
  "world_facts": [],
  "terminology": []
}
```

### 4. Human-Readable Output

When `--json` is not specified, output rich-formatted text.

```
$ edword query character "Greg Walsh"

Greg Walsh (char_greg_walsh)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Also known as: Greg, Dr. Walsh, Walsh

Facts:
  occupation: Senior research engineer (high)
  age: 45 (high)
  appearance: Dark-circled eyes, showing signs of strain (medium)

Relationships:
  spouse → Elena Walsh (former)
  parent_of → Maya Walsh (active)
  colleague → Marcus Chen (active)

Appearances: chapter-01, chapter-02, chapter-03, ... (15 total)
```

### 5. Error Handling

- If no index exists: "No index found. Run `edword index build` first."
- If character/location not found: Return `{"found": false}` (not an error)
- If ambiguous match: Return `{"found": false, "matches": [...]}` with suggestions

### 6. Edge Case Handling (per Codex review)

#### Input Validation for `_parse_chapter_range`
```python
def _parse_chapter_range(range_str: str) -> list[str]:
    """Parse '1-5' or '1,3,7' into chapter number strings.

    Handles:
    - Whitespace: "1 - 5" -> ["1", "2", "3", "4", "5"]
    - Reversed ranges: "5-1" -> ["1", "2", "3", "4", "5"]
    - Invalid input: raises ValueError with clear message
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
```

#### Empty Dimensions
Return empty lists/counts gracefully, not errors:
```json
{
  "total_events": 0,
  "events": []
}
```

#### Multiple Matches - Deterministic Ordering
When multiple items match (e.g., partial name match), return sorted by:
1. Exact match first
2. Then by canonical_name/id alphabetically

```python
def _sort_matches(matches: list, query: str) -> list:
    """Sort matches: exact first, then alphabetically."""
    def sort_key(item):
        name = item.get("canonical_name", item.get("name", ""))
        is_exact = name.lower() == query.lower()
        return (not is_exact, name.lower())
    return sorted(matches, key=sort_key)
```

#### Non-existent Book
```python
def _load_index(project_root: Path, book: Optional[str] = None) -> AccumulatedIndex:
    project = discover_project(project_root)
    if not project.books:
        raise ValueError("No books found in project")

    book_id = book or project.books[0].name

    # Validate book exists
    if book and not any(b.name == book for b in project.books):
        available = [b.name for b in project.books]
        raise ValueError(f"Book '{book}' not found. Available: {available}")

    storage = IndexStorage(project_root)
    index = storage.load_accumulated(book_id)
    if index is None:
        raise ValueError(f"No index for '{book_id}'. Run 'edword index build' first.")
    return index
```

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `edword/query.py` | Create | Query functions |
| `edword/cli.py` | Modify | Add query subcommands |
| `tests/test_query.py` | Create | Unit tests for query functions |
| `docs/user-guide.md` | Modify | Document query commands |

---

## Testing Plan

### Unit Tests (`tests/test_query.py`)

```python
# --- Core functionality ---
def test_query_character_found():
    """Character lookup returns correct data."""

def test_query_character_not_found():
    """Missing character returns found=false."""

def test_query_character_by_mention():
    """Can find character by alias/mention."""

def test_query_timeline_all():
    """Timeline returns all events."""

def test_query_timeline_chapter_range():
    """Timeline respects chapter range filter."""

def test_query_location_found():
    """Location lookup returns correct data."""

def test_query_artifact_found():
    """Artifact lookup returns correct data."""

def test_query_world_found():
    """World/terminology lookup returns matches."""

def test_query_search_specific_fields():
    """Search only matches designated text fields, not IDs or metadata."""

# --- Edge cases (per Codex review) ---
def test_parse_chapter_range_simple():
    """Chapter range '1-5' returns ['1','2','3','4','5']."""

def test_parse_chapter_range_reversed():
    """Reversed range '5-1' still returns ['1','2','3','4','5']."""

def test_parse_chapter_range_whitespace():
    """Range with whitespace '1 - 5' is handled."""

def test_parse_chapter_range_list():
    """List format '1,3,7' returns ['1','3','7']."""

def test_parse_chapter_range_invalid():
    """Invalid range 'abc' raises ValueError."""

def test_query_empty_dimension():
    """Query on empty dimension returns empty list, not error."""

def test_query_multiple_matches_ordering():
    """Multiple matches are sorted: exact first, then alphabetically."""

def test_query_nonexistent_book():
    """Query on non-existent book raises clear error."""

def test_query_no_index():
    """Query before index build raises clear error."""

# --- CLI output tests ---
def test_cli_json_output_valid():
    """--json flag produces valid JSON."""

def test_cli_rich_output_no_crash():
    """Human-readable output doesn't crash on edge cases."""
```

### Integration Tests

```bash
# Test with real trilogy index
cd ~/books/myriad_trilogy
edword query character "Greg" --json | jq .found  # should be true
edword query timeline --json | jq .total_events   # should be > 0
edword query location "Cascade" --json | jq .found
edword query artifact "headset" --json | jq .found
edword query world "Myriad" --json | jq .total_matches
edword query search "neural" --json | jq .total_matches

# Edge case tests
edword query character "NonExistent" --json | jq .found  # should be false
edword query timeline --chapters "5-1" --json  # reversed range should work
edword query character "greg" --json | jq .found  # case-insensitive
```

---

## Success Criteria

1. All six query commands work (`character`, `timeline`, `location`, `artifact`, `world`, `search`)
2. `--json` flag produces valid, parseable JSON
3. Human-readable output is clear and formatted with Rich
4. Tests pass (unit + integration + edge cases)
5. Works on Myriad Trilogy index
6. Documentation updated (user-guide.md)
7. Search only matches designated text fields (not IDs/metadata)
8. Edge cases handled gracefully:
   - Empty dimensions return empty lists
   - Invalid input raises clear ValueError
   - Multiple matches sorted deterministically
   - Non-existent book/index gives actionable error message

---

## Open Questions (Resolved)

1. **Fuzzy matching**: Should character lookup use fuzzy matching for typos?
   - Decision: Start with exact + case-insensitive, add fuzzy later if needed

2. **Pagination**: Should timeline/search support pagination for large results?
   - Decision: Add `--limit` flag, default to all results

3. **Cross-book queries**: Should queries work across all books or require `--book`?
   - Decision: Default to first book via discovery.py, require `--book` for multi-book

4. **Missing dimensions**: Plan originally omitted artifacts and world_facts
   - Decision: Added `artifact` and `world` commands per Gemini review

5. **Search noise**: Raw JSON search would match IDs and field names
   - Decision: Search only specific text fields per dimension

6. **Edge cases** (per Codex review):
   - Input validation for chapter ranges (whitespace, reversed, invalid)
   - Empty dimensions should return empty lists, not errors
   - Multiple matches need deterministic ordering
   - Non-existent book/index needs clear error messages
   - Decision: Added Section 6 with implementation details
