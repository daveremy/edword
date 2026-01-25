"""Tests for query operations."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from edword.query import (
    QueryError,
    _normalize,
    _parse_chapter_range,
    _sort_matches,
    _chapter_matches_range,
    _get_chapter_number,
    _is_chapter_at_or_before,
    query_character,
    query_timeline,
    query_location,
    query_artifact,
    query_world,
    query_search,
)


# --- Helper function tests ---


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("GREG") == "greg"

    def test_strip_whitespace(self):
        assert _normalize("  Greg  ") == "greg"

    def test_combined(self):
        assert _normalize("  GREG WALSH  ") == "greg walsh"


class TestParseChapterRange:
    def test_simple_range(self):
        """Chapter range '1-5' returns ['1','2','3','4','5']."""
        assert _parse_chapter_range("1-5") == ["1", "2", "3", "4", "5"]

    def test_reversed_range(self):
        """Reversed range '5-1' still returns ['1','2','3','4','5']."""
        assert _parse_chapter_range("5-1") == ["1", "2", "3", "4", "5"]

    def test_whitespace_in_range(self):
        """Range with whitespace '1 - 5' is handled."""
        assert _parse_chapter_range("1 - 5") == ["1", "2", "3", "4", "5"]

    def test_list_format(self):
        """List format '1,3,7' returns ['1','3','7']."""
        assert _parse_chapter_range("1,3,7") == ["1", "3", "7"]

    def test_list_with_whitespace(self):
        """List with whitespace '1, 3, 7' returns ['1','3','7']."""
        assert _parse_chapter_range("1, 3, 7") == ["1", "3", "7"]

    def test_empty_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="Empty chapter range"):
            _parse_chapter_range("")

    def test_invalid_range_raises(self):
        """Invalid range 'abc' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid range format"):
            _parse_chapter_range("abc-def")

    def test_invalid_list_raises(self):
        """Invalid list 'a,b,c' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid chapter list"):
            _parse_chapter_range("a,b,c")


class TestChapterMatchesRange:
    def test_matches_chapter_id(self):
        """chapter-05 matches ['5']."""
        assert _chapter_matches_range("chapter-05", ["5"]) is True

    def test_matches_with_suffix(self):
        """chapter-05b matches ['5']."""
        assert _chapter_matches_range("chapter-05b", ["5"]) is True

    def test_no_match(self):
        """chapter-10 doesn't match ['5', '6']."""
        assert _chapter_matches_range("chapter-10", ["5", "6"]) is False

    def test_none_chapter_id(self):
        """None chapter_id returns False."""
        assert _chapter_matches_range(None, ["5"]) is False

    def test_empty_chapter_id(self):
        """Empty chapter_id returns False."""
        assert _chapter_matches_range("", ["5"]) is False


class TestSortMatches:
    def test_exact_first(self):
        """Exact match comes first."""
        matches = [
            {"canonical_name": "Greg Walsh Jr"},
            {"canonical_name": "Greg Walsh"},
        ]
        sorted_matches = _sort_matches(matches, "Greg Walsh")
        assert sorted_matches[0]["canonical_name"] == "Greg Walsh"

    def test_alphabetical_order(self):
        """Non-exact matches sorted alphabetically."""
        matches = [
            {"canonical_name": "Zach Walsh"},
            {"canonical_name": "Adam Walsh"},
        ]
        sorted_matches = _sort_matches(matches, "someone")
        assert sorted_matches[0]["canonical_name"] == "Adam Walsh"
        assert sorted_matches[1]["canonical_name"] == "Zach Walsh"

    def test_custom_name_field(self):
        """Uses custom name_field."""
        matches = [
            {"name": "Location B"},
            {"name": "Location A"},
        ]
        sorted_matches = _sort_matches(matches, "someone", name_field="name")
        assert sorted_matches[0]["name"] == "Location A"


# --- Query function tests with mocked index ---


@pytest.fixture
def mock_index():
    """Create a mock AccumulatedIndex for testing."""
    from edword.index.schema import (
        AccumulatedIndex,
        Character,
        CharacterFact,
        Relationship,
        TimelineEvent,
        Location,
        Artifact,
        WorldFact,
        Terminology,
        Evidence,
        WorldFactCategory,
        Confidence,
    )

    evidence = Evidence(quote="test quote", line=1, char_span=None, chapter="chapter-01")

    return AccumulatedIndex(
        book="book1",
        chapters_indexed=["chapter-01"],
        last_updated="2024-01-01T00:00:00",
        characters=[
            Character(
                id="char_greg",
                canonical_name="Greg Walsh",
                mentions=["Greg", "Dr. Walsh"],
                facts=[
                    CharacterFact(
                        predicate="age",
                        value="45",
                        confidence=Confidence.HIGH,
                        evidence=evidence,
                    )
                ],
                relationships=[],
                state_changes=[],
                appearances=["chapter-01"],
            ),
            Character(
                id="char_maya",
                canonical_name="Maya Walsh",
                mentions=["Maya"],
                facts=[],
                relationships=[],
                state_changes=[],
                appearances=["chapter-01"],
            ),
        ],
        timeline=[
            TimelineEvent(
                id="evt_1",
                event="Test event 1",
                evidence=evidence,
            ),
            TimelineEvent(
                id="evt_2",
                event="Another event",
                evidence=Evidence(quote="test", line=10, char_span=None, chapter="chapter-02"),
            ),
        ],
        locations=[
            Location(
                id="loc_cascade",
                name="Cascade Labs",
                description="Tech company in Seattle",
                evidence=evidence,
            ),
        ],
        artifacts=[
            Artifact(
                id="item_headset",
                name="Neural Headset",
                status="prototype",
                evidence=evidence,
            ),
        ],
        world_facts=[
            WorldFact(
                category=WorldFactCategory.TECHNOLOGY,
                fact="Neural interfaces allow brain-computer communication",
                confidence=Confidence.HIGH,
                evidence=evidence,
            ),
        ],
        terminology=[
            Terminology(
                term="Myriad",
                definition="The collective of internal entities",
                first_mention=True,
                evidence=evidence,
            ),
        ],
        narrative=[],
    )


@pytest.fixture
def mock_project_root(tmp_path):
    """Create a temporary project root."""
    return tmp_path


class TestQueryCharacter:
    def test_found_by_canonical_name(self, mock_project_root, mock_index):
        """Character lookup by canonical name works."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_character(mock_project_root, "Greg Walsh")
            assert result["found"] is True
            assert result["character"]["canonical_name"] == "Greg Walsh"

    def test_found_by_mention(self, mock_project_root, mock_index):
        """Character lookup by alias/mention works."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_character(mock_project_root, "Dr. Walsh")
            assert result["found"] is True
            assert result["character"]["canonical_name"] == "Greg Walsh"

    def test_case_insensitive(self, mock_project_root, mock_index):
        """Character lookup is case-insensitive."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_character(mock_project_root, "greg walsh")
            assert result["found"] is True

    def test_not_found(self, mock_project_root, mock_index):
        """Missing character returns found=false."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_character(mock_project_root, "NonexistentPerson")
            assert result["found"] is False
            assert result["character"] is None

    def test_partial_match_single(self, mock_project_root, mock_index):
        """Single partial match is returned as found."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_character(mock_project_root, "Maya")
            assert result["found"] is True
            assert result["character"]["canonical_name"] == "Maya Walsh"

    def test_partial_match_multiple(self, mock_project_root, mock_index):
        """Multiple partial matches return matches list."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_character(mock_project_root, "Walsh")
            # Both Greg Walsh and Maya Walsh contain "Walsh"
            assert result["found"] is False
            assert "matches" in result
            assert len(result["matches"]) == 2


class TestQueryTimeline:
    def test_returns_all_events(self, mock_project_root, mock_index):
        """Timeline returns all events without filter."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_timeline(mock_project_root)
            assert result["total_events"] == 2

    def test_chapter_range_filter(self, mock_project_root, mock_index):
        """Timeline respects chapter range filter."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_timeline(mock_project_root, chapter_range="1")
            assert result["total_events"] == 1
            assert result["events"][0]["id"] == "evt_1"

    def test_limit(self, mock_project_root, mock_index):
        """Timeline respects limit parameter."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_timeline(mock_project_root, limit=1)
            assert result["total_events"] == 1

    def test_empty_result(self, mock_project_root, mock_index):
        """Timeline with no matches returns empty list."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_timeline(mock_project_root, chapter_range="99")
            assert result["total_events"] == 0
            assert result["events"] == []


class TestQueryLocation:
    def test_found(self, mock_project_root, mock_index):
        """Location lookup returns correct data."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_location(mock_project_root, "Cascade Labs")
            assert result["found"] is True
            assert result["location"]["name"] == "Cascade Labs"

    def test_case_insensitive(self, mock_project_root, mock_index):
        """Location lookup is case-insensitive."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_location(mock_project_root, "cascade labs")
            assert result["found"] is True

    def test_not_found(self, mock_project_root, mock_index):
        """Missing location returns found=false."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_location(mock_project_root, "Nonexistent")
            assert result["found"] is False


class TestQueryArtifact:
    def test_found(self, mock_project_root, mock_index):
        """Artifact lookup returns correct data."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_artifact(mock_project_root, "Neural Headset")
            assert result["found"] is True
            assert result["artifact"]["name"] == "Neural Headset"

    def test_not_found(self, mock_project_root, mock_index):
        """Missing artifact returns found=false."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_artifact(mock_project_root, "Nonexistent")
            assert result["found"] is False


class TestQueryWorld:
    def test_found_in_world_facts(self, mock_project_root, mock_index):
        """World query finds matches in world_facts."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_world(mock_project_root, "neural")
            assert result["found"] is True
            assert len(result["world_facts"]) == 1

    def test_found_in_terminology(self, mock_project_root, mock_index):
        """World query finds matches in terminology."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_world(mock_project_root, "Myriad")
            assert result["found"] is True
            assert len(result["terminology"]) == 1

    def test_not_found(self, mock_project_root, mock_index):
        """World query with no matches returns empty."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_world(mock_project_root, "nonexistent")
            assert result["found"] is False
            assert result["total_matches"] == 0


class TestQuerySearch:
    def test_searches_characters(self, mock_project_root, mock_index):
        """Search finds characters."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_search(mock_project_root, "Greg")
            assert len(result["characters"]) == 1
            assert result["characters"][0]["canonical_name"] == "Greg Walsh"

    def test_searches_locations(self, mock_project_root, mock_index):
        """Search finds locations."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_search(mock_project_root, "Cascade")
            assert len(result["locations"]) == 1

    def test_searches_events(self, mock_project_root, mock_index):
        """Search finds timeline events."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_search(mock_project_root, "event")
            assert len(result["events"]) == 2

    def test_searches_artifacts(self, mock_project_root, mock_index):
        """Search finds artifacts."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_search(mock_project_root, "Neural")
            assert len(result["artifacts"]) == 1

    def test_limit_per_dimension(self, mock_project_root, mock_index):
        """Search respects limit per dimension."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_search(mock_project_root, "event", limit=1)
            assert len(result["events"]) == 1

    def test_total_matches(self, mock_project_root, mock_index):
        """Search returns correct total."""
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            result = query_search(mock_project_root, "Walsh")
            assert result["total_matches"] == 2  # Greg Walsh and Maya Walsh


# --- Error handling tests ---


class TestEmptyQueryValidation:
    """Tests for empty query string validation."""

    def test_character_empty_name_raises(self, mock_project_root, mock_index):
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            with pytest.raises(QueryError, match="cannot be empty"):
                query_character(mock_project_root, "")

    def test_character_whitespace_only_raises(self, mock_project_root, mock_index):
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            with pytest.raises(QueryError, match="cannot be empty"):
                query_character(mock_project_root, "   ")

    def test_location_empty_name_raises(self, mock_project_root, mock_index):
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            with pytest.raises(QueryError, match="cannot be empty"):
                query_location(mock_project_root, "")

    def test_artifact_empty_name_raises(self, mock_project_root, mock_index):
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            with pytest.raises(QueryError, match="cannot be empty"):
                query_artifact(mock_project_root, "")

    def test_world_empty_term_raises(self, mock_project_root, mock_index):
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            with pytest.raises(QueryError, match="cannot be empty"):
                query_world(mock_project_root, "")

    def test_search_empty_query_raises(self, mock_project_root, mock_index):
        with patch("edword.query._load_index", return_value=(mock_index, "book1")):
            with pytest.raises(QueryError, match="cannot be empty"):
                query_search(mock_project_root, "")


class TestQueryErrors:
    def test_no_books_raises(self, mock_project_root):
        """Query on project with no books raises error."""
        from edword.discovery import ProjectStructure

        mock_project = ProjectStructure(
            root=mock_project_root,
            manuscripts_dir=mock_project_root / "manuscripts",
            codex_dir=mock_project_root / "codex",
            books=[],
            codex_files=[],
        )
        with patch("edword.common.discover_project", return_value=mock_project):
            with pytest.raises(QueryError, match="No books found"):
                query_character(mock_project_root, "Greg")

    def test_nonexistent_book_raises(self, mock_project_root, mock_index):
        """Query on non-existent book raises error."""
        from edword.discovery import ProjectStructure, BookInfo

        mock_project = ProjectStructure(
            root=mock_project_root,
            manuscripts_dir=mock_project_root / "manuscripts",
            codex_dir=mock_project_root / "codex",
            books=[BookInfo(name="book1", path=mock_project_root, chapters=[])],
            codex_files=[],
        )
        with patch("edword.common.discover_project", return_value=mock_project):
            with patch("edword.common.get_book_by_name", return_value=None):
                with pytest.raises(QueryError, match="not found"):
                    query_character(mock_project_root, "Greg", book="nonexistent")

    def test_no_index_raises(self, mock_project_root):
        """Query before index build raises error."""
        from edword.discovery import ProjectStructure, BookInfo

        mock_project = ProjectStructure(
            root=mock_project_root,
            manuscripts_dir=mock_project_root / "manuscripts",
            codex_dir=mock_project_root / "codex",
            books=[BookInfo(name="book1", path=mock_project_root, chapters=[])],
            codex_files=[],
        )
        with patch("edword.common.discover_project", return_value=mock_project):
            with patch("edword.common.get_book_by_name", return_value=mock_project.books[0]):
                with patch("edword.common.IndexStorage") as MockStorage:
                    MockStorage.return_value.load_accumulated_index.return_value = None
                    with pytest.raises(QueryError, match="No index"):
                        query_character(mock_project_root, "Greg")


# --- Chapter number extraction tests ---


class TestGetChapterNumber:
    def test_extracts_from_chapter_id(self):
        """Extracts 5 from 'chapter-05'."""
        assert _get_chapter_number("chapter-05") == 5

    def test_extracts_with_suffix(self):
        """Extracts 5 from 'chapter-05b'."""
        assert _get_chapter_number("chapter-05b") == 5

    def test_strips_leading_zeros(self):
        """Extracts 5 from 'chapter-005'."""
        assert _get_chapter_number("chapter-005") == 5

    def test_none_returns_none(self):
        """None chapter_id returns None."""
        assert _get_chapter_number(None) is None

    def test_empty_returns_none(self):
        """Empty chapter_id returns None."""
        assert _get_chapter_number("") is None

    def test_no_numbers_returns_none(self):
        """Chapter ID without numbers returns None."""
        assert _get_chapter_number("prologue") is None


class TestIsChapterAtOrBefore:
    def test_at_chapter(self):
        """chapter-05 is at chapter 5."""
        assert _is_chapter_at_or_before("chapter-05", 5) is True

    def test_before_chapter(self):
        """chapter-03 is before chapter 5."""
        assert _is_chapter_at_or_before("chapter-03", 5) is True

    def test_after_chapter(self):
        """chapter-10 is after chapter 5."""
        assert _is_chapter_at_or_before("chapter-10", 5) is False

    def test_none_chapter_id(self):
        """None chapter_id returns False."""
        assert _is_chapter_at_or_before(None, 5) is False


# --- World query with as_of_chapter tests ---


@pytest.fixture
def mock_index_multi_chapter():
    """Create a mock AccumulatedIndex with data from multiple chapters."""
    from edword.index.schema import (
        AccumulatedIndex,
        WorldFact,
        Terminology,
        Evidence,
        WorldFactCategory,
        Confidence,
    )

    return AccumulatedIndex(
        book="book1",
        chapters_indexed=["chapter-01", "chapter-03", "chapter-05"],
        last_updated="2024-01-01T00:00:00",
        characters=[],
        timeline=[],
        locations=[],
        artifacts=[],
        world_facts=[
            WorldFact(
                category=WorldFactCategory.TECHNOLOGY,
                fact="Neural interfaces introduced",
                confidence=Confidence.HIGH,
                evidence=Evidence(quote="test", line=1, char_span=None, chapter="chapter-01"),
            ),
            WorldFact(
                category=WorldFactCategory.TECHNOLOGY,
                fact="Neural interfaces can control devices",
                confidence=Confidence.HIGH,
                evidence=Evidence(quote="test", line=1, char_span=None, chapter="chapter-03"),
            ),
            WorldFact(
                category=WorldFactCategory.TECHNOLOGY,
                fact="Neural interfaces become widespread",
                confidence=Confidence.HIGH,
                evidence=Evidence(quote="test", line=1, char_span=None, chapter="chapter-05"),
            ),
        ],
        terminology=[
            Terminology(
                term="Neural Interface",
                definition="Brain-computer connection device",
                first_mention=True,
                evidence=Evidence(quote="test", line=1, char_span=None, chapter="chapter-01"),
            ),
            Terminology(
                term="Neural Interface",
                definition="Updated: Now includes wireless capability",
                first_mention=False,
                evidence=Evidence(quote="test", line=1, char_span=None, chapter="chapter-05"),
            ),
        ],
        narrative=[],
    )


class TestQueryWorldAsOfChapter:
    def test_no_filter_returns_all(self, mock_project_root, mock_index_multi_chapter):
        """Without as_of, returns all matching entries."""
        with patch("edword.query._load_index", return_value=(mock_index_multi_chapter, "book1")):
            result = query_world(mock_project_root, "Neural")
            assert result["found"] is True
            assert len(result["world_facts"]) == 3
            assert len(result["terminology"]) == 2

    def test_as_of_filters_world_facts(self, mock_project_root, mock_index_multi_chapter):
        """as_of_chapter filters world_facts to chapters at or before."""
        with patch("edword.query._load_index", return_value=(mock_index_multi_chapter, "book1")):
            result = query_world(mock_project_root, "Neural", as_of_chapter="3")
            assert result["found"] is True
            assert len(result["world_facts"]) == 2  # chapter 1 and 3, not 5
            assert result["as_of_chapter"] == 3

    def test_as_of_filters_terminology(self, mock_project_root, mock_index_multi_chapter):
        """as_of_chapter filters terminology to chapters at or before."""
        with patch("edword.query._load_index", return_value=(mock_index_multi_chapter, "book1")):
            result = query_world(mock_project_root, "Neural", as_of_chapter="3")
            assert len(result["terminology"]) == 1  # only chapter 1

    def test_as_of_accepts_chapter_id_format(self, mock_project_root, mock_index_multi_chapter):
        """as_of_chapter accepts 'chapter-03' format."""
        with patch("edword.query._load_index", return_value=(mock_index_multi_chapter, "book1")):
            result = query_world(mock_project_root, "Neural", as_of_chapter="chapter-03")
            assert result["as_of_chapter"] == 3
            assert len(result["world_facts"]) == 2

    def test_as_of_invalid_raises(self, mock_project_root, mock_index_multi_chapter):
        """Invalid as_of_chapter raises QueryError."""
        with patch("edword.query._load_index", return_value=(mock_index_multi_chapter, "book1")):
            with pytest.raises(QueryError, match="Invalid chapter"):
                query_world(mock_project_root, "Neural", as_of_chapter="abc")

    def test_includes_chapter_in_output(self, mock_project_root, mock_index_multi_chapter):
        """Each result includes chapter provenance."""
        with patch("edword.query._load_index", return_value=(mock_index_multi_chapter, "book1")):
            result = query_world(mock_project_root, "Neural")
            for fact in result["world_facts"]:
                assert "chapter" in fact
            for term in result["terminology"]:
                assert "chapter" in term
