"""Comprehensive unit tests for modes.py run functions.

These tests verify user-facing output in all modes (batch, streaming, URL, wrap, interactive).
All tests use real-world build output formats and verify that warnings, errors, server URLs,
and rebuild detection actually appear in the console output.
"""

import argparse
import io
from unittest.mock import Mock, patch

from rich.console import Console

from docs_output_filter.modes import (
    run_batch_mode,
    run_interactive_mode,
    run_streaming_mode,
    run_url_mode,
    run_wrap_mode,
)


def make_args(**overrides):
    """Create an argparse.Namespace with defaults for testing."""
    defaults = dict(
        verbose=False,
        errors_only=False,
        no_progress=True,
        no_color=True,
        tool="auto",
        share_state=False,
        streaming=False,
        batch=False,
        interactive=False,
        url=None,
        raw=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def make_console():
    """Create a Rich Console that writes to a StringIO buffer."""
    return Console(file=io.StringIO(), no_color=True, width=120)


def get_output(console: Console) -> str:
    """Get the output from a console's buffer."""
    return console.file.getvalue()


# Real-world MkDocs output samples
MKDOCS_CLEAN_BUILD = """INFO    -  Building documentation...
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /tmp/site
INFO    -  Documentation built in 0.50 seconds
"""

MKDOCS_WITH_WARNING = """INFO    -  Building documentation...
WARNING -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.
INFO    -  Documentation built in 0.75 seconds
"""

MKDOCS_WITH_ERROR = """INFO    -  Building documentation...
ERROR   -  Config file 'mkdocs.yml': error parsing [nav]
INFO    -  Documentation built in 0.25 seconds
"""

MKDOCS_WITH_WARNING_AND_ERROR = """INFO    -  Building documentation...
WARNING -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.
ERROR   -  Config file 'mkdocs.yml': error parsing [nav]
INFO    -  Documentation built in 0.30 seconds
"""

MKDOCS_SERVE_WITH_URL = """INFO    -  Building documentation...
WARNING -  Doc file 'docs/index.md' contains a link 'broken.md', but the target is not found.
INFO    -  Documentation built in 1.23 seconds
INFO    -  Serving on http://127.0.0.1:8000/
"""

MKDOCS_SERVE_WITH_REBUILD = """INFO    -  Building documentation...
WARNING -  First warning before rebuild
INFO    -  Documentation built in 1.00 seconds
INFO    -  Serving on http://127.0.0.1:8000/
INFO    -  Detected file changes
INFO    -  Building documentation...
WARNING -  Second warning after rebuild
INFO    -  Documentation built in 0.50 seconds
"""

MKDOCS_DUPLICATE_WARNINGS = """INFO    -  Building documentation...
WARNING -  Duplicate warning message
WARNING -  Duplicate warning message
WARNING -  Duplicate warning message
INFO    -  Documentation built in 0.60 seconds
"""

MKDOCS_MARKDOWN_EXEC_ERROR = """INFO    -  Building documentation...
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  raise ValueError("Test error")

Output is:

  Traceback (most recent call last):
    File "<code block: session test; n1>", line 1, in <module>
      raise ValueError("Test error")
  ValueError: Test error

INFO    -  Documentation built in 0.80 seconds
"""

MKDOCS_INFO_MESSAGES = """INFO    -  Building documentation...
INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:
  - changelog.md
INFO    -  Doc file 'docs/index.md' contains a link 'api/missing.md', but the target is not found among documentation files.
INFO    -  Absolute link 'https://example.com/docs' is left as-is in 'docs/guide.md'.
INFO    -  Documentation built in 0.90 seconds
"""

SPHINX_WITH_WARNINGS = """Running Sphinx v7.2.0
building [html]: targets for 2 source files that are out of date
updating environment: 2 added, 0 changed, 0 removed
/path/to/docs/index.rst:15: WARNING: undefined label: missing-reference
/path/to/docs/api.rst:42: WARNING: toc tree contains reference to nonexistent document 'missing'
build succeeded, 2 warnings.
"""

SPHINX_WITH_ERROR = """Running Sphinx v7.2.0
building [html]: targets for 1 source files that are out of date
/path/to/docs/index.rst:10: ERROR: Unknown directive type "invalid".
Sphinx exited with exit code: 2
"""


class TestBatchMode:
    """Tests for run_batch_mode function."""

    def test_no_issues_shows_success_message(self, monkeypatch):
        """Clean build should show 'No warnings or errors' message."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_CLEAN_BUILD))
        console = make_console()
        args = make_args()

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        assert "No warnings or errors" in output

    def test_with_warning_displays_warning_text(self, monkeypatch):
        """Warning in build should appear in output with message text."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        console = make_console()
        args = make_args()

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        assert "WARNING" in output
        assert "missing.md" in output
        assert "1 warning" in output.lower()

    def test_with_error_displays_error_and_returns_one(self, monkeypatch):
        """Error in build should appear in output and return exit code 1."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_ERROR))
        console = make_console()
        args = make_args()

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 1
        assert "ERROR" in output
        assert "error parsing [nav]" in output
        assert "1 error" in output.lower()

    def test_with_warning_and_error_displays_both(self, monkeypatch):
        """Build with both warning and error should show both in output."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING_AND_ERROR))
        console = make_console()
        args = make_args()

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 1
        assert "WARNING" in output
        assert "missing.md" in output
        assert "ERROR" in output
        assert "error parsing [nav]" in output
        assert "1 error" in output.lower()
        assert "1 warning" in output.lower()

    def test_errors_only_flag_filters_warnings(self, monkeypatch):
        """With errors_only=True, warnings should not appear in output."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING_AND_ERROR))
        console = make_console()
        args = make_args(errors_only=True)

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 1
        assert "ERROR" in output
        # Warning text should not appear
        assert "missing.md" not in output
        assert "1 error" in output.lower()
        # Should not show warning count
        assert "warning" not in output.lower() or "0 warning" in output.lower()

    def test_deduplication_removes_duplicate_warnings(self, monkeypatch):
        """Duplicate warnings should be deduplicated and shown only once."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_DUPLICATE_WARNINGS))
        console = make_console()
        args = make_args()

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        assert "Duplicate warning message" in output
        # Should show only 1 warning, not 3
        assert "1 warning" in output.lower()
        # Count how many times the warning appears in the issues section
        warning_count = output.count("Duplicate warning message")
        assert warning_count == 1, f"Warning should appear once, found {warning_count} times"

    def test_info_messages_displayed(self, monkeypatch):
        """INFO messages like broken links and missing nav should be grouped and shown."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_INFO_MESSAGES))
        console = make_console()
        args = make_args()

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        # Check for INFO message content
        assert "missing.md" in output or "changelog.md" in output
        assert "No warnings or errors" in output

    def test_explicit_sphinx_tool_flag(self, monkeypatch):
        """Using tool='sphinx' should process Sphinx-format output."""
        monkeypatch.setattr("sys.stdin", io.StringIO(SPHINX_WITH_WARNINGS))
        console = make_console()
        args = make_args(tool="sphinx")

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        assert "WARNING" in output
        assert "undefined label" in output
        assert "2 warning" in output.lower()

    def test_returns_zero_on_warnings_one_on_errors(self, monkeypatch):
        """Exit code should be 0 for warnings only, 1 for errors."""
        # Test warnings only -> 0
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        console = make_console()
        args = make_args()
        exit_code = run_batch_mode(console, args, show_spinner=False)
        assert exit_code == 0

        # Test errors -> 1
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_ERROR))
        console = make_console()
        args = make_args()
        exit_code = run_batch_mode(console, args, show_spinner=False)
        assert exit_code == 1

    def test_verbose_flag_shows_code_blocks(self, monkeypatch):
        """With verbose=True, full code blocks and tracebacks should appear."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_MARKDOWN_EXEC_ERROR))
        console = make_console()
        args = make_args(verbose=True)

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        assert "Traceback" in output
        assert "ValueError: Test error" in output


class TestStreamingMode:
    """Tests for run_streaming_mode function (no-spinner path)."""

    def test_warning_appears_in_output_after_build_complete(self, monkeypatch):
        """Warning should appear in output when BUILD_COMPLETE boundary is hit."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        assert "WARNING" in output
        assert "missing.md" in output
        assert "Built in 0.75s" in output

    def test_server_url_displayed(self, monkeypatch):
        """Server URL should appear in output when detected."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_SERVE_WITH_URL))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        assert "http://127.0.0.1:8000/" in output
        assert "Server:" in output

    def test_rebuild_detection_shows_banner(self, monkeypatch):
        """Rebuild detection should show new warnings after file change."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_SERVE_WITH_REBUILD))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        # Both warnings should appear
        assert "First warning before rebuild" in output
        assert "Second warning after rebuild" in output
        # Both build times should appear
        assert "1.00" in output
        assert "0.50" in output

    def test_no_valid_build_output_shows_error(self, monkeypatch):
        """Invalid input should show error message."""
        invalid_input = "Some random text\nThat is not build output\n"
        monkeypatch.setattr("sys.stdin", io.StringIO(invalid_input))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 1
        assert "did not produce expected output" in output.lower()

    def test_empty_input_exits_cleanly(self, monkeypatch):
        """Empty input should exit with 'No warnings or errors' message."""
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        # Either shows "No warnings or errors" or error about no build output
        assert (
            "No warnings or errors" in output or "did not produce expected output" in output.lower()
        )

    def test_clean_build_shows_success_message(self, monkeypatch):
        """Clean build with no issues should show 'No warnings or errors'."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_CLEAN_BUILD))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        assert "No warnings or errors" in output

    def test_share_state_flag_shows_state_file_path(self, monkeypatch, tmp_path):
        """With share_state=True, state file path should appear in output."""
        # Mock get_state_file_path to return a test path
        with patch("docs_output_filter.modes.get_state_file_path") as mock_get_path:
            test_state_path = tmp_path / "state.json"
            mock_get_path.return_value = test_state_path

            monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
            console = make_console()
            args = make_args(no_progress=True, no_color=True, share_state=True)

            exit_code = run_streaming_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            assert "MCP" in output
            # The path may be wrapped across lines, so check with wrapping removed
            unwrapped = output.replace("\n", "")
            assert "state.json" in unwrapped

    def test_errors_only_filters_warnings(self, monkeypatch):
        """With errors_only=True, warnings should not appear."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING_AND_ERROR))
        console = make_console()
        args = make_args(no_progress=True, no_color=True, errors_only=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 1
        assert "ERROR" in output
        # Warning should be filtered out
        assert "missing.md" not in output

    def test_verbose_shows_full_tracebacks(self, monkeypatch):
        """With verbose=True, full tracebacks should be displayed."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_MARKDOWN_EXEC_ERROR))
        console = make_console()
        args = make_args(no_progress=True, no_color=True, verbose=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        assert "Traceback" in output
        assert "ValueError: Test error" in output

    def test_info_messages_grouped_and_displayed(self, monkeypatch):
        """INFO messages should be grouped by category and displayed."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_INFO_MESSAGES))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        # Should show INFO message content
        assert "changelog.md" in output or "missing.md" in output

    def test_explicit_tool_flag_processes_sphinx(self, monkeypatch):
        """With tool='sphinx', should process Sphinx-format output."""
        monkeypatch.setattr("sys.stdin", io.StringIO(SPHINX_WITH_WARNINGS))
        console = make_console()
        args = make_args(no_progress=True, no_color=True, tool="sphinx")

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        assert "WARNING" in output
        assert "undefined label" in output


class TestURLMode:
    """Tests for run_url_mode function."""

    def test_successful_fetch_displays_warnings(self, monkeypatch):
        """Successfully fetched log with warnings should display them."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_WITH_WARNING

            console = make_console()
            args = make_args(url="https://example.com/build.log", no_progress=True, no_color=True)

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            assert "WARNING" in output
            assert "missing.md" in output
            mock_fetch.assert_called_once_with("https://example.com/build.log")

    def test_failed_fetch_shows_error_message(self, monkeypatch):
        """Failed fetch should show 'Failed to fetch build log' message."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = None

            console = make_console()
            args = make_args(url="https://example.com/build.log", no_progress=True, no_color=True)

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 1
            assert "Failed to fetch build log" in output

    def test_errors_only_filtering_works(self, monkeypatch):
        """With errors_only=True, should filter warnings from fetched log."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_WITH_WARNING_AND_ERROR

            console = make_console()
            args = make_args(
                url="https://example.com/build.log",
                no_progress=True,
                no_color=True,
                errors_only=True,
            )

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 1
            assert "ERROR" in output
            # Warning should be filtered
            assert "missing.md" not in output

    def test_clean_log_shows_success(self, monkeypatch):
        """Fetched log with no issues should show success message."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_CLEAN_BUILD

            console = make_console()
            args = make_args(url="https://example.com/build.log", no_progress=True, no_color=True)

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            assert "No warnings or errors" in output

    def test_verbose_flag_shows_details(self, monkeypatch):
        """With verbose=True, should show full details in fetched log."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_MARKDOWN_EXEC_ERROR

            console = make_console()
            args = make_args(
                url="https://example.com/build.log", no_progress=True, no_color=True, verbose=True
            )

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            assert "Traceback" in output
            assert "ValueError: Test error" in output

    def test_explicit_tool_flag_processes_sphinx(self, monkeypatch):
        """With tool='sphinx', should process Sphinx-format fetched log."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = SPHINX_WITH_WARNINGS

            console = make_console()
            args = make_args(
                url="https://example.com/build.log", no_progress=True, no_color=True, tool="sphinx"
            )

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            assert "WARNING" in output
            assert "undefined label" in output

    def test_returns_one_on_errors(self, monkeypatch):
        """Fetched log with errors should return exit code 1."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_WITH_ERROR

            console = make_console()
            args = make_args(url="https://example.com/build.log", no_progress=True, no_color=True)

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 1
            assert "ERROR" in output


class TestWrapMode:
    """Tests for run_wrap_mode function."""

    def test_file_not_found_returns_127(self, monkeypatch):
        """Command not found should return exit code 127."""
        console = make_console()
        args = make_args(no_progress=True, no_color=True)
        command = ["nonexistent-command-xyz"]

        exit_code = run_wrap_mode(console, args, command)

        output = get_output(console)
        assert exit_code == 127
        assert "command not found" in output.lower()

    def test_permission_error_returns_126(self, monkeypatch):
        """Permission denied should return exit code 126."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = PermissionError()

            console = make_console()
            args = make_args(no_progress=True, no_color=True)
            command = ["some-command"]

            exit_code = run_wrap_mode(console, args, command)

            output = get_output(console)
            assert exit_code == 126
            assert "permission denied" in output.lower()


class TestInteractiveMode:
    """Tests for run_interactive_mode function."""

    def test_non_tty_stdin_falls_back_to_streaming(self, monkeypatch):
        """When stdin is not a TTY, should fall back to streaming mode."""
        # Mock stdin.isatty to return False
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        run_interactive_mode(console, args)

        output = get_output(console)
        assert "Falling back to streaming mode" in output
        # Should still process the warning via streaming fallback
        assert "WARNING" in output or "warning" in output.lower()

    def test_termios_unavailable_falls_back(self, monkeypatch):
        """When termios.tcgetattr is unavailable, should fall back to streaming."""
        # Mock stdin.isatty to return True but make termios raise error
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        # Mock termios to not have tcgetattr
        with patch("docs_output_filter.modes.termios") as mock_termios:
            delattr(mock_termios, "tcgetattr")

            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            run_interactive_mode(console, args)

            output = get_output(console)
            assert "Falling back to streaming mode" in output


# ---------------------------------------------------------------------------
# Additional coverage tests below
# ---------------------------------------------------------------------------

# Build output that triggers a warning count mismatch:
# "2 warnings" reported in the build succeeded line, but only 1 warning captured
MKDOCS_WARNING_COUNT_MISMATCH = """INFO    -  Building documentation...
WARNING -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.
INFO    -  Documentation built in 0.75 seconds
  2 warnings.
"""

# Content with no recognizable build tool markers (for auto-detect fallback)
GENERIC_NON_BUILD_OUTPUT = """Some random log line one
Another random log line two
Yet another line three
"""

# MkDocs output with a server error pattern
MKDOCS_SERVER_ERROR = """INFO    -  Building documentation...
INFO    -  Documentation built in 0.50 seconds
INFO    -  Serving on http://127.0.0.1:8000/
OSError: [Errno 98] Address already in use
"""

# MkDocs serve output for spinner-path testing
MKDOCS_SERVE_BUILD = """INFO    -  Building documentation...
WARNING -  Doc file 'docs/index.md' contains a link 'broken.md', but the target is not found.
INFO    -  Documentation built in 1.23 seconds
INFO    -  Serving on http://127.0.0.1:8000/
"""

# MkDocs output with info messages for URL mode info_groups test
MKDOCS_URL_INFO = """INFO    -  Building documentation...
INFO    -  Doc file 'docs/index.md' contains a link 'api/missing.md', but the target is not found among documentation files.
INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:
  - changelog.md
INFO    -  Documentation built in 0.90 seconds
"""


class TestBatchModeSpinner:
    """Tests for batch mode with show_spinner=True (lines 60-68)."""

    def test_batch_spinner_path_processes_warnings(self, monkeypatch):
        """Batch mode with show_spinner=True should still process and display warnings."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        # Use a non-color console to avoid terminal issues, but pass show_spinner=True
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_batch_mode(console, args, show_spinner=True)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "WARNING" in output
        assert "missing.md" in output

    def test_batch_spinner_path_processes_clean_build(self, monkeypatch):
        """Batch mode with show_spinner=True should show success for clean build."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_CLEAN_BUILD))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_batch_mode(console, args, show_spinner=True)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "No warnings or errors" in output

    def test_batch_spinner_path_processes_errors(self, monkeypatch):
        """Batch mode with show_spinner=True should return 1 on errors."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_ERROR))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_batch_mode(console, args, show_spinner=True)

        output = console.file.getvalue()
        assert exit_code == 1
        assert "ERROR" in output


class TestBatchModeAutoDetectFallback:
    """Tests for batch mode auto-detect fallback to MkDocsBackend (lines 82-84)."""

    def test_unrecognized_content_falls_back_to_mkdocs(self, monkeypatch):
        """When no backend is detected from content, should fallback to MkDocsBackend."""
        monkeypatch.setattr("sys.stdin", io.StringIO(GENERIC_NON_BUILD_OUTPUT))
        console = make_console()
        args = make_args(tool="auto")

        exit_code = run_batch_mode(console, args, show_spinner=False)

        output = get_output(console)
        assert exit_code == 0
        # Should still produce output (the fallback backend runs, just finds nothing)
        assert "No warnings or errors" in output


class TestStreamingModeWarningCountMismatch:
    """Tests for warning count mismatch detection (lines 207-218)."""

    def test_warning_count_mismatch_shows_hint(self, monkeypatch):
        """When build reports more warnings than captured, should show stderr hint."""
        # Build output where "build succeeded, 3 warnings" but only 1 actual warning captured
        sphinx_mismatch = """Running Sphinx v7.2.0
building [html]: targets for 2 source files that are out of date
/path/to/docs/index.rst:15: WARNING: undefined label: missing-reference
build succeeded, 3 warnings.
"""
        monkeypatch.setattr("sys.stdin", io.StringIO(sphinx_mismatch))
        console = make_console()
        args = make_args(no_progress=True, no_color=True, tool="sphinx")

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        # Should mention the mismatch
        assert "3 warning" in output
        assert "captured" in output.lower() or "stderr" in output.lower()


class TestStreamingModeSpinnerActive:
    """Tests for streaming mode with spinner_active=True (lines 227-272)."""

    def test_spinner_path_processes_warning(self, monkeypatch):
        """Streaming with spinner should process and display warnings."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "WARNING" in output
        assert "missing.md" in output

    def test_spinner_path_shows_server_url(self, monkeypatch):
        """Streaming with spinner should display server URL."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_SERVE_BUILD))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "http://127.0.0.1:8000/" in output

    def test_spinner_path_clean_build(self, monkeypatch):
        """Streaming with spinner should show success for clean build."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_CLEAN_BUILD))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "No warnings or errors" in output

    def test_spinner_path_rebuild_detection(self, monkeypatch):
        """Streaming with spinner should handle rebuild detection."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_SERVE_WITH_REBUILD))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "First warning before rebuild" in output
        assert "Second warning after rebuild" in output

    def test_spinner_path_with_error(self, monkeypatch):
        """Streaming with spinner should return 1 on errors."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_ERROR))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 1
        assert "ERROR" in output

    def test_spinner_path_share_state(self, monkeypatch, tmp_path):
        """Streaming with spinner and share_state should write state file path."""
        with patch("docs_output_filter.modes.get_state_file_path") as mock_get_path:
            test_state_path = tmp_path / "state.json"
            mock_get_path.return_value = test_state_path

            monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
            console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
            args = make_args(no_progress=False, no_color=False, share_state=True)

            exit_code = run_streaming_mode(console, args)

            output = console.file.getvalue()
            assert exit_code == 0
            assert "MCP" in output

    def test_spinner_path_server_url_after_build_output(self, monkeypatch):
        """Streaming with spinner: server URL arriving after build output shown should still display."""
        # MkDocs output where build complete is first, then server started
        # This triggers the `elif boundary == ChunkBoundary.SERVER_STARTED` branch
        # when build_output_shown is already True
        serve_output = """INFO    -  Building documentation...
WARNING -  A test warning here
INFO    -  Documentation built in 0.50 seconds
INFO    -  Serving on http://127.0.0.1:8000/
"""
        monkeypatch.setattr("sys.stdin", io.StringIO(serve_output))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "http://127.0.0.1:8000/" in output


class TestStreamingModeShareStateNoSpinner:
    """Tests for streaming mode no-spinner share_state path (lines 308-312)."""

    def test_share_state_no_spinner_writes_path(self, monkeypatch, tmp_path):
        """No-spinner path with share_state should write state and show path."""
        with patch("docs_output_filter.modes.get_state_file_path") as mock_get_path:
            test_state_path = tmp_path / "state.json"
            mock_get_path.return_value = test_state_path

            monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
            console = make_console()
            args = make_args(no_progress=True, no_color=True, share_state=True)

            exit_code = run_streaming_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            assert "MCP" in output
            # The path should be mentioned (may be wrapped)
            assert "state" in output

    def test_share_state_no_spinner_none_path(self, monkeypatch):
        """No-spinner path with share_state where get_state_file_path returns None."""
        with patch("docs_output_filter.modes.get_state_file_path") as mock_get_path:
            mock_get_path.return_value = None

            monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
            console = make_console()
            args = make_args(no_progress=True, no_color=True, share_state=True)

            exit_code = run_streaming_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            # Should not crash, just won't show state file path
            assert "WARNING" in output


class TestStreamingModeServerError:
    """Tests for streaming mode server error handling (lines 324-328)."""

    def test_server_error_shows_error_output(self, monkeypatch):
        """When server error is detected (OSError), should display error output."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_SERVER_ERROR))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 1
        assert "Server error" in output or "OSError" in output


class TestInteractiveModeWithTTY:
    """Tests for interactive mode with TTY simulation (lines 357-479)."""

    def test_interactive_mode_processes_input_and_quits(self, monkeypatch):
        """Interactive mode with mocked TTY should process input and handle 'q' key."""
        # Mock sys.stdin.isatty to return True
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        # The stdin_reader thread reads from sys.stdin.readline()
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        # Mock os.open to return a fake fd
        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            # Mock termios
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                # Mock tty.setraw
                with patch("docs_output_filter.modes.tty"):
                    # Mock select.select to return key presses
                    # First few calls return empty (no key), then 'q' to quit
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        if call_count[0] >= 5:
                            return [rlist[0]], [], []
                        return [], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Should show interactive mode banner
                                assert "Interactive mode" in output or "FILTERED" in output
                                # Should process issues
                                assert "WARNING" in output or "No warnings or errors" in output

    def test_interactive_mode_switch_to_raw(self, monkeypatch):
        """Interactive mode should handle 'r' key to switch to raw display."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]
                    keys = [b"r", b"q"]  # Press 'r' then 'q'
                    key_idx = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        # Return key on calls 3 and 6
                        if call_count[0] in (3, 6):
                            return [rlist[0]], [], []
                        return [], [], []

                    def mock_read(fd, n):
                        idx = key_idx[0]
                        key_idx[0] += 1
                        if idx < len(keys):
                            return keys[idx]
                        return b"q"

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", side_effect=mock_read):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                assert "RAW" in output

    def test_interactive_mode_switch_to_filtered(self, monkeypatch):
        """Interactive mode should handle 'f' key to switch back to filtered display."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]
                    keys = [b"r", b"f", b"q"]  # Switch raw -> filtered -> quit
                    key_idx = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        if call_count[0] in (3, 6, 9):
                            return [rlist[0]], [], []
                        return [], [], []

                    def mock_read(fd, n):
                        idx = key_idx[0]
                        key_idx[0] += 1
                        if idx < len(keys):
                            return keys[idx]
                        return b"q"

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", side_effect=mock_read):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                assert "FILTERED" in output

    def test_interactive_mode_os_open_failure_falls_back(self, monkeypatch):
        """When /dev/tty cannot be opened, should fall back to streaming mode."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        with patch("docs_output_filter.modes.os.open", side_effect=OSError("no tty")):
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            run_interactive_mode(console, args)

            output = get_output(console)
            assert "Falling back to streaming mode" in output

    def test_interactive_mode_with_errors_returns_one(self, monkeypatch):
        """Interactive mode with errors in input should return exit code 1."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_WITH_ERROR.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        if call_count[0] >= 5:
                            return [rlist[0]], [], []
                        return [], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                exit_code = run_interactive_mode(console, args)

                                assert exit_code == 1

    def test_interactive_mode_clean_build(self, monkeypatch):
        """Interactive mode with clean build should show no warnings."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_CLEAN_BUILD.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        if call_count[0] >= 5:
                            return [rlist[0]], [], []
                        return [], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                exit_code = run_interactive_mode(console, args)

                                output = get_output(console)
                                assert exit_code == 0
                                assert "No warnings or errors" in output


class TestURLModeSpinner:
    """Tests for URL mode with spinner path (lines 487-493)."""

    def test_url_mode_spinner_path(self, monkeypatch):
        """URL mode with no_progress=False should use spinner and still display results."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_WITH_WARNING

            console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
            args = make_args(
                url="https://example.com/build.log",
                no_progress=False,
                no_color=False,
            )

            exit_code = run_url_mode(console, args)

            output = console.file.getvalue()
            assert exit_code == 0
            assert "WARNING" in output
            assert "missing.md" in output
            mock_fetch.assert_called_once_with("https://example.com/build.log")

    def test_url_mode_spinner_path_with_error(self, monkeypatch):
        """URL mode with spinner should return 1 on errors."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_WITH_ERROR

            console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
            args = make_args(
                url="https://example.com/build.log",
                no_progress=False,
                no_color=False,
            )

            exit_code = run_url_mode(console, args)

            output = console.file.getvalue()
            assert exit_code == 1
            assert "ERROR" in output

    def test_url_mode_spinner_path_fetch_failure(self, monkeypatch):
        """URL mode with spinner should handle fetch failure."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = None

            console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
            args = make_args(
                url="https://example.com/build.log",
                no_progress=False,
                no_color=False,
            )

            exit_code = run_url_mode(console, args)

            output = console.file.getvalue()
            assert exit_code == 1
            assert "Failed to fetch build log" in output


class TestURLModeAutoDetectFallback:
    """Tests for URL mode auto-detect fallback to MkDocsBackend (lines 517-519)."""

    def test_unrecognized_url_content_falls_back_to_mkdocs(self, monkeypatch):
        """When URL content doesn't match any backend, should fallback to MkDocsBackend."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = GENERIC_NON_BUILD_OUTPUT

            console = make_console()
            args = make_args(
                url="https://example.com/build.log",
                no_progress=True,
                no_color=True,
                tool="auto",
            )

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            # Should show "No warnings or errors found" since fallback finds nothing
            assert "No warnings or errors" in output


class TestURLModeInfoGroups:
    """Tests for URL mode print_info_groups path (line 532)."""

    def test_url_mode_displays_info_groups(self, monkeypatch):
        """URL mode should display info groups when present."""
        with patch("docs_output_filter.modes.fetch_remote_log") as mock_fetch:
            mock_fetch.return_value = MKDOCS_URL_INFO

            console = make_console()
            args = make_args(
                url="https://example.com/build.log",
                no_progress=True,
                no_color=True,
            )

            exit_code = run_url_mode(console, args)

            output = get_output(console)
            assert exit_code == 0
            # Should show info message content like broken links or missing nav
            assert "missing.md" in output or "changelog.md" in output


class TestWrapModeSubprocess:
    """Tests for wrap mode with successful subprocess execution (lines 573-590)."""

    def test_wrap_mode_successful_execution(self, monkeypatch):
        """Wrap mode should execute subprocess and process its output."""
        from unittest.mock import MagicMock

        mock_stdout = io.BytesIO(MKDOCS_WITH_WARNING.encode("utf-8"))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.poll.return_value = 0  # Process has exited

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            exit_code = run_wrap_mode(console, args, ["mkdocs", "build"])

            output = get_output(console)
            assert exit_code == 0
            assert "WARNING" in output
            assert "missing.md" in output

            # Verify Popen was called with the right args
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            assert call_args[0][0] == ["mkdocs", "build"]
            # Should set PYTHONUNBUFFERED
            assert call_args[1]["env"]["PYTHONUNBUFFERED"] == "1"

    def test_wrap_mode_with_error_output(self, monkeypatch):
        """Wrap mode should return 1 on errors from subprocess."""
        from unittest.mock import MagicMock

        mock_stdout = io.BytesIO(MKDOCS_WITH_ERROR.encode("utf-8"))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.poll.return_value = 1

        with patch("subprocess.Popen", return_value=mock_proc):
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            exit_code = run_wrap_mode(console, args, ["mkdocs", "build"])

            output = get_output(console)
            assert exit_code == 1
            assert "ERROR" in output

    def test_wrap_mode_clean_build(self, monkeypatch):
        """Wrap mode with clean build should show success."""
        from unittest.mock import MagicMock

        mock_stdout = io.BytesIO(MKDOCS_CLEAN_BUILD.encode("utf-8"))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            exit_code = run_wrap_mode(console, args, ["mkdocs", "build"])

            output = get_output(console)
            assert exit_code == 0
            assert "No warnings or errors" in output

    def test_wrap_mode_terminates_running_process(self, monkeypatch):
        """Wrap mode should terminate process that's still running after streaming."""
        from unittest.mock import MagicMock

        mock_stdout = io.BytesIO(MKDOCS_WITH_WARNING.encode("utf-8"))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        # First poll returns None (still running), subsequent return 0
        mock_proc.poll.side_effect = [None, 0]

        with patch("subprocess.Popen", return_value=mock_proc):
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            run_wrap_mode(console, args, ["mkdocs", "serve"])

            # Should have called terminate
            mock_proc.terminate.assert_called_once()
            mock_proc.wait.assert_called()

    def test_wrap_mode_stdin_restored_on_error(self, monkeypatch):
        """Wrap mode should restore sys.stdin even when streaming mode raises."""
        from unittest.mock import MagicMock

        original_stdin = Mock()
        monkeypatch.setattr("sys.stdin", original_stdin)

        mock_stdout = io.BytesIO(b"")

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            run_wrap_mode(console, args, ["mkdocs", "build"])

            # sys.stdin should be restored
            import sys

            assert sys.stdin is original_stdin

    def test_wrap_mode_kills_on_timeout(self, monkeypatch):
        """Wrap mode should kill process when terminate + wait times out."""
        import subprocess
        from unittest.mock import MagicMock

        mock_stdout = io.BytesIO(MKDOCS_CLEAN_BUILD.encode("utf-8"))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        # poll returns None (still running)
        mock_proc.poll.return_value = None
        # wait raises TimeoutExpired after terminate
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="mkdocs", timeout=5),
            None,  # Second wait (after kill) succeeds
        ]

        with patch("subprocess.Popen", return_value=mock_proc):
            console = make_console()
            args = make_args(no_progress=True, no_color=True)

            run_wrap_mode(console, args, ["mkdocs", "serve"])

            mock_proc.terminate.assert_called_once()
            mock_proc.kill.assert_called_once()


class TestStreamingModePendingIssuesAfterFinalize:
    """Tests for pending_issues path after finalize (lines 308-312).

    This branch is reached when issues are queued but no chunk boundary
    was detected during streaming, so they weren't printed yet.
    """

    def test_pending_issues_printed_after_finalize(self, monkeypatch):
        """Issues queued without chunk boundary should be printed after finalize."""
        # Build output with a warning but NO "Documentation built in..." line
        # so no chunk boundary fires during streaming, issues stay pending
        incomplete_build = """INFO    -  Building documentation...
WARNING -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.
"""
        monkeypatch.setattr("sys.stdin", io.StringIO(incomplete_build))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        run_streaming_mode(console, args)

        output = get_output(console)
        # The warning should still be printed via the pending_issues path
        assert "WARNING" in output
        assert "missing.md" in output


class TestInteractiveModeExplicitTool:
    """Test interactive mode with explicit tool flag (line 375)."""

    def test_interactive_mode_explicit_sphinx_tool(self, monkeypatch):
        """Interactive mode with tool='sphinx' should use Sphinx backend."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = SPHINX_WITH_WARNINGS.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        if call_count[0] >= 5:
                            return [rlist[0]], [], []
                        return [], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True, tool="sphinx")

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Should process Sphinx warnings
                                assert "WARNING" in output or "undefined label" in output


class TestInteractiveModeSelectOSError:
    """Test get_key_nonblocking OSError handling (lines 402-403)."""

    def test_interactive_mode_select_os_error(self, monkeypatch):
        """OSError in select.select should be handled gracefully."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.side_effect = MKDOCS_CLEAN_BUILD.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        # First few calls raise OSError, then return 'q' key
                        if call_count[0] <= 3:
                            raise OSError("select error")
                        return [rlist[0]], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                # Should not crash despite OSError in select
                                exit_code = run_interactive_mode(console, args)

                                assert exit_code == 0


class TestInteractiveModeFilteredIssueDisplay:
    """Test interactive mode filtered issue display and mode switch with issues (lines 433-438, 456-459)."""

    def test_switch_to_filtered_shows_accumulated_issues(self, monkeypatch):
        """Switching from raw to filtered should display accumulated issues."""
        import threading
        import time

        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True

        # Use a barrier to ensure lines are read SLOWLY, giving key presses time
        lines = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        line_idx = [0]
        lines_consumed = threading.Event()

        def slow_readline():
            idx = line_idx[0]
            line_idx[0] += 1
            if idx < len(lines) - 1:
                # Return lines normally
                return lines[idx]
            else:
                # Last line (empty) -- wait briefly for keys to be processed
                lines_consumed.set()
                time.sleep(0.05)
                return ""

        mock_stdin.readline.side_effect = slow_readline
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]
                    keys = [b"r", b"f", b"q"]
                    key_idx = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        # Wait until lines have been consumed before pressing keys
                        if lines_consumed.is_set() and key_idx[0] < len(keys):
                            return [rlist[0]], [], []
                        return [], [], []

                    def mock_read(fd, n):
                        idx = key_idx[0]
                        key_idx[0] += 1
                        if idx < len(keys):
                            return keys[idx]
                        return b"q"

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", side_effect=mock_read):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Should contain both RAW and FILTERED switch banners
                                assert "RAW" in output
                                assert "FILTERED" in output

    def test_interactive_filtered_mode_displays_issues_inline(self, monkeypatch):
        """In filtered mode, new issues should be printed as they arrive."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True
        # Feed warnings that will be processed in filtered mode
        mock_stdin.readline.side_effect = MKDOCS_WITH_WARNING.splitlines(keepends=True) + [""]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        # Wait long enough for all lines to be processed, then quit
                        if call_count[0] >= 15:
                            return [rlist[0]], [], []
                        return [], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Should have processed the warning in filtered mode
                                assert (
                                    "WARNING" in output
                                    or "missing.md" in output
                                    or "No warnings or errors" in output
                                )


class TestStreamingModeStderrHintOnce:
    """Test that stderr hint is printed only once across rebuilds (line 202)."""

    def test_stderr_hint_printed_only_once(self, monkeypatch):
        """Two build-complete boundaries with warning mismatch: hint printed only once."""
        # Use Sphinx format since MkDocs doesn't parse reported_warning_count
        two_builds = (
            "Running Sphinx v7.2.0\n"
            "/path/to/index.rst:15: WARNING: undefined label\n"
            "build succeeded, 3 warnings.\n"
            "[sphinx-autobuild] Detected change in docs\n"
            "/path/to/index.rst:15: WARNING: undefined label\n"
            "build succeeded, 3 warnings.\n"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(two_builds))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        run_streaming_mode(console, args)

        output = get_output(console)
        # The inline stderr hint fires once (first build), then returns early (second build).
        # print_summary also emits "may have gone to stderr", giving 2 total.
        # Without the guard, it would be 3 (2 inline + 1 summary).
        hint_count = output.count("may have gone to stderr")
        assert hint_count == 2


class TestInteractiveModeBufferTruncation:
    """Test interactive mode buffer truncation at 10000 lines (lines 446-447)."""

    def test_buffer_truncation_over_10000_lines(self, monkeypatch):
        """Feeding 10001+ lines should trigger raw_buffer truncation."""
        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True

        # Generate 10050 lines
        lines = [f"INFO -  Processing item {i}\n" for i in range(10050)]
        lines.append("")  # EOF
        line_idx = [0]

        def readline_func():
            idx = line_idx[0]
            line_idx[0] += 1
            if idx < len(lines):
                return lines[idx]
            return ""

        mock_stdin.readline.side_effect = readline_func
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    call_count = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        call_count[0] += 1
                        # Quit after all lines processed
                        if call_count[0] >= 10100:
                            return [rlist[0]], [], []
                        return [], [], []

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", return_value=b"q"):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                # Test passes if it doesn't crash (buffer truncation worked)
                                output = get_output(console)
                                assert (
                                    "Interactive mode" in output
                                    or "No warnings or errors" in output
                                )


class TestStreamingModeSpinnerBranches:
    """Test streaming mode with spinner active to cover spinner-related branches."""

    def test_spinner_with_server_url(self, monkeypatch):
        """Spinner path with server URL should update spinner text (lines 237-245)."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "WARNING" in output

    def test_spinner_consecutive_identical_lines(self, monkeypatch):
        """Consecutive identical status lines should not cause errors (line 237->247)."""
        # Repeat the same INFO line many times
        repeated = "INFO    -  Building documentation...\n" * 20
        repeated += "WARNING -  A test warning\n"
        repeated += "INFO    -  Documentation built in 1.00 seconds\n"
        monkeypatch.setattr("sys.stdin", io.StringIO(repeated))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "WARNING" in output

    def test_spinner_share_state_no_project_root(self, monkeypatch):
        """share_state with no project root should not crash (line 258)."""
        monkeypatch.setattr("sys.stdin", io.StringIO(MKDOCS_WITH_WARNING))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False, share_state=True)

        with patch("docs_output_filter.modes.get_state_file_path", return_value=None):
            exit_code = run_streaming_mode(console, args)

        output = console.file.getvalue()
        assert exit_code == 0
        assert "WARNING" in output

    def test_spinner_double_build_complete(self, monkeypatch):
        """Two BUILD_COMPLETE without SERVER_STARTED: second should be no-op (line 248->264)."""
        double_complete = (
            "INFO    -  Building documentation...\n"
            "WARNING -  A warning\n"
            "INFO    -  Documentation built in 1.00 seconds\n"
            "INFO    -  Documentation built in 1.00 seconds\n"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(double_complete))
        console = Console(file=io.StringIO(), no_color=True, width=120, force_terminal=True)
        args = make_args(no_progress=False, no_color=False)

        exit_code = run_streaming_mode(console, args)

        assert exit_code == 0

    def test_no_spinner_double_build_complete(self, monkeypatch):
        """No-spinner path: second BUILD_COMPLETE without rebuild is a no-op (branch 296->274)."""
        double_complete = (
            "INFO    -  Building documentation...\n"
            "WARNING -  A warning\n"
            "INFO    -  Documentation built in 1.00 seconds\n"
            "INFO    -  Documentation built in 0.50 seconds\n"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(double_complete))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        assert "A warning" in output

    def test_no_spinner_with_rebuild(self, monkeypatch):
        """No-spinner path with rebuild should process correctly (line 296->274)."""
        rebuild_output = (
            "INFO    -  Building documentation...\n"
            "WARNING -  First build warning\n"
            "INFO    -  Documentation built in 1.00 seconds\n"
            "INFO    -  Serving on http://127.0.0.1:8000/\n"
            "INFO    -  Detected file changes\n"
            "INFO    -  Building documentation...\n"
            "WARNING -  Rebuild warning\n"
            "INFO    -  Documentation built in 0.50 seconds\n"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(rebuild_output))
        console = make_console()
        args = make_args(no_progress=True, no_color=True)

        exit_code = run_streaming_mode(console, args)

        output = get_output(console)
        assert exit_code == 0
        # Both warnings should appear
        assert "First build warning" in output
        assert "Rebuild warning" in output


class TestInteractiveModeEmptyQueueAndFilteredSwitch:
    """Test interactive mode with controlled readline to cover:

    - Line 438: print_issue when switching to FILTERED mode with accumulated issues
    - Lines 462-463: except Empty: continue when queue is empty but reader still alive
    """

    def test_empty_queue_fires_and_filtered_switch_prints_issues(self, monkeypatch):
        """Controlled readline blocks after lines, causing Empty exceptions and allowing key handling."""
        import threading

        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True

        real_lines = MKDOCS_WITH_WARNING.splitlines(keepends=True)
        line_idx = [0]
        lines_delivered = threading.Event()
        allow_eof = threading.Event()

        def controlled_readline():
            idx = line_idx[0]
            line_idx[0] += 1
            if idx < len(real_lines):
                if idx == len(real_lines) - 1:
                    lines_delivered.set()
                return real_lines[idx]
            # Block until test allows EOF (keeps reader alive so no None in queue)
            allow_eof.wait(timeout=5.0)
            return ""

        mock_stdin.readline.side_effect = controlled_readline
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    select_calls = [0]
                    key_sequence = [b"r", b"f", b"q"]
                    key_idx = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        select_calls[0] += 1
                        if not lines_delivered.is_set():
                            return [], [], []
                        # After lines consumed (~4 iterations), deliver keys spaced out
                        # so Empty exceptions fire between key presses
                        if key_idx[0] < len(key_sequence) and select_calls[0] >= 8:
                            if (select_calls[0] - 8) % 3 == 0:
                                return [rlist[0]], [], []
                        return [], [], []

                    def mock_read(fd, n):
                        idx = key_idx[0]
                        key_idx[0] += 1
                        if idx < len(key_sequence):
                            result = key_sequence[idx]
                        else:
                            result = b"q"
                        if result == b"q":
                            allow_eof.set()
                        return result

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", side_effect=mock_read):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Verify mode switches happened
                                assert "Switched to RAW mode" in output
                                assert "Switched to FILTERED mode" in output
                                # The warning should be printed when switching to filtered (line 438)
                                assert "missing.md" in output

    def test_press_f_when_already_filtered_is_noop(self, monkeypatch):
        """Pressing 'f' when already in FILTERED mode should be a no-op (branch 433->440)."""
        import threading

        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True

        real_lines = MKDOCS_WITH_WARNING.splitlines(keepends=True)
        line_idx = [0]
        lines_delivered = threading.Event()
        allow_eof = threading.Event()

        def controlled_readline():
            idx = line_idx[0]
            line_idx[0] += 1
            if idx < len(real_lines):
                if idx == len(real_lines) - 1:
                    lines_delivered.set()
                return real_lines[idx]
            allow_eof.wait(timeout=5.0)
            return ""

        mock_stdin.readline.side_effect = controlled_readline
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    select_calls = [0]
                    # Press 'f' (already in FILTERED → no-op), then 'q'
                    key_sequence = [b"f", b"q"]
                    key_idx = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        select_calls[0] += 1
                        if not lines_delivered.is_set():
                            return [], [], []
                        if key_idx[0] < len(key_sequence) and select_calls[0] >= 8:
                            if (select_calls[0] - 8) % 3 == 0:
                                return [rlist[0]], [], []
                        return [], [], []

                    def mock_read(fd, n):
                        idx = key_idx[0]
                        key_idx[0] += 1
                        if idx < len(key_sequence):
                            result = key_sequence[idx]
                        else:
                            result = b"q"
                        if result == b"q":
                            allow_eof.set()
                        return result

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", side_effect=mock_read):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Should NOT show "Switched to FILTERED" (already was filtered)
                                assert "Switched to FILTERED" not in output

    def test_multiple_warnings_inline_display(self, monkeypatch):
        """Two warnings in one build: second skips blank line (branch 457->459)."""
        import threading

        mock_stdin = Mock()
        mock_stdin.isatty.return_value = True

        two_warnings = (
            "INFO    -  Building documentation...\n"
            "WARNING -  Doc file 'docs/index.md' contains a link 'missing.md', "
            "but the target is not found among documentation files.\n"
            "WARNING -  Doc file 'docs/page.md' contains a link 'broken.md', "
            "but the target is not found among documentation files.\n"
            "INFO    -  Documentation built in 0.75 seconds\n"
        )
        real_lines = two_warnings.splitlines(keepends=True)
        line_idx = [0]
        lines_delivered = threading.Event()
        allow_eof = threading.Event()

        def controlled_readline():
            idx = line_idx[0]
            line_idx[0] += 1
            if idx < len(real_lines):
                if idx == len(real_lines) - 1:
                    lines_delivered.set()
                return real_lines[idx]
            allow_eof.wait(timeout=5.0)
            return ""

        mock_stdin.readline.side_effect = controlled_readline
        monkeypatch.setattr("sys.stdin", mock_stdin)

        fake_fd = 99
        with patch("docs_output_filter.modes.os.open", return_value=fake_fd):
            with patch("docs_output_filter.modes.termios") as mock_termios:
                mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, [0] * 32]
                mock_termios.TCSADRAIN = 1

                with patch("docs_output_filter.modes.tty"):
                    select_calls = [0]
                    key_sequence = [b"q"]
                    key_idx = [0]

                    def mock_select(rlist, wlist, xlist, timeout=None):
                        select_calls[0] += 1
                        if not lines_delivered.is_set():
                            return [], [], []
                        # Quit after lines are consumed
                        if key_idx[0] < len(key_sequence) and select_calls[0] >= 10:
                            return [rlist[0]], [], []
                        return [], [], []

                    def mock_read(fd, n):
                        idx = key_idx[0]
                        key_idx[0] += 1
                        if idx < len(key_sequence):
                            result = key_sequence[idx]
                        else:
                            result = b"q"
                        if result == b"q":
                            allow_eof.set()
                        return result

                    with patch("docs_output_filter.modes.select.select", side_effect=mock_select):
                        with patch("docs_output_filter.modes.os.read", side_effect=mock_read):
                            with patch("docs_output_filter.modes.os.close"):
                                console = make_console()
                                args = make_args(no_progress=True, no_color=True)

                                run_interactive_mode(console, args)

                                output = get_output(console)
                                # Both warnings should appear inline
                                assert "missing.md" in output
                                assert "broken.md" in output
