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

### Not Yet Implemented
- Query commands (`edword query character`, `edword query timeline`)
- Check command (`edword check` for real-time consistency)
- `--json` flag for AI consumption
- MCP server for AI assistant integration
- CoVe verification for high-severity findings

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

### Phase 2: Check Command
Real-time consistency checking for new text.

```bash
echo "Greg's blue eyes sparkled" | edword check --json
# Returns: conflict with indexed "brown eyes"
```

**Tasks:**
- [ ] Implement `edword check` - compare text against index
- [ ] Support stdin and argument input
- [ ] Return structured conflicts with evidence

### Phase 3: JSON Output Everywhere
Add `--json` flag to all commands for AI consumption.

**Tasks:**
- [ ] `edword index status --json`
- [ ] `edword index build --json` (progress + result)
- [ ] `edword analyze --json`
- [ ] `edword info --json`

### Phase 4: MCP Server (Optional)
For AI assistants with MCP support (faster than CLI).

```python
@mcp.tool()
def query_character(name: str) -> dict: ...

@mcp.tool()
def check_text(text: str) -> dict: ...
```

**Tasks:**
- [ ] Create `edword/mcp/server.py` with FastMCP
- [ ] Implement MCP tools that call same core logic as CLI
- [ ] Add `edword mcp serve` command
- [ ] Document MCP setup for Claude Code

### Phase 5: CoVe Verification
Chain-of-Verification for high-severity findings.

**Tasks:**
- [ ] Implement `edword/passes/verifier.py`
- [ ] Add `--verify` flag to analyze command
- [ ] Load text spans, generate questions, synthesize judgment

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
| `edword/index/` | Index building, storage, accumulation |
| `edword/passes/` | Analysis passes |
| `edword/llm/` | LLM provider abstraction |
| `edword/prompts/` | Extraction and verification prompts |
| `docs/architecture-decisions.md` | Why CLI-first |
| `docs/hybrid-verification-plan.md` | CoVe design |
