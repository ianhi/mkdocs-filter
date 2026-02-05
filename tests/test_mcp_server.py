"""Tests for MCP server functionality."""

import subprocess
import sys
from pathlib import Path

from mkdocs_filter.mcp_server import MkdocsFilterServer
from mkdocs_filter.parsing import Issue, Level


class TestMkdocsFilterServer:
    """Tests for MkdocsFilterServer class."""

    def test_creates_server_with_project_dir(self, tmp_path: Path) -> None:
        """Should create server with project directory."""
        # Create a minimal mkdocs project
        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text("site_name: Test\n")
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# Test\n")

        server = MkdocsFilterServer(project_dir=tmp_path)
        assert server.project_dir == tmp_path
        assert not server.pipe_mode

    def test_creates_server_in_pipe_mode(self) -> None:
        """Should create server in pipe mode."""
        server = MkdocsFilterServer(pipe_mode=True)
        assert server.pipe_mode
        assert server.project_dir is None

    def test_parse_output_extracts_issues(self) -> None:
        """Should parse mkdocs output and extract issues."""
        server = MkdocsFilterServer(pipe_mode=True)

        output = """INFO -  Building documentation...
WARNING -  A warning message
ERROR -  An error message
INFO -  Documentation built in 1.23 seconds"""

        server._parse_output(output)

        assert len(server.issues) == 2
        assert server.issues[0].level == Level.WARNING
        assert server.issues[0].message == "A warning message"
        assert server.issues[1].level == Level.ERROR
        assert server.issues[1].message == "An error message"

    def test_parse_output_extracts_build_info(self) -> None:
        """Should extract build info from output."""
        server = MkdocsFilterServer(pipe_mode=True)

        output = """INFO -  Building documentation to directory: /path/to/site
INFO -  Serving on http://127.0.0.1:8000/
INFO -  Documentation built in 2.50 seconds"""

        server._parse_output(output)

        assert server.build_info.build_dir == "/path/to/site"
        assert server.build_info.server_url == "http://127.0.0.1:8000/"
        assert server.build_info.build_time == "2.50"

    def test_parse_output_deduplicates_issues(self) -> None:
        """Should deduplicate identical issues."""
        server = MkdocsFilterServer(pipe_mode=True)

        output = """WARNING -  Same warning
WARNING -  Same warning
WARNING -  Same warning"""

        server._parse_output(output)

        assert len(server.issues) == 1

    def test_issue_to_dict_basic(self) -> None:
        """Should convert issue to dictionary."""
        server = MkdocsFilterServer(pipe_mode=True)
        issue = Issue(
            level=Level.WARNING,
            source="mkdocs",
            message="Test message",
            file="test.md",
        )

        result = server._issue_to_dict(issue)

        assert result["level"] == "WARNING"
        assert result["source"] == "mkdocs"
        assert result["message"] == "Test message"
        assert result["file"] == "test.md"
        assert "id" in result

    def test_issue_to_dict_verbose(self) -> None:
        """Should include code and traceback when verbose."""
        server = MkdocsFilterServer(pipe_mode=True)
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="ValueError: test",
            file="test.md",
            code="raise ValueError('test')",
            output="Traceback...",
        )

        result = server._issue_to_dict(issue, verbose=True)

        assert result["code"] == "raise ValueError('test')"
        assert result["traceback"] == "Traceback..."

    def test_issue_ids_are_stable(self) -> None:
        """Same issue should get same ID."""
        server = MkdocsFilterServer(pipe_mode=True)
        issue = Issue(
            level=Level.WARNING,
            source="mkdocs",
            message="Test message",
        )

        result1 = server._issue_to_dict(issue)
        result2 = server._issue_to_dict(issue)

        assert result1["id"] == result2["id"]

    def test_get_build_info_json(self) -> None:
        """Should return build info as JSON."""
        import json

        server = MkdocsFilterServer(pipe_mode=True)
        server.build_info.server_url = "http://localhost:8000/"
        server.build_info.build_dir = "/path/to/site"
        server.build_info.build_time = "1.23"

        result = server._get_build_info_json()
        data = json.loads(result)

        assert data["server_url"] == "http://localhost:8000/"
        assert data["build_dir"] == "/path/to/site"
        assert data["build_time"] == "1.23"


class TestMCPServerCLI:
    """Tests for MCP server command-line interface."""

    def test_help_flag(self) -> None:
        """--help should print help and exit."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter.mcp_server", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "MCP" in result.stdout or "mcp" in result.stdout.lower()
        assert "--project-dir" in result.stdout
        assert "--pipe" in result.stdout

    def test_requires_project_dir_or_pipe(self) -> None:
        """Should require either --project-dir or --pipe."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter.mcp_server"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "project-dir" in result.stderr.lower() or "pipe" in result.stderr.lower()

    def test_validates_project_dir_exists(self, tmp_path: Path) -> None:
        """Should validate that project directory exists."""
        nonexistent = tmp_path / "nonexistent"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter.mcp_server", "--project-dir", str(nonexistent)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "does not exist" in result.stderr

    def test_validates_mkdocs_yml_exists(self, tmp_path: Path) -> None:
        """Should validate that mkdocs.yml exists in project directory."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter.mcp_server", "--project-dir", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "mkdocs.yml" in result.stderr.lower()
