"""Tests for check operations."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from edword.check import (
    CheckError,
    Conflict,
    CharacterMention,
    FactResult,
    _split_sentences,
    _normalize,
    _find_character_mentions,
    _get_mention_window,
    _has_negation,
    _has_negation_near,
    _extract_age_in_window,
    _extract_trait_in_window,
    _values_match,
    _check_character_in_window,
    _get_indexed_fact,
    _deduplicate_conflicts,
    check_text,
    HAS_RAPIDFUZZ,
)


# --- Fixtures ---


@pytest.fixture
def mock_character():
    """Create a mock character with facts."""
    from edword.index.schema import (
        Character,
        CharacterFact,
        Evidence,
        Confidence,
    )

    evidence = Evidence(quote="test quote", line=1, char_span=None, chapter="chapter-01")

    return Character(
        id="char_greg",
        canonical_name="Greg Walsh",
        mentions=["Greg", "Dr. Walsh"],
        facts=[
            CharacterFact(
                predicate="age",
                value="45",
                confidence=Confidence.HIGH,
                evidence=evidence,
            ),
            CharacterFact(
                predicate="eye_color",
                value="brown",
                confidence=Confidence.HIGH,
                evidence=evidence,
            ),
            CharacterFact(
                predicate="hair_color",
                value="gray",
                confidence=Confidence.HIGH,
                evidence=evidence,
            ),
        ],
        relationships=[],
        state_changes=[],
    )


@pytest.fixture
def mock_character_maya():
    """Create a second mock character."""
    from edword.index.schema import (
        Character,
        CharacterFact,
        Evidence,
        Confidence,
    )

    evidence = Evidence(quote="test quote", line=10, char_span=None, chapter="chapter-02")

    return Character(
        id="char_maya",
        canonical_name="Maya Walsh",
        mentions=["Maya"],
        facts=[
            CharacterFact(
                predicate="age",
                value="17",
                confidence=Confidence.HIGH,
                evidence=evidence,
            ),
            CharacterFact(
                predicate="eye_color",
                value="blue",
                confidence=Confidence.HIGH,
                evidence=evidence,
            ),
        ],
        relationships=[],
        state_changes=[],
    )


@pytest.fixture
def mock_index(mock_character, mock_character_maya):
    """Create a mock AccumulatedIndex for testing."""
    from edword.index.schema import AccumulatedIndex

    return AccumulatedIndex(
        book="book1",
        chapters_indexed=["chapter-01", "chapter-02"],
        last_updated="2024-01-01T00:00:00",
        characters=[mock_character, mock_character_maya],
        timeline=[],
        locations=[],
        artifacts=[],
        world_facts=[],
        terminology=[],
        narrative=[],
    )


@pytest.fixture
def mock_project_root(tmp_path):
    return tmp_path


# --- Helper Function Tests ---


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("GREG") == "greg"

    def test_strip_whitespace(self):
        assert _normalize("  Greg  ") == "greg"

    def test_combined(self):
        assert _normalize("  GREG WALSH  ") == "greg walsh"


class TestSplitSentences:
    def test_single_sentence(self):
        sentences = _split_sentences("Greg walked into the room.")
        assert len(sentences) == 1
        assert sentences[0][0] == "Greg walked into the room."

    def test_multiple_sentences(self):
        text = "Greg walked in. He sat down. Maya looked up."
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_question_mark(self):
        text = "What did Greg do? He sat down."
        sentences = _split_sentences(text)
        assert len(sentences) == 2

    def test_exclamation(self):
        text = "Greg ran! Maya followed."
        sentences = _split_sentences(text)
        assert len(sentences) == 2

    def test_handles_abbreviations(self):
        """Common abbreviations like Dr. Mr. shouldn't split."""
        text = "Dr. Walsh examined the patient."
        sentences = _split_sentences(text)
        # Should be one sentence, not split on Dr.
        assert len(sentences) == 1

    def test_empty_text(self):
        sentences = _split_sentences("")
        assert len(sentences) == 1
        assert sentences[0][0] == ""


class TestFindCharacterMentions:
    def test_finds_canonical_name(self, mock_character):
        """Finds 'Greg Walsh' in text."""
        text = "Greg Walsh walked into the room."
        mentions = _find_character_mentions(text, [mock_character])
        assert len(mentions) == 1
        assert mentions[0].matched_text == "Greg Walsh"
        assert mentions[0].character.id == "char_greg"

    def test_finds_mention_alias(self, mock_character):
        """Finds 'Dr. Walsh' when it's in mentions."""
        text = "Dr. Walsh examined the data."
        mentions = _find_character_mentions(text, [mock_character])
        assert len(mentions) == 1
        assert mentions[0].matched_text == "Dr. Walsh"

    def test_finds_first_name(self, mock_character):
        """Finds 'Greg' when it's in mentions."""
        text = "Greg looked at the screen."
        mentions = _find_character_mentions(text, [mock_character])
        assert len(mentions) == 1
        assert mentions[0].matched_text == "Greg"

    def test_case_insensitive(self, mock_character):
        """Finds 'greg' when index has 'Greg'."""
        text = "greg walked into the room."
        mentions = _find_character_mentions(text, [mock_character])
        assert len(mentions) == 1

    def test_word_boundaries(self, mock_character):
        """Doesn't match 'Gregory' when looking for 'Greg'."""
        text = "Gregory walked into the room."
        mentions = _find_character_mentions(text, [mock_character])
        assert len(mentions) == 0

    def test_multiple_mentions(self, mock_character, mock_character_maya):
        """Finds multiple character mentions."""
        text = "Greg and Maya talked."
        mentions = _find_character_mentions(text, [mock_character, mock_character_maya])
        assert len(mentions) == 2

    def test_no_pronoun_matching(self, mock_character):
        """Does NOT match 'he', 'she', 'they' (V1 limitation)."""
        text = "He walked into the room. She followed."
        mentions = _find_character_mentions(text, [mock_character])
        assert len(mentions) == 0


class TestGetMentionWindow:
    def test_gets_containing_sentence(self):
        """Returns sentence containing the mention."""
        text = "The sun was bright. Greg walked in. It was noon."
        sentences = _split_sentences(text)
        # "Greg" appears around position 20-24
        window = _get_mention_window(text, sentences, 20, 24)
        assert "Greg" in window
        assert "walked in" in window

    def test_fallback_for_no_match(self):
        """Falls back to surrounding context if no sentence found."""
        text = "Greg walked in"
        sentences = []  # Empty sentences list
        window = _get_mention_window(text, sentences, 0, 4)
        assert "Greg" in window


class TestNegationDetection:
    def test_detects_not(self):
        """'not a lawyer' has negation."""
        assert _has_negation("He was not a lawyer.") is True

    def test_detects_no(self):
        assert _has_negation("He had no experience.") is True

    def test_detects_never(self):
        assert _has_negation("He never worked there.") is True

    def test_detects_former(self):
        """'former engineer' has negation."""
        assert _has_negation("The former engineer walked in.") is True

    def test_detects_ex_prefix(self):
        assert _has_negation("His ex-wife called.") is True

    def test_detects_no_longer(self):
        assert _has_negation("He was no longer young.") is True

    def test_detects_wasnt(self):
        assert _has_negation("He wasn't 45 years old.") is True

    def test_no_negation(self):
        """'is a lawyer' has no negation."""
        assert _has_negation("He is a lawyer.") is False

    def test_no_negation_normal_text(self):
        assert _has_negation("Greg walked into the room.") is False


class TestExtractAges:
    def test_is_years_old(self):
        """'Greg is 35 years old' -> (35, 0.9)"""
        result = _extract_age_in_window("Greg is 35 years old.", "Greg")
        assert result is not None
        assert result[0] == 35
        assert result[1] >= 0.8

    def test_was_years_old(self):
        """'Greg was 35 years old' -> (35, 0.9)"""
        result = _extract_age_in_window("Greg was 35 years old then.", "Greg")
        assert result is not None
        assert result[0] == 35

    def test_turned_age(self):
        """'Greg turned 35' -> (35, 0.9)"""
        result = _extract_age_in_window("Greg turned 35 last week.", "Greg")
        assert result is not None
        assert result[0] == 35

    def test_appositive(self):
        """'Greg, 35, walked' -> (35, 0.8)"""
        result = _extract_age_in_window("Greg, 35, walked into the room.", "Greg")
        assert result is not None
        assert result[0] == 35
        assert result[1] >= 0.7

    def test_year_old_prefix(self):
        """'35-year-old Greg' -> (35, 0.85)"""
        result = _extract_age_in_window("The 35-year-old Greg nodded.", "Greg")
        assert result is not None
        assert result[0] == 35

    def test_a_year_old_pattern(self):
        """'Greg, a 35-year-old engineer' -> (35, 0.85)"""
        result = _extract_age_in_window("Greg, a 35-year-old engineer, walked in.", "Greg")
        assert result is not None
        assert result[0] == 35
        assert result[1] >= 0.8

    def test_an_year_old_pattern(self):
        """'Greg, an 80-year-old veteran' -> (80, 0.85)"""
        result = _extract_age_in_window("Greg, an 80-year-old veteran, sat down.", "Greg")
        assert result is not None
        assert result[0] == 80

    def test_a_year_old_full_name(self):
        """'Greg Walsh, a 35-year-old software engineer' -> (35, 0.85)"""
        result = _extract_age_in_window(
            "Greg Walsh, a 35-year-old software engineer, drove to work.", "Greg Walsh"
        )
        assert result is not None
        assert result[0] == 35

    def test_no_match_without_name(self):
        """'the 35-year-old man' -> None (no name attribution)"""
        result = _extract_age_in_window("The 35-year-old man walked.", "Greg")
        # This should not match because "Greg" isn't in the pattern
        assert result is None

    def test_no_match_different_name(self):
        """Age for different character doesn't match."""
        result = _extract_age_in_window("Maya is 17 years old.", "Greg")
        assert result is None

    def test_unreasonable_age_rejected(self):
        """Ages over 150 are rejected."""
        result = _extract_age_in_window("Greg is 200 years old.", "Greg")
        assert result is None

    def test_yo_abbreviation(self):
        """'Greg is 35 y.o.' -> (35, 0.9)"""
        result = _extract_age_in_window("Greg is 35 y.o.", "Greg")
        assert result is not None
        assert result[0] == 35


class TestExtractTraits:
    def test_possessive_eyes(self):
        """'Greg's blue eyes' -> ('eye_color', 'blue', 0.9)"""
        traits = _extract_trait_in_window("Greg's blue eyes sparkled.", "Greg")
        assert len(traits) >= 1
        assert any(t[0] == "eye_color" and t[1] == "blue" for t in traits)

    def test_possessive_hair(self):
        """'Greg's brown hair' -> ('hair_color', 'brown', 0.9)"""
        traits = _extract_trait_in_window("Greg's brown hair was messy.", "Greg")
        assert len(traits) >= 1
        assert any(t[0] == "hair_color" and t[1] == "brown" for t in traits)

    def test_had_pattern_eyes(self):
        """'Greg had blue eyes' -> ('eye_color', 'blue', 0.8)"""
        traits = _extract_trait_in_window("Greg had blue eyes.", "Greg")
        assert len(traits) >= 1
        assert any(t[0] == "eye_color" for t in traits)

    def test_has_pattern_hair(self):
        """'Greg has gray hair' -> ('hair_color', 'gray', 0.8)"""
        traits = _extract_trait_in_window("Greg has gray hair.", "Greg")
        assert len(traits) >= 1
        assert any(t[0] == "hair_color" for t in traits)

    def test_with_pattern(self):
        """'Greg with blue eyes' -> ('eye_color', 'blue', 0.8)"""
        traits = _extract_trait_in_window("Greg with blue eyes looked up.", "Greg")
        assert len(traits) >= 1

    def test_no_match_different_name(self):
        """Traits for different character don't match."""
        traits = _extract_trait_in_window("Maya's blue eyes sparkled.", "Greg")
        assert len(traits) == 0

    def test_adjective_before_color(self):
        """'Greg's dark brown eyes' should capture 'brown' or 'dark'"""
        traits = _extract_trait_in_window("Greg's dark brown eyes.", "Greg")
        # Should capture at least one trait
        assert len(traits) >= 1


class TestValuesMatch:
    def test_exact_match(self):
        """'blue' matches 'blue'."""
        assert _values_match("blue", "blue") is True

    def test_case_insensitive(self):
        """'Blue' matches 'blue'."""
        assert _values_match("Blue", "blue") is True

    def test_whitespace_tolerance(self):
        """' blue ' matches 'blue'."""
        assert _values_match(" blue ", "blue") is True

    def test_numeric_comparison(self):
        """'45' matches '45'."""
        assert _values_match("45", "45") is True

    def test_no_match(self):
        """'blue' doesn't match 'brown'."""
        assert _values_match("blue", "brown") is False

    def test_age_mismatch(self):
        """'45' doesn't match '35'."""
        assert _values_match("45", "35") is False


class TestGetIndexedFact:
    def test_finds_age(self, mock_character):
        """Gets age fact from character."""
        result = _get_indexed_fact(mock_character, "age")
        assert result is not None
        assert result[0] == "45"

    def test_finds_eye_color(self, mock_character):
        """Gets eye_color fact from character."""
        result = _get_indexed_fact(mock_character, "eye_color")
        assert result is not None
        assert result[0] == "brown"

    def test_returns_none_for_missing(self, mock_character):
        """Returns None for missing fact."""
        result = _get_indexed_fact(mock_character, "occupation")
        assert result is None

    def test_case_insensitive_predicate(self, mock_character):
        """Predicate matching is case-insensitive."""
        result = _get_indexed_fact(mock_character, "AGE")
        assert result is not None


class TestCheckCharacterInWindow:
    def test_detects_age_conflict(self, mock_character):
        """Detects age contradiction: index=45, text=35."""
        window = "Greg is 35 years old."
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        assert len(conflicts) == 1
        assert conflicts[0].field == "age"
        assert conflicts[0].indexed_value == "45"
        assert conflicts[0].text_value == "35"

    def test_detects_eye_color_conflict(self, mock_character):
        """Detects eye color contradiction."""
        window = "Greg's blue eyes sparkled."
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        assert len(conflicts) == 1
        assert conflicts[0].field == "eye_color"
        assert conflicts[0].indexed_value == "brown"
        assert conflicts[0].text_value == "blue"

    def test_no_conflict_when_matches(self, mock_character):
        """No conflict when values match."""
        window = "Greg is 45 years old."
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        assert len(conflicts) == 0

    def test_skips_negated_claims(self, mock_character):
        """'not 35 years old' doesn't create conflict."""
        window = "Greg was not 35 years old."
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        assert len(conflicts) == 0

    def test_skips_former_claims(self, mock_character):
        """'formerly had brown eyes' is skipped."""
        window = "Greg formerly had blue eyes, now they're brown."
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        assert len(conflicts) == 0


# --- False Positive Prevention Tests ---


class TestFalsePositivePrevention:
    def test_multiple_characters_in_sentence(self, mock_character, mock_character_maya):
        """'Greg looked at Maya's blue eyes' doesn't attribute to Greg."""
        window = "Greg looked at Maya's blue eyes."
        # Check Greg - shouldn't find blue eyes conflict
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        eye_conflicts = [c for c in conflicts if c.field == "eye_color"]
        assert len(eye_conflicts) == 0

    def test_unrelated_color(self, mock_character):
        """'The blue sky above Greg' doesn't create eye_color conflict."""
        window = "The blue sky above Greg was beautiful."
        conflicts = _check_character_in_window(window, mock_character, "Greg")
        assert len(conflicts) == 0


# --- Integration Tests ---


class TestCheckText:
    def test_returns_conflicts(self, mock_project_root, mock_index):
        """Integration: finds conflicts in text."""
        with patch("edword.check._load_index", return_value=(mock_index, "book1")):
            result = check_text(mock_project_root, "Greg is 35 years old.")
            assert result["has_conflicts"] is True
            assert len(result["conflicts"]) == 1
            assert result["conflicts"][0]["field"] == "age"

    def test_no_conflicts(self, mock_project_root, mock_index):
        """Integration: no conflicts when text matches."""
        with patch("edword.check._load_index", return_value=(mock_index, "book1")):
            result = check_text(mock_project_root, "Greg is 45 years old.")
            assert result["has_conflicts"] is False
            assert len(result["conflicts"]) == 0

    def test_empty_text_error(self, mock_project_root):
        """Empty text raises error."""
        with pytest.raises(CheckError, match="cannot be empty"):
            check_text(mock_project_root, "")

    def test_whitespace_only_error(self, mock_project_root):
        """Whitespace-only text raises error."""
        with pytest.raises(CheckError, match="cannot be empty"):
            check_text(mock_project_root, "   ")

    def test_includes_snippet(self, mock_project_root, mock_index):
        """Conflict includes context snippet."""
        with patch("edword.check._load_index", return_value=(mock_index, "book1")):
            result = check_text(mock_project_root, "Greg is 35 years old.")
            assert "snippet" in result["conflicts"][0]
            assert "Greg" in result["conflicts"][0]["snippet"]

    def test_includes_book(self, mock_project_root, mock_index):
        """Result includes book identifier."""
        with patch("edword.check._load_index", return_value=(mock_index, "book1")):
            result = check_text(mock_project_root, "Greg walked in.")
            assert result["book"] == "book1"

    def test_includes_character_count(self, mock_project_root, mock_index):
        """Result includes count of characters checked."""
        with patch("edword.check._load_index", return_value=(mock_index, "book1")):
            result = check_text(mock_project_root, "Greg and Maya talked.")
            assert result["characters_checked"] >= 1

    def test_handles_no_characters(self, mock_project_root):
        """Handles index with no characters gracefully."""
        from edword.index.schema import AccumulatedIndex

        empty_index = AccumulatedIndex(
            book="book1",
            chapters_indexed=[],
            characters=[],
        )
        with patch("edword.check._load_index", return_value=(empty_index, "book1")):
            result = check_text(mock_project_root, "Some random text.")
            assert result["has_conflicts"] is False
            assert result["characters_checked"] == 0

    def test_handles_text_with_no_character_mentions(self, mock_project_root, mock_index):
        """Handles text that mentions no known characters."""
        with patch("edword.check._load_index", return_value=(mock_index, "book1")):
            result = check_text(mock_project_root, "The weather was nice.")
            assert result["has_conflicts"] is False
            assert result["characters_checked"] == 0


# --- Conflict Model Tests ---


class TestConflictModel:
    def test_to_dict(self):
        """Conflict converts to dictionary properly."""
        conflict = Conflict(
            entity_type="character",
            entity_name="Greg Walsh",
            field="age",
            indexed_value="45",
            text_value="35",
            severity="error",
            confidence=0.9,
            snippet="Greg is 35 years old.",
            indexed_evidence={"chapter": "chapter-01", "line": 10},
        )
        d = conflict.to_dict()
        assert d["entity_type"] == "character"
        assert d["entity_name"] == "Greg Walsh"
        assert d["field"] == "age"
        assert d["indexed_evidence"]["chapter"] == "chapter-01"

    def test_to_dict_without_evidence(self):
        """Conflict without evidence converts properly."""
        conflict = Conflict(
            entity_type="character",
            entity_name="Greg Walsh",
            field="age",
            indexed_value="45",
            text_value="35",
            severity="error",
            confidence=0.9,
            snippet="Greg is 35 years old.",
            indexed_evidence=None,
        )
        d = conflict.to_dict()
        assert d["indexed_evidence"] is None


# --- FactResult Tests ---


class TestFactResult:
    def test_factresult_namedtuple(self, mock_character):
        """FactResult is a proper NamedTuple with value and evidence."""
        result = _get_indexed_fact(mock_character, "age")
        assert result is not None
        assert result.value == "45"
        assert result.evidence is not None
        assert result.evidence["chapter"] == "chapter-01"

    def test_factresult_unpacking(self, mock_character):
        """FactResult can be unpacked like a tuple."""
        result = _get_indexed_fact(mock_character, "age")
        value, evidence = result
        assert value == "45"
        assert evidence is not None


# --- Load Index Error Tests ---


class TestLoadIndexErrors:
    def test_no_books_raises_check_error(self, mock_project_root):
        """Raises CheckError when no books found."""
        from edword.common import IndexError as CommonIndexError

        with patch("edword.check.load_index") as mock_load:
            mock_load.side_effect = CommonIndexError("No books found in project")
            with pytest.raises(CheckError, match="No books found"):
                check_text(mock_project_root, "Some text")

    def test_invalid_book_raises_check_error(self, mock_project_root):
        """Raises CheckError when book not found."""
        from edword.common import IndexError as CommonIndexError

        with patch("edword.check.load_index") as mock_load:
            mock_load.side_effect = CommonIndexError("Book 'foo' not found")
            with pytest.raises(CheckError, match="not found"):
                check_text(mock_project_root, "Some text", book="foo")

    def test_no_index_raises_check_error(self, mock_project_root):
        """Raises CheckError when no index for book."""
        from edword.common import IndexError as CommonIndexError

        with patch("edword.check.load_index") as mock_load:
            mock_load.side_effect = CommonIndexError("No index for 'book1'")
            with pytest.raises(CheckError, match="No index"):
                check_text(mock_project_root, "Some text")


# --- Overlapping Mention Tests ---


class TestOverlappingMentions:
    def test_longest_name_matched_first(self):
        """'Greg Walsh' matches before 'Greg' for same position."""
        from edword.index.schema import Character

        greg_walsh = Character(
            id="char_greg_walsh",
            canonical_name="Greg Walsh",
            mentions=[],
            facts=[],
            relationships=[],
            state_changes=[],
        )
        greg = Character(
            id="char_greg",
            canonical_name="Greg",
            mentions=[],
            facts=[],
            relationships=[],
            state_changes=[],
        )

        text = "Greg Walsh walked in."
        mentions = _find_character_mentions(text, [greg, greg_walsh])

        # Should only match "Greg Walsh", not "Greg" separately
        assert len(mentions) == 1
        assert mentions[0].matched_text == "Greg Walsh"
        assert mentions[0].character.id == "char_greg_walsh"

    def test_separate_mentions_both_found(self):
        """Both 'Greg Walsh' and separate 'Greg' are found."""
        from edword.index.schema import Character

        greg_walsh = Character(
            id="char_greg_walsh",
            canonical_name="Greg Walsh",
            mentions=[],
            facts=[],
            relationships=[],
            state_changes=[],
        )
        greg_other = Character(
            id="char_greg_other",
            canonical_name="Greg",
            mentions=[],
            facts=[],
            relationships=[],
            state_changes=[],
        )

        text = "Greg Walsh met Greg at the door."
        mentions = _find_character_mentions(text, [greg_other, greg_walsh])

        # Should find "Greg Walsh" and standalone "Greg"
        assert len(mentions) == 2
        matched_texts = [m.matched_text for m in mentions]
        assert "Greg Walsh" in matched_texts
        assert "Greg" in matched_texts


# --- Proximity-Based Negation Tests ---


class TestProximityNegation:
    def test_negation_inside_match_detected(self):
        """Negation inside the match span is detected."""
        text = "Greg formerly had blue eyes."
        # The match span would be roughly 0-24 for "Greg formerly had blue eyes"
        assert _has_negation_near(text, 0, 24) is True

    def test_negation_before_match_close(self):
        """Negation just before match is detected."""
        text = "He was not 45 years old."
        # "not" is at ~7-10, age claim would be at ~11-24
        assert _has_negation_near(text, 11, 24) is True

    def test_negation_far_from_match_not_detected(self):
        """Negation far from match is NOT detected."""
        text = "He was not happy, but his beautiful blue eyes shone."
        # "not" is at ~7-10, "blue eyes" would be at ~38-48
        # More than 4 words between them
        assert _has_negation_near(text, 38, 48) is False

    def test_no_negation_returns_false(self):
        """No negation in text returns False."""
        text = "Greg has blue eyes."
        assert _has_negation_near(text, 0, 19) is False


# --- Deduplication Tests ---


class TestDeduplication:
    def test_removes_duplicate_conflicts(self):
        """Removes duplicates based on (name, field, text_value)."""
        conflicts = [
            Conflict("character", "Greg", "age", "45", "35", "error", 0.9, "snippet1"),
            Conflict("character", "Greg", "age", "45", "35", "error", 0.8, "snippet2"),
        ]
        unique = _deduplicate_conflicts(conflicts)
        assert len(unique) == 1
        assert unique[0].snippet == "snippet1"  # Keeps first

    def test_keeps_different_fields(self):
        """Keeps conflicts for different fields."""
        conflicts = [
            Conflict("character", "Greg", "age", "45", "35", "error", 0.9, "snippet1"),
            Conflict("character", "Greg", "eye_color", "brown", "blue", "warning", 0.9, "snippet2"),
        ]
        unique = _deduplicate_conflicts(conflicts)
        assert len(unique) == 2

    def test_keeps_different_characters(self):
        """Keeps conflicts for different characters."""
        conflicts = [
            Conflict("character", "Greg", "age", "45", "35", "error", 0.9, "snippet1"),
            Conflict("character", "Maya", "age", "17", "35", "error", 0.9, "snippet2"),
        ]
        unique = _deduplicate_conflicts(conflicts)
        assert len(unique) == 2


# --- Fuzzy Matching Tests ---


class TestFuzzyMatching:
    def test_exact_match_works_without_rapidfuzz(self):
        """Exact match works regardless of rapidfuzz."""
        assert _values_match("brown", "brown") is True
        assert _values_match("BROWN", "brown") is True

    def test_numeric_match_works(self):
        """Numeric matching works for ages."""
        assert _values_match("45", "45") is True
        assert _values_match("45 years old", "45") is False  # Can't parse "45 years old" as int

    @pytest.mark.skipif(not HAS_RAPIDFUZZ, reason="rapidfuzz not installed")
    def test_fuzzy_match_with_rapidfuzz(self):
        """Fuzzy matching works when rapidfuzz is available."""
        # "dark brown" should fuzzy match "brown" with high similarity
        assert _values_match("brown", "dark brown") is True

    @pytest.mark.skipif(HAS_RAPIDFUZZ, reason="Test for when rapidfuzz not installed")
    def test_no_fuzzy_without_rapidfuzz(self):
        """Without rapidfuzz, only exact matches work."""
        assert _values_match("brown", "dark brown") is False
