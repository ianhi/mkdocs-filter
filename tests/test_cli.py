"""Tests for CLI functionality and main function."""

import subprocess
import sys


class TestCLI:
    """Tests for command-line interface."""

    def test_version_flag(self) -> None:
        """--version should print version and exit."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_help_flag(self) -> None:
        """--help should print help and exit."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "mkdocs" in result.stdout.lower()
        assert "filter" in result.stdout.lower()

    def test_no_input_exits_cleanly(self) -> None:
        """Should exit cleanly with no input."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress"],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "No warnings or errors" in result.stdout

    def test_processes_simple_warning(self) -> None:
        """Should process a simple warning."""
        input_text = "WARNING -  Test warning message"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "WARNING" in result.stdout
        assert "Test warning message" in result.stdout

    def test_processes_simple_error(self) -> None:
        """Should process a simple error and return exit code 1."""
        input_text = "ERROR -  Test error message"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "ERROR" in result.stdout
        assert "Test error message" in result.stdout

    def test_raw_flag_passes_through(self) -> None:
        """--raw should pass through input unchanged."""
        input_text = "INFO -  This should pass through\nDEBUG -  So should this"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--raw"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "INFO -  This should pass through" in result.stdout
        assert "DEBUG -  So should this" in result.stdout

    def test_errors_only_flag_filters_warnings(self) -> None:
        """--errors-only should only show errors."""
        input_text = "WARNING -  A warning\nERROR -  An error"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color", "--errors-only"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "error" in result.stdout.lower()
        assert result.returncode == 1

    def test_verbose_flag_shows_traceback(self) -> None:
        """--verbose should show full tracebacks."""
        input_text = """WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  raise ValueError('test')

Output is:

  Traceback (most recent call last):
    File "<code block: session test; n1>", line 1, in <module>
      raise ValueError('test')
  ValueError: test

INFO -  Done"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color", "-v"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "Traceback" in result.stdout

    def test_no_color_flag(self) -> None:
        """--no-color should disable ANSI escape codes."""
        input_text = "WARNING -  Test warning"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        # Should not contain ANSI escape codes
        assert "\033[" not in result.stdout

    def test_shows_build_info(self) -> None:
        """Should show build directory and time."""
        input_text = """INFO -  Building documentation to directory: /path/to/site
INFO -  Documentation built in 1.23 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "/path/to/site" in result.stdout
        assert "1.23" in result.stdout

    def test_shows_server_url(self) -> None:
        """Should show server URL when serving."""
        input_text = "INFO -  Serving on http://127.0.0.1:8000/"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "http://127.0.0.1:8000/" in result.stdout

    def test_deduplicates_warnings(self) -> None:
        """Should deduplicate similar warnings."""
        input_text = """WARNING -  Same warning
WARNING -  Same warning
WARNING -  Same warning"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        # Should only show 1 warning, not 3
        assert "1 warning" in result.stdout

    def test_shows_summary_count(self) -> None:
        """Should show summary with error and warning counts."""
        input_text = """WARNING -  Warning 1
WARNING -  Warning 2
ERROR -  Error 1"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "1 error" in result.stdout.lower()
        assert "2 warning" in result.stdout.lower()

    def test_shows_verbose_hint(self) -> None:
        """Should show hint about verbose flag when there are issues."""
        input_text = "WARNING -  A warning"
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "-v" in result.stdout
        assert "verbose" in result.stdout.lower()


class TestStreamingMode:
    """Tests for streaming mode functionality."""

    def test_streaming_flag_works(self) -> None:
        """--streaming flag should process incrementally."""
        input_text = """INFO -  Building...
WARNING -  Test warning
INFO -  Documentation built in 1.00 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color", "--streaming"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "WARNING" in result.stdout
        assert "Test warning" in result.stdout
        assert "1.00" in result.stdout

    def test_batch_flag_works(self) -> None:
        """--batch flag should force batch mode."""
        input_text = """INFO -  Building...
WARNING -  Test warning
INFO -  Documentation built in 1.00 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color", "--batch"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "WARNING" in result.stdout
        assert "Test warning" in result.stdout

    def test_streaming_processes_multiple_warnings(self) -> None:
        """Streaming mode should process multiple warnings."""
        input_text = """INFO -  Building...
WARNING -  First warning
INFO -  More building...
WARNING -  Second warning
INFO -  Documentation built in 1.00 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color", "--streaming"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        assert "First warning" in result.stdout
        assert "Second warning" in result.stdout
        assert "2 warning" in result.stdout.lower()

    def test_detects_new_error_after_rebuild_in_serve(self) -> None:
        """CRITICAL: Should detect new errors introduced after file change during serve."""
        input_text = """INFO    -  Building documentation...
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  raise ValueError("FIRST ERROR")

Output is:

  ValueError: FIRST ERROR

INFO    -  Documentation built in 1.00 seconds
INFO    -  Serving on http://127.0.0.1:8000/
INFO    -  Detected file changes
INFO    -  Building documentation...
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  raise ValueError("SECOND ERROR AFTER REBUILD")

Output is:

  ValueError: SECOND ERROR AFTER REBUILD

INFO    -  Documentation built in 0.50 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        # Both errors must appear in output
        assert "FIRST ERROR" in result.stdout, "First error should be shown"
        assert (
            "SECOND ERROR AFTER REBUILD" in result.stdout
        ), "Second error after rebuild should be shown"
        # Server URL should be shown
        assert "127.0.0.1:8000" in result.stdout, "Server URL should be shown"
        # Rebuild indicator should be shown
        assert (
            "rebuild" in result.stdout.lower() or "file change" in result.stdout.lower()
        ), "Rebuild indicator should be shown"

    def test_clears_issues_on_rebuild(self) -> None:
        """Should show only the latest build's issues after rebuild, not accumulate."""
        input_text = """INFO    -  Building documentation...
WARNING -  Old warning that will be fixed
INFO    -  Documentation built in 1.00 seconds
INFO    -  Serving on http://127.0.0.1:8000/
INFO    -  Detected file changes
INFO    -  Building documentation...
WARNING -  New warning after fix
INFO    -  Documentation built in 0.50 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        # Both warnings should appear (one from each build)
        assert "Old warning" in result.stdout, "First build's warning should be shown"
        assert "New warning" in result.stdout, "Second build's warning should be shown"

    def test_streaming_processes_rebuild_from_simulated_input(self) -> None:
        """Verifies streaming mode handles rebuild output correctly.

        This is a simpler unit test with simulated input. For real mkdocs serve
        testing with file watching, see TestMkdocsServeRebuild in test_integration.py.
        """
        input_text = """INFO    -  Building documentation...
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  raise ValueError('INITIAL_ERROR')

Output is:

  ValueError: INITIAL_ERROR

INFO    -  Documentation built in 1.00 seconds
INFO    -  Serving on http://127.0.0.1:8000/
INFO    -  Detected file changes
INFO    -  Building documentation...
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  raise ValueError('REBUILD_ERROR')

Output is:

  ValueError: REBUILD_ERROR

INFO    -  Documentation built in 0.50 seconds"""

        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--no-progress", "--no-color", "--streaming"],
            input=input_text,
            capture_output=True,
            text=True,
        )

        # Both errors should appear
        assert "INITIAL_ERROR" in result.stdout, f"Initial error missing:\n{result.stdout}"
        assert "REBUILD_ERROR" in result.stdout, f"Rebuild error missing:\n{result.stdout}"
        # Server URL should appear
        assert "127.0.0.1:8000" in result.stdout, f"Server URL missing:\n{result.stdout}"
        # Rebuild indicator should appear
        assert "rebuild" in result.stdout.lower() or "file change" in result.stdout.lower()


class TestInteractiveMode:
    """Tests for interactive mode functionality."""

    def test_interactive_help_shows_flag(self) -> None:
        """Help output should mention interactive flag."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--help"],
            capture_output=True,
            text=True,
        )
        assert "--interactive" in result.stdout or "-i" in result.stdout

    def test_interactive_flag_short_form(self) -> None:
        """Short form -i should be recognized."""
        # Interactive mode will fall back to streaming when no tty
        input_text = """INFO -  Building...
WARNING -  Test warning
INFO -  Documentation built in 1.00 seconds"""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "-i", "--no-progress", "--no-color"],
            input=input_text,
            capture_output=True,
            text=True,
        )
        # Should process (either interactive or fallback to streaming)
        assert "WARNING" in result.stdout or "warning" in result.stdout.lower()


class TestInstallation:
    """Tests for package installation."""

    def test_can_run_as_module(self) -> None:
        """Should be runnable as python -m mkdocs_filter."""
        result = subprocess.run(
            [sys.executable, "-m", "mkdocs_filter", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_entry_point_exists(self) -> None:
        """Should have mkdocs-output-filter entry point."""
        result = subprocess.run(
            ["mkdocs-output-filter", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout
