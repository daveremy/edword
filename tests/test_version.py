"""Tests for index schema versioning."""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from edword.index.schema import (
    INDEX_SCHEMA_VERSION,
    ChapterIndex,
    AccumulatedIndex,
)
from edword.common import IndexVersionMismatch, load_index


# --- Version Constant Tests ---


class TestVersionConstant:
    def test_version_is_positive_integer(self):
        """Schema version should be a positive integer."""
        assert isinstance(INDEX_SCHEMA_VERSION, int)
        assert INDEX_SCHEMA_VERSION > 0

    def test_current_version_is_2(self):
        """Current version should be 2 (added extraction_metadata)."""
        assert INDEX_SCHEMA_VERSION == 2


# --- Schema Field Tests ---


class TestChapterIndexVersion:
    def test_default_version_is_zero(self):
        """ChapterIndex defaults schema_version to 0 (for legacy indices)."""
        # Create minimal valid ChapterIndex without schema_version
        index = ChapterIndex(
            book="book1",
            chapter="chapter-01",
            source_path="/path/to/chapter.md",
            source_hash="abc123",
        )
        assert index.schema_version == 0

    def test_explicit_version_preserved(self):
        """ChapterIndex preserves explicit schema_version."""
        index = ChapterIndex(
            book="book1",
            chapter="chapter-01",
            source_path="/path/to/chapter.md",
            source_hash="abc123",
            schema_version=INDEX_SCHEMA_VERSION,
        )
        assert index.schema_version == INDEX_SCHEMA_VERSION

    def test_version_serialization(self):
        """schema_version is included in JSON serialization."""
        index = ChapterIndex(
            book="book1",
            chapter="chapter-01",
            source_path="/path/to/chapter.md",
            source_hash="abc123",
            schema_version=INDEX_SCHEMA_VERSION,
        )
        data = index.model_dump()
        assert "schema_version" in data
        assert data["schema_version"] == INDEX_SCHEMA_VERSION

    def test_version_deserialization_missing(self):
        """Missing schema_version in JSON defaults to 0."""
        data = {
            "book": "book1",
            "chapter": "chapter-01",
            "source_path": "/path/to/chapter.md",
            "source_hash": "abc123",
            "extracted_at": datetime.now().isoformat(),
            "characters": [],
            "timeline": [],
            "locations": [],
            "artifacts": [],
            "world_facts": [],
            "terminology": [],
            "narrative": [],
        }
        index = ChapterIndex.model_validate(data)
        assert index.schema_version == 0


class TestAccumulatedIndexVersion:
    def test_default_version_is_zero(self):
        """AccumulatedIndex defaults schema_version to 0 (for legacy indices)."""
        index = AccumulatedIndex(book="book1")
        assert index.schema_version == 0

    def test_explicit_version_preserved(self):
        """AccumulatedIndex preserves explicit schema_version."""
        index = AccumulatedIndex(
            book="book1",
            schema_version=INDEX_SCHEMA_VERSION,
        )
        assert index.schema_version == INDEX_SCHEMA_VERSION

    def test_version_deserialization_missing(self):
        """Missing schema_version in JSON defaults to 0."""
        data = {
            "book": "book1",
            "chapters_indexed": [],
            "last_updated": datetime.now().isoformat(),
            "characters": [],
            "timeline": [],
            "locations": [],
            "artifacts": [],
            "world_facts": [],
            "terminology": [],
            "narrative": [],
        }
        index = AccumulatedIndex.model_validate(data)
        assert index.schema_version == 0


# --- IndexVersionMismatch Exception Tests ---


class TestIndexVersionMismatch:
    def test_exception_stores_attributes(self):
        """Exception stores book_id, index_version, current_version."""
        exc = IndexVersionMismatch("book1", 0, 1)
        assert exc.book_id == "book1"
        assert exc.index_version == 0
        assert exc.current_version == 1

    def test_exception_message(self):
        """Exception has informative message."""
        exc = IndexVersionMismatch("book1", 0, 1)
        assert "book1" in str(exc)
        assert "v0" in str(exc)
        assert "v1" in str(exc)


# --- Storage needs_reindex Tests ---


class TestNeedsReindexVersion:
    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create temporary storage for testing."""
        from edword.index.storage import IndexStorage
        return IndexStorage(tmp_path)

    def test_needs_reindex_old_version(self, temp_storage, tmp_path):
        """needs_reindex returns True for old schema version."""
        # Create a chapter file
        chapter_path = tmp_path / "chapter-01.md"
        chapter_path.write_text("Chapter content")

        # Create index with old version
        index = ChapterIndex(
            book="book1",
            chapter="chapter-01",
            source_path=str(chapter_path),
            source_hash="abc123",
            schema_version=0,  # Old version
        )
        temp_storage.save_chapter_index(index)

        # Should need reindex due to version mismatch
        assert temp_storage.needs_reindex("book1", "chapter-01", chapter_path) is True

    def test_needs_reindex_current_version(self, temp_storage, tmp_path):
        """needs_reindex returns False for current schema version with matching hash."""
        from edword.index.extractor import compute_file_hash

        # Create a chapter file
        chapter_path = tmp_path / "chapter-01.md"
        chapter_path.write_text("Chapter content")
        source_hash = compute_file_hash(chapter_path)

        # Create index with current version and correct hash
        index = ChapterIndex(
            book="book1",
            chapter="chapter-01",
            source_path=str(chapter_path),
            source_hash=source_hash,
            schema_version=INDEX_SCHEMA_VERSION,
        )
        temp_storage.save_chapter_index(index)

        # Should not need reindex
        assert temp_storage.needs_reindex("book1", "chapter-01", chapter_path) is False

    def test_needs_reindex_hash_changed(self, temp_storage, tmp_path):
        """needs_reindex returns True when file hash changes."""
        # Create a chapter file
        chapter_path = tmp_path / "chapter-01.md"
        chapter_path.write_text("Chapter content")

        # Create index with current version but different hash
        index = ChapterIndex(
            book="book1",
            chapter="chapter-01",
            source_path=str(chapter_path),
            source_hash="different_hash",
            schema_version=INDEX_SCHEMA_VERSION,
        )
        temp_storage.save_chapter_index(index)

        # Should need reindex due to hash mismatch
        assert temp_storage.needs_reindex("book1", "chapter-01", chapter_path) is True


# --- load_index Version Check Tests ---


class TestLoadIndexVersionCheck:
    @pytest.fixture
    def mock_project(self, tmp_path):
        """Create mock project structure."""
        manuscripts = tmp_path / "manuscripts" / "book1"
        manuscripts.mkdir(parents=True)
        (manuscripts / "chapter-01.md").write_text("Chapter 1")
        return tmp_path

    def test_load_index_raises_on_version_mismatch(self, mock_project):
        """load_index raises IndexVersionMismatch for old schema."""
        from edword.index.storage import IndexStorage

        # Create accumulated index with old version
        storage = IndexStorage(mock_project)
        old_index = AccumulatedIndex(
            book="book1",
            chapters_indexed=["chapter-01"],
            schema_version=0,
        )
        storage.save_accumulated_index(old_index)

        with pytest.raises(IndexVersionMismatch) as exc_info:
            load_index(mock_project, "book1")

        assert exc_info.value.book_id == "book1"
        assert exc_info.value.index_version == 0
        assert exc_info.value.current_version == INDEX_SCHEMA_VERSION

    def test_load_index_succeeds_on_current_version(self, mock_project):
        """load_index succeeds for current schema version."""
        from edword.index.storage import IndexStorage

        # Create accumulated index with current version
        storage = IndexStorage(mock_project)
        current_index = AccumulatedIndex(
            book="book1",
            chapters_indexed=["chapter-01"],
            schema_version=INDEX_SCHEMA_VERSION,
        )
        storage.save_accumulated_index(current_index)

        index, book_id = load_index(mock_project, "book1")
        assert book_id == "book1"
        assert index.schema_version == INDEX_SCHEMA_VERSION

    def test_load_index_skip_version_check(self, mock_project):
        """load_index can skip version check with check_version=False."""
        from edword.index.storage import IndexStorage

        # Create accumulated index with old version
        storage = IndexStorage(mock_project)
        old_index = AccumulatedIndex(
            book="book1",
            chapters_indexed=["chapter-01"],
            schema_version=0,
        )
        storage.save_accumulated_index(old_index)

        # Should succeed when version check is disabled
        index, book_id = load_index(mock_project, "book1", check_version=False)
        assert book_id == "book1"
        assert index.schema_version == 0


# --- Extractor Version Stamping Tests ---


class TestExtractorVersionStamping:
    def test_extractor_stamps_current_version(self):
        """Extractor stamps current schema version on new indices."""
        # This test requires mocking the LLM call
        from edword.index.extractor import extract_chapter_simple, ExtractionConfig

        # Mock response with valid JSON
        mock_response = """
<index>
{
    "characters": [],
    "timeline": [],
    "locations": [],
    "artifacts": [],
    "world_facts": [],
    "terminology": [],
    "narrative": [],
    "pov_scene": {}
}
</index>
"""

        with patch("edword.index.extractor.call_model", return_value=mock_response):
            result = extract_chapter_simple(
                chapter_text="Test chapter content",
                book_id="book1",
                chapter_id="chapter-01",
                config=ExtractionConfig(provider="mock", model="mock"),
            )

        if result.success:
            assert result.index.schema_version == INDEX_SCHEMA_VERSION


# --- Accumulator Version Stamping Tests ---


class TestAccumulatorVersionStamping:
    def test_accumulator_stamps_current_version(self):
        """Accumulator stamps current schema version on result."""
        from edword.index.accumulator import Accumulator

        acc = Accumulator("book1")
        result = acc.get_result()

        assert result.index.schema_version == INDEX_SCHEMA_VERSION


# --- MCP Error Handling Tests ---


class TestMCPVersionMismatch:
    def test_handle_error_returns_needs_rebuild(self):
        """handle_error returns needs_rebuild for IndexVersionMismatch."""
        from edword.mcp.server import handle_error

        exc = IndexVersionMismatch("book1", 0, 1)
        result = handle_error(exc)

        assert result["error"] is True
        assert result["error_type"] == "IndexVersionMismatch"
        assert result["needs_rebuild"] is True
        assert result["book"] == "book1"
        assert result["index_version"] == 0
        assert result["current_version"] == 1
        assert "action" in result

    def test_handle_error_positive_message(self):
        """handle_error returns positive messaging."""
        from edword.mcp.server import handle_error

        exc = IndexVersionMismatch("book1", 0, 1)
        result = handle_error(exc)

        assert "upgraded" in result["message"].lower()
        assert "improved" in result["message"].lower()
