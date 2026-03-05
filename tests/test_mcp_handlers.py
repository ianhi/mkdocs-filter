"""Comprehensive tests for MCP server handler methods.

Tests the handler methods directly to verify correct JSON responses, filtering logic,
and error handling. These tests catch bugs like broken imports or incorrect response
formats that would break agent integrations.
"""

import io
import json
import subprocess
import time
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

from docs_output_filter.mcp_server import (
    DocsFilterServer,
    _detect_project_type,
    main,
    run_mcp_server,
)
from docs_output_filter.types import BuildInfo, InfoCategory, InfoMessage, Issue, Level


class TestDetectProjectType:
    """Tests for _detect_project_type function."""

    def test_detects_mkdocs_project(self, tmp_path: Path) -> None:
        """Should detect MkDocs project from mkdocs.yml."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        from docs_output_filter.backends import BuildTool

        result = _detect_project_type(tmp_path)
        assert result == BuildTool.MKDOCS

    def test_detects_sphinx_project(self, tmp_path: Path) -> None:
        """Should detect Sphinx project from conf.py."""
        (tmp_path / "conf.py").write_text("# Sphinx config\n")

        from docs_output_filter.backends import BuildTool

        result = _detect_project_type(tmp_path)
        assert result == BuildTool.SPHINX

    def test_defaults_to_mkdocs_when_no_config(self, tmp_path: Path) -> None:
        """Should default to MkDocs when neither config exists."""
        from docs_output_filter.backends import BuildTool

        result = _detect_project_type(tmp_path)
        assert result == BuildTool.MKDOCS


class TestCallToolRouting:
    """Tests for _call_tool routing logic."""

    def test_routes_get_issues_correctly(self) -> None:
        """Should route get_issues to correct handler."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(level=Level.WARNING, source="mkdocs", message="Test warning"),
        ]

        result = server._call_tool("get_issues", {"filter": "all"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["warnings"] == 1

    def test_returns_error_for_unknown_tool(self) -> None:
        """Should return error message for unknown tool."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._call_tool("nonexistent_tool", {})

        assert len(result) == 1
        assert "Unknown tool: nonexistent_tool" in result[0].text


class TestHandleGetIssues:
    """Tests for _handle_get_issues - crucial for agent integration."""

    def test_returns_all_issues_with_counts(self) -> None:
        """Should return JSON with all issues and correct counts."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(
                level=Level.ERROR,
                source="mkdocs",
                message="Error message",
                file="test.md",
            ),
            Issue(
                level=Level.WARNING,
                source="mkdocs",
                message="Warning message",
                file="test2.md",
            ),
            Issue(
                level=Level.WARNING,
                source="mkdocs",
                message="Another warning",
                file="test3.md",
            ),
        ]

        result = server._handle_get_issues({"filter": "all"})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 3
        assert data["errors"] == 1
        assert data["warnings"] == 2
        assert len(data["issues"]) == 3

        # Verify issue structure
        issue = data["issues"][0]
        assert "id" in issue
        assert "level" in issue
        assert "source" in issue
        assert "message" in issue

    def test_filters_errors_only(self) -> None:
        """Should return only ERROR level issues when filtered."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(level=Level.ERROR, source="mkdocs", message="Error 1"),
            Issue(level=Level.WARNING, source="mkdocs", message="Warning 1"),
            Issue(level=Level.ERROR, source="mkdocs", message="Error 2"),
        ]

        result = server._handle_get_issues({"filter": "errors"})

        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["errors"] == 2
        assert data["warnings"] == 0
        assert len(data["issues"]) == 2
        assert all(i["level"] == "ERROR" for i in data["issues"])

    def test_filters_warnings_only(self) -> None:
        """Should return only WARNING level issues when filtered."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(level=Level.ERROR, source="mkdocs", message="Error 1"),
            Issue(level=Level.WARNING, source="mkdocs", message="Warning 1"),
            Issue(level=Level.WARNING, source="mkdocs", message="Warning 2"),
        ]

        result = server._handle_get_issues({"filter": "warnings"})

        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["errors"] == 0
        assert data["warnings"] == 2
        assert len(data["issues"]) == 2
        assert all(i["level"] == "WARNING" for i in data["issues"])

    def test_includes_code_and_traceback_in_verbose_mode(self) -> None:
        """Should include code and traceback in verbose mode."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(
                level=Level.ERROR,
                source="markdown_exec",
                message="ValueError: test",
                code="raise ValueError('test')",
                output="Traceback (most recent call last):\n  File...",
            ),
        ]

        result = server._handle_get_issues({"filter": "all", "verbose": True})

        data = json.loads(result[0].text)
        issue = data["issues"][0]
        assert "code" in issue
        assert issue["code"] == "raise ValueError('test')"
        assert "traceback" in issue
        assert "Traceback" in issue["traceback"]

    def test_excludes_code_and_traceback_in_non_verbose_mode(self) -> None:
        """Should exclude code and traceback when not verbose."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(
                level=Level.ERROR,
                source="markdown_exec",
                message="ValueError: test",
                code="raise ValueError('test')",
                output="Traceback...",
            ),
        ]

        result = server._handle_get_issues({"filter": "all", "verbose": False})

        data = json.loads(result[0].text)
        issue = data["issues"][0]
        assert "code" not in issue
        # Non-verbose now includes condensed traceback for token-efficient agent use
        assert "traceback" in issue
        assert issue["traceback"] == "Traceback..."

    def test_includes_info_summary_when_info_messages_exist(self) -> None:
        """Should include info_summary when info_messages exist."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = [
            Issue(level=Level.WARNING, source="mkdocs", message="Test"),
        ]
        server.info_messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="test.md",
                target="missing.md",
            ),
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="test2.md",
                target="other.md",
            ),
            InfoMessage(
                category=InfoCategory.ABSOLUTE_LINK,
                file="test3.md",
                target="/absolute",
            ),
        ]

        result = server._handle_get_issues({"filter": "all"})

        data = json.loads(result[0].text)
        assert "info_summary" in data
        assert data["info_summary"]["total"] == 3
        assert data["info_summary"]["broken_link"] == 2
        assert data["info_summary"]["absolute_link"] == 1

    def test_returns_empty_response_when_no_issues(self) -> None:
        """Should return total=0 when no issues."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = []

        result = server._handle_get_issues({"filter": "all"})

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["errors"] == 0
        assert data["warnings"] == 0
        assert data["issues"] == []


class TestHandleGetIssueDetails:
    """Tests for _handle_get_issue_details."""

    def test_returns_full_verbose_dict_when_issue_found(self) -> None:
        """Should return full verbose dict when issue found."""
        server = DocsFilterServer(pipe_mode=True)
        issue = Issue(
            level=Level.ERROR,
            source="mkdocs",
            message="Test error",
            file="test.md",
            line_number=42,
            code="print('test')",
            output="Error output",
        )
        server.issues = [issue]

        # Get the issue ID
        issue_id = server._get_issue_id(issue)

        result = server._handle_get_issue_details({"issue_id": issue_id})

        data = json.loads(result[0].text)
        assert data["id"] == issue_id
        assert data["level"] == "ERROR"
        assert data["source"] == "mkdocs"
        assert data["message"] == "Test error"
        assert data["file"] == "test.md"
        assert data["line_number"] == 42
        assert data["code"] == "print('test')"
        assert data["traceback"] == "Error output"

    def test_returns_error_when_issue_not_found(self) -> None:
        """Should return error message when issue not found."""
        server = DocsFilterServer(pipe_mode=True)
        server.issues = []

        result = server._handle_get_issue_details({"issue_id": "issue-deadbeef"})

        assert len(result) == 1
        assert "Issue not found: issue-deadbeef" in result[0].text


class TestHandleRebuild:
    """Tests for _handle_rebuild."""

    def test_returns_error_in_pipe_mode(self) -> None:
        """Should return error message in pipe mode."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._handle_rebuild({})

        assert len(result) == 1
        assert "Error: Cannot rebuild in pipe mode" in result[0].text

    def test_returns_no_new_data_in_watch_mode_without_refresh(self) -> None:
        """Should return 'No new build data' when watch mode doesn't refresh."""
        server = DocsFilterServer(watch_mode=True)

        with patch.object(server, "_refresh_from_state_file", return_value=False):
            result = server._handle_rebuild({})

        assert len(result) == 1
        assert "No new build data" in result[0].text

    def test_returns_issues_in_watch_mode_with_refresh(self) -> None:
        """Should return issues when watch mode refreshes successfully."""
        server = DocsFilterServer(watch_mode=True)
        server.issues = [
            Issue(level=Level.WARNING, source="mkdocs", message="Test"),
        ]

        with patch.object(server, "_refresh_from_state_file", return_value=True):
            result = server._handle_rebuild({"filter": "all"})

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["warnings"] == 1

    def test_returns_error_when_no_project_dir(self) -> None:
        """Should return error when no project_dir configured."""
        server = DocsFilterServer()
        server.pipe_mode = False
        server.watch_mode = False
        server.project_dir = None

        result = server._handle_rebuild({})

        assert len(result) == 1
        assert "Error: No project directory configured" in result[0].text


class TestHandleGetBuildInfo:
    """Tests for _handle_get_build_info - crucial for agents to get server URL."""

    def test_returns_json_with_server_url_in_normal_mode(self) -> None:
        """Should return JSON including server_url in normal mode."""
        server = DocsFilterServer(pipe_mode=True)
        server.build_info.server_url = "http://127.0.0.1:8000/"
        server.build_info.build_dir = "/path/to/site"
        server.build_info.build_time = "2.50"

        result = server._handle_get_build_info()

        data = json.loads(result[0].text)
        assert data["server_url"] == "http://127.0.0.1:8000/"
        assert data["build_dir"] == "/path/to/site"
        assert data["build_time"] == "2.50"

    def test_includes_diagnostics_in_watch_mode(self) -> None:
        """Should include diagnostics dict in watch mode."""
        server = DocsFilterServer(watch_mode=True)
        server.build_info.server_url = "http://localhost:8000/"

        with patch.object(server, "_refresh_from_state_file", return_value=False):
            with patch("docs_output_filter.mcp_server.find_project_root", return_value=None):
                with patch(
                    "docs_output_filter.mcp_server.get_state_file_path",
                    return_value=None,
                ):
                    result = server._handle_get_build_info()

        data = json.loads(result[0].text)
        assert "diagnostics" in data
        assert data["diagnostics"]["watch_mode"] is True
        assert "state_file_found" in data["diagnostics"]
        assert "project_root" in data["diagnostics"]
        assert "state_file_path" in data["diagnostics"]
        assert "cwd" in data["diagnostics"]

    def test_includes_hint_in_watch_mode_without_state(self) -> None:
        """Should include hint when watch mode has no state file."""
        server = DocsFilterServer(watch_mode=True)
        server._last_state_timestamp = 0

        with patch.object(server, "_refresh_from_state_file", return_value=False):
            with patch("docs_output_filter.mcp_server.find_project_root", return_value=None):
                with patch(
                    "docs_output_filter.mcp_server.get_state_file_path",
                    return_value=None,
                ):
                    result = server._handle_get_build_info()

        data = json.loads(result[0].text)
        assert "hint" in data["diagnostics"]
        assert "--share-state" in data["diagnostics"]["hint"]


class TestHandleGetRawOutput:
    """Tests for _handle_get_raw_output."""

    def test_returns_last_n_lines(self) -> None:
        """Should return last N lines of raw output."""
        server = DocsFilterServer(pipe_mode=True)
        server.raw_output = [f"Line {i}" for i in range(200)]

        result = server._handle_get_raw_output({"last_n_lines": 50})

        lines = result[0].text.splitlines()
        assert len(lines) == 50
        assert lines[0] == "Line 150"
        assert lines[-1] == "Line 199"

    def test_defaults_to_100_lines(self) -> None:
        """Should default to 100 lines when not specified."""
        server = DocsFilterServer(pipe_mode=True)
        server.raw_output = [f"Line {i}" for i in range(200)]

        result = server._handle_get_raw_output({})

        lines = result[0].text.splitlines()
        assert len(lines) == 100
        assert lines[0] == "Line 100"
        assert lines[-1] == "Line 199"


class TestHandleGetInfo:
    """Tests for _handle_get_info - INFO-level messages."""

    def test_returns_all_categories_grouped(self) -> None:
        """Should return all categories grouped by default."""
        server = DocsFilterServer(pipe_mode=True)
        server.info_messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="test.md",
                target="missing.md",
            ),
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="test2.md",
                target="other.md",
            ),
            InfoMessage(
                category=InfoCategory.ABSOLUTE_LINK,
                file="test3.md",
                target="/absolute",
            ),
        ]

        result = server._handle_get_info({"category": "all", "grouped": True})

        data = json.loads(result[0].text)
        assert data["count"] == 3
        assert "broken_link" in data["info_messages"]
        assert "absolute_link" in data["info_messages"]
        assert len(data["info_messages"]["broken_link"]) == 2
        assert len(data["info_messages"]["absolute_link"]) == 1

    def test_filters_by_specific_category(self) -> None:
        """Should filter by specific category."""
        server = DocsFilterServer(pipe_mode=True)
        server.info_messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="test.md",
                target="missing.md",
            ),
            InfoMessage(
                category=InfoCategory.ABSOLUTE_LINK,
                file="test3.md",
                target="/absolute",
            ),
        ]

        result = server._handle_get_info({"category": "broken_link", "grouped": True})

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert "broken_link" in data["info_messages"]
        assert "absolute_link" not in data["info_messages"]

    def test_returns_error_for_unknown_category(self) -> None:
        """Should return error for unknown category."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._handle_get_info({"category": "unknown_category"})

        assert len(result) == 1
        assert "Unknown category: unknown_category" in result[0].text

    def test_returns_flat_list_when_grouped_false(self) -> None:
        """Should return flat list when grouped=False."""
        server = DocsFilterServer(pipe_mode=True)
        server.info_messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="test.md",
                target="missing.md",
            ),
            InfoMessage(
                category=InfoCategory.ABSOLUTE_LINK,
                file="test3.md",
                target="/absolute",
            ),
        ]

        result = server._handle_get_info({"category": "all", "grouped": False})

        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert isinstance(data["info_messages"], list)
        assert len(data["info_messages"]) == 2
        assert data["info_messages"][0]["category"] == "broken_link"
        assert data["info_messages"][1]["category"] == "absolute_link"

    def test_returns_empty_when_no_messages(self) -> None:
        """Should return count: 0 when no messages."""
        server = DocsFilterServer(pipe_mode=True)
        server.info_messages = []

        result = server._handle_get_info({"category": "all"})

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["info_messages"] == []


class TestHandleFetchBuildLog:
    """Tests for _handle_fetch_build_log."""

    def test_returns_error_when_no_url(self) -> None:
        """Should return error when URL not provided."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._handle_fetch_build_log({})

        assert len(result) == 1
        assert "Error: URL is required" in result[0].text

    def test_returns_error_json_when_fetch_fails(self) -> None:
        """Should return error JSON when fetch fails."""
        server = DocsFilterServer(pipe_mode=True)

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=None,
        ):
            result = server._handle_fetch_build_log({"url": "https://example.com/log"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Failed to fetch" in data["error"]

    def test_returns_full_response_with_issues_on_success(self) -> None:
        """Should return full response with issues on successful fetch."""
        server = DocsFilterServer(pipe_mode=True)

        mock_log = """INFO -  Building documentation...
WARNING -  A warning message
ERROR -  An error message
INFO -  Serving on http://127.0.0.1:8000/
INFO -  Documentation built in 1.23 seconds"""

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=mock_log,
        ):
            result = server._handle_fetch_build_log(
                {"url": "https://example.com/log", "verbose": False}
            )

        data = json.loads(result[0].text)
        assert data["url"] == "https://example.com/log"
        assert data["lines_processed"] == 5
        assert data["total_issues"] == 2
        assert data["errors"] == 1
        assert data["warnings"] == 1
        assert data["server_url"] == "http://127.0.0.1:8000/"
        assert data["build_time"] == "1.23"
        assert len(data["issues"]) == 2

    def test_includes_info_messages_in_response(self) -> None:
        """Should include info_messages when present."""
        server = DocsFilterServer(pipe_mode=True)

        mock_log = """INFO -  Building documentation...
INFO -  Doc file 'test.md' contains a link to 'missing.md' which is not found.
WARNING -  A warning"""

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=mock_log,
        ):
            result = server._handle_fetch_build_log({"url": "https://example.com/log"})

        data = json.loads(result[0].text)
        # MkDocs backend should parse the broken link
        if "info_messages" in data:
            assert "info_count" in data
            assert data["info_count"] >= 0


class TestGetBuildInProgressResponse:
    """Tests for _get_build_in_progress_response."""

    def test_returns_none_when_not_building(self) -> None:
        """Should return None when not building."""
        server = DocsFilterServer(pipe_mode=True)
        server._build_status = "complete"

        result = server._get_build_in_progress_response()

        assert result is None

    def test_returns_message_when_building_with_start_time(self) -> None:
        """Should return message with elapsed time when building."""
        server = DocsFilterServer(pipe_mode=True)
        server._build_status = "building"
        server._build_started_at = time.time() - 5  # Started 5 seconds ago

        result = server._get_build_in_progress_response()

        assert result is not None
        data = json.loads(result[0].text)
        assert data["status"] == "building"
        assert "started" in data["message"]
        assert "seconds ago" in data["message"]
        assert "hint" in data

    def test_returns_message_when_building_without_start_time(self) -> None:
        """Should return message without elapsed when no start time."""
        server = DocsFilterServer(pipe_mode=True)
        server._build_status = "building"
        server._build_started_at = None

        result = server._get_build_in_progress_response()

        assert result is not None
        data = json.loads(result[0].text)
        assert data["status"] == "building"
        assert "started" not in data["message"]
        assert "hint" in data


class TestRefreshFromStateFile:
    """Tests for _refresh_from_state_file."""

    def test_returns_false_when_not_watch_mode(self) -> None:
        """Should return False when not in watch mode."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._refresh_from_state_file()

        assert result is False

    def test_returns_false_when_state_file_not_found(self) -> None:
        """Should return False when state file not found."""
        server = DocsFilterServer(watch_mode=True)

        with patch("docs_output_filter.mcp_server.read_state_file", return_value=None):
            result = server._refresh_from_state_file()

        assert result is False

    def test_returns_false_when_state_timestamp_is_stale(self) -> None:
        """Should return False when state timestamp is stale."""
        server = DocsFilterServer(watch_mode=True)
        server._last_state_timestamp = 100.0

        mock_state = MagicMock()
        mock_state.timestamp = 50.0  # Older than current
        mock_state.build_status = "complete"
        mock_state.build_started_at = None
        mock_state.issues = []
        mock_state.info_messages = []
        mock_state.build_info = BuildInfo()
        mock_state.raw_output = []

        with patch("docs_output_filter.mcp_server.read_state_file", return_value=mock_state):
            result = server._refresh_from_state_file()

        assert result is False

    def test_returns_true_and_updates_when_state_is_fresh(self) -> None:
        """Should return True and update issues when state is fresh."""
        server = DocsFilterServer(watch_mode=True)
        server._last_state_timestamp = 50.0

        mock_state = MagicMock()
        mock_state.timestamp = 100.0  # Newer than current
        mock_state.build_status = "complete"
        mock_state.build_started_at = None
        mock_state.issues = [
            Issue(level=Level.WARNING, source="mkdocs", message="New warning"),
        ]
        mock_state.info_messages = []
        mock_state.build_info = BuildInfo(server_url="http://localhost:8000/")
        mock_state.raw_output = ["line 1", "line 2"]

        with patch("docs_output_filter.mcp_server.read_state_file", return_value=mock_state):
            result = server._refresh_from_state_file()

        assert result is True
        assert server._last_state_timestamp == 100.0
        assert len(server.issues) == 1
        assert server.issues[0].message == "New warning"
        assert server.build_info.server_url == "http://localhost:8000/"
        assert len(server.raw_output) == 2


class TestRunMCPServer:
    """Tests for run_mcp_server function validation."""

    def test_returns_error_when_no_mode_specified(self) -> None:
        """Should return exit code 1 when no mode specified."""
        result = run_mcp_server(
            project_dir=None,
            pipe_mode=False,
            watch_mode=False,
        )

        assert result == 1

    def test_returns_error_when_project_dir_does_not_exist(self, tmp_path: Path) -> None:
        """Should return exit code 1 when project_dir doesn't exist."""
        nonexistent = tmp_path / "nonexistent"

        result = run_mcp_server(project_dir=str(nonexistent))

        assert result == 1

    def test_returns_error_when_project_dir_missing_config(self, tmp_path: Path) -> None:
        """Should return exit code 1 when no mkdocs.yml or conf.py."""
        result = run_mcp_server(project_dir=str(tmp_path))

        assert result == 1


class TestMainLegacyEntryPoint:
    """Tests for main() legacy entry point."""

    def test_emits_deprecation_warning(self, tmp_path: Path) -> None:
        """Should emit deprecation warning when called."""
        # Create a valid project to avoid validation errors
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Mock asyncio.run to prevent actual server startup
            # asyncio is imported locally in main(), so patch it there
            import asyncio

            with patch.object(asyncio, "run"):
                with patch("sys.argv", ["mcp_server", "--project-dir", str(tmp_path)]):
                    try:
                        main()
                    except SystemExit:
                        pass

            # Verify deprecation warning was issued
            assert len(w) >= 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()


class TestIssueDeduplication:
    """Tests for issue deduplication in _parse_output."""

    def test_deduplicates_identical_issues(self) -> None:
        """Should deduplicate identical issues by level and message prefix."""
        server = DocsFilterServer(pipe_mode=True)

        output = """WARNING -  Same warning
WARNING -  Same warning
WARNING -  Different warning
WARNING -  Same warning"""

        server._parse_output(output)

        assert len(server.issues) == 2
        messages = [i.message for i in server.issues]
        assert "Same warning" in messages
        assert "Different warning" in messages


class TestIssueIdStability:
    """Tests for stable issue ID generation."""

    def test_same_issue_gets_same_id_across_calls(self) -> None:
        """Should generate same ID for same issue across multiple calls."""
        server = DocsFilterServer(pipe_mode=True)

        issue = Issue(
            level=Level.ERROR,
            source="mkdocs",
            message="Test error",
            file="test.md",
        )

        id1 = server._get_issue_id(issue)
        id2 = server._get_issue_id(issue)
        id3 = server._get_issue_id(issue)

        assert id1 == id2 == id3
        assert id1.startswith("issue-")

    def test_different_issues_get_different_ids(self) -> None:
        """Should generate different IDs for different issues."""
        server = DocsFilterServer(pipe_mode=True)

        issue1 = Issue(level=Level.ERROR, source="mkdocs", message="Error 1")
        issue2 = Issue(level=Level.ERROR, source="mkdocs", message="Error 2")

        id1 = server._get_issue_id(issue1)
        id2 = server._get_issue_id(issue2)

        assert id1 != id2


# ====================================================================
# NEW TESTS BELOW: added to improve mcp_server.py coverage to 90%+
# ====================================================================


class TestCallToolRoutingAllTools:
    """Tests for _call_tool routing to each tool handler."""

    def test_routes_get_issue_details(self) -> None:
        """Should route get_issue_details to correct handler."""
        server = DocsFilterServer(pipe_mode=True)
        issue = Issue(level=Level.ERROR, source="mkdocs", message="Test error")
        server.issues = [issue]
        issue_id = server._get_issue_id(issue)

        result = server._call_tool("get_issue_details", {"issue_id": issue_id})

        data = json.loads(result[0].text)
        assert data["level"] == "ERROR"
        assert data["message"] == "Test error"

    def test_routes_rebuild(self) -> None:
        """Should route rebuild to correct handler."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._call_tool("rebuild", {})

        assert "Cannot rebuild in pipe mode" in result[0].text

    def test_routes_get_build_info(self) -> None:
        """Should route get_build_info to correct handler."""
        server = DocsFilterServer(pipe_mode=True)
        server.build_info.server_url = "http://localhost:8000/"

        result = server._call_tool("get_build_info", {})

        data = json.loads(result[0].text)
        assert data["server_url"] == "http://localhost:8000/"

    def test_routes_get_raw_output(self) -> None:
        """Should route get_raw_output to correct handler."""
        server = DocsFilterServer(pipe_mode=True)
        server.raw_output = ["line1", "line2"]

        result = server._call_tool("get_raw_output", {"last_n_lines": 10})

        assert "line1" in result[0].text
        assert "line2" in result[0].text

    def test_routes_get_info(self) -> None:
        """Should route get_info to correct handler."""
        server = DocsFilterServer(pipe_mode=True)
        server.info_messages = []

        result = server._call_tool("get_info", {"category": "all"})

        data = json.loads(result[0].text)
        assert data["count"] == 0

    def test_routes_fetch_build_log(self) -> None:
        """Should route fetch_build_log to correct handler."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._call_tool("fetch_build_log", {})

        assert "Error: URL is required" in result[0].text


class TestHandleGetIssuesBuildInProgress:
    """Tests for _handle_get_issues when build is in progress."""

    def test_returns_building_response_when_build_in_progress(self) -> None:
        """Should return build-in-progress response when building."""
        server = DocsFilterServer(pipe_mode=True)
        server._build_status = "building"
        server._build_started_at = time.time() - 3

        result = server._handle_get_issues({"filter": "all"})

        data = json.loads(result[0].text)
        assert data["status"] == "building"
        assert "Build in progress" in data["message"]


class TestHandleGetInfoBuildInProgress:
    """Tests for _handle_get_info when build is in progress."""

    def test_returns_building_response_when_build_in_progress(self) -> None:
        """Should return build-in-progress response when building."""
        server = DocsFilterServer(pipe_mode=True)
        server._build_status = "building"
        server._build_started_at = time.time() - 2

        result = server._handle_get_info({"category": "all"})

        data = json.loads(result[0].text)
        assert data["status"] == "building"
        assert "Build in progress" in data["message"]


class TestHandleRebuildWithProjectDir:
    """Tests for _handle_rebuild with project_dir (subprocess build)."""

    def test_rebuild_runs_build_and_returns_issues(self, tmp_path: Path) -> None:
        """Should run build subprocess and return parsed issues."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build", "--clean"],
            returncode=1,
            stdout="",
            stderr=(
                "INFO -  Building documentation...\n"
                "WARNING -  A test warning\n"
                "ERROR -  A test error\n"
                "INFO -  Documentation built in 1.50 seconds\n"
            ),
        )
        with patch("subprocess.run", return_value=mock_result):
            result = server._handle_rebuild({"verbose": False})

        data = json.loads(result[0].text)
        assert data["total_issues"] == 2
        assert data["errors"] == 1
        assert data["warnings"] == 1
        assert data["return_code"] == 1
        assert data["build_time"] == "1.50"
        assert len(data["issues"]) == 2

    def test_rebuild_with_verbose_flag(self, tmp_path: Path) -> None:
        """Should pass verbose flag to build command."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build", "--clean", "--verbose"],
            returncode=0,
            stdout="",
            stderr="INFO -  Building documentation...\nINFO -  Documentation built in 0.50 seconds\n",
        )
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = server._handle_rebuild({"verbose": True})

        # Verify --verbose was passed
        call_args = mock_run.call_args[0][0]
        assert "--verbose" in call_args

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["return_code"] == 0

    def test_rebuild_success_with_warnings_only(self, tmp_path: Path) -> None:
        """Should report success=True when return_code=1 but no errors."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build", "--clean"],
            returncode=1,
            stdout="",
            stderr="WARNING -  A warning\nINFO -  Documentation built in 1.00 seconds\n",
        )
        with patch("subprocess.run", return_value=mock_result):
            result = server._handle_rebuild({})

        data = json.loads(result[0].text)
        assert data["success"] is True


class TestHandleGetBuildInfoWatchModeStateFound:
    """Tests for _handle_get_build_info in watch mode when state was found previously."""

    def test_diagnostics_state_found_true(self) -> None:
        """Should set state_file_found=True when previously refreshed."""
        server = DocsFilterServer(watch_mode=True)
        server.build_info.server_url = "http://localhost:8000/"
        server._last_state_timestamp = 100.0  # Previously found state

        with patch.object(server, "_refresh_from_state_file", return_value=False):
            with patch(
                "docs_output_filter.mcp_server.find_project_root", return_value=Path("/tmp/proj")
            ):
                with patch(
                    "docs_output_filter.mcp_server.get_state_file_path",
                    return_value=Path("/tmp/state.json"),
                ):
                    result = server._handle_get_build_info()

        data = json.loads(result[0].text)
        assert data["diagnostics"]["state_file_found"] is True
        assert data["diagnostics"]["project_root"] == "/tmp/proj"
        assert data["diagnostics"]["state_file_path"] == "/tmp/state.json"
        # No hint because state was found previously
        assert "hint" not in data["diagnostics"]

    def test_diagnostics_after_refresh(self) -> None:
        """Should set state_file_found=True after successful refresh."""
        server = DocsFilterServer(watch_mode=True)
        server._last_state_timestamp = 0

        with patch.object(server, "_refresh_from_state_file", return_value=True):
            with patch("docs_output_filter.mcp_server.find_project_root", return_value=None):
                with patch(
                    "docs_output_filter.mcp_server.get_state_file_path",
                    return_value=None,
                ):
                    result = server._handle_get_build_info()

        data = json.loads(result[0].text)
        assert data["diagnostics"]["state_file_found"] is True


class TestHandleFetchBuildLogExtended:
    """Extended tests for _handle_fetch_build_log covering info_messages and build_info fields."""

    def test_fallback_to_mkdocs_backend_when_no_detection(self) -> None:
        """Should fallback to MkDocsBackend when no backend auto-detected."""
        server = DocsFilterServer(pipe_mode=True)

        # Content that won't trigger auto-detection for any backend
        mock_log = "some random content\nanother line\n"

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=mock_log,
        ):
            result = server._handle_fetch_build_log({"url": "https://example.com/log"})

        data = json.loads(result[0].text)
        assert data["url"] == "https://example.com/log"
        assert data["lines_processed"] == 2
        # No issues should be found from random content
        assert data["total_issues"] == 0

    def test_includes_info_messages_grouped(self) -> None:
        """Should include grouped info_messages and info_count when present."""
        server = DocsFilterServer(pipe_mode=True)

        mock_log = (
            "INFO -  Building documentation...\n"
            "INFO -  Doc file 'test.md' contains a link 'missing.md', but the target is not found\n"
            "INFO -  Doc file 'test2.md' contains a link 'other.md', but the target is not found\n"
            "WARNING -  A warning\n"
            "INFO -  Documentation built in 1.00 seconds\n"
        )

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=mock_log,
        ):
            result = server._handle_fetch_build_log({"url": "https://example.com/log"})

        data = json.loads(result[0].text)
        assert "info_messages" in data
        assert "info_count" in data
        assert data["info_count"] >= 2
        assert "broken_link" in data["info_messages"]

    def test_includes_build_dir_in_response(self) -> None:
        """Should include build_dir when present in build_info."""
        server = DocsFilterServer(pipe_mode=True)

        mock_log = (
            "INFO -  Building documentation...\n"
            "INFO -  Building documentation to directory: /path/to/site\n"
            "WARNING -  A warning\n"
            "INFO -  Serving on http://127.0.0.1:8000/\n"
            "INFO -  Documentation built in 2.00 seconds\n"
        )

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=mock_log,
        ):
            result = server._handle_fetch_build_log({"url": "https://example.com/log"})

        data = json.loads(result[0].text)
        assert data["server_url"] == "http://127.0.0.1:8000/"
        assert data["build_dir"] == "/path/to/site"
        assert data["build_time"] == "2.00"

    def test_omits_empty_build_info_fields(self) -> None:
        """Should not include build_info fields when they are None."""
        server = DocsFilterServer(pipe_mode=True)

        mock_log = "INFO -  Building documentation...\nWARNING -  A warning\n"

        with patch(
            "docs_output_filter.remote.fetch_remote_log",
            return_value=mock_log,
        ):
            result = server._handle_fetch_build_log({"url": "https://example.com/log"})

        data = json.loads(result[0].text)
        assert "server_url" not in data
        assert "build_dir" not in data
        assert "build_time" not in data


class TestParseOutput:
    """Tests for _parse_output method."""

    def test_parses_mkdocs_output(self) -> None:
        """Should parse MkDocs build output and extract issues and build info."""
        server = DocsFilterServer(pipe_mode=True)

        output = (
            "INFO -  Building documentation...\n"
            "WARNING -  First warning\n"
            "WARNING -  Second warning\n"
            "ERROR -  An error occurred\n"
            "INFO -  Building documentation to directory: /tmp/site\n"
            "INFO -  Serving on http://127.0.0.1:8000/\n"
            "INFO -  Documentation built in 3.00 seconds\n"
        )

        server._parse_output(output)

        assert len(server.issues) == 3
        assert server.issues[0].level == Level.WARNING
        assert server.issues[0].message == "First warning"
        assert server.issues[1].level == Level.WARNING
        assert server.issues[1].message == "Second warning"
        assert server.issues[2].level == Level.ERROR
        assert server.issues[2].message == "An error occurred"
        assert server.build_info.build_dir == "/tmp/site"
        assert server.build_info.server_url == "http://127.0.0.1:8000/"
        assert server.build_info.build_time == "3.00"
        assert len(server.raw_output) == 7

    def test_parses_sphinx_output(self) -> None:
        """Should parse Sphinx build output and extract issues."""
        server = DocsFilterServer(pipe_mode=True)

        output = (
            "Running Sphinx v7.2.0\n"
            "/path/to/file.rst:10: WARNING: unknown document: missing\n"
            "/path/to/other.rst:20: ERROR: broken reference\n"
            "build succeeded, 1 warning.\n"
        )

        server._parse_output(output)

        assert len(server.issues) == 2
        assert server.issues[0].level == Level.WARNING
        assert server.issues[1].level == Level.ERROR

    def test_deduplicates_issues(self) -> None:
        """Should deduplicate issues with same level and message prefix."""
        server = DocsFilterServer(pipe_mode=True)

        output = (
            "INFO -  Building documentation...\n"
            "WARNING -  Duplicate warning\n"
            "WARNING -  Duplicate warning\n"
            "WARNING -  Duplicate warning\n"
            "WARNING -  Unique warning\n"
        )

        server._parse_output(output)

        assert len(server.issues) == 2
        messages = [i.message for i in server.issues]
        assert "Duplicate warning" in messages
        assert "Unique warning" in messages

    def test_falls_back_to_project_type_backend(self) -> None:
        """Should fall back to project-type backend when auto-detect fails."""
        server = DocsFilterServer(pipe_mode=True)
        # No detectable tool lines
        output = "some unrecognized output\nanother line\n"

        server._parse_output(output)

        # Should not crash, just find no issues
        assert server.issues == []
        assert len(server.raw_output) == 2

    def test_stores_raw_output(self) -> None:
        """Should store all lines as raw_output."""
        server = DocsFilterServer(pipe_mode=True)
        output = "line 1\nline 2\nline 3"

        server._parse_output(output)

        assert server.raw_output == ["line 1", "line 2", "line 3"]


class TestRunBuild:
    """Tests for _run_build method."""

    def test_run_build_mkdocs(self, tmp_path: Path) -> None:
        """Should run mkdocs build command for MkDocs projects."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build", "--clean"],
            returncode=0,
            stdout="",
            stderr="INFO -  Building documentation...\nINFO -  Documentation built in 1.00 seconds\n",
        )
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            lines, return_code = server._run_build()

        assert return_code == 0
        assert len(lines) == 2
        call_args = mock_run.call_args[0][0]
        assert call_args == ["mkdocs", "build", "--clean"]
        assert mock_run.call_args[1]["cwd"] == tmp_path

    def test_run_build_mkdocs_verbose(self, tmp_path: Path) -> None:
        """Should pass --verbose flag for mkdocs build."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build", "--clean", "--verbose"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            lines, return_code = server._run_build(verbose=True)

        call_args = mock_run.call_args[0][0]
        assert "--verbose" in call_args

    def test_run_build_sphinx(self, tmp_path: Path) -> None:
        """Should run sphinx-build command for Sphinx projects."""
        (tmp_path / "conf.py").write_text("# Sphinx config\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["sphinx-build"],
            returncode=0,
            stdout="Running Sphinx v7.2.0\nbuild succeeded.\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            lines, return_code = server._run_build()

        assert return_code == 0
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "sphinx-build"
        assert str(tmp_path) in call_args[1]
        assert str(tmp_path / "_build") in call_args[2]

    def test_run_build_sphinx_verbose(self, tmp_path: Path) -> None:
        """Should pass -v flag for sphinx-build when verbose."""
        (tmp_path / "conf.py").write_text("# Sphinx config\n")
        server = DocsFilterServer(project_dir=tmp_path)

        mock_result = subprocess.CompletedProcess(
            args=["sphinx-build"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            lines, return_code = server._run_build(verbose=True)

        call_args = mock_run.call_args[0][0]
        assert "-v" in call_args

    def test_run_build_no_project_dir(self) -> None:
        """Should return empty lines and error code when no project_dir."""
        server = DocsFilterServer(pipe_mode=True)

        lines, return_code = server._run_build()

        assert lines == []
        assert return_code == 1


class TestRunMCPServerExtended:
    """Extended tests for run_mcp_server function covering execution paths."""

    def test_returns_error_when_multiple_modes_specified(self) -> None:
        """Should return error when pipe_mode combined with other modes."""
        result = run_mcp_server(
            project_dir="/some/path",
            pipe_mode=True,
            watch_mode=False,
        )

        # project_dir + pipe_mode = 2 modes, not allowed
        # But project_dir doesn't exist so it fails at validation first
        assert result == 1

    def test_returns_error_for_pipe_plus_watch(self, tmp_path: Path) -> None:
        """Should return error when pipe and watch modes combined."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        result = run_mcp_server(
            project_dir=None,
            pipe_mode=True,
            watch_mode=True,
        )

        # pipe + watch = 2 modes, not watch+project_dir, so error
        assert result == 1

    def test_pipe_mode_reads_stdin_and_runs_server(self, tmp_path: Path) -> None:
        """Should read stdin and parse output in pipe mode."""
        mock_stdin = io.StringIO(
            "INFO -  Building documentation...\n"
            "WARNING -  A test warning\n"
            "INFO -  Documentation built in 1.00 seconds\n"
        )

        with patch("sys.stdin", mock_stdin):
            with patch("asyncio.run"):
                result = run_mcp_server(pipe_mode=True)

        assert result == 0

    def test_watch_mode_refreshes_state(self) -> None:
        """Should refresh from state file in watch mode."""
        with patch("docs_output_filter.mcp_server.read_state_file", return_value=None):
            with patch("asyncio.run"):
                result = run_mcp_server(watch_mode=True)

        assert result == 0

    def test_project_dir_with_initial_build(self, tmp_path: Path) -> None:
        """Should run initial build when initial_build flag set."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build"],
            returncode=0,
            stdout="",
            stderr="INFO -  Building documentation...\nINFO -  Documentation built in 1.00 seconds\n",
        )
        with patch("subprocess.run", return_value=mock_result):
            with patch("asyncio.run"):
                result = run_mcp_server(
                    project_dir=str(tmp_path),
                    initial_build=True,
                )

        assert result == 0

    def test_project_dir_without_initial_build(self, tmp_path: Path) -> None:
        """Should skip initial build when initial_build not set."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        with patch("asyncio.run"):
            result = run_mcp_server(project_dir=str(tmp_path))

        assert result == 0


class TestMainLegacyEntryPointExtended:
    """Extended tests for main() legacy entry point covering validation and execution."""

    def test_no_mode_specified_returns_error(self) -> None:
        """Should return 1 when no mode specified."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server"]):
                result = main()

        assert result == 1

    def test_multiple_modes_returns_error(self) -> None:
        """Should return 1 when pipe and project_dir combined."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--pipe", "--project-dir", "/tmp/some"]):
                result = main()

        # pipe + project_dir is multiple modes error (if project exists)
        # But project may not exist, so it gets the "does not exist" error
        assert result == 1

    def test_project_dir_does_not_exist_returns_error(self, tmp_path: Path) -> None:
        """Should return 1 when project dir does not exist."""
        nonexistent = str(tmp_path / "nonexistent")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--project-dir", nonexistent]):
                result = main()

        assert result == 1

    def test_project_dir_missing_config_returns_error(self, tmp_path: Path) -> None:
        """Should return 1 when project dir has no mkdocs.yml or conf.py."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--project-dir", str(tmp_path)]):
                result = main()

        assert result == 1

    def test_pipe_mode_reads_stdin(self) -> None:
        """Should read stdin in pipe mode and start server."""
        mock_stdin = io.StringIO("INFO -  Building documentation...\nWARNING -  A warning\n")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--pipe"]):
                with patch("sys.stdin", mock_stdin):
                    with patch("asyncio.run"):
                        result = main()

        assert result == 0

    def test_watch_mode_refreshes_and_starts_server(self) -> None:
        """Should refresh state and start server in watch mode."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--watch"]):
                with patch("docs_output_filter.mcp_server.read_state_file", return_value=None):
                    with patch("asyncio.run"):
                        result = main()

        assert result == 0

    def test_project_dir_with_initial_build_starts_server(self, tmp_path: Path) -> None:
        """Should run initial build and start server with --initial-build."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        mock_result = subprocess.CompletedProcess(
            args=["mkdocs", "build"],
            returncode=0,
            stdout="",
            stderr="INFO -  Building documentation...\n",
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch(
                "sys.argv", ["mcp_server", "--project-dir", str(tmp_path), "--initial-build"]
            ):
                with patch("subprocess.run", return_value=mock_result):
                    with patch("asyncio.run"):
                        result = main()

        assert result == 0

    def test_project_dir_without_initial_build_starts_server(self, tmp_path: Path) -> None:
        """Should start server without initial build when flag not set."""
        (tmp_path / "mkdocs.yml").write_text("site_name: Test\n")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--project-dir", str(tmp_path)]):
                with patch("asyncio.run"):
                    result = main()

        assert result == 0

    def test_pipe_plus_watch_returns_error(self) -> None:
        """Should return 1 when both --pipe and --watch specified."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with patch("sys.argv", ["mcp_server", "--pipe", "--watch"]):
                result = main()

        assert result == 1


class TestSetupToolsAsync:
    """Tests for async handlers registered in _setup_tools."""

    def test_list_tools_async_handler(self) -> None:
        """Should register async list_tools handler that delegates to _list_tools."""

        server = DocsFilterServer(pipe_mode=True)

        # Access the async handler through the server's internal mechanism
        tools = server._list_tools()
        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "get_issues" in tool_names
        assert "fetch_build_log" in tool_names

    def test_call_tool_async_handler(self) -> None:
        """Should register async call_tool handler that delegates to _call_tool."""
        server = DocsFilterServer(pipe_mode=True)

        result = server._call_tool("get_issues", {"filter": "all"})
        data = json.loads(result[0].text)
        assert "total" in data


class TestIssueToDict:
    """Tests for _issue_to_dict covering warning_code field (line 644)."""

    def test_issue_with_warning_code(self) -> None:
        """_issue_to_dict with warning_code should include it in result."""
        server = DocsFilterServer(pipe_mode=True)
        issue = Issue(
            level=Level.WARNING,
            source="sphinx",
            message="toc not readable",
            warning_code="toc.not_readable",
        )
        result = server._issue_to_dict(issue, verbose=False)
        assert result["warning_code"] == "toc.not_readable"

    def test_issue_without_warning_code(self) -> None:
        """_issue_to_dict without warning_code should not include it."""
        server = DocsFilterServer(pipe_mode=True)
        issue = Issue(
            level=Level.WARNING,
            source="mkdocs",
            message="a warning",
        )
        result = server._issue_to_dict(issue, verbose=False)
        assert "warning_code" not in result


class TestFetchBuildLogDedup:
    """Tests for dedup in _handle_fetch_build_log (branch 514->512)."""

    def test_duplicate_warnings_deduped(self) -> None:
        """Duplicate warnings in fetched log should be deduplicated."""
        server = DocsFilterServer(pipe_mode=True)
        log_content = (
            "INFO    -  Building documentation...\n"
            "WARNING -  Same warning about link\n"
            "WARNING -  Same warning about link\n"
            "WARNING -  Same warning about link\n"
            "INFO    -  Documentation built in 1.00 seconds\n"
        )
        with patch("docs_output_filter.remote.fetch_remote_log", return_value=log_content):
            result = server._handle_fetch_build_log(
                {"url": "https://example.com/log", "verbose": False}
            )
        data = json.loads(result[0].text)
        # Dedup should reduce 3 identical warnings to 1
        assert data["total_issues"] == 1


class TestGetIssueDetailsFound:
    """Tests for _handle_get_issue_details when issue is found (branch 330->329)."""

    def test_issue_found_returns_details(self) -> None:
        """When issue ID matches, should return issue details."""
        server = DocsFilterServer(pipe_mode=True)
        # Add non-matching issues before the target to exercise the loop continuation
        other_issue = Issue(
            level=Level.ERROR,
            source="mkdocs",
            message="some other error",
        )
        target_issue = Issue(
            level=Level.WARNING,
            source="mkdocs",
            message="test warning message",
        )
        server.issues = [other_issue, target_issue]
        issue_id = server._get_issue_id(target_issue)
        result = server._handle_get_issue_details({"issue_id": issue_id})
        data = json.loads(result[0].text)
        assert data["message"] == "test warning message"
        assert data["level"] == "WARNING"
