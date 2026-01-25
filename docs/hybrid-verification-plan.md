# Hybrid Index-Verification Architecture (v2)

## Overview

A two-phase architecture for scalable consistency checking of long-form documents, combining structured extraction with Chain-of-Verification (CoVe) style LLM verification.

**Based on established research:**
- LIGHT Framework (2025) - Memory-augmented LLM processing
- Chain-of-Verification (Meta, 2024-2026) - Self-verification patterns
- TLDM Benchmark (2025) - Long-context limitations
- Hybrid LLM + Deterministic Systems (2026)

---

## Architecture

### Three-Tier Memory Model (inspired by LIGHT)

```
┌─────────────────────────────────────────────────────────────────┐
│                     LONG-TERM MEMORY                            │
│                  (Accumulated Index - JSON)                     │
│  Characters, Timeline, Locations, Artifacts, World Facts        │
│  Persisted to disk, cached by file hash                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SHORT-TERM MEMORY                            │
│                 (Current Chapter Context)                       │
│  Text spans relevant to current verification                    │
│  Loaded on-demand, discarded after use                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SCRATCHPAD                                 │
│              (Active Verification State)                        │
│  Current candidates, verification questions, partial results    │
│  Ephemeral, used during analysis passes                         │
└─────────────────────────────────────────────────────────────────┘
```

### Two-Phase Pipeline

```
Phase 1: Index Building (One-time, Cached)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Chapter 1 ──┐
Chapter 2 ──┼── LLM Delta Extract ──► Python Accumulate ──► Accumulated Index
Chapter N ──┘   (Haiku, fast)          (deterministic)       (JSON on disk)


Phase 2: Analysis + Verification (On-demand)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                    ┌──────────────────────┐
Accumulated Index ──► Python Pass ──► Candidate Findings   │
                      (instant)     │ (may have false+)    │
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │  CoVe Verification   │
                                    │  1. Load text spans  │
                                    │  2. Generate Qs      │
                                    │  3. Answer Qs        │
                                    │  4. Final judgment   │
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │  Verified Findings   │
                                    │  (high precision)    │
                                    └──────────────────────┘
```

---

## Chain-of-Verification (CoVe) Implementation

Based on Meta's CoVe research, verification follows four steps:

### Step 1: Draft Assessment
```
Given this potential inconsistency:
  "Greg's age is stated as 35 in chapter 11b but 45 in codex"

Initial assessment: This appears to be an age contradiction.
```

### Step 2: Generate Verification Questions
```
Q1: What is the exact quote containing "35" in chapter 11b?
Q2: Does the context suggest this is literal age or something else (duration, metaphor)?
Q3: What is the exact quote about Greg's age in the codex?
Q4: Could both statements be true in different contexts?
```

### Step 3: Answer Questions Independently
Each question answered without seeing other answers (reduces bias):
```
A1: "We've kept you alive for thirty-five years" - spoken by Greg's internal entities
A2: Context suggests duration entities have existed, not Greg's literal age
A3: Codex states "Age: 45" in character profile
A4: Yes - Greg is 45, entities have been with him for 35 years (since age 10)
```

### Step 4: Final Verified Judgment
```
VERIFIED: No (false positive)
CONFIDENCE: High
EXPLANATION: The "35 years" refers to how long Greg's internal entities
have been with him, not his chronological age. Greg is 45, and his
entities emerged when he was approximately 10 years old.
```

---

## Implementation Plan

### 1. Verifier Module (`edword/passes/verifier.py`)

```python
@dataclass
class VerificationResult:
    original_finding: Finding
    verified: bool
    confidence: Literal["high", "medium", "low"]
    explanation: str
    verification_questions: list[str]
    evidence_spans: list[str]

class CoVeVerifier:
    """Chain-of-Verification style finding verifier."""

    def verify(self, finding: Finding, manuscript: Manuscript) -> VerificationResult:
        # 1. Load relevant text spans
        spans = self._fetch_evidence_spans(finding, manuscript)

        # 2. Generate verification questions
        questions = self._generate_questions(finding, spans)

        # 3. Answer each question independently
        answers = [self._answer_question(q, spans) for q in questions]

        # 4. Synthesize final judgment
        return self._synthesize_judgment(finding, questions, answers, spans)
```

### 2. CLI Integration

```bash
# Default: verify errors only
edword analyze continuity-index --verify

# Verify all findings (slower)
edword analyze continuity-index --verify-all

# Skip verification (fast mode)
edword analyze continuity-index --no-verify

# Verify with specific model
edword analyze continuity-index --verify --verify-model sonnet
```

### 3. MCP Server (for AI assistant integration)

```python
# edword/mcp/server.py
@mcp.tool()
async def check_consistency(book: str, chapters: Optional[str] = None) -> dict:
    """Check manuscript for consistency issues."""
    # Returns structured findings for AI consumption

@mcp.tool()
async def verify_finding(finding_id: str) -> dict:
    """Verify a specific finding with CoVe."""
    # Returns verification result

@mcp.tool()
async def get_character_facts(character: str) -> dict:
    """Get all known facts about a character from index."""
    # Returns character data for AI reference
```

---

## Interfaces

### CLI (Human Users)
Primary interface for authors and editors:
- `edword index build` - Build/update index
- `edword analyze` - Run analysis passes
- `edword ask` - Ad-hoc RLM queries

### MCP Server (AI Assistants)
For AI writing assistants (Claude, etc.):
- Structured tool calls
- Real-time consistency checking during writing
- Character/timeline lookups

### Python API (Programmatic)
For integration into other tools:
```python
from edword import EdwordProject

project = EdwordProject("path/to/manuscript")
project.build_index()
findings = project.analyze(passes=["continuity-index"], verify=True)
```

---

## Evaluation Plan

### Ground Truth Dataset
1. Take clean manuscript (Myriad Trilogy Book 1)
2. Inject 50 known errors across categories:
   - Age contradictions (10)
   - Timeline violations (10)
   - Character state errors (10)
   - Relationship contradictions (10)
   - World fact inconsistencies (10)

### Metrics
| Metric | Definition |
|--------|------------|
| Precision | True issues / All reported issues |
| Recall | Found issues / All injected issues |
| F1 | Harmonic mean of precision and recall |
| Cost | Tokens per verified finding |
| Latency | Time from command to results |

### Baselines
1. **Pure RLM**: Full manuscript in context, ask for issues
2. **Pure Index**: Our current Python-only analysis
3. **Sliding Window**: Analyze N chapters at a time with overlap
4. **Full Context**: GPT-4/Claude with entire manuscript (if fits)

### Ablations
- With/without verification
- Different index schemas
- Different verification models
- Batch vs individual verification

---

## Research Paper Outline

**Title:** "Scalable Consistency Checking for Long-Form Narratives via Memory-Augmented Extraction and Chain-of-Verification"

**Abstract:** We present a two-phase architecture for detecting inconsistencies in book-length documents that exceed LLM context limits...

**Contributions:**
1. Three-tier memory architecture for long document analysis
2. Delta extraction + deterministic accumulation pattern
3. Application of CoVe to editorial consistency checking
4. Evaluation on fiction manuscripts with injected errors

**Related Work:**
- LIGHT (memory-augmented LLMs)
- Chain-of-Verification (Meta)
- FEVER (fact verification)
- TLDM (long-context benchmarks)
- PAL/PoT (program-aided language models)

---

## Open Questions

1. **Verification granularity**: Verify every candidate or only errors?
2. **Batch efficiency**: How many candidates per verification call?
3. **Model selection**: Same model for extraction and verification?
4. **MCP vs CLI**: Which should be primary for AI assistants?
5. **Real-time checking**: Can we verify during writing, not just after?
