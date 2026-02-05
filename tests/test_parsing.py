"""Unit tests for mkdocs output parsing functions."""

from rich.console import Console

from mkdocs_filter import (
    BuildInfo,
    ChunkBoundary,
    Issue,
    Level,
    StreamingProcessor,
    dedent_code,
    detect_chunk_boundary,
    extract_build_info,
    is_in_multiline_block,
    parse_markdown_exec_issue,
    parse_mkdocs_output,
)


class TestExtractBuildInfo:
    """Tests for extract_build_info function."""

    def test_extracts_server_url(self) -> None:
        lines = [
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]
        info = extract_build_info(lines)
        assert info.server_url == "http://127.0.0.1:8000/"

    def test_extracts_build_time(self) -> None:
        lines = [
            "INFO -  Documentation built in 78.99 seconds",
        ]
        info = extract_build_info(lines)
        assert info.build_time == "78.99"

    def test_extracts_build_directory(self) -> None:
        lines = [
            "INFO -  Building documentation to directory: /path/to/site",
        ]
        info = extract_build_info(lines)
        assert info.build_dir == "/path/to/site"

    def test_extracts_all_info(self) -> None:
        lines = [
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Serving on http://127.0.0.1:8000/",
            "INFO -  Documentation built in 1.23 seconds",
        ]
        info = extract_build_info(lines)
        assert info.server_url == "http://127.0.0.1:8000/"
        assert info.build_time == "1.23"
        assert info.build_dir == "/path/to/site"

    def test_returns_empty_when_no_info(self) -> None:
        lines = ["INFO -  Some other log line"]
        info = extract_build_info(lines)
        assert info.server_url is None
        assert info.build_time is None
        assert info.build_dir is None


class TestParseMkdocsOutput:
    """Tests for parse_mkdocs_output function."""

    def test_no_warnings_or_errors(self) -> None:
        lines = [
            "INFO -  Cleaning site directory",
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Documentation built in 0.12 seconds",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 0

    def test_parses_simple_warning(self) -> None:
        lines = [
            "WARNING -  Some warning message",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert issues[0].source == "mkdocs"
        assert issues[0].message == "Some warning message"

    def test_parses_simple_error(self) -> None:
        lines = [
            "ERROR -  Something bad happened",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.ERROR
        assert issues[0].source == "mkdocs"
        assert issues[0].message == "Something bad happened"

    def test_parses_broken_link_warning(self) -> None:
        lines = [
            "WARNING -  Doc file 'index.md' contains a link 'missing.md', but the target is not found among documentation files.",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert issues[0].file == "index.md"
        assert "missing.md" in issues[0].message

    def test_parses_nav_reference_warning(self) -> None:
        lines = [
            "WARNING -  A reference to 'missing.md' is included in the 'nav' configuration, which is not found in the documentation files.",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert "nav" in issues[0].message.lower()
        assert issues[0].file == "missing.md"

    def test_parses_multiple_warnings(self) -> None:
        lines = [
            "INFO -  Building...",
            "WARNING -  First warning",
            "INFO -  More info",
            "WARNING -  Second warning",
            "INFO -  Done",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 2
        assert issues[0].message == "First warning"
        assert issues[1].message == "Second warning"

    def test_strips_stderr_prefix(self) -> None:
        lines = [
            "[stderr] WARNING -  Some warning",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].message == "Some warning"

    def test_strips_timestamp_prefix(self) -> None:
        lines = [
            "2024-01-01 12:00:00,000 - mkdocs.structure - WARNING - Some warning",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        # The timestamp should be stripped
        assert "2024-01-01" not in issues[0].message


class TestParseMarkdownExecIssue:
    """Tests for parse_markdown_exec_issue function."""

    def test_parses_markdown_exec_error_basic(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('test error')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session test; n1>", line 1, in <module>',
            "      raise ValueError('test error')",
            "  ValueError: test error",
            "",
            "INFO -  next log line",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 0, Level.WARNING)

        assert issue is not None
        assert issue.level == Level.WARNING
        assert issue.source == "markdown_exec"
        assert "ValueError: test error" in issue.message
        assert issue.code is not None
        assert "raise ValueError" in issue.code
        assert issue.output is not None
        assert "Traceback" in issue.output

    def test_extracts_session_and_line_info(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  x = 1",
            "  y = 2",
            "  raise ValueError('error')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session mytest; n1>", line 3, in <module>',
            "      raise ValueError('error')",
            "  ValueError: error",
            "",
            "INFO -  Done",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 0, Level.WARNING)

        assert issue is not None
        assert issue.file is not None
        assert "session 'mytest'" in issue.file
        assert "line 3" in issue.file

    def test_extracts_file_from_verbose_mode(self) -> None:
        lines = [
            "DEBUG   -  Reading: test.md",
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('error')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session test; n1>", line 1, in <module>',
            "      raise ValueError('error')",
            "  ValueError: error",
            "",
            "INFO -  Done",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 1, Level.WARNING)

        assert issue is not None
        assert issue.file is not None
        assert "test.md" in issue.file

    def test_stops_at_next_log_line(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  print('hello')",
            "",
            "Output is:",
            "",
            "  some output",
            "",
            "INFO -  Building documentation to directory: /path",
            "INFO -  More info",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 0, Level.WARNING)

        assert issue is not None
        assert end_idx == 10  # Should stop at the INFO line


class TestDedentCode:
    """Tests for dedent_code function."""

    def test_removes_consistent_indent(self) -> None:
        code = "  line1\n  line2\n  line3"
        result = dedent_code(code)
        assert result == "line1\nline2\nline3"

    def test_preserves_relative_indent(self) -> None:
        code = "  line1\n    line2\n  line3"
        result = dedent_code(code)
        assert result == "line1\n  line2\nline3"

    def test_handles_empty_lines(self) -> None:
        code = "  line1\n\n  line3"
        result = dedent_code(code)
        assert result == "line1\n\nline3"

    def test_returns_unchanged_if_no_indent(self) -> None:
        code = "line1\nline2"
        result = dedent_code(code)
        assert result == "line1\nline2"

    def test_handles_empty_string(self) -> None:
        result = dedent_code("")
        assert result == ""


class TestIssueDataclass:
    """Tests for Issue dataclass."""

    def test_creates_minimal_issue(self) -> None:
        issue = Issue(level=Level.WARNING, source="test", message="test message")
        assert issue.level == Level.WARNING
        assert issue.source == "test"
        assert issue.message == "test message"
        assert issue.file is None
        assert issue.code is None
        assert issue.output is None

    def test_creates_full_issue(self) -> None:
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Error occurred",
            file="test.md",
            code="raise Error()",
            output="Traceback...",
        )
        assert issue.level == Level.ERROR
        assert issue.file == "test.md"
        assert issue.code == "raise Error()"
        assert issue.output == "Traceback..."


class TestBuildInfoDataclass:
    """Tests for BuildInfo dataclass."""

    def test_creates_empty_build_info(self) -> None:
        info = BuildInfo()
        assert info.server_url is None
        assert info.build_dir is None
        assert info.build_time is None

    def test_creates_full_build_info(self) -> None:
        info = BuildInfo(
            server_url="http://localhost:8000/",
            build_dir="/path/to/site",
            build_time="1.23",
        )
        assert info.server_url == "http://localhost:8000/"
        assert info.build_dir == "/path/to/site"
        assert info.build_time == "1.23"


class TestDetectChunkBoundary:
    """Tests for detect_chunk_boundary function."""

    def test_detects_build_complete(self) -> None:
        line = "INFO -  Documentation built in 78.99 seconds"
        assert detect_chunk_boundary(line) == ChunkBoundary.BUILD_COMPLETE

    def test_detects_server_started(self) -> None:
        line = "INFO -  Serving on http://127.0.0.1:8000/"
        assert detect_chunk_boundary(line) == ChunkBoundary.SERVER_STARTED

    def test_detects_rebuild_started_file_changes(self) -> None:
        line = "INFO -  Detected file changes"
        assert detect_chunk_boundary(line) == ChunkBoundary.REBUILD_STARTED

    def test_detects_rebuild_started_reloading(self) -> None:
        line = "INFO -  Reloading docs on file change"
        assert detect_chunk_boundary(line) == ChunkBoundary.REBUILD_STARTED

    def test_returns_none_for_normal_line(self) -> None:
        line = "INFO -  Building documentation..."
        assert detect_chunk_boundary(line) == ChunkBoundary.NONE

    def test_detects_error_block_end_after_blank(self) -> None:
        line = "INFO -  Building documentation"
        prev_line = ""
        assert detect_chunk_boundary(line, prev_line) == ChunkBoundary.ERROR_BLOCK_END


class TestIsInMultilineBlock:
    """Tests for is_in_multiline_block function."""

    def test_detects_unclosed_markdown_exec_block(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('test')",
        ]
        assert is_in_multiline_block(lines) is True

    def test_detects_closed_markdown_exec_block(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('test')",
            "",
            "Output is:",
            "",
            "  ValueError: test",
            "",
            "INFO -  Done building",
        ]
        assert is_in_multiline_block(lines) is False

    def test_returns_false_for_empty_buffer(self) -> None:
        assert is_in_multiline_block([]) is False

    def test_returns_false_for_normal_lines(self) -> None:
        lines = [
            "INFO -  Building...",
            "INFO -  Done",
        ]
        assert is_in_multiline_block(lines) is False


class TestStreamingProcessor:
    """Tests for StreamingProcessor class."""

    def test_processes_simple_warning(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        def capture_issue(issue: Issue) -> None:
            captured_issues.append(issue)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=capture_issue,
        )

        lines = [
            "INFO -  Building...",
            "WARNING -  Test warning message",
            "INFO -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        all_issues, build_info = processor.finalize()

        assert len(all_issues) == 1
        assert all_issues[0].level == Level.WARNING
        assert all_issues[0].message == "Test warning message"
        assert build_info.build_time == "1.00"

    def test_deduplicates_warnings(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        lines = [
            "WARNING -  Same warning",
            "WARNING -  Same warning",
            "WARNING -  Same warning",
            "INFO -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        all_issues, _ = processor.finalize()
        assert len(all_issues) == 1

    def test_filters_errors_only(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=True,
            on_issue=lambda i: captured_issues.append(i),
        )

        lines = [
            "WARNING -  A warning",
            "ERROR -  An error",
            "INFO -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        all_issues, _ = processor.finalize()
        assert len(all_issues) == 1
        assert all_issues[0].level == Level.ERROR

    def test_extracts_build_info(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
        )

        lines = [
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Serving on http://127.0.0.1:8000/",
            "INFO -  Documentation built in 2.50 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        _, build_info = processor.finalize()

        assert build_info.build_dir == "/path/to/site"
        assert build_info.server_url == "http://127.0.0.1:8000/"
        assert build_info.build_time == "2.50"

    def test_buffer_size_limit(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(console=console, verbose=False, errors_only=False)

        # Add more lines than buffer max size
        for i in range(300):
            processor.process_line(f"INFO -  Line {i}")

        # Buffer should be trimmed to max size
        assert len(processor.buffer) <= StreamingProcessor.BUFFER_MAX_SIZE

    def test_detects_error_after_rebuild_during_serve(self) -> None:
        """CRITICAL: Should detect new errors introduced after initial build during serve."""
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        def capture_issue(issue: Issue) -> None:
            captured_issues.append(issue)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=capture_issue,
        )

        # Simulate initial clean build
        initial_build = [
            "INFO -  Building documentation...",
            "INFO -  Cleaning site directory",
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]
        for line in initial_build:
            processor.process_line(line)

        # At this point, no issues should be detected
        assert len(captured_issues) == 0
        assert processor.build_info.server_url == "http://127.0.0.1:8000/"

        # Simulate file change detection and rebuild with an error
        rebuild_with_error = [
            "INFO -  Detected file changes",
            "INFO -  Building documentation...",
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('NEW ERROR AFTER SERVE')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session test; n1>", line 1, in <module>',
            "      raise ValueError('NEW ERROR AFTER SERVE')",
            "  ValueError: NEW ERROR AFTER SERVE",
            "",
            "INFO -  Documentation built in 0.50 seconds",
        ]
        for line in rebuild_with_error:
            processor.process_line(line)

        # Should have detected the new error
        all_issues, build_info = processor.finalize()
        assert len(all_issues) == 1
        assert all_issues[0].level == Level.WARNING
        assert all_issues[0].source == "markdown_exec"
        assert "NEW ERROR AFTER SERVE" in all_issues[0].message
        assert all_issues[0].code is not None
        assert "raise ValueError" in all_issues[0].code

    def test_clears_state_on_rebuild(self) -> None:
        """Should clear previous issues when rebuild starts."""
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        # First build with a warning
        first_build = [
            "INFO -  Building...",
            "WARNING -  First build warning",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]
        for line in first_build:
            processor.process_line(line)

        assert len(captured_issues) == 1
        assert "First build" in captured_issues[0].message

        # Rebuild after file change - this should clear state
        rebuild = [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "WARNING -  Second build warning",
            "INFO -  Documentation built in 0.50 seconds",
        ]
        for line in rebuild:
            processor.process_line(line)

        # After finalize, should only have the second warning (state was cleared)
        all_issues, _ = processor.finalize()
        # captured_issues will have both (callback was called for both)
        # but processor.all_issues should only have the second one
        assert len(all_issues) == 1
        assert "Second build" in all_issues[0].message

    def test_multiple_rebuilds_each_detected(self) -> None:
        """Should detect issues across multiple rebuilds during serve."""
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        # Initial clean build
        for line in [
            "INFO -  Building...",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]:
            processor.process_line(line)

        assert len(captured_issues) == 0

        # First rebuild with error
        for line in [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "ERROR -  First rebuild error",
            "INFO -  Documentation built in 0.50 seconds",
        ]:
            processor.process_line(line)

        # Should have captured one error
        assert len(captured_issues) == 1
        assert "First rebuild" in captured_issues[0].message

        # Second rebuild with different error
        for line in [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "ERROR -  Second rebuild error",
            "INFO -  Documentation built in 0.30 seconds",
        ]:
            processor.process_line(line)

        # Should have captured two errors total (one from each rebuild)
        assert len(captured_issues) == 2
        assert "Second rebuild" in captured_issues[1].message
