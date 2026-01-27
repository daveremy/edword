# Edword Development Plan

## Vision

AI-powered editorial memory for long-form fiction. The author never leaves their AI assistant - edword provides invisible infrastructure that "just works."

## Current State (v0.2)

### Implemented
- **Index Building**: `edword index build` - LLM extracts facts chapter-by-chapter
- **Index Management**: `edword index show`, `edword index clear`
- **Analysis Passes**: `edword analyze` with `--index` flag
  - continuity_index: detects contradicting facts
  - codex_validation_index: compares manuscript to codex
- **RLM Mode**: `edword ask` for ad-hoc queries (not index-based)
- **Project Discovery**: `edword info`, `edword init`
- **LLM Providers**: Claude CLI, Gemini CLI support

### Recently Added
- CoVe verification for high-severity findings (`--verify` flag)

---

## Development Phases

### Phase 1: Query Commands (COMPLETE)
Add structured query commands for AI assistants to retrieve indexed data.

```bash
edword query character "Greg Walsh" --json
edword query timeline --book book1 --json
edword query location "the lab" --json
edword query artifact "Neural Headset" --json
edword query world "Myriad" --json
edword query search "neural interface" --json
```

**Tasks:**
- [x] Implement `query character` - return facts, relationships, appearances
- [x] Implement `query timeline` - return events with ordering
- [x] Implement `query location` - return location details
- [x] Implement `query artifact` - return artifact/item details
- [x] Implement `query world` - search world facts and terminology
- [x] Implement `query search` - free-text search across index
- [x] Add `--json` flag to all query commands
- [x] Add unit tests (52 tests passing)
- [x] Update user-guide.md documentation

### Phase 2: Check Command (COMPLETE)
Real-time consistency checking for new text.

```bash
echo "Greg's blue eyes sparkled" | edword check --json
# Returns: conflict with indexed "brown eyes"
```

**Tasks:**
- [x] Implement `edword check` - compare text against index
- [x] Support stdin and argument input
- [x] Return structured conflicts with evidence
- [x] Proximity-based negation detection (avoids false positives)
- [x] Single-pass O(N) character mention finding
- [x] Add unit tests (88 tests in test_check.py)
- [x] Create shared `common.py` module for code reuse

### Phase 3: JSON Output Everywhere (COMPLETE)
Add `--json` flag to all commands for AI consumption.

**Tasks:**
- [x] `edword index show --json` (summary and chapter detail)
- [x] `edword index build --json` (progress + result + contradiction details)
- [x] `edword analyze --json`
- [x] `edword info --json`

### Phase 4: MCP Server (COMPLETE)
**Priority integration for AI writing assistants.** MCP provides seamless tool access - the AI calls `query_character("Greg")` directly instead of spawning shell commands and parsing JSON.

CLI remains valuable for manual usage, scripting, and AI assistants without MCP support. But MCP is how the assistant *should* interact during a writing session.

**Tools implemented:**
- `edword_query_character` - Look up character facts, relationships, appearances
- `edword_query_timeline` - Get timeline events with filtering
- `edword_query_location` - Look up location details
- `edword_query_artifact` - Look up significant items
- `edword_query_world` - Search world facts and terminology
- `edword_query_search` - Cross-dimensional search
- `edword_check_text` - Check text for contradictions
- `edword_index_status` - Get project/index status with staleness detection

**Tasks:**
- [x] Create `edword/mcp/server.py` with FastMCP
- [x] Implement MCP tools that call same core logic as CLI
- [x] Add `edword mcp serve` command
- [x] Document MCP setup for Claude Code, Claude Desktop, Codex, Gemini
- [x] Add to trilogy's `.mcp.json`
- [x] Add unit tests (24 tests in test_mcp.py)

### Phase 5: CoVe Verification (COMPLETE)
Chain-of-Verification for high-severity findings.

**Implementation:**
- 4-step verification: load evidence, generate questions, answer independently, synthesize verdict
- Verdicts: confirmed (real issue), dismissed (false positive), uncertain (need more context)
- Error handling: returns uncertain on LLM failure instead of crashing

**Tasks:**
- [x] Implement `edword/passes/verifier.py` - CoVeVerifier class
- [x] Add `--verify`, `--verify-all`, `--no-verify`, `--verify-model` flags to analyze command
- [x] Load text spans from chapter files based on finding location
- [x] Generate verification questions, answer independently, synthesize judgment
- [x] Add MCP tool `edword_verify_finding` for AI assistant integration
- [x] Add prompt templates: `cove_generate_questions.md`, `cove_answer_question.md`, `cove_synthesize.md`
- [x] Add tag parsers: `TAG_QUESTIONS`, `TAG_ANSWER`, `TAG_VERDICT` in parsing.py
- [x] Extend Finding dataclass with optional `verification` field
- [x] Update CLI serialization to include verification results in JSON output
- [x] Add unit tests (28 tests in test_verifier.py)

### Phase 6: Schema Versioning (COMPLETE)
Automatic detection and handling of index schema changes after edword upgrades.

**Implementation:**
- `INDEX_SCHEMA_VERSION` constant (currently v1) in `edword/index/schema.py`
- `schema_version` field on `ChapterIndex` and `AccumulatedIndex` (defaults to 0 for legacy)
- `IndexVersionMismatch` exception raised when loading outdated indices
- CLI prompts for rebuild with progress indicator; MCP returns `needs_rebuild: true`
- `needs_reindex()` checks version even when file hash matches

**Tasks:**
- [x] Add `INDEX_SCHEMA_VERSION` constant and `schema_version` field to models
- [x] Update `needs_reindex()` to check schema version
- [x] Add `IndexVersionMismatch` exception and version check in `load_index()`
- [x] Add `handle_version_mismatch()` CLI helper with progress indicator
- [x] Update MCP `handle_error()` to return `needs_rebuild: true`
- [x] Update `index show` to display Status column (Current/Outdated)
- [x] Add unit tests (21 tests in test_version.py)

**User experience:**
- Positive messaging: "Edword has been upgraded with improved analysis"
- Interactive rebuild prompt with time warning and progress indicator
- `index show` displays version status without blocking

---

## Architecture Principles

1. **CLI-first**: Works with any AI that has shell access
2. **--json for AI**: Structured output for programmatic consumption
3. **MCP optional**: Enhancement for supporting AIs, not required
4. **Transparent**: Author can run same commands AI uses
5. **Incremental**: Only re-process changed chapters

---

## Dogfooding

Primary test case: **Myriad Trilogy** (`/Users/dremy/books/myriad_trilogy/`)

- 3 books, ~100k words total
- Complex character web, timeline, world-building
- Active development - real issues to find

Run regularly:
```bash
cd ~/books/myriad_trilogy
edword index build
edword analyze --index
```

---

## Success Criteria

1. **Author never types commands** - AI handles edword transparently
2. **Finds real issues** - Catches continuity errors in Myriad Trilogy
3. **Fast enough** - Queries return in <1s, full analysis in <30s
4. **AI-friendly** - `--json` output is easy to parse and act on

---

## Files Reference

| File | Purpose |
|------|---------|
| `edword/cli.py` | All CLI commands |
| `edword/common.py` | Shared utilities (load_index, base exceptions) |
| `edword/query.py` | Query operations (character, timeline, location, etc.) |
| `edword/check.py` | Real-time consistency checking |
| `edword/index/` | Index building, storage, accumulation |
| `edword/passes/` | Analysis passes |
| `edword/llm/` | LLM provider abstraction |
| `edword/prompts/` | Extraction and verification prompts |
| `docs/architecture-decisions.md` | Why CLI-first |
| `docs/hybrid-verification-plan.md` | CoVe design |
