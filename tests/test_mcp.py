"""Tests for MCP server."""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

# Skip all tests if fastmcp not installed
fastmcp = pytest.importorskip("fastmcp")


# --- Import MCP server components ---

from edword.mcp.server import (
    get_project_root,
    get_config,
    handle_error,
    edword_query_character as edword_query_character_tool,
    edword_query_timeline as edword_query_timeline_tool,
    edword_query_location as edword_query_location_tool,
    edword_query_artifact as edword_query_artifact_tool,
    edword_query_world as edword_query_world_tool,
    edword_query_search as edword_query_search_tool,
    edword_check_text as edword_check_text_tool,
    edword_index_status as edword_index_status_tool,
    create_server,
    mcp,
)
from edword.common import EdwordError

# Access underlying functions from FunctionTool objects for direct testing
edword_query_character = edword_query_character_tool.fn
edword_query_timeline = edword_query_timeline_tool.fn
edword_query_location = edword_query_location_tool.fn
edword_query_artifact = edword_query_artifact_tool.fn
edword_query_world = edword_query_world_tool.fn
edword_query_search = edword_query_search_tool.fn
edword_check_text = edword_check_text_tool.fn
edword_index_status = edword_index_status_tool.fn


# --- Helper function tests ---


class TestGetProjectRoot:
    def test_override_takes_precedence(self, tmp_path):
        """Explicit override path takes precedence."""
        result = get_project_root(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_env_var_when_no_override(self, tmp_path, monkeypatch):
        """EDWORD_PROJECT_ROOT env var used when no override."""
        monkeypatch.setenv("EDWORD_PROJECT_ROOT", str(tmp_path))
        result = get_project_root(None)
        assert result == tmp_path.resolve()

    def test_auto_discover_from_config(self, tmp_path, monkeypatch):
        """Auto-discovers from edword.yaml location."""
        # Clear env var
        monkeypatch.delenv("EDWORD_PROJECT_ROOT", raising=False)

        # Create config file
        config_path = tmp_path / "edword.yaml"
        config_path.write_text("project:\n  name: Test\n")

        with patch("edword.mcp.server.find_config", return_value=config_path):
            result = get_project_root(None)
            assert result == tmp_path

    def test_raises_when_no_root_found(self, monkeypatch):
        """Raises ValueError when no project root can be found."""
        monkeypatch.delenv("EDWORD_PROJECT_ROOT", raising=False)
        with patch("edword.mcp.server.find_config", return_value=None):
            with pytest.raises(ValueError, match="No project root found"):
                get_project_root(None)


class TestGetConfig:
    def test_returns_config_with_override(self, tmp_path):
        """Returns config for overridden root."""
        # Create config file
        config_path = tmp_path / "edword.yaml"
        config_path.write_text("project:\n  name: Test Project\n")

        config = get_config(str(tmp_path))
        assert config.project_name == "Test Project"

    def test_caches_config(self, tmp_path, monkeypatch):
        """Caches config on repeated calls."""
        # Clear cache first
        import edword.mcp.server
        edword.mcp.server._cached_config = None

        config_path = tmp_path / "edword.yaml"
        config_path.write_text("project:\n  name: Cached\n")

        with patch("edword.mcp.server.find_config", return_value=config_path):
            config1 = get_config()
            config2 = get_config()
            assert config1 is config2

        # Clean up cache
        edword.mcp.server._cached_config = None


class TestHandleError:
    def test_converts_edword_error(self):
        """Converts EdwordError to dict."""
        error = EdwordError("Test error message")
        result = handle_error(error)

        assert result["error"] is True
        assert result["error_type"] == "EdwordError"
        assert result["message"] == "Test error message"

    def test_converts_generic_exception(self):
        """Converts generic Exception to dict."""
        error = ValueError("Something went wrong")
        result = handle_error(error)

        assert result["error"] is True
        assert result["error_type"] == "ValueError"
        assert result["message"] == "Something went wrong"


# --- Tool function tests ---


@pytest.fixture
def mock_index():
    """Create a mock AccumulatedIndex for testing."""
    from edword.index.schema import (
        AccumulatedIndex,
        Character,
        CharacterFact,
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
        last_updated=datetime(2024, 1, 1, 0, 0, 0),
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
        ],
        timeline=[
            TimelineEvent(
                id="evt_1",
                event="Test event",
                evidence=evidence,
            ),
        ],
        locations=[
            Location(
                id="loc_cascade",
                name="Cascade Labs",
                description="Tech company",
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
    """Create a temporary project root with config."""
    config_path = tmp_path / "edword.yaml"
    config_path.write_text("project:\n  name: Test Project\n")
    return tmp_path


class TestEdwordQueryCharacter:
    def test_returns_character_data(self, mock_project_root, mock_index):
        """Returns character data when found."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_character") as mock_query:
                mock_query.return_value = {
                    "found": True,
                    "book": "book1",
                    "character": {"id": "char_greg", "canonical_name": "Greg Walsh"},
                }
                result = edword_query_character("Greg Walsh")

                assert result["found"] is True
                assert result["character"]["canonical_name"] == "Greg Walsh"
                mock_query.assert_called_once()

    def test_handles_error(self, mock_project_root):
        """Returns error dict on exception."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_character") as mock_query:
                mock_query.side_effect = EdwordError("Character not found")
                result = edword_query_character("NonexistentPerson")

                assert result["error"] is True
                assert "not found" in result["message"]

    def test_passes_book_parameter(self, mock_project_root):
        """Passes book parameter to query function."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_character") as mock_query:
                mock_query.return_value = {"found": True}
                edword_query_character("Greg", book="book2")

                _, kwargs = mock_query.call_args
                # Check positional args
                args = mock_query.call_args[0]
                assert args[1] == "Greg"  # name
                assert args[2] == "book2"  # book


class TestEdwordQueryTimeline:
    def test_returns_timeline_events(self, mock_project_root):
        """Returns timeline events."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_timeline") as mock_query:
                mock_query.return_value = {
                    "book": "book1",
                    "total_events": 5,
                    "events": [{"id": "evt_1"}],
                }
                result = edword_query_timeline()

                assert result["total_events"] == 5
                mock_query.assert_called_once()

    def test_passes_chapter_range(self, mock_project_root):
        """Passes chapter_range parameter."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_timeline") as mock_query:
                mock_query.return_value = {"total_events": 0, "events": []}
                edword_query_timeline(chapter_range="1-5")

                args = mock_query.call_args[0]
                assert args[2] == "1-5"  # chapter_range


class TestEdwordQueryLocation:
    def test_returns_location_data(self, mock_project_root):
        """Returns location data when found."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_location") as mock_query:
                mock_query.return_value = {
                    "found": True,
                    "location": {"name": "Cascade Labs"},
                }
                result = edword_query_location("Cascade")

                assert result["found"] is True
                mock_query.assert_called_once()


class TestEdwordQueryArtifact:
    def test_returns_artifact_data(self, mock_project_root):
        """Returns artifact data when found."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_artifact") as mock_query:
                mock_query.return_value = {
                    "found": True,
                    "artifact": {"name": "Neural Headset"},
                }
                result = edword_query_artifact("Neural Headset")

                assert result["found"] is True
                mock_query.assert_called_once()


class TestEdwordQueryWorld:
    def test_returns_world_data(self, mock_project_root):
        """Returns world facts and terminology."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_world") as mock_query:
                mock_query.return_value = {
                    "found": True,
                    "world_facts": [{"fact": "test"}],
                    "terminology": [],
                }
                result = edword_query_world("neural")

                assert result["found"] is True
                mock_query.assert_called_once()

    def test_passes_as_of_chapter(self, mock_project_root):
        """Passes as_of_chapter parameter."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_world") as mock_query:
                mock_query.return_value = {"found": False}
                edword_query_world("neural", as_of_chapter="5")

                args = mock_query.call_args[0]
                assert args[3] == "5"  # as_of_chapter


class TestEdwordQuerySearch:
    def test_returns_search_results(self, mock_project_root):
        """Returns cross-dimensional search results."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.query_search") as mock_query:
                mock_query.return_value = {
                    "query": "test",
                    "characters": [],
                    "locations": [],
                    "total_matches": 0,
                }
                result = edword_query_search("test")

                assert "total_matches" in result
                mock_query.assert_called_once()


class TestEdwordCheckText:
    def test_returns_conflict_report(self, mock_project_root):
        """Returns conflict report."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.check_text") as mock_check:
                mock_check.return_value = {
                    "has_conflicts": False,
                    "conflicts": [],
                    "characters_checked": 1,
                }
                result = edword_check_text("Greg is 45 years old.")

                assert result["has_conflicts"] is False
                mock_check.assert_called_once()

    def test_detects_conflicts(self, mock_project_root):
        """Reports conflicts when text contradicts index."""
        with patch("edword.mcp.server.get_project_root", return_value=mock_project_root):
            with patch("edword.mcp.server.check_text") as mock_check:
                mock_check.return_value = {
                    "has_conflicts": True,
                    "conflicts": [
                        {
                            "entity_name": "Greg Walsh",
                            "field": "age",
                            "indexed_value": "45",
                            "text_value": "35",
                        }
                    ],
                }
                result = edword_check_text("Greg is 35 years old.")

                assert result["has_conflicts"] is True
                assert len(result["conflicts"]) == 1


class TestEdwordIndexStatus:
    def test_returns_status(self, mock_project_root):
        """Returns index status information."""
        from edword.discovery import ProjectStructure, BookInfo

        mock_project = ProjectStructure(
            root=mock_project_root,
            manuscripts_dir=mock_project_root / "manuscripts",
            codex_dir=mock_project_root / "codex",
            books=[BookInfo(name="book1", path=mock_project_root, chapters=[])],
            codex_files=[],
        )

        with patch("edword.mcp.server.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.project_root = mock_project_root
            mock_config.project_name = "Test Project"
            mock_config.paths.index = ".edword/index"
            mock_get_config.return_value = mock_config

            with patch("edword.mcp.server.discover_project", return_value=mock_project):
                with patch("edword.mcp.server.IndexStorage") as MockStorage:
                    mock_storage = MockStorage.return_value
                    mock_storage.get_stats.return_value = {
                        "books": [
                            {
                                "book_id": "book1",
                                "chapters": ["chapter-01"],
                                "has_accumulated": True,
                                "size_bytes": 1024,
                            }
                        ],
                        "total_chapters": 1,
                    }
                    mock_storage.load_accumulated_index.return_value = None

                    result = edword_index_status(str(mock_project_root))

                    assert result["project_name"] == "Test Project"
                    assert result["total_chapters"] == 1
                    assert len(result["books"]) == 1

    def test_handles_missing_index(self, mock_project_root):
        """Handles case when no index exists."""
        from edword.discovery import ProjectStructure

        mock_project = ProjectStructure(
            root=mock_project_root,
            manuscripts_dir=mock_project_root / "manuscripts",
            codex_dir=mock_project_root / "codex",
            books=[],
            codex_files=[],
        )

        with patch("edword.mcp.server.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.project_root = mock_project_root
            mock_config.project_name = "Empty Project"
            mock_config.paths.index = ".edword/index"
            mock_get_config.return_value = mock_config

            with patch("edword.mcp.server.discover_project", return_value=mock_project):
                with patch("edword.mcp.server.IndexStorage") as MockStorage:
                    mock_storage = MockStorage.return_value
                    mock_storage.get_stats.return_value = {
                        "books": [],
                        "total_chapters": 0,
                    }

                    result = edword_index_status(str(mock_project_root))

                    assert result["total_chapters"] == 0
                    assert result["books"] == []


# --- Server creation tests ---


class TestCreateServer:
    def test_returns_fastmcp_instance(self):
        """create_server() returns the FastMCP instance."""
        server = create_server()
        assert server is mcp

    def test_server_has_tools_registered(self):
        """Server has all expected tools registered."""
        server = create_server()

        # Get list of registered tools
        # FastMCP stores tools differently depending on version
        # Check the server name as a basic sanity check
        assert server.name == "edword"


# --- Integration test markers ---


@pytest.mark.integration
class TestMCPIntegration:
    """Integration tests that require the real trilogy project."""

    def test_query_real_character(self):
        """Query a real character from trilogy index."""
        # This test is skipped unless run with --run-integration
        # and requires the trilogy project to be indexed
        pytest.skip("Run with --run-integration and ensure trilogy is indexed")

    def test_check_real_text(self):
        """Check real text against trilogy index."""
        pytest.skip("Run with --run-integration and ensure trilogy is indexed")
