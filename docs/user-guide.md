# Edword User Guide

*For authors working with AI writing assistants*

## Overview

Edword helps you and your AI assistant maintain consistency in your manuscript. It builds a "memory" of your story that your AI can query while helping you write.

## Quick Start

### 1. Set Up Your Project

```bash
cd ~/my-novel
edword init
```

This creates `edword.yaml` with sensible defaults.

### 2. Build the Index

```bash
edword index build
```

This reads all your chapters and extracts facts about characters, timeline, locations, etc. It takes a few minutes the first time, but subsequent runs only process changed chapters.

### 3. Check for Issues

```bash
edword analyze --index
```

This compares your manuscript against your codex (world bible) and finds inconsistencies.

---

## Working with an AI Assistant

### The Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. YOU: Build/update the index                                 │
│     $ edword index build                                        │
│     (Run this after significant writing sessions)               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. AI ASSISTANT: Query the index while helping you write       │
│     "What color are Sarah's eyes?"                              │
│     "When did the protagonist arrive in London?"                │
│     "Check if this new paragraph contradicts anything"          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. YOU: Periodically check for issues                          │
│     $ edword analyze --index --verify                           │
│     (Weekly or before major milestones)                         │
└─────────────────────────────────────────────────────────────────┘
```

### When to Rebuild the Index

Rebuild after:
- Finishing a chapter
- Major revisions to existing chapters
- Adding new characters or plot points

You don't need to rebuild:
- For every small edit
- While actively writing a scene (the AI uses the existing index)

### Commands Your AI Assistant Might Run

If your AI has access to the terminal, it might run:

```bash
# Quick check of index status
edword index show

# Query specific character (returns JSON for AI parsing)
edword query character "Maya" --json

# Query timeline events
edword query timeline --json

# Search across everything
edword query search "neural interface" --json

# Check a specific chapter
edword analyze --chapters 5 --index
```

---

## Query Commands

Query commands let you (or your AI) look up facts from the index. All support `--json` for structured output.

### Query a Character

```bash
# Basic usage
edword query character "Greg Walsh"

# JSON output for AI consumption
edword query character "Greg Walsh" --json

# Search by alias
edword query character "Dr. Walsh" --json
```

Returns: canonical name, facts, relationships, appearances, state changes.

### Query Timeline

```bash
# All events
edword query timeline --json

# Filter by chapter range
edword query timeline --chapters "1-5" --json

# Limit results
edword query timeline --limit 10 --json
```

Returns: events with time references and ordering constraints.

### Query Location

```bash
edword query location "Cascade Labs" --json
```

Returns: location details, characters present, description.

### Query Artifact

```bash
edword query artifact "Neural Headset" --json
```

Returns: artifact status, holder, evidence.

### Query World/Terminology

```bash
# All matching entries
edword query world "Myriad" --json

# Filter by chapter (show state as of chapter 5)
edword query world "Myriad" --as-of 5 --json
```

Returns: matching world facts and terminology definitions, with chapter provenance. Use `--as-of` to see the world state at a specific point in the story.

### Search Across Everything

```bash
edword query search "neural interface" --json
```

Searches characters, locations, events, artifacts, world facts, and terminology. Returns matches from each dimension.

---

## Project Structure

Edword expects this layout:

```
my-novel/
├── edword.yaml              # Configuration
├── manuscripts/
│   └── book1/
│       └── chapters/
│           ├── chapter-01.md
│           ├── chapter-02.md
│           └── ...
├── codex/                   # Your world bible (optional but recommended)
│   ├── characters/
│   │   ├── protagonist.md
│   │   └── ...
│   ├── locations/
│   ├── timeline/
│   └── ...
└── .edword/                 # Generated (add to .gitignore)
    ├── index/               # Extracted facts
    ├── hashes.json          # Tracks which files changed
    └── cache/               # LLM response cache
```

---

## The Codex (World Bible)

Your codex is the "ground truth" for your story. Edword compares the manuscript against it.

### Character Files

```markdown
# Sarah Chen

**Age:** 32
**Occupation:** Detective
**Appearance:** Black hair, brown eyes, athletic build

## Relationships
- Partner: Detective Mike Torres
- Sister: Dr. Emily Chen

## Background
Former military intelligence, joined NYPD in 2019.
```

### Why Maintain a Codex?

1. **Consistency**: Edword catches when the manuscript contradicts the codex
2. **AI Reference**: Your AI assistant can look up facts
3. **Your Memory**: After 100k words, you'll forget details

---

## Common Workflows

### "I just finished writing chapter 10"

```bash
edword index build              # Updates index (only reprocesses chapter 10)
edword analyze --index          # Check for any new issues
```

### "I'm about to write a scene with Sarah"

Ask your AI: "What do we know about Sarah from the index?"

Or run:
```bash
edword ask "Summarize everything about Sarah Chen"
```

### "I think I introduced a plot hole"

```bash
edword analyze continuity-index --verify --chapters 5-10
```

This runs continuity checking on chapters 5-10 with LLM verification.

### "I changed a character's backstory"

1. Update the codex file
2. Run: `edword index build --force` (rebuilds everything)
3. Run: `edword analyze codex-validation-index`

---

## Tips

### Speed Up Index Building

```bash
# Process chapters in parallel
edword index build --workers 4

# Only index one book
edword index build --book book1
```

### Reduce False Positives

- Keep your codex up to date
- Use the `--verify` flag to let the LLM filter false positives
- Review and dismiss recurring false positives

### Save Money on LLM Calls

- Use `haiku` model for extraction (fast, cheap)
- Use `sonnet` for verification (only on errors)
- Incremental indexing means you only pay for changed chapters

---

## Troubleshooting

### "Index is out of date"

Run: `edword index build`

### "Too many false positives"

Run with verification: `edword analyze --verify`

### "AI assistant can't find character X"

The character might not be extracted yet. Check:
```bash
edword index show | grep "character-name"
```

If missing, the chapter mentioning them might need re-indexing:
```bash
edword index build --force --chapters 5
```

---

## Getting Help

```bash
edword --help           # All commands
edword index --help     # Index commands
edword analyze --help   # Analysis commands
```
