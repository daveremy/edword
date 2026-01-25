# Edword Research Notes

## Project Overview

Edword is an AI-powered editorial analysis tool for long-form manuscripts. It addresses a fundamental limitation: book-length documents exceed LLM context windows, making traditional "read and analyze" approaches infeasible.

## Core Innovation

**Memory-Augmented Extraction with Chain-of-Verification (MAEV)**

A two-phase architecture combining:
1. **Delta Extraction + Deterministic Accumulation**: LLM extracts structured facts per chapter, Python accumulates into a knowledge graph
2. **Index-Based Candidate Generation**: Python rules identify potential inconsistencies (fast, may have false positives)
3. **Chain-of-Verification (CoVe)**: LLM verifies candidates with targeted questions (precise, handles ambiguity)

## Related Work

### Memory-Augmented LLMs

**LIGHT Framework (October 2025)**
- Proposes three-tier memory: long-term episodic, short-term working, scratchpad
- Found even 1M token LLMs struggle without explicit memory
- *Our contribution*: Apply this to editorial consistency, not dialogue

**Citation**: arXiv 2510.27246

### Verification & Self-Correction

**Chain-of-Verification (Meta, 2024)**
- Four-step process: draft → generate questions → answer independently → synthesize
- Reduces hallucination by forcing explicit verification
- *Our contribution*: Apply to fact-checking extracted data, not generated content

**Citation**: Dhuliawala et al., ACL 2024

**LADDER Framework (2025)**
- Recursive problem decomposition for self-improving LLMs
- 7B model achieves 73% on MIT Integration Bee (vs GPT-4o's 42%)
- *Our contribution*: Recursive verification of editorial findings

**Citation**: arXiv 2503.00735

### Fact Verification

**FEVER Dataset & Systems**
- Retrieve evidence from Wikipedia, classify claims as supported/refuted/NEI
- Two-stage: document retrieval → sentence selection → verification
- *Our contribution*: Apply to fiction (no ground truth KB), focus on internal consistency

**Citation**: Thorne et al., NAACL 2018 (arXiv 1803.05355)

### Long Document Processing

**TLDM Benchmark (May 2025)**
- Tests LLM understanding of novels (plot, storyworld, timeline)
- Key finding: No frontier LLM retains stable understanding beyond 64k tokens
- *Our contribution*: Solve this via chunking + accumulation, validate approach

**Citation**: arXiv 2505.14925

**AIE Framework (December 2024)**
- Automated Information Extraction for hybrid long documents
- Compares "Refine" vs "Map-Reduce" strategies
- *Our contribution*: Delta extraction avoids Map-Reduce summarization loss

**Citation**: arXiv 2412.20072

### Program-Aided Language Models

**PAL / PoT (ICML 2023)**
- LLM generates code, Python executes
- Offloads deterministic computation to reliable runtime
- *Our contribution*: Similar pattern - LLM extracts, Python accumulates/analyzes

**Citation**: Gao et al., ICML 2023

## What's Novel

### 1. Application Domain
No existing work specifically addresses **fiction manuscript consistency**. Related work focuses on:
- Fact-checking news/Wikipedia (FEVER)
- Long document QA (TLDM)
- Code generation (PAL)

Fiction has unique challenges:
- No external ground truth (codex is also part of the document)
- Ambiguity is often intentional (unreliable narrators, mysteries)
- Consistency spans 100k+ tokens across chapters

### 2. Delta Extraction Pattern
Most long document approaches use:
- **Sliding window**: Loses cross-window context
- **Map-Reduce summarization**: Information loss at each reduction
- **Retrieval**: Requires knowing what to retrieve

Our pattern:
- Extract only new facts from current chapter
- Accumulate via deterministic Python (no LLM degradation)
- Pass entity list (not full context) for pronoun resolution

### 3. Index as Candidate Generator
Unlike retrieve-then-verify (which requires a query), we:
- Build complete knowledge graph from extraction
- Use Python rules to find potential conflicts
- Verify only flagged candidates

This inverts the typical RAG pattern: instead of "find evidence for claim", we "find claims that need evidence".

### 4. CoVe for Editorial Verification
Chain-of-Verification was designed for reducing hallucinations in generated content. We apply it to:
- Verify extracted facts against source text
- Distinguish true contradictions from context-dependent statements
- Explain findings to human editors

## Research Questions

1. **Recall ceiling**: How much does Phase 1 extraction miss? Can we measure/improve?
2. **Verification efficiency**: Batch vs individual? How many candidates per call?
3. **Cross-document consistency**: Can this scale to multi-book series with shared canon?
4. **Real-time integration**: Can verification happen during writing, not just after?
5. **Domain transfer**: Does the approach work for legal contracts, medical records, etc.?

## Evaluation Strategy

### Ground Truth Construction
1. Take clean, edited manuscript (Myriad Trilogy Book 1)
2. Create copy with injected errors:
   - 10 age contradictions
   - 10 timeline violations
   - 10 character state errors (alive→dead→speaking)
   - 10 relationship contradictions
   - 10 world fact inconsistencies
3. Run system, measure precision/recall

### Baselines
| Baseline | Description |
|----------|-------------|
| Full Context | Feed entire manuscript to Claude/GPT-4 (if fits) |
| Sliding Window | Analyze 5-chapter windows with 2-chapter overlap |
| Pure RLM | Recursive exploration without indexing |
| Pure Index | Our Python analysis without CoVe verification |

### Metrics
- **Precision**: Verified issues / All reported issues
- **Recall**: Found issues / All injected issues
- **F1**: Harmonic mean
- **Cost**: Tokens per verified finding
- **Latency**: Wall clock time

### Ablations
- Index schema variants (what to extract)
- Verification model (Haiku vs Sonnet vs Opus)
- Batch size for verification
- With/without entity list for extraction

## Potential Paper Structure

**Title**: "Scalable Consistency Checking for Long-Form Narratives via Memory-Augmented Extraction and Chain-of-Verification"

1. **Introduction**: The context window problem for book-length analysis
2. **Related Work**: LIGHT, CoVe, FEVER, TLDM, PAL
3. **Method**: Three-tier memory, delta extraction, CoVe verification
4. **Implementation**: Edword system description
5. **Evaluation**: Injected error experiments, baselines, ablations
6. **Results**: Precision/recall, cost, latency analysis
7. **Discussion**: Failure modes, domain transfer, limitations
8. **Conclusion**: Summary, future work

**Target Venues**: ACL, EMNLP, NAACL (NLP), CHI (if focusing on editor UX)

## Open Source Strategy

- Release Edword as MIT-licensed tool
- Publish evaluation dataset (injected errors)
- Provide reproducibility scripts
- Consider companion blog post for practitioner audience
