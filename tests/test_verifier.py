"""Tests for Chain-of-Verification (CoVe) verifier."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

from edword.passes.verifier import (
    CoVeVerifier,
    VerificationVerdict,
    VerificationResult,
    VerificationQuestion,
    EXCLUDED_TOKENS,
    VALID_CONFIDENCES,
    _create_mock_book,
)
from edword.passes.base import Finding, Severity
from edword.discovery import BookInfo


# --- Fixtures ---


@pytest.fixture
def mock_finding():
    """Create a mock finding for testing."""
    return Finding(
        severity=Severity.ERROR,
        message="Character age contradiction: Greg is 35 in chapter 1 but 45 in chapter 5",
        location="Chapters: 1, 5",
        context="Greg turned 35 last month",
    )


@pytest.fixture
def verifier():
    """Create a CoVeVerifier instance for testing."""
    return CoVeVerifier(provider="claude", model="sonnet")


@pytest.fixture
def temp_book(tmp_path):
    """Create a temporary book with chapter files for testing."""
    book_dir = tmp_path / "book1"
    book_dir.mkdir()

    (book_dir / "01.md").write_text(
        "# Chapter 1\n\nGreg turned 35 last month. He celebrated with cake.\n"
    )
    (book_dir / "05.md").write_text(
        "# Chapter 5\n\nGreg, at 45, looked at his gray hair in the mirror.\n"
    )
    (book_dir / "chapter-08-intro.md").write_text(
        "# Chapter 8: The Introduction\n\nThe story continues.\n"
    )
    (book_dir / "10.md").write_text(
        "# Chapter 10\n\nThe finale.\n"
    )

    chapters = sorted(book_dir.glob("*.md"))
    return BookInfo(name="book1", path=book_dir, chapters=chapters)


@pytest.fixture
def temp_manuscripts(tmp_path):
    """Create temporary manuscript files for testing (legacy)."""
    book_dir = tmp_path / "book1"
    book_dir.mkdir()

    (book_dir / "1.md").write_text(
        "# Chapter 1\n\nGreg turned 35 last month. He celebrated with cake.\n"
    )
    (book_dir / "5.md").write_text(
        "# Chapter 5\n\nGreg, at 45, looked at his gray hair in the mirror.\n"
    )

    return tmp_path


# --- Parse Chapter IDs Tests ---


class TestParseChapterIds:
    def test_parse_simple_chapters(self, verifier):
        """Parses 'Chapters: 8, 11b' correctly."""
        result = verifier._parse_chapter_ids("Chapters: 8, 11b")
        assert result == ["8", "11b"]

    def test_parse_single_chapter(self, verifier):
        """Parses 'Chapter 5' correctly."""
        result = verifier._parse_chapter_ids("Chapter 5")
        assert result == ["5"]

    def test_parse_chapter_with_name(self, verifier):
        """Parses chapter references in various formats."""
        result = verifier._parse_chapter_ids("See chapter-01 for details")
        assert "chapter-01" in result

    def test_parse_chapter_intro_format(self, verifier):
        """Parses 'chapter-08-intro' format."""
        result = verifier._parse_chapter_ids("Found in chapter-08-intro")
        assert "chapter-08-intro" in result

    def test_parse_none_returns_empty(self, verifier):
        """Returns empty list for None."""
        result = verifier._parse_chapter_ids(None)
        assert result == []

    def test_parse_empty_returns_empty(self, verifier):
        """Returns empty list for empty string."""
        result = verifier._parse_chapter_ids("")
        assert result == []

    def test_parse_no_chapter_reference(self, verifier):
        """Returns empty for text without chapter references."""
        result = verifier._parse_chapter_ids("Some random text")
        assert result == []

    def test_parse_multiple_formats(self, verifier):
        """Handles various chapter ID formats."""
        result = verifier._parse_chapter_ids("Chapters: 1, 2, 3")
        assert len(result) == 3
        assert result == ["1", "2", "3"]

    # --- NEW: Line number exclusion tests ---

    def test_excludes_line_numbers(self, verifier):
        """'Chapter 8, line 42' should NOT include 42 as chapter ID."""
        result = verifier._parse_chapter_ids("Chapter 8, line 42")
        assert "8" in result
        assert "42" not in result

    def test_excludes_line_numbers_variant(self, verifier):
        """'Chapter 8 line 42' should NOT include 42."""
        result = verifier._parse_chapter_ids("Chapter 8 line 42")
        assert "8" in result
        assert "42" not in result

    def test_excludes_paragraph_numbers(self, verifier):
        """'Chapter 3, paragraph 5' should NOT include 5."""
        result = verifier._parse_chapter_ids("Chapter 3, paragraph 5")
        assert "3" in result
        assert "5" not in result

    def test_excludes_page_numbers(self, verifier):
        """'Chapter 2, page 100' should NOT include 100."""
        result = verifier._parse_chapter_ids("Chapter 2, page 100")
        assert "2" in result
        assert "100" not in result

    # --- NEW: Chapter range tests ---

    def test_expands_chapter_range(self, verifier):
        """'Chapters: 8-10' expands to [8, 9, 10]."""
        result = verifier._parse_chapter_ids("Chapters: 8-10")
        assert result == ["8", "9", "10"]

    def test_expands_chapter_range_single(self, verifier):
        """'Chapters: 5-5' returns just [5]."""
        result = verifier._parse_chapter_ids("Chapters: 5-5")
        assert result == ["5"]

    def test_mixed_range_and_individual(self, verifier):
        """'Chapters: 1, 3-5, 8' handles mixed format."""
        result = verifier._parse_chapter_ids("Chapters: 1, 3-5, 8")
        assert "1" in result
        assert "3" in result
        assert "4" in result
        assert "5" in result
        assert "8" in result

    def test_limits_range_expansion(self, verifier):
        """Large ranges are limited to prevent memory issues."""
        result = verifier._parse_chapter_ids("Chapters: 1-100")
        # Should be limited (range > 10 not expanded)
        assert len(result) <= 11

    # --- NEW: Punctuation stripping tests ---

    def test_strips_trailing_parenthesis(self, verifier):
        """'Chapters: 8, 11b)' strips trailing )."""
        result = verifier._parse_chapter_ids("Chapters: 8, 11b)")
        assert "11b" in result
        assert "11b)" not in result

    def test_strips_trailing_period(self, verifier):
        """'Chapter 5.' strips trailing period."""
        result = verifier._parse_chapter_ids("Chapter 5.")
        assert "5" in result

    def test_strips_multiple_punctuation(self, verifier):
        """Strips various trailing punctuation."""
        result = verifier._parse_chapter_ids("Chapters: 3;, 5!)")
        assert "3" in result
        assert "5" in result


class TestCleanChapterId:
    def test_removes_trailing_paren(self, verifier):
        assert verifier._clean_chapter_id("11b)") == "11b"

    def test_removes_trailing_period(self, verifier):
        assert verifier._clean_chapter_id("5.") == "5"

    def test_removes_trailing_comma(self, verifier):
        assert verifier._clean_chapter_id("3,") == "3"

    def test_removes_multiple_punctuation(self, verifier):
        assert verifier._clean_chapter_id("2);") == "2"

    def test_preserves_internal_punctuation(self, verifier):
        # Hyphen in chapter-01 should be preserved
        assert verifier._clean_chapter_id("chapter-01") == "chapter-01"

    def test_strips_whitespace(self, verifier):
        assert verifier._clean_chapter_id("  5  ") == "5"


class TestParseChapterList:
    def test_simple_list(self, verifier):
        result = verifier._parse_chapter_list("8, 11b, 12")
        assert result == ["8", "11b", "12"]

    def test_range(self, verifier):
        result = verifier._parse_chapter_list("8-10")
        assert result == ["8", "9", "10"]

    def test_mixed(self, verifier):
        result = verifier._parse_chapter_list("1, 3-5, 8")
        assert "1" in result
        assert "3" in result
        assert "4" in result
        assert "5" in result
        assert "8" in result

    def test_excludes_line_keyword(self, verifier):
        result = verifier._parse_chapter_list("8 line 42")
        assert "8" in result
        assert "42" not in result


# --- Match Chapter Paths Tests ---


class TestMatchChapterPaths:
    def test_exact_match(self, verifier, temp_book):
        """Exact filename match works."""
        result = verifier._match_chapter_paths(["01"], temp_book.chapters)
        assert len(result) == 1
        assert result[0].stem == "01"

    def test_numeric_match_with_padding(self, verifier, temp_book):
        """'1' matches '01.md'."""
        result = verifier._match_chapter_paths(["1"], temp_book.chapters)
        assert len(result) == 1
        assert result[0].stem == "01"

    def test_numeric_match_chapter_prefix(self, verifier, temp_book):
        """'8' matches 'chapter-08-intro.md'."""
        result = verifier._match_chapter_paths(["8"], temp_book.chapters)
        assert len(result) == 1
        assert "08" in result[0].stem

    def test_prefix_match(self, verifier, temp_book):
        """'chapter-08' matches 'chapter-08-intro.md'."""
        result = verifier._match_chapter_paths(["chapter-08"], temp_book.chapters)
        assert len(result) == 1
        assert result[0].stem == "chapter-08-intro"

    def test_multiple_matches(self, verifier, temp_book):
        """Multiple IDs return multiple paths."""
        result = verifier._match_chapter_paths(["1", "5"], temp_book.chapters)
        assert len(result) == 2

    def test_no_match_returns_empty(self, verifier, temp_book):
        """Non-existent chapter returns empty list."""
        result = verifier._match_chapter_paths(["99"], temp_book.chapters)
        assert len(result) == 0


# --- Safe Read File Tests ---


class TestSafeReadFile:
    def test_reads_file_successfully(self, verifier, temp_book):
        """Successfully reads existing file."""
        content = verifier._safe_read_file(temp_book.chapters[0], 1000)
        assert content is not None
        assert "Chapter 1" in content

    def test_returns_none_for_missing_file(self, verifier, tmp_path):
        """Returns None for missing file."""
        content = verifier._safe_read_file(tmp_path / "missing.md", 1000)
        assert content is None

    def test_truncates_to_max_chars(self, verifier, tmp_path):
        """Truncates to max_chars."""
        test_file = tmp_path / "large.md"
        test_file.write_text("A" * 1000)
        content = verifier._safe_read_file(test_file, 100)
        assert content is not None
        assert len(content) == 100

    def test_handles_permission_error(self, verifier, tmp_path):
        """Handles permission errors gracefully."""
        # Create a directory (can't read as file)
        test_dir = tmp_path / "not_a_file"
        test_dir.mkdir()
        content = verifier._safe_read_file(test_dir, 1000)
        assert content is None


# --- Load Evidence Tests ---


class TestLoadEvidence:
    def test_loads_from_location(self, verifier, temp_book, mock_finding):
        """Loads chapter content based on finding location."""
        evidence = verifier._load_evidence(mock_finding, temp_book)
        assert "Chapter" in evidence

    def test_falls_back_to_context(self, verifier, temp_book):
        """Falls back to finding.context if no chapters found."""
        finding = Finding(
            severity=Severity.ERROR,
            message="Test finding",
            location="Unknown location xyz",
            context="This is the context from the finding",
        )
        evidence = verifier._load_evidence(finding, temp_book)
        assert "context from the finding" in evidence

    def test_falls_back_to_first_chapter(self, verifier, temp_book):
        """Falls back to first chapter if no location or context."""
        finding = Finding(
            severity=Severity.ERROR,
            message="Test finding",
            location=None,
            context=None,
        )
        evidence = verifier._load_evidence(finding, temp_book)
        assert len(evidence) > 0
        assert "Chapter 1" in evidence

    def test_truncates_large_evidence(self, verifier, tmp_path):
        """Truncates evidence to reasonable size."""
        book_dir = tmp_path / "book1"
        book_dir.mkdir()
        large_content = "A" * 50000
        (book_dir / "1.md").write_text(large_content)

        book = BookInfo(
            name="book1",
            path=book_dir,
            chapters=[book_dir / "1.md"]
        )

        finding = Finding(
            severity=Severity.ERROR,
            message="Test",
            location="Chapter 1",
        )
        evidence = verifier._load_evidence(finding, book)
        assert len(evidence) <= 10000

    def test_empty_book_returns_empty(self, verifier, tmp_path):
        """Empty book returns empty evidence."""
        book_dir = tmp_path / "empty_book"
        book_dir.mkdir()

        book = BookInfo(name="empty", path=book_dir, chapters=[])

        finding = Finding(
            severity=Severity.ERROR,
            message="Test",
            location="Chapter 1",
        )
        evidence = verifier._load_evidence(finding, book)
        assert evidence == ""


# --- Generate Questions Tests ---


class TestGenerateQuestions:
    @patch("edword.passes.verifier.call_model")
    def test_parses_questions_from_response(self, mock_call, verifier, mock_finding):
        """Parses questions from LLM response."""
        mock_call.return_value = '<EDWORD_QUESTIONS>["Is the age accurate?", "What context is missing?", "Could this be intentional?"]</EDWORD_QUESTIONS>'

        questions = verifier._generate_questions(mock_finding, "Evidence text")

        assert len(questions) == 3
        assert questions[0].question == "Is the age accurate?"

    @patch("edword.passes.verifier.call_model")
    def test_limits_to_five_questions(self, mock_call, verifier, mock_finding):
        """Limits questions to 5 maximum."""
        mock_call.return_value = '<EDWORD_QUESTIONS>["Q1?", "Q2?", "Q3?", "Q4?", "Q5?", "Q6?", "Q7?"]</EDWORD_QUESTIONS>'

        questions = verifier._generate_questions(mock_finding, "Evidence text")

        assert len(questions) <= 5

    @patch("edword.passes.verifier.call_model")
    def test_fallback_on_parse_failure(self, mock_call, verifier, mock_finding):
        """Returns fallback questions on parse failure."""
        mock_call.return_value = "Invalid response without tags"

        questions = verifier._generate_questions(mock_finding, "Evidence text")

        assert len(questions) == 3
        assert any("accurate" in q.question.lower() for q in questions)

    # --- NEW: Validation tests ---

    @patch("edword.passes.verifier.call_model")
    def test_filters_non_string_questions(self, mock_call, verifier, mock_finding):
        """Filters out non-string items from questions list."""
        mock_call.return_value = '<EDWORD_QUESTIONS>["Valid?", 123, null, "", "Also valid?"]</EDWORD_QUESTIONS>'

        questions = verifier._generate_questions(mock_finding, "Evidence text")

        # Should only have valid string questions
        assert len(questions) == 2
        assert questions[0].question == "Valid?"
        assert questions[1].question == "Also valid?"

    @patch("edword.passes.verifier.call_model")
    def test_strips_question_whitespace(self, mock_call, verifier, mock_finding):
        """Strips whitespace from questions."""
        mock_call.return_value = '<EDWORD_QUESTIONS>["  Question with spaces  "]</EDWORD_QUESTIONS>'

        questions = verifier._generate_questions(mock_finding, "Evidence text")

        assert questions[0].question == "Question with spaces"


# --- Answer Question Tests ---


class TestAnswerQuestion:
    @patch("edword.passes.verifier.call_model")
    def test_extracts_answer(self, mock_call, verifier):
        """Extracts answer from EDWORD_ANSWER tags."""
        mock_call.return_value = '<EDWORD_ANSWER>The text says Greg is 35: "Greg turned 35"</EDWORD_ANSWER>'

        answer = verifier._answer_question("What age is Greg?", "Evidence text")

        assert "Greg is 35" in answer

    @patch("edword.passes.verifier.call_model")
    def test_returns_raw_on_parse_failure(self, mock_call, verifier):
        """Returns truncated raw response if tags not found."""
        mock_call.return_value = "The age mentioned is 35 years old."

        answer = verifier._answer_question("What age?", "Evidence")

        assert "35" in answer
        assert len(answer) <= 500


# --- Synthesize Tests ---


class TestSynthesize:
    @patch("edword.passes.verifier.call_model")
    def test_parses_confirmed_verdict(self, mock_call, verifier, mock_finding):
        """Parses confirmed verdict from response."""
        mock_call.return_value = '''<EDWORD_VERDICT>
{
  "verdict": "confirmed",
  "confidence": "high",
  "explanation": "The text clearly shows conflicting ages."
}
</EDWORD_VERDICT>'''

        questions = [VerificationQuestion("Q?", "A")]
        result = verifier._synthesize(mock_finding, questions, "Evidence")

        assert result.verdict == VerificationVerdict.CONFIRMED
        assert result.confidence == "high"

    @patch("edword.passes.verifier.call_model")
    def test_parses_dismissed_verdict(self, mock_call, verifier, mock_finding):
        """Parses dismissed verdict from response."""
        mock_call.return_value = '''<EDWORD_VERDICT>
{
  "verdict": "dismissed",
  "confidence": "medium",
  "explanation": "Time skip explains the age difference."
}
</EDWORD_VERDICT>'''

        questions = [VerificationQuestion("Q?", "A")]
        result = verifier._synthesize(mock_finding, questions, "Evidence")

        assert result.verdict == VerificationVerdict.DISMISSED
        assert result.confidence == "medium"

    # --- NEW: Validation tests ---

    @patch("edword.passes.verifier.call_model")
    def test_uncertain_on_invalid_verdict(self, mock_call, verifier, mock_finding):
        """Returns uncertain for invalid verdict value."""
        mock_call.return_value = '''<EDWORD_VERDICT>
{"verdict": "invalid_value", "confidence": "low", "explanation": "Something"}
</EDWORD_VERDICT>'''

        questions = [VerificationQuestion("Q?", "A")]
        result = verifier._synthesize(mock_finding, questions, "Evidence")

        assert result.verdict == VerificationVerdict.UNCERTAIN

    @patch("edword.passes.verifier.call_model")
    def test_normalizes_confidence(self, mock_call, verifier, mock_finding):
        """Normalizes invalid confidence to 'low'."""
        mock_call.return_value = '''<EDWORD_VERDICT>
{"verdict": "confirmed", "confidence": "SUPER_HIGH", "explanation": "Test"}
</EDWORD_VERDICT>'''

        questions = [VerificationQuestion("Q?", "A")]
        result = verifier._synthesize(mock_finding, questions, "Evidence")

        assert result.verdict == VerificationVerdict.CONFIRMED
        assert result.confidence == "low"  # Normalized from invalid

    @patch("edword.passes.verifier.call_model")
    def test_normalizes_uppercase_values(self, mock_call, verifier, mock_finding):
        """Normalizes uppercase verdict and confidence."""
        mock_call.return_value = '''<EDWORD_VERDICT>
{"verdict": "CONFIRMED", "confidence": "HIGH", "explanation": "Test"}
</EDWORD_VERDICT>'''

        questions = [VerificationQuestion("Q?", "A")]
        result = verifier._synthesize(mock_finding, questions, "Evidence")

        assert result.verdict == VerificationVerdict.CONFIRMED
        assert result.confidence == "high"

    @patch("edword.passes.verifier.call_model")
    def test_uncertain_on_parse_failure(self, mock_call, verifier, mock_finding):
        """Returns uncertain on parse failure."""
        mock_call.return_value = "Invalid response without proper tags"

        questions = [VerificationQuestion("Q?", "A")]
        result = verifier._synthesize(mock_finding, questions, "Evidence")

        assert result.verdict == VerificationVerdict.UNCERTAIN
        assert result.confidence == "low"


# --- Full Verification Tests ---


class TestVerify:
    @patch("edword.passes.verifier.call_model")
    def test_full_verification_confirmed(self, mock_call, verifier, mock_finding, temp_book):
        """Full verification returns confirmed verdict."""
        mock_call.side_effect = [
            '<EDWORD_QUESTIONS>["Is the age contradiction real?"]</EDWORD_QUESTIONS>',
            '<EDWORD_ANSWER>Yes, chapter 1 says 35, chapter 5 says 45.</EDWORD_ANSWER>',
            '<EDWORD_VERDICT>{"verdict":"confirmed","confidence":"high","explanation":"Real contradiction"}</EDWORD_VERDICT>',
        ]

        result = verifier.verify(mock_finding, temp_book)

        assert result.verdict == VerificationVerdict.CONFIRMED
        assert result.confidence == "high"
        assert len(result.questions) == 1
        assert result.questions[0].answer is not None

    @patch("edword.passes.verifier.call_model")
    def test_full_verification_dismissed(self, mock_call, verifier, mock_finding, temp_book):
        """Full verification returns dismissed verdict."""
        mock_call.side_effect = [
            '<EDWORD_QUESTIONS>["Is there a time skip?", "Is aging mentioned?"]</EDWORD_QUESTIONS>',
            '<EDWORD_ANSWER>Yes, 10 years pass.</EDWORD_ANSWER>',
            '<EDWORD_ANSWER>The character ages normally.</EDWORD_ANSWER>',
            '<EDWORD_VERDICT>{"verdict":"dismissed","confidence":"high","explanation":"Time skip"}</EDWORD_VERDICT>',
        ]

        result = verifier.verify(mock_finding, temp_book)

        assert result.verdict == VerificationVerdict.DISMISSED
        assert len(result.questions) == 2

    @patch("edword.passes.verifier.call_model")
    def test_handles_provider_error(self, mock_call, verifier, mock_finding, temp_book):
        """Returns uncertain on provider error."""
        from edword.llm.providers import ProviderError

        mock_call.side_effect = ProviderError("API error")

        result = verifier.verify(mock_finding, temp_book)

        assert result.verdict == VerificationVerdict.UNCERTAIN
        assert "provider error" in result.explanation.lower()

    @patch("edword.passes.verifier.call_model")
    def test_handles_unexpected_error(self, mock_call, verifier, mock_finding, temp_book):
        """Returns uncertain on unexpected error."""
        mock_call.side_effect = RuntimeError("Unexpected error")

        result = verifier.verify(mock_finding, temp_book)

        assert result.verdict == VerificationVerdict.UNCERTAIN
        assert "error" in result.explanation.lower()

    # --- NEW: Empty evidence test ---

    def test_returns_uncertain_for_empty_evidence(self, verifier, tmp_path):
        """Returns uncertain when no evidence can be loaded."""
        book_dir = tmp_path / "empty_book"
        book_dir.mkdir()
        book = BookInfo(name="empty", path=book_dir, chapters=[])

        finding = Finding(
            severity=Severity.ERROR,
            message="Test finding",
            location="Chapter 99",  # Non-existent
            context=None,
        )

        result = verifier.verify(finding, book)

        assert result.verdict == VerificationVerdict.UNCERTAIN
        assert "no evidence" in result.explanation.lower()


# --- Verification Result Tests ---


class TestVerificationResult:
    def test_result_has_all_fields(self):
        """VerificationResult has all expected fields."""
        result = VerificationResult(
            verdict=VerificationVerdict.CONFIRMED,
            confidence="high",
            explanation="Test explanation",
            questions=[VerificationQuestion("Q?", "A")],
            evidence_excerpt="Test evidence",
        )

        assert result.verdict == VerificationVerdict.CONFIRMED
        assert result.confidence == "high"
        assert result.explanation == "Test explanation"
        assert len(result.questions) == 1
        assert result.evidence_excerpt == "Test evidence"


# --- Verification Verdict Tests ---


class TestVerificationVerdict:
    def test_enum_values(self):
        """Enum has expected values."""
        assert VerificationVerdict.CONFIRMED.value == "confirmed"
        assert VerificationVerdict.DISMISSED.value == "dismissed"
        assert VerificationVerdict.UNCERTAIN.value == "uncertain"

    def test_enum_from_string(self):
        """Can create enum from string value."""
        assert VerificationVerdict("confirmed") == VerificationVerdict.CONFIRMED
        assert VerificationVerdict("dismissed") == VerificationVerdict.DISMISSED


# --- Constants Tests ---


class TestConstants:
    def test_excluded_tokens(self):
        """EXCLUDED_TOKENS contains expected values."""
        assert "line" in EXCLUDED_TOKENS
        assert "lines" in EXCLUDED_TOKENS
        assert "paragraph" in EXCLUDED_TOKENS
        assert "page" in EXCLUDED_TOKENS

    def test_valid_confidences(self):
        """VALID_CONFIDENCES contains expected values."""
        assert "high" in VALID_CONFIDENCES
        assert "medium" in VALID_CONFIDENCES
        assert "low" in VALID_CONFIDENCES
        assert len(VALID_CONFIDENCES) == 3


# --- Backwards Compatibility Tests ---


class TestBackwardsCompatibility:
    def test_create_mock_book(self, temp_manuscripts):
        """_create_mock_book creates valid BookInfo from paths."""
        book = _create_mock_book(temp_manuscripts, "book1")

        assert book.name == "book1"
        assert book.path == temp_manuscripts / "book1"
        assert len(book.chapters) == 2

    def test_create_mock_book_nonexistent(self, tmp_path):
        """_create_mock_book handles non-existent paths."""
        book = _create_mock_book(tmp_path, "nonexistent")

        assert book.name == "nonexistent"
        assert book.chapters == []


# --- Integration Tests ---


class TestVerifierIntegration:
    @pytest.mark.integration
    def test_real_verification_skipped_without_api(self, mock_finding, temp_book):
        """Skip real API calls in CI."""
        pytest.skip("Integration test requires API access")
