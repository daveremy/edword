# Edword MCP Guide

*For AI assistants helping authors write novels*

## Overview

Edword provides tools to help you maintain consistency while assisting with novel writing. The author builds an index of their manuscript; you query it to recall facts and check new content.

## Architecture Understanding

```
Author's Workflow                    Your Workflow (AI Assistant)
─────────────────                    ────────────────────────────
1. Writes chapters
2. Runs: edword index build     ───► Index becomes available
3. Continues writing             ◄──► You query index, help write
4. Periodically rebuilds         ───► Index updates
```

**Key insight**: You don't rebuild the index. The author does. Your job is to use the existing index effectively.

## Available Tools

### `query_character(name: str) -> CharacterFacts`

Look up everything known about a character.

```python
# Example usage
facts = query_character("Greg Walsh")
# Returns: age, relationships, appearances, state changes, etc.
```

**When to use:**
- Before writing dialogue for a character
- When the author asks "What do we know about X?"
- To check a character's current state (alive? injured? location?)

### `query_timeline(book: str, chapter_range?: str) -> TimelineEvents`

Get timeline events, optionally filtered by chapter range.

```python
events = query_timeline("book1", "1-10")
# Returns: events with relative ordering, dates, durations
```

**When to use:**
- When writing scenes that reference past events
- To check "how long ago" calculations
- To verify event sequences

### `check_consistency(text: str, book: str) -> ConsistencyResult`

Check if new text contradicts the existing index.

```python
result = check_consistency(
    "Sarah's blue eyes sparkled in the moonlight.",
    "book1"
)
# Returns: {conflicts: [{field: "eye_color", indexed: "brown", new: "blue"}]}
```

**When to use:**
- Before suggesting new descriptive passages
- When introducing facts about characters
- After writing a significant scene

### `get_index_status() -> IndexStatus`

Check if the index exists and when it was last updated.

```python
status = get_index_status()
# Returns: {exists: true, last_updated: "2026-01-24T10:30:00", chapters: 31, stale: false}
```

**When to use:**
- At the start of a session
- If queries return unexpected results
- Before suggesting the author rebuild

## Best Practices

### 1. Check Index Status Early

At the start of a writing session:

```
You: "Let me check the story index status..."
[calls get_index_status()]
You: "The index was last updated 3 days ago and covers 31 chapters.
      If you've made significant changes since then, consider running
      `edword index build` to update it."
```

### 2. Query Before Introducing Facts

Before writing: "Sarah brushed her dark hair from her face..."

```
[calls query_character("Sarah")]
# Check: What color is Sarah's hair in the index?
# If not specified → safe to introduce
# If "blonde" → warn the author or match existing
```

### 3. Verify After Writing Significant Scenes

After helping write a major scene:

```
[calls check_consistency(new_scene_text, "book1")]
# Report any conflicts to the author
```

### 4. Know Your Limitations

**You CAN:**
- Query the existing index
- Check new text against indexed facts
- Suggest the author rebuild the index

**You CANNOT:**
- Rebuild the index yourself (too expensive, author's decision)
- Modify the index
- Access chapters not yet indexed

### 5. Handle Missing Information Gracefully

If a query returns no data:

```
You: "I don't have information about Detective Torres in the index.
      This could mean:
      1. They haven't appeared in the story yet
      2. The chapter mentioning them hasn't been indexed
      3. They're a new character you're introducing

      Would you like to add them to the codex, or should I proceed
      with the details you have in mind?"
```

## Common Scenarios

### Scenario: Author Asks "What color are Sarah's eyes?"

```python
facts = query_character("Sarah")
if "eye_color" in facts:
    return f"According to the index, Sarah has {facts.eye_color} eyes,
             established in {facts.eye_color_source}."
else:
    return "I don't have Sarah's eye color in the index.
            This might not be established yet - would you like to decide now?"
```

### Scenario: Author Wants to Write a Flashback

```python
timeline = query_timeline("book1")
# Find the relevant event
# Check relative timing
# Help write with accurate "X months ago" references
```

### Scenario: Checking a New Chapter for Issues

```python
# Read the new chapter text
check_consistency(chapter_text, "book1")
# Report any conflicts with existing canon
```

### Scenario: Index Seems Outdated

```
You: "I noticed the index was built 2 weeks ago. If you've added new
      chapters or made significant revisions, you might want to update it:

      $ edword index build

      This only processes changed files, so it should be quick."
```

## Error Handling

### Index Not Found

```
"The manuscript index hasn't been built yet. Please run:
 $ edword index build

 This will take a few minutes for the first run."
```

### Character Not in Index

```
"I don't have [character] in my index. They might be:
 - A new character you're introducing
 - Mentioned in a chapter that isn't indexed yet
 - Spelled differently in the manuscript

 Would you like me to proceed with the information you provide?"
```

### Stale Index Warning

```
"The index is from [date] but the manuscript files have changed since then.
 Some information might be outdated. Consider running:
 $ edword index build"
```

## Integration with CLI

When the author has terminal access, you can suggest CLI commands:

| Situation | Suggest |
|-----------|---------|
| Need to update index | `edword index build` |
| Check for issues | `edword analyze --index` |
| View character details | `edword ask "Tell me about [character]"` |
| Debug missing data | `edword index show` |

## Performance Considerations

- Queries against the index are fast (milliseconds)
- `check_consistency` is fast for short text, slower for full chapters
- Never suggest rebuilding the index casually - it costs time and money
- Batch your queries when possible rather than making many small calls
