# Edword - AI Assistant Configuration

## Project Overview

Edword is an AI-powered editorial memory for long-form fiction. It solves the problem of maintaining consistency across book-length documents that exceed LLM context windows.

## Architecture

Two-phase pipeline:
1. **Index Building**: LLM extracts facts chapter-by-chapter into structured JSON
2. **Analysis**: Python passes analyze the accumulated index for inconsistencies

See `docs/dev-plan.md` for current status and roadmap.

## Key Principles

1. **CLI-first** - Works with any AI that has shell access
2. **`--json` for AI** - Structured output for programmatic consumption
3. **Transparent** - Author can run same commands the AI uses
4. **Incremental** - Only re-process changed chapters

## Development

```bash
# Install in dev mode
cd ~/books/edword
pip install -e .

# Run tests
pytest

# Test with Myriad Trilogy
cd ~/books/myriad_trilogy
edword index build
edword analyze --index
```

## Dogfood Project

Primary test case: **Myriad Trilogy** (`/Users/dremy/books/myriad_trilogy/`)

This trilogy is being written with AI assistance and serves as the real-world test for edword. When making changes to edword, test against the trilogy.

## File Structure

```
edword/
├── cli.py              # All CLI commands (typer)
├── config.py           # Configuration loading
├── discovery.py        # Project structure detection
├── index/              # Index building & storage
│   ├── extractor.py    # LLM fact extraction
│   ├── accumulator.py  # Merge chapter facts
│   ├── storage.py      # Index persistence
│   └── schema.py       # Index data structures
├── passes/             # Analysis passes
│   ├── continuity_index.py
│   └── codex_validation_index.py
├── llm/                # LLM provider abstraction
│   └── providers.py    # Claude/Gemini CLI wrappers
├── prompts/            # LLM prompt templates
└── mcp/                # MCP server (planned)
```

## Current Priority

Phase 1: Query Commands - see `docs/dev-plan.md`

Add `edword query character`, `edword query timeline`, etc. with `--json` output for AI consumption.
