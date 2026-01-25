# Architecture Decision: Transparent Integration

## Design Philosophy

**The author should never leave their AI assistant.** Edword should be invisible infrastructure that "just works."

```
┌─────────────────────────────────────────────────────────────────┐
│                      Author's Experience                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Author: "Let's work on chapter 12. Can you check if           │
│           anything contradicts what we've established?"         │
│                                                                 │
│  AI: "I'll check the manuscript index..."                       │
│      [runs edword commands transparently]                       │
│      "Found one issue: In chapter 8 you said Sarah has          │
│       brown eyes, but chapter 12 says blue. Which is correct?"  │
│                                                                 │
│  Author: "Brown. Fix chapter 12."                               │
│                                                                 │
│  AI: [fixes it, updates index]                                  │
│      "Done. Anything else?"                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

The author never types a command. The author never thinks about indexes.

## Implementation: CLI as Universal Interface

The AI assistant runs CLI commands via Bash. This works with any AI that has shell access (Claude Code, Cursor, Codex, etc.).

### Why CLI-First (Not MCP-First)

| Aspect | CLI via Bash | MCP |
|--------|--------------|-----|
| Works with any AI | ✅ Yes | ❌ Requires MCP support |
| No extra setup | ✅ Just install edword | ❌ Configure MCP server |
| Structured output | ✅ Use `--json` flag | ✅ Native |
| Debugging | ✅ Author can run same commands | ❌ Hidden |

**Decision:** CLI is primary. MCP is optional optimization for AIs that support it.

### CLI Design for AI Consumption

Every command should support `--json` for structured output:

```bash
# Human-friendly (default)
$ edword index status
Index: book1 (31 chapters)
Last updated: 2 hours ago
Stale chapters: chapter-11, chapter-12

# AI-friendly
$ edword index status --json
{
  "book": "book1",
  "chapters_indexed": 31,
  "last_updated": "2026-01-24T08:30:00Z",
  "stale_chapters": ["chapter-11", "chapter-12"]
}
```

### Commands the AI Will Use

```bash
# Check if index needs updating
edword index status --json

# Build/update index (incremental by default)
edword index build

# Query character facts
edword query character "Greg Walsh" --json

# Query timeline
edword query timeline --book book1 --json

# Check text for consistency issues
echo "Sarah's blue eyes..." | edword check --book book1 --json

# Run analysis
edword analyze --index --json
```

### AI Behavior

The AI should:

1. **On session start:** Run `edword index status --json` to check freshness
2. **If stale:** Run `edword index build` (shows progress to user)
3. **During writing:** Use `edword query` and `edword check` as needed
4. **Periodically:** Run `edword analyze` to catch issues
5. **Always:** Be transparent - tell the user what it's doing

Example AI behavior:
```
AI: "Let me check your manuscript index...
     [running edword index status]

     The index is 3 days old and chapters 11-12 have changed.
     Updating now...
     [running edword index build]

     Done! Ready to help with your writing."
```

## MCP as Optional Enhancement

If the AI supports MCP, edword can provide a server for faster queries:

```python
# Only used if MCP is available and configured
@mcp.tool()
async def query_character(name: str) -> dict:
    """Faster than CLI for frequent queries."""
    ...
```

But this is **optional**. The CLI works for everything.

## Directory Detection

The AI needs to know where the manuscript is. Options:

1. **Explicit:** Author says "my book is in ~/novels/my-book"
2. **Auto-detect:** AI looks for `edword.yaml` in current directory
3. **Remember:** AI stores project location in conversation context

Recommended: Auto-detect + remember.

```bash
# AI runs this to find projects
find . -name "edword.yaml" -maxdepth 3
```

## Installation Experience

```
Author: "I want to use edword for my novel"

AI: "I'll help you set that up. First, let me install edword...
     [pip install edword]

     Now let's initialize your project...
     [cd ~/my-novel && edword init]

     And build the initial index (this takes a few minutes)...
     [edword index build]

     Done! I now have a memory of your story. I know about 15 characters,
     42 locations, and 156 timeline events. What would you like to work on?"
```

From then on, edword is invisible. The AI just uses it.

## Summary

| Who | Sees What |
|-----|-----------|
| Author | Seamless AI assistance, never types commands |
| AI Assistant | Runs CLI commands transparently |
| Power User | Can run CLI directly if they want |
| Developer | Can use MCP for custom integrations |

The CLI is the universal interface. Everything else is built on top of it.
