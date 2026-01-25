# Edword

*AI-powered editorial analysis for book manuscripts.*

Edword is a CLI tool that uses LLMs to perform systematic editorial analysis on book manuscripts. It can check for continuity errors, validate facts against a codex (world bible), track character consistency, and more.

## Architecture: Memory-Augmented Extraction with Chain-of-Verification

Edword solves a fundamental problem: **book-length documents exceed LLM context windows**. Our approach:

```
Phase 1: Index Building (One-time, Cached)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Chapter 1 ──┐
Chapter 2 ──┼── LLM Extract ──► Python Accumulate ──► Knowledge Graph
Chapter N ──┘   (per chapter)    (deterministic)       (JSON index)


Phase 2: Analysis + Verification (On-demand)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Index ──► Python Analysis ──► Candidates ──► CoVe Verify ──► Findings
          (instant)           (may have FP)  (LLM precision)  (verified)
```

**Key innovations:**
- **Delta extraction**: LLM extracts only from current chapter (avoids context limits)
- **Deterministic accumulation**: Python merges facts (no LLM degradation)
- **Chain-of-Verification**: LLM verifies candidates with targeted questions (reduces false positives)

Based on established research: [LIGHT Framework](https://arxiv.org/abs/2510.27246), [Chain-of-Verification](https://learnprompting.org/docs/advanced/self_criticism/chain_of_verification), [FEVER](https://fever.ai/). See [docs/research.md](docs/research.md) for details.

## Features

- **Index-Based Analysis**: Process full books by extracting structured facts chapter-by-chapter, then running analysis passes on the accumulated index
- **Ad-Hoc Exploration (RLM)**: Ask questions about your manuscript using the Recursive Language Model pattern
- **Codex Validation**: Compare manuscript facts against your world bible
- **Continuity Checking**: Detect timeline inconsistencies and contradictions
- **Multiple LLM Support**: Works with Claude and Gemini via their CLI tools
- **Incremental Processing**: Only re-index changed chapters

## Prerequisites

Edword uses CLI-based LLM access (no API keys required if you have a subscription):

```bash
# Install Claude CLI (recommended)
npm install -g @anthropic-ai/claude-code

# Or Gemini CLI
pip install gemini-cli
```

Verify installation:
```bash
claude --version
gemini --version
```

## Installation

```bash
cd ~/books/edword
pip install -e .
```

## Quick Start

```bash
# Navigate to your book project
cd ~/books/my_novel

# Initialize edword configuration
edword init

# Show project structure
edword info

# Build the index (extracts facts from all chapters)
edword index build

# Run analysis passes
edword analyze

# Ask an ad-hoc question
edword ask "What is the protagonist's motivation in chapter 5?"
```

## Project Structure

Edword expects a conventional project structure:

```
my_novel/
├── edword.yaml          # Configuration (created by `edword init`)
├── manuscripts/
│   ├── book1/
│   │   └── chapters/
│   │       ├── chapter-01.md
│   │       ├── chapter-02.md
│   │       └── ...
│   └── book2/
│       └── chapters/
│           └── ...
├── codex/               # World bible (optional but recommended)
│   ├── characters/
│   │   ├── protagonist.md
│   │   └── ...
│   ├── locations/
│   ├── timeline/
│   └── ...
└── .edword/             # Generated data (gitignore this)
    ├── index/           # Extracted facts per chapter
    └── cache/           # LLM response cache
```

## CLI Commands

### Index Commands (Build the Knowledge Base)

```bash
# Build index for all books
edword index build

# Build index for specific book
edword index build --book book1

# Force rebuild (ignore cache)
edword index build --force

# Show index summary
edword index show

# Show specific chapter's index
edword index show --chapter 5

# Clear all index files
edword index clear
```

### Analysis Commands (Run Editorial Passes)

```bash
# Run all enabled passes
edword analyze

# Run specific passes
edword analyze continuity
edword analyze continuity codex_validation

# Analyze specific book or chapters
edword analyze --book book1
edword analyze --chapters 1-8

# Save report to file
edword analyze --save

# Force RLM mode (ad-hoc, bypasses index)
edword analyze --mode rlm
```

### Ad-Hoc Exploration (RLM Mode)

```bash
# Ask a question about the manuscript
edword ask "What motivates Greg in chapter 5?"

# Scope to specific book/chapter
edword ask --book book1 --chapter 5 "What happens in this chapter?"
```

### Other Commands

```bash
# Initialize configuration
edword init

# Show project info
edword info

# List available passes
edword passes

# Manage reports
edword report list
edword report view latest
```

## Configuration

Create `edword.yaml` in your project root (or run `edword init`):

```yaml
project:
  name: "My Novel"

paths:
  manuscripts: "manuscripts/"
  codex: "codex/"
  index: ".edword/index/"

llm:
  provider: "claude"

  # Index building - high volume, uses fast model
  index:
    provider: "claude"
    model: "haiku"
    max_retries: 3

  # RLM mode - ad-hoc exploration
  rlm:
    provider: "claude"
    model: "sonnet"
    recursive_model: "haiku"
    max_iterations: 25

  # Verification of high-severity findings
  verification:
    provider: "claude"
    model: "sonnet"
    enabled: true

index:
  dimensions:
    - characters
    - timeline
    - locations
    - artifacts
    - world_facts
    - terminology
    - narrative
  incremental: true

passes:
  continuity:
    enabled: true
  codex_validation:
    enabled: true
  prose_quality:
    enabled: true
    filter_words: ["felt", "saw", "heard", "realized", "seemed"]
  character_voice:
    enabled: true
    pov_characters: ["Protagonist Name"]
```

## How It Works

### Two Analysis Modes

**1. Index-Based Analysis (Default)**

For systematic, full-book analysis:

1. **Index Building**: Each chapter is processed independently by a fast LLM (Haiku) to extract structured facts: characters, timeline events, locations, artifacts, world facts, terminology, and narrative elements.

2. **Accumulation**: A Python-based accumulator merges chapter indices, resolving entities by canonical ID and detecting contradictions.

3. **Analysis Passes**: Passes compare the accumulated index against the codex (ground truth) to find inconsistencies. No LLM needed - just structured comparison.

4. **Verification**: High-severity findings are optionally verified by an RLM that reads the original text.

**2. RLM Mode (Ad-Hoc)**

For specific questions:

1. The manuscript section is loaded into context
2. An LLM explores it via Python code execution (REPL pattern)
3. For large documents, recursive calls process chunks
4. Returns a direct answer to your question

### Why Two Modes?

- **Index mode** scales to full books (150K+ chars) by processing chapter-by-chapter
- **RLM mode** is better for targeted questions that don't need full-book context
- Both can work together: index finds candidates, RLM verifies

## Analysis Passes

| Pass | Purpose | What It Checks |
|------|---------|----------------|
| `continuity` | Timeline consistency | Dates, "X months ago", event sequence, contradictions |
| `codex_validation` | Manuscript matches codex | Names, ages, relationships, facts |
| `character_voice` | Voice consistency | Vocabulary, POV violations, speech patterns |
| `prose_quality` | Writing quality | Filter words, repetition, passive voice |
| `pacing` | Rhythm analysis | Scene length, tension curves |
| `structure` | Story structure | Act beats, inciting incident |
| `foreshadowing` | Thread tracking | Setups, payoffs, orphaned threads |

## Example Output

```
$ edword analyze continuity codex_validation

╭─────────────────────────────────────────────────────╮
│              Edword Analysis Report                 │
│           My Novel / Book 1                         │
╰─────────────────────────────────────────────────────╯

┌─────────────── Summary ───────────────┐
│  Errors: 2    Warnings: 8    Info: 12 │
└───────────────────────────────────────┘

[continuity] Character age inconsistency
  Chapter 8: DOB 1988 implies age 36-37
  Chapter 4: "forty-two years old"
  → Update DOB to 1983 or fix stated age

[codex_validation] Service duration mismatch
  Chapter 8: "eight years army intelligence"
  Codex: 4 years army (ages 18-22)
  → Update manuscript to match codex
```

## Tips

### Speed Up Index Building

- Use `--book` to index one book at a time
- Enable incremental mode (default) to skip unchanged chapters
- Use Haiku for extraction (fast and cheap)

### Improve Accuracy

- Keep your codex up to date - it's the ground truth
- Review and correct index files manually if needed
- Use verification for high-severity findings

### Debugging

```bash
# See what edword detects
edword info

# Check index contents
edword index show --chapter 1

# View a specific report
edword report view latest
```

## Interfaces

Edword supports multiple interfaces for different use cases:

### CLI (Human Users)
Primary interface for authors and editors. See commands above.

### MCP Server (AI Assistants) - Planned
For AI writing assistants (Claude Code, etc.) to check consistency in real-time:

```python
# Tools available via MCP
check_consistency(book, chapters)  # Run analysis passes
verify_finding(finding_id)         # Verify specific finding
get_character_facts(character)     # Query character data
get_timeline(book)                 # Query timeline events
```

### Python API (Programmatic)
For integration into other tools:

```python
from edword import EdwordProject

project = EdwordProject("path/to/manuscript")
project.build_index()
findings = project.analyze(passes=["continuity-index"], verify=True)
```

## Documentation

### For Authors
- [User Guide](docs/user-guide.md) - Getting started, workflows, tips

### For AI Assistants
- [MCP Guide](docs/mcp-guide.md) - How to use edword tools effectively

### Technical
- [Architecture Plan](docs/hybrid-verification-plan.md) - System design, CoVe verification
- [Architecture Decisions](docs/architecture-decisions.md) - CLI/MCP integration rationale
- [Research Notes](docs/research.md) - Related work, novelty claims, evaluation plan

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy edword
```

## Research

This project explores scalable consistency checking for long documents. We're investigating whether the combination of delta extraction, deterministic accumulation, and Chain-of-Verification represents a novel contribution to the field.

See [docs/research.md](docs/research.md) for related work, research questions, and evaluation plans.

## License

MIT
