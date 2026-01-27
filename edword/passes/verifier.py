"""Chain-of-Verification (CoVe) for editorial findings.

Implements a 4-step verification process to reduce false positives:
1. Draft Assessment - Load relevant evidence
2. Generate Questions - Create verification questions about the finding
3. Answer Questions - Answer each question independently (reduces bias)
4. Synthesize Judgment - Combine answers into final verdict
"""

import re
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from ..prompts import render_prompt
from ..llm.providers import call_model, ProviderError
from ..llm.parsing import extract_questions, extract_answer, extract_verdict
from ..index.schema import AccumulatedIndex
from .base import Finding

if TYPE_CHECKING:
    from ..discovery import BookInfo


# Words that indicate line/paragraph references, not chapter IDs
EXCLUDED_TOKENS = frozenset([
    "line", "lines", "paragraph", "paragraphs", "page", "pages",
    "section", "sections", "verse", "verses", "scene", "scenes",
])

# Valid confidence levels
VALID_CONFIDENCES = frozenset(["high", "medium", "low"])


class VerificationVerdict(Enum):
    """Possible verification outcomes."""
    CONFIRMED = "confirmed"    # Finding is real
    DISMISSED = "dismissed"    # False positive
    UNCERTAIN = "uncertain"    # Need more context / LLM error


@dataclass
class VerificationQuestion:
    """A verification question with its answer."""
    question: str
    answer: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of CoVe verification process."""
    verdict: VerificationVerdict
    confidence: str  # "high", "medium", "low"
    explanation: str
    questions: list[VerificationQuestion] = field(default_factory=list)
    evidence_excerpt: str = ""


class CoVeVerifier:
    """Chain-of-Verification for editorial findings.

    Verifies findings through a multi-step process to reduce false positives.
    Each step is independent to avoid confirmation bias.
    """

    def __init__(
        self,
        provider: str = "claude",
        model: str = "sonnet",
    ):
        """Initialize the verifier.

        Args:
            provider: LLM provider ("claude" or "gemini")
            model: Model to use for verification
        """
        self.provider = provider
        self.model = model

    def verify(
        self,
        finding: Finding,
        book: "BookInfo",
    ) -> VerificationResult:
        """Run 4-step CoVe verification on a finding.

        Args:
            finding: The finding to verify
            book: BookInfo object with chapter paths

        Returns:
            VerificationResult with verdict and supporting data
        """
        try:
            # Step 1: Load evidence (from chapter files)
            evidence = self._load_evidence(finding, book)

            # If no evidence found, return uncertain
            if not evidence or not evidence.strip():
                return VerificationResult(
                    verdict=VerificationVerdict.UNCERTAIN,
                    confidence="low",
                    explanation="No evidence could be loaded for verification",
                )

            # Step 2: Generate verification questions
            questions = self._generate_questions(finding, evidence)

            # Step 3: Answer each question independently
            for q in questions:
                q.answer = self._answer_question(q.question, evidence)

            # Step 4: Synthesize final judgment
            return self._synthesize(finding, questions, evidence)

        except ProviderError as e:
            # LLM failed - return uncertain verdict
            return VerificationResult(
                verdict=VerificationVerdict.UNCERTAIN,
                confidence="low",
                explanation=f"LLM provider error: {e}",
            )
        except Exception as e:
            # Unexpected error - also return uncertain
            return VerificationResult(
                verdict=VerificationVerdict.UNCERTAIN,
                confidence="low",
                explanation=f"Verification error: {type(e).__name__}: {e}",
            )

    def _load_evidence(
        self,
        finding: Finding,
        book: "BookInfo",
    ) -> str:
        """Load relevant chapter text for verification.

        Strategy:
        1. Try to parse chapter IDs from finding.location and match to book.chapters
        2. Fallback: use finding.context if available
        3. Last resort: load first chapter from book

        Args:
            finding: Finding to load evidence for
            book: BookInfo with chapter paths

        Returns:
            Evidence text (truncated to reasonable size)
        """
        # Try to extract chapter IDs from location (e.g., "Chapters: 8, 11b")
        requested_ids = self._parse_chapter_ids(finding.location)

        evidence_parts = []
        max_chars = 10000  # Limit total evidence size

        if requested_ids:
            # Match requested IDs to actual chapter paths
            matched_paths = self._match_chapter_paths(requested_ids, book.chapters)
            if matched_paths:
                chars_per_chapter = max_chars // max(len(matched_paths), 1)
                for ch_path in matched_paths[:3]:  # Max 3 chapters
                    content = self._safe_read_file(ch_path, chars_per_chapter)
                    if content:
                        evidence_parts.append(f"=== {ch_path.stem} ===\n{content}")

        if not evidence_parts and finding.context:
            # Use context from the finding itself
            evidence_parts.append(finding.context)

        if not evidence_parts and book.chapters:
            # Fallback: load first chapter that exists
            content = self._safe_read_file(book.chapters[0], max_chars)
            if content:
                evidence_parts.append(content)

        return "\n\n".join(evidence_parts)[:max_chars]

    def _match_chapter_paths(
        self,
        requested_ids: list[str],
        chapter_paths: list[Path],
    ) -> list[Path]:
        """Match requested chapter IDs to actual chapter file paths.

        Handles various naming conventions:
        - "8" matches "8.md", "08.md", "chapter-08.md", "chapter-8-intro.md"
        - "chapter-01" matches "chapter-01.md", "chapter-01-intro.md"

        Args:
            requested_ids: List of chapter IDs to find
            chapter_paths: List of actual chapter file paths

        Returns:
            List of matched paths (may be fewer than requested if not found)
        """
        matched = []
        for req_id in requested_ids:
            req_lower = req_id.lower()
            # Try to extract just the number for flexible matching
            num_match = re.search(r'\d+', req_id)
            req_num = num_match.group() if num_match else None

            for ch_path in chapter_paths:
                stem = ch_path.stem.lower()

                # Exact match
                if stem == req_lower:
                    matched.append(ch_path)
                    break

                # Number-based match (e.g., "8" matches "chapter-08")
                if req_num:
                    stem_num_match = re.search(r'\d+', stem)
                    if stem_num_match:
                        # Compare numeric values to handle zero-padding
                        if int(stem_num_match.group()) == int(req_num):
                            matched.append(ch_path)
                            break

                # Prefix match (e.g., "chapter-01" matches "chapter-01-intro")
                if stem.startswith(req_lower):
                    matched.append(ch_path)
                    break

        return matched

    def _safe_read_file(self, path: Path, max_chars: int) -> Optional[str]:
        """Safely read a file with error handling.

        Args:
            path: Path to read
            max_chars: Maximum characters to read

        Returns:
            File content or None if read failed
        """
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except (OSError, IOError) as e:
            # Log error but continue - don't abort all evidence loading
            return None

    def _parse_chapter_ids(self, location: Optional[str]) -> list[str]:
        """Parse chapter IDs from location string.

        Handles various formats:
        - "Chapters: 8, 11b" -> ["8", "11b"]
        - "Chapter 8, line 42" -> ["8"] (excludes "42" as it's a line number)
        - "Chapters: 8-10" -> ["8", "9", "10"] (expands ranges)
        - "chapter-01-intro" -> ["chapter-01-intro"]

        Args:
            location: Location string from finding

        Returns:
            List of chapter IDs
        """
        if not location:
            return []

        # First, try to find standalone chapter references like "chapter-01"
        # This handles formats like "chapter-01-intro", "chapter-05"
        chapter_refs = re.findall(r'chapter-?\d+[\w-]*', location, re.IGNORECASE)
        if chapter_refs:
            return [self._clean_chapter_id(ref) for ref in chapter_refs[:3]]

        # Match patterns like "Chapters: 8, 11b" or "Chapter 8, line 42"
        # Require colon or space followed by content
        match = re.search(r'[Cc]hapters?[:\s]+(.+?)(?:\.|$)', location)
        if match:
            raw = match.group(1)
            return self._parse_chapter_list(raw)

        return []

    def _parse_chapter_list(self, raw: str) -> list[str]:
        """Parse a comma/space separated list of chapter references.

        Handles:
        - Simple list: "8, 11b, 12"
        - Ranges: "8-10" -> ["8", "9", "10"]
        - Mixed: "8, 10-12, 15"
        - Excludes line/paragraph references

        Args:
            raw: Raw string containing chapter references

        Returns:
            List of chapter IDs
        """
        result = []

        # Split by comma first
        parts = re.split(r',\s*', raw)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Check for range (e.g., "8-10")
            range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                if end >= start and (end - start) <= 10:  # Limit range expansion
                    result.extend(str(i) for i in range(start, end + 1))
                continue

            # Split by space for "8 line 42" -> take only valid chapter refs
            tokens = part.split()
            for i, token in enumerate(tokens):
                token_clean = self._clean_chapter_id(token)
                if not token_clean:
                    continue

                # Skip if this token is preceded by a line/paragraph keyword
                if i > 0 and tokens[i - 1].lower() in EXCLUDED_TOKENS:
                    continue

                # Skip if token itself is an excluded keyword
                if token_clean.lower() in EXCLUDED_TOKENS:
                    continue

                # Valid chapter ID: starts with digit or is short alphanumeric
                if token_clean[0].isdigit() and len(token_clean) <= 5:
                    result.append(token_clean)
                    break  # Only take first valid token per comma-separated part

        return result[:5]  # Limit to 5 chapters

    def _clean_chapter_id(self, raw_id: str) -> str:
        """Clean a chapter ID by removing trailing punctuation.

        Args:
            raw_id: Raw chapter ID string

        Returns:
            Cleaned chapter ID
        """
        # Remove trailing punctuation like ), ., :, etc.
        return re.sub(r'[)\].,;:!?\'"]+$', '', raw_id.strip())

    def _generate_questions(
        self,
        finding: Finding,
        evidence: str,
    ) -> list[VerificationQuestion]:
        """Step 2: Generate 3-5 verification questions.

        Args:
            finding: Finding to generate questions for
            evidence: Evidence text

        Returns:
            List of VerificationQuestion objects
        """
        prompt = render_prompt(
            "cove_generate_questions",
            finding_message=finding.message,
            finding_location=finding.location or "unknown",
            evidence=evidence[:8000],
        )
        response = call_model(self.provider, prompt, model=self.model)

        result = extract_questions(response)
        if result.success and isinstance(result.data, list):
            questions = [
                VerificationQuestion(question=q.strip())
                for q in result.data[:5]
                if isinstance(q, str) and q.strip()
            ]
            if questions:
                return questions

        # Fallback: return generic questions
        return [
            VerificationQuestion("Is the manuscript quote accurate as described in the finding?"),
            VerificationQuestion("Is there context that resolves this apparent contradiction?"),
            VerificationQuestion("Could both claims be true in different contexts or timeframes?"),
        ]

    def _answer_question(self, question: str, evidence: str) -> str:
        """Step 3: Answer a single question.

        Args:
            question: Question to answer
            evidence: Evidence text

        Returns:
            Answer string
        """
        prompt = render_prompt(
            "cove_answer_question",
            question=question,
            evidence=evidence[:8000],
        )
        response = call_model(self.provider, prompt, model=self.model)

        result = extract_answer(response)
        return result.content if result.success else response[:500]

    def _synthesize(
        self,
        finding: Finding,
        questions: list[VerificationQuestion],
        evidence: str,
    ) -> VerificationResult:
        """Step 4: Synthesize final verdict from Q&A.

        Args:
            finding: Original finding
            questions: Questions with answers
            evidence: Evidence text (for excerpt)

        Returns:
            VerificationResult with verdict
        """
        qa_text = "\n\n".join(
            f"**Q:** {q.question}\n**A:** {q.answer}"
            for q in questions if q.answer
        )
        prompt = render_prompt(
            "cove_synthesize",
            finding_message=finding.message,
            qa_pairs=qa_text,
        )
        response = call_model(self.provider, prompt, model=self.model)

        result = extract_verdict(response)
        if result.success and isinstance(result.data, dict):
            data = result.data
            verdict_str = str(data.get("verdict", "uncertain")).lower().strip()
            confidence_str = str(data.get("confidence", "low")).lower().strip()

            # Parse verdict with fallback, validate confidence
            try:
                verdict = VerificationVerdict(verdict_str)
            except ValueError:
                verdict = VerificationVerdict.UNCERTAIN

            return VerificationResult(
                verdict=verdict,
                confidence=confidence_str if confidence_str in VALID_CONFIDENCES else "low",
                explanation=str(data.get("explanation", "")),
                questions=questions,
                evidence_excerpt=evidence[:500],
            )

        # Fallback if parsing fails
        return VerificationResult(
            verdict=VerificationVerdict.UNCERTAIN,
            confidence="low",
            explanation="Could not parse verification response",
            questions=questions,
            evidence_excerpt=evidence[:500],
        )


# Backwards compatibility: allow passing paths instead of BookInfo
def _create_mock_book(manuscripts_path: Path, book_name: str) -> "BookInfo":
    """Create a minimal BookInfo from path for backwards compatibility."""
    from ..discovery import BookInfo

    book_path = manuscripts_path / book_name
    chapters = sorted(book_path.glob("*.md")) if book_path.exists() else []
    return BookInfo(name=book_name, path=book_path, chapters=chapters)
