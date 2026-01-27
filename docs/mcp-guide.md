# Edword MCP Guide

*For AI assistants helping authors write novels*

## Setup

### Installation

Install edword with MCP support:

```bash
pip install edword[mcp]
# or with uv:
uv pip install edword[mcp]
```

### Claude Code Configuration

Add to your project's `.mcp.json` file in the project root:

```json
{
  "mcpServers": {
    "edword": {
      "command": "/path/to/your/venv/bin/edword",
      "args": ["mcp", "serve"],
      "env": {
        "EDWORD_PROJECT_ROOT": "/path/to/your/manuscript/project"
      }
    }
  }
}
```

Example for the Myriad Trilogy:

```json
{
  "mcpServers": {
    "edword": {
      "command": "/Users/dremy/books/edword/.venv/bin/edword",
      "args": ["mcp", "serve"],
      "env": {
        "EDWORD_PROJECT_ROOT": "/Users/dremy/books/myriad_trilogy"
      }
    }
  }
}
```

When you start Claude Code in the project, it will detect the MCP server and prompt you to approve it.

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "edword": {
      "command": "/path/to/your/venv/bin/edword",
      "args": ["mcp", "serve"],
      "env": {
        "EDWORD_PROJECT_ROOT": "/path/to/your/manuscript/project"
      }
    }
  }
}
```

### Codex CLI Configuration

For OpenAI's Codex CLI, create or edit `~/.codex/config.yaml`:

```yaml
mcp_servers:
  edword:
    command: /path/to/your/venv/bin/edword
    args:
      - mcp
      - serve
    env:
      EDWORD_PROJECT_ROOT: /path/to/your/manuscript/project
```

Or use the command-line flag:
```bash
codex --mcp-server "edword:/path/to/edword mcp serve" "Query Greg Walsh's facts"
```

### Gemini CLI Configuration

For Google's Gemini CLI, create or edit `~/.gemini/config.yaml`:

```yaml
mcp_servers:
  edword:
    command: /path/to/your/venv/bin/edword
    args:
      - mcp
      - serve
    env:
      EDWORD_PROJECT_ROOT: /path/to/your/manuscript/project
```

Or use environment variables:
```bash
export GEMINI_MCP_SERVERS='{"edword":{"command":"/path/to/edword","args":["mcp","serve"],"env":{"EDWORD_PROJECT_ROOT":"/path/to/project"}}}'
gemini -p "What do we know about Greg Walsh?"
```

### Generic MCP Setup

For any MCP-compatible client, edword exposes a stdio-based MCP server:

```bash
# Start the MCP server (stdio transport)
edword mcp serve

# With explicit project root
EDWORD_PROJECT_ROOT=/path/to/project edword mcp serve
```

The server follows the [Model Context Protocol](https://modelcontextprotocol.io/) specification and should work with any compliant client.

### Verifying Setup

After configuration, restart your AI assistant. The edword tools should appear in the available tools list. You can verify by asking the assistant to check the index status:

```
"Use edword to check the manuscript index status"
```

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

### `edword_query_character(name, book?, project_root?)`

Look up everything known about a character.

```python
# Example usage
facts = edword_query_character(name="Greg Walsh")
# Returns: age, relationships, appearances, state changes, etc.
```

**When to use:**
- Before writing dialogue for a character
- When the author asks "What do we know about X?"
- To check a character's current state (alive? injured? location?)

### `edword_query_timeline(book?, chapter_range?, limit?, project_root?)`

Get timeline events, optionally filtered by chapter range.

```python
events = edword_query_timeline(book="book1", chapter_range="1-10")
# Returns: events with relative ordering, dates, durations
```

**When to use:**
- When writing scenes that reference past events
- To check "how long ago" calculations
- To verify event sequences

### `edword_query_location(name, book?, project_root?)`

Look up location details.

```python
location = edword_query_location(name="Cascade Labs")
# Returns: description, characters present, significance
```

**When to use:**
- Before writing scenes in a specific location
- To check what details have been established about a place

### `edword_query_artifact(name, book?, project_root?)`

Look up significant items or artifacts.

```python
artifact = edword_query_artifact(name="Neural Headset")
# Returns: status, holder, significance
```

**When to use:**
- When referencing important objects in the story
- To check an item's current state or location

### `edword_query_world(term, book?, as_of_chapter?, project_root?)`

Search world-building facts and terminology.

```python
facts = edword_query_world(term="neural interface", as_of_chapter="5")
# Returns: world facts and terminology established by chapter 5
```

**When to use:**
- When writing about technology, magic systems, or world rules
- To check what the reader knows at a given point in the story

### `edword_query_search(query, book?, limit?, project_root?)`

Search across all index dimensions.

```python
results = edword_query_search(query="Myriad")
# Returns: characters, locations, events, artifacts, facts, terms
```

**When to use:**
- When you need to find anything related to a topic
- For open-ended exploration of the story world

### `edword_check_text(text, book?, project_root?)`

Check if new text contradicts the existing index.

```python
result = edword_check_text(
    text="Sarah's blue eyes sparkled in the moonlight.",
    book="book1"
)
# Returns: {has_conflicts: true, conflicts: [{field: "eye_color", indexed: "brown", new: "blue"}]}
```

**When to use:**
- Before suggesting new descriptive passages
- When introducing facts about characters
- After writing a significant scene

### `edword_index_status(project_root?)`

Check if the index exists and when it was last updated.

```python
status = edword_index_status()
# Returns: {project_name: "...", books: [...], total_chapters: 31, stale: false}
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
[calls edword_index_status()]
You: "The index was last updated 3 days ago and covers 31 chapters.
      If you've made significant changes since then, consider running
      `edword index build` to update it."
```

### 2. Query Before Introducing Facts

Before writing: "Sarah brushed her dark hair from her face..."

```
[calls edword_query_character(name="Sarah")]
# Check: What color is Sarah's hair in the index?
# If not specified → safe to introduce
# If "blonde" → warn the author or match existing
```

### 3. Verify After Writing Significant Scenes

After helping write a major scene:

```
[calls edword_check_text(text=new_scene_text, book="book1")]
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
facts = edword_query_character(name="Sarah")
if facts.get("found") and facts.get("character"):
    # Look for eye_color in facts
    for fact in facts["character"].get("facts", []):
        if fact["predicate"] == "eye_color":
            return f"According to the index, Sarah has {fact['value']} eyes."
return "I don't have Sarah's eye color in the index. This might not be established yet."
```

### Scenario: Author Wants to Write a Flashback

```python
timeline = edword_query_timeline(book="book1")
# Find the relevant event
# Check relative timing
# Help write with accurate "X months ago" references
```

### Scenario: Checking a New Chapter for Issues

```python
# Read the new chapter text
result = edword_check_text(text=chapter_text, book="book1")
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

### Index Needs Upgrade (Schema Version Mismatch)

When edword is upgraded, the index schema may change. Tools will return a special error:

```json
{
  "error": true,
  "error_type": "IndexVersionMismatch",
  "message": "Edword has been upgraded with improved analysis capabilities.",
  "needs_rebuild": true,
  "book": "book1",
  "action": "Run 'edword index build --book book1' to rebuild"
}
```

**How to handle:**
```
"The edword index needs to be rebuilt to use the latest analysis features.
 This happens after edword upgrades. Please run:

 $ edword index build

 This will re-analyze all chapters with the improved extraction."
```

The `needs_rebuild: true` flag lets you detect this programmatically and suggest the rebuild to the author.

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
| View character details | `edword query character "Greg Walsh"` |
| Debug missing data | `edword index show` |

## Performance Considerations

- Queries against the index are fast (milliseconds)
- `edword_check_text` is fast for short text, slower for full chapters
- Never suggest rebuilding the index casually - it costs time and money
- Batch your queries when possible rather than making many small calls

## Tool Parameter Reference

All tools accept an optional `project_root` parameter. If not provided, the tool uses:
1. The `EDWORD_PROJECT_ROOT` environment variable (set in MCP config)
2. Auto-discovery by searching for `edword.yaml` up from the current directory

For most configurations, you don't need to pass `project_root` explicitly.
