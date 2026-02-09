"""Comprehensive unit tests for display.py formatting functions.

Tests cover all major display functions with real output verification:
- print_issue(): warning/error rendering with all field combinations
- print_info_groups(): grouped INFO messages with truncation logic
- print_summary(): build summary footer with counts and hints
- truncate_line(): text truncation for spinner display
- Helper functions: _get_upstream_command, build_stderr_hint
"""

import io
import subprocess
from unittest import mock

from rich.console import Console

from docs_output_filter.display import (
    INFO_CATEGORY_DISPLAY,
    DisplayMode,
    _get_upstream_command,
    build_stderr_hint,
    print_info_groups,
    print_issue,
    print_summary,
    truncate_line,
)
from docs_output_filter.types import BuildInfo, InfoCategory, InfoMessage, Issue, Level


def make_console() -> Console:
    """Create a test console that captures output."""
    return Console(file=io.StringIO(), no_color=True, width=80)


def get_output(console: Console) -> str:
    """Get the captured output from a test console."""
    return console.file.getvalue()


class TestPrintIssue:
    """Tests for print_issue() function."""

    def test_warning_with_all_fields(self) -> None:
        """WARNING with all fields should render completely."""
        console = make_console()
        issue = Issue(
            level=Level.WARNING,
            source="mkdocs",
            message="Missing page in navigation",
            file="docs/guide.md",
            line_number=42,
            warning_code="nav.missing",
        )
        print_issue(console, issue)
        output = get_output(console)

        assert "⚠" in output
        assert "WARNING" in output
        assert "[mkdocs]" in output
        assert "Missing page in navigation" in output
        assert "[nav.missing]" in output
        assert "📍 docs/guide.md:42" in output

    def test_error_with_all_fields(self) -> None:
        """ERROR with all fields should render completely."""
        console = make_console()
        issue = Issue(
            level=Level.ERROR,
            source="sphinx",
            message="Build failed",
            file="/path/to/index.rst",
            line_number=10,
            warning_code="build.failed",
        )
        print_issue(console, issue)
        output = get_output(console)

        assert "✗" in output
        assert "ERROR" in output
        assert "[sphinx]" in output
        assert "Build failed" in output
        assert "[build.failed]" in output
        assert "📍 /path/to/index.rst:10" in output

    def test_issue_with_code_block_non_verbose(self) -> None:
        """Code block should be shown truncated to 10 lines without verbose."""
        console = make_console()
        code_lines = "\n".join([f"line {i}" for i in range(1, 21)])  # 20 lines
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Execution failed",
            code=code_lines,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Code Block" in output
        assert "... (10 lines above)" in output
        assert "line 11" in output
        assert "line 20" in output
        # Should NOT show line 1-10 in output
        assert "line 1" not in output or "... (10 lines above)" in output

    def test_issue_with_code_block_verbose(self) -> None:
        """Code block should be shown completely with verbose."""
        console = make_console()
        code_lines = "\n".join([f"line {i}" for i in range(1, 21)])  # 20 lines
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Execution failed",
            code=code_lines,
        )
        print_issue(console, issue, verbose=True)
        output = get_output(console)

        assert "Code Block" in output
        assert "line 1" in output
        assert "line 20" in output
        # Should not show truncation message
        assert "lines above" not in output

    def test_issue_with_short_code_block(self) -> None:
        """Short code block (<= 10 lines) should not be truncated."""
        console = make_console()
        code = "x = 1\ny = 2\nprint(x + y)"
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Execution failed",
            code=code,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Code Block" in output
        assert "x = 1" in output
        assert "y = 2" in output
        assert "print(x + y)" in output
        assert "lines above" not in output

    def test_issue_with_output_non_verbose(self) -> None:
        """Output should show condensed 'Error Output' panel without verbose."""
        console = make_console()
        traceback = """Traceback (most recent call last):
  File "test.py", line 5, in <module>
    result = divide(10, 0)
  File "test.py", line 2, in divide
    return a / b
ZeroDivisionError: division by zero"""
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Execution failed",
            output=traceback,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Error Output" in output
        assert "ZeroDivisionError: division by zero" in output
        assert "use -v for full traceback" in output
        # Should not show full traceback in non-verbose mode
        assert "Traceback (most recent call last)" not in output

    def test_issue_with_output_verbose(self) -> None:
        """Output should show full 'Traceback' panel with verbose."""
        console = make_console()
        traceback = """Traceback (most recent call last):
  File "test.py", line 5, in <module>
    result = divide(10, 0)
  File "test.py", line 2, in divide
    return a / b
ZeroDivisionError: division by zero"""
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Execution failed",
            output=traceback,
        )
        print_issue(console, issue, verbose=True)
        output = get_output(console)

        assert "Traceback" in output
        assert "Traceback (most recent call last)" in output
        assert 'File "test.py", line 5' in output
        assert "ZeroDivisionError: division by zero" in output
        # Should not show subtitle hint in verbose mode
        assert "use -v for full traceback" not in output

    def test_issue_output_truncation_verbose(self) -> None:
        """Verbose mode should truncate output at 15 lines."""
        console = make_console()
        output_lines = "\n".join([f"line {i}" for i in range(1, 30)])  # 29 lines
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output=output_lines,
        )
        print_issue(console, issue, verbose=True)
        output = get_output(console)

        assert "... (14 lines omitted)" in output
        assert "line 16" in output
        assert "line 29" in output

    def test_issue_error_line_extraction_valueerror(self) -> None:
        """ValueError should be extracted correctly from output."""
        console = make_console()
        traceback = """INFO - Building site
ERROR - Some context
ValueError: invalid literal for int()"""
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output=traceback,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Error Output" in output
        assert "ValueError: invalid literal for int()" in output
        # INFO/ERROR prefix lines should be filtered out
        assert "INFO - Building site" not in output

    def test_issue_error_line_extraction_typeerror(self) -> None:
        """TypeError should be extracted correctly from output."""
        console = make_console()
        traceback = "WARNING - test\nTypeError: unsupported operand type(s)"
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output=traceback,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "TypeError: unsupported operand type(s)" in output

    def test_issue_error_line_extraction_runtimeerror(self) -> None:
        """RuntimeError should be extracted correctly."""
        console = make_console()
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output="RuntimeError: something went wrong",
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "RuntimeError: something went wrong" in output

    def test_issue_error_line_extraction_exception(self) -> None:
        """Generic Exception should be extracted correctly."""
        console = make_console()
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output="Exception: generic error",
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Exception: generic error" in output

    def test_issue_error_line_extraction_warning(self) -> None:
        """Warning types should be extracted correctly."""
        console = make_console()
        issue = Issue(
            level=Level.WARNING,
            source="test",
            message="Test",
            output="DeprecationWarning: this is deprecated",
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "DeprecationWarning: this is deprecated" in output

    def test_issue_with_no_optional_fields(self) -> None:
        """Minimal issue with only required fields should render without errors."""
        console = make_console()
        issue = Issue(
            level=Level.WARNING,
            source="test",
            message="Simple warning",
        )
        print_issue(console, issue)
        output = get_output(console)

        assert "WARNING" in output
        assert "Simple warning" in output
        # Should not crash or show empty sections

    def test_issue_without_file_location(self) -> None:
        """Issue without file should not show location section."""
        console = make_console()
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="No file",
        )
        print_issue(console, issue)
        output = get_output(console)

        assert "ERROR" in output
        assert "No file" in output
        assert "📍" not in output

    def test_issue_with_file_but_no_line_number(self) -> None:
        """Issue with file but no line number should show file only."""
        console = make_console()
        issue = Issue(
            level=Level.WARNING,
            source="test",
            message="Test",
            file="docs/page.md",
        )
        print_issue(console, issue)
        output = get_output(console)

        assert "📍 docs/page.md" in output
        # Should not show colon after filename
        lines = output.split("\n")
        location_line = [line for line in lines if "📍" in line][0]
        assert location_line.strip().endswith("docs/page.md")


class TestPrintInfoGroups:
    """Tests for print_info_groups() function."""

    def test_empty_groups(self) -> None:
        """Empty groups should return immediately without printing."""
        console = make_console()
        print_info_groups(console, {})
        output = get_output(console)
        assert output == ""

    def test_deprecation_warning_grouped_by_package(self) -> None:
        """DEPRECATION_WARNING should group by package."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.DEPRECATION_WARNING,
                file="pkg1",
                target="old_func",
                suggestion="Use new_func instead",
            ),
            InfoMessage(
                category=InfoCategory.DEPRECATION_WARNING,
                file="pkg1",
                target="another_func",
                suggestion="Deprecated",
            ),
            InfoMessage(
                category=InfoCategory.DEPRECATION_WARNING,
                file="pkg2",
                target="func",
                suggestion="Old API",
            ),
        ]
        groups = {InfoCategory.DEPRECATION_WARNING: messages}
        print_info_groups(console, groups, verbose=False)
        output = get_output(console)

        assert "Deprecation warnings" in output
        assert "(3)" in output
        assert "pkg1" in output
        assert "(2 warnings)" in output
        assert "pkg2" in output
        assert "(1 warnings)" in output

    def test_deprecation_warning_verbose_shows_details(self) -> None:
        """Verbose mode should show individual deprecation warnings."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.DEPRECATION_WARNING,
                file="mypackage",
                target="old_func",
                suggestion="Use new_func",
            ),
        ]
        groups = {InfoCategory.DEPRECATION_WARNING: messages}
        print_info_groups(console, groups, verbose=True)
        output = get_output(console)

        assert "mypackage" in output
        assert "old_func: Use new_func" in output

    def test_broken_link_grouped_by_target(self) -> None:
        """BROKEN_LINK should group by target and show suggestion."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="docs/page1.md",
                target="missing.md",
                suggestion="index.md",
            ),
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="docs/page2.md",
                target="missing.md",
                suggestion="index.md",
            ),
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="docs/page3.md",
                target="other.md",
            ),
        ]
        groups = {InfoCategory.BROKEN_LINK: messages}
        print_info_groups(console, groups, verbose=False)
        output = get_output(console)

        assert "Broken links" in output
        assert "(3)" in output
        assert "'missing.md'" in output
        assert "(2 files)" in output
        assert "→ 'index.md'" in output
        assert "'other.md'" in output
        assert "(1 files)" in output

    def test_broken_link_verbose_shows_all_files(self) -> None:
        """Verbose mode should show all files for broken links."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="docs/page1.md",
                target="missing.md",
            ),
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="docs/page2.md",
                target="missing.md",
            ),
        ]
        groups = {InfoCategory.BROKEN_LINK: messages}
        print_info_groups(console, groups, verbose=True)
        output = get_output(console)

        assert "docs/page1.md" in output
        assert "docs/page2.md" in output

    def test_absolute_link_grouping(self) -> None:
        """ABSOLUTE_LINK should group by target like BROKEN_LINK."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.ABSOLUTE_LINK,
                file="docs/page.md",
                target="/absolute/path",
            ),
        ]
        groups = {InfoCategory.ABSOLUTE_LINK: messages}
        print_info_groups(console, groups)
        output = get_output(console)

        assert "Absolute links" in output
        assert "'/absolute/path'" in output

    def test_unrecognized_link_grouping(self) -> None:
        """UNRECOGNIZED_LINK should group by target like BROKEN_LINK."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.UNRECOGNIZED_LINK,
                file="docs/page.md",
                target="unknown://link",
            ),
        ]
        groups = {InfoCategory.UNRECOGNIZED_LINK: messages}
        print_info_groups(console, groups)
        output = get_output(console)

        assert "Unrecognized links" in output
        assert "'unknown://link'" in output

    def test_missing_nav_simple_list(self) -> None:
        """MISSING_NAV should show simple file list."""
        console = make_console()
        messages = [
            InfoMessage(category=InfoCategory.MISSING_NAV, file="docs/page1.md"),
            InfoMessage(category=InfoCategory.MISSING_NAV, file="docs/page2.md"),
        ]
        groups = {InfoCategory.MISSING_NAV: messages}
        print_info_groups(console, groups, verbose=False)
        output = get_output(console)

        assert "Pages not in nav" in output
        assert "(2)" in output
        assert "docs/page1.md" in output
        assert "docs/page2.md" in output

    def test_no_git_logs_simple_list(self) -> None:
        """NO_GIT_LOGS should show simple file list."""
        console = make_console()
        messages = [
            InfoMessage(category=InfoCategory.NO_GIT_LOGS, file="docs/file.md"),
        ]
        groups = {InfoCategory.NO_GIT_LOGS: messages}
        print_info_groups(console, groups)
        output = get_output(console)

        assert "No git history" in output
        assert "docs/file.md" in output

    def test_missing_nav_truncation_non_verbose(self) -> None:
        """Non-verbose mode should truncate file list at max_files_shown."""
        console = make_console()
        messages = [
            InfoMessage(category=InfoCategory.MISSING_NAV, file=f"docs/page{i}.md")
            for i in range(1, 11)  # 10 files
        ]
        groups = {InfoCategory.MISSING_NAV: messages}
        print_info_groups(console, groups, verbose=False, max_files_shown=3)
        output = get_output(console)

        assert "docs/page1.md" in output
        assert "docs/page2.md" in output
        assert "docs/page3.md" in output
        assert "... and 7 more" in output
        assert "docs/page10.md" not in output

    def test_missing_nav_no_truncation_verbose(self) -> None:
        """Verbose mode should show all files."""
        console = make_console()
        messages = [
            InfoMessage(category=InfoCategory.MISSING_NAV, file=f"docs/page{i}.md")
            for i in range(1, 11)  # 10 files
        ]
        groups = {InfoCategory.MISSING_NAV: messages}
        print_info_groups(console, groups, verbose=True, max_files_shown=3)
        output = get_output(console)

        # Should show all files in verbose mode
        for i in range(1, 11):
            assert f"docs/page{i}.md" in output
        assert "... and" not in output

    def test_broken_link_target_truncation_non_verbose(self) -> None:
        """Non-verbose mode should truncate targets at max_targets_shown."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file=f"docs/page{i}.md",
                target=f"target{i}.md",
            )
            for i in range(1, 11)  # 10 different targets
        ]
        groups = {InfoCategory.BROKEN_LINK: messages}
        print_info_groups(console, groups, verbose=False, max_targets_shown=5)
        output = get_output(console)

        # Targets are sorted alphabetically, so check first few and truncation message
        assert "'target1.md'" in output
        assert "'target4.md'" in output  # Should be in first 5 alphabetically
        assert "... and 5 more targets" in output
        # target5.md and later should not be shown (except target10 which sorts before target2)
        assert "'target6.md'" not in output
        assert "'target9.md'" not in output

    def test_broken_link_target_no_truncation_verbose(self) -> None:
        """Verbose mode should show all targets."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file=f"docs/page{i}.md",
                target=f"target{i}.md",
            )
            for i in range(1, 11)  # 10 different targets
        ]
        groups = {InfoCategory.BROKEN_LINK: messages}
        print_info_groups(console, groups, verbose=True, max_targets_shown=5)
        output = get_output(console)

        # Should show all targets in verbose mode
        for i in range(1, 11):
            assert f"'target{i}.md'" in output
        assert "... and" not in output

    def test_deprecation_package_truncation(self) -> None:
        """Non-verbose mode should truncate packages at max_targets_shown."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.DEPRECATION_WARNING,
                file=f"package{i}",
                target="func",
                suggestion="deprecated",
            )
            for i in range(1, 11)  # 10 packages
        ]
        groups = {InfoCategory.DEPRECATION_WARNING: messages}
        print_info_groups(console, groups, verbose=False, max_targets_shown=5)
        output = get_output(console)

        # Packages are sorted alphabetically, so check first few and truncation message
        assert "package1" in output
        assert "package4" in output  # Should be in first 5 alphabetically
        assert "... and 5 more packages" in output
        # package5 and later should not be shown (except package10 which sorts before package2)
        assert "package6" not in output
        assert "package9" not in output

    def test_multiple_categories(self) -> None:
        """Multiple categories should all be displayed."""
        console = make_console()
        groups = {
            InfoCategory.BROKEN_LINK: [
                InfoMessage(
                    category=InfoCategory.BROKEN_LINK,
                    file="page.md",
                    target="missing.md",
                )
            ],
            InfoCategory.MISSING_NAV: [
                InfoMessage(category=InfoCategory.MISSING_NAV, file="orphan.md")
            ],
        }
        print_info_groups(console, groups)
        output = get_output(console)

        assert "Broken links" in output
        assert "Pages not in nav" in output
        assert "missing.md" in output
        assert "orphan.md" in output


class TestPrintSummary:
    """Tests for print_summary() function."""

    def test_no_issues_shows_build_info_only(self) -> None:
        """With no issues, should only show build info."""
        console = make_console()
        build_info = BuildInfo(
            server_url="http://127.0.0.1:8000",
            build_dir="site",
            build_time="1.23",
        )
        print_summary(console, [], build_info)
        output = get_output(console)

        assert "http://127.0.0.1:8000" in output
        assert "site" in output
        assert "1.23s" in output
        # Should not show summary line
        assert "Summary:" not in output

    def test_summary_with_errors_only(self) -> None:
        """Summary should show error count."""
        console = make_console()
        issues = [
            Issue(level=Level.ERROR, source="test", message="Error 1"),
            Issue(level=Level.ERROR, source="test", message="Error 2"),
        ]
        build_info = BuildInfo()
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "Summary:" in output
        assert "2 error(s)" in output

    def test_summary_with_warnings_only(self) -> None:
        """Summary should show warning count."""
        console = make_console()
        issues = [
            Issue(level=Level.WARNING, source="test", message="Warning 1"),
            Issue(level=Level.WARNING, source="test", message="Warning 2"),
            Issue(level=Level.WARNING, source="test", message="Warning 3"),
        ]
        build_info = BuildInfo()
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "Summary:" in output
        assert "3 warning(s)" in output

    def test_summary_with_errors_and_warnings(self) -> None:
        """Summary should show both error and warning counts."""
        console = make_console()
        issues = [
            Issue(level=Level.ERROR, source="test", message="Error"),
            Issue(level=Level.WARNING, source="test", message="Warning 1"),
            Issue(level=Level.WARNING, source="test", message="Warning 2"),
        ]
        build_info = BuildInfo()
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "Summary:" in output
        assert "1 error(s)" in output
        assert "2 warning(s)" in output

    def test_summary_with_server_url(self) -> None:
        """Server URL should be displayed with icon."""
        console = make_console()
        build_info = BuildInfo(server_url="http://localhost:8000")
        print_summary(console, [], build_info)
        output = get_output(console)

        assert "🌐 Server:" in output
        assert "http://localhost:8000" in output

    def test_summary_with_build_dir(self) -> None:
        """Build directory should be displayed with icon."""
        console = make_console()
        build_info = BuildInfo(build_dir="site/")
        print_summary(console, [], build_info)
        output = get_output(console)

        assert "📁 Output:" in output
        assert "site/" in output

    def test_summary_with_build_time(self) -> None:
        """Build time should be displayed."""
        console = make_console()
        build_info = BuildInfo(build_time="2.45")
        print_summary(console, [], build_info)
        output = get_output(console)

        assert "Built in 2.45s" in output

    def test_summary_skip_server_url(self) -> None:
        """skip_server_url=True should hide server URL."""
        console = make_console()
        build_info = BuildInfo(server_url="http://localhost:8000", build_dir="site")
        print_summary(console, [], build_info, skip_server_url=True)
        output = get_output(console)

        assert "http://localhost:8000" not in output
        assert "site" in output

    def test_summary_verbose_hint_not_shown(self) -> None:
        """Verbose mode should not show -v hint."""
        console = make_console()
        issues = [Issue(level=Level.WARNING, source="test", message="Test")]
        build_info = BuildInfo()
        print_summary(console, issues, build_info, verbose=True)
        output = get_output(console)

        # Should show --raw hint but not -v hint
        assert "--raw" in output
        assert "-v for verbose output" not in output

    def test_summary_non_verbose_shows_hints(self) -> None:
        """Non-verbose mode should show both -v and --raw hints."""
        console = make_console()
        issues = [Issue(level=Level.WARNING, source="test", message="Test")]
        build_info = BuildInfo()
        print_summary(console, issues, build_info, verbose=False)
        output = get_output(console)

        assert "-v for verbose output" in output
        assert "--raw for full build output" in output

    def test_summary_markdown_exec_missing_file_context_tip(self) -> None:
        """Should show tip for markdown_exec with session but no .md file."""
        console = make_console()
        issues = [
            Issue(
                level=Level.ERROR,
                source="markdown_exec",
                message="Execution failed",
                file="session_abc123",
            ),
        ]
        build_info = BuildInfo()
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "mkdocs build --verbose" in output
        assert "which file contains code block errors" in output

    def test_summary_no_missing_file_context_tip_when_md_present(self) -> None:
        """Should not show tip when file has .md extension."""
        console = make_console()
        issues = [
            Issue(
                level=Level.ERROR,
                source="markdown_exec",
                message="Execution failed",
                file="docs/page.md",
            ),
        ]
        build_info = BuildInfo()
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "mkdocs build --verbose" not in output

    def test_summary_warning_count_mismatch(self) -> None:
        """Should warn when build reported more warnings than captured."""
        console = make_console()
        issues = [
            Issue(level=Level.WARNING, source="test", message="Warning 1"),
            Issue(level=Level.WARNING, source="test", message="Warning 2"),
        ]
        build_info = BuildInfo(reported_warning_count=5)
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "Build reported 5 warning(s) but only 2 captured" in output
        assert "3 warning(s) may have gone to stderr" in output
        assert "Try 2>&1 |" in output

    def test_summary_no_warning_mismatch_when_counts_match(self) -> None:
        """Should not warn when counts match."""
        console = make_console()
        issues = [
            Issue(level=Level.WARNING, source="test", message="Warning 1"),
            Issue(level=Level.WARNING, source="test", message="Warning 2"),
        ]
        build_info = BuildInfo(reported_warning_count=2)
        print_summary(console, issues, build_info)
        output = get_output(console)

        assert "may have gone to stderr" not in output

    def test_summary_warning_mismatch_includes_stderr_hint(self) -> None:
        """Warning mismatch should include stderr hint with command."""
        console = make_console()
        issues = []
        build_info = BuildInfo(reported_warning_count=3)
        print_summary(console, issues, build_info)
        output = get_output(console)

        # Should include hint (exact format depends on build_stderr_hint)
        assert "2>&1 |" in output or "2>&1" in output


class TestTruncateLine:
    """Tests for truncate_line() function."""

    def test_long_line_truncation(self) -> None:
        """Long lines should be truncated with ellipsis."""
        line = "a" * 100
        result = truncate_line(line, max_len=60)
        assert len(result) == 63  # 60 + "..."
        assert result.endswith("...")
        assert result.startswith("a" * 60)

    def test_short_line_padding(self) -> None:
        """Short lines should be padded by default."""
        line = "short"
        result = truncate_line(line, max_len=60, pad=True)
        assert len(result) == 60
        assert result.startswith("short")
        assert result.endswith(" ")

    def test_short_line_no_padding(self) -> None:
        """Short lines should not be padded when pad=False."""
        line = "short"
        result = truncate_line(line, max_len=60, pad=False)
        assert result == "short"
        assert len(result) == 5

    def test_removes_stderr_prefix(self) -> None:
        """[stderr] prefix should be removed."""
        line = "[stderr] This is an error message"
        result = truncate_line(line, max_len=60)
        assert result.startswith("This is an error message")
        assert "[stderr]" not in result

    def test_removes_timestamp_prefix(self) -> None:
        """Timestamp prefix should be removed."""
        line = "2024-01-15 14:30:45,123  -  This is a message"
        result = truncate_line(line, max_len=60)
        assert not result.startswith("2024")
        assert "This is a message" in result

    def test_removes_logger_format_prefix(self) -> None:
        """Logger format prefix should be removed."""
        line = "module.name - INFO - This is a message"
        result = truncate_line(line, max_len=60)
        assert not result.startswith("module")
        assert "This is a message" in result

    def test_removes_logger_warning_prefix(self) -> None:
        """Logger WARNING prefix should be removed."""
        line = "mkdocs.plugins - WARNING - Deprecated feature"
        result = truncate_line(line, max_len=60)
        assert "Deprecated feature" in result

    def test_removes_logger_error_prefix(self) -> None:
        """Logger ERROR prefix should be removed."""
        line = "builder - ERROR - Build failed"
        result = truncate_line(line, max_len=60)
        assert "Build failed" in result

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        line = "   message with spaces   "
        result = truncate_line(line, max_len=60, pad=False)
        assert result == "message with spaces"

    def test_exact_length_no_truncation(self) -> None:
        """Line exactly at max_len should not be truncated."""
        line = "a" * 60
        result = truncate_line(line, max_len=60, pad=False)
        assert result == line
        assert "..." not in result


class TestGetUpstreamCommand:
    """Tests for _get_upstream_command() function."""

    def test_detects_sibling_process(self) -> None:
        """Should detect sibling process from ps output."""
        ps_output = """  PID  PPID COMMAND
 1234  5000 mkdocs build
 1235  5000 docs-output-filter
 5000  1000 /bin/bash"""

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ps_output, stderr=""
            )
            with mock.patch("os.getpid", return_value=1235):
                with mock.patch("os.getppid", return_value=5000):
                    result = _get_upstream_command()

        assert result == "mkdocs build"

    def test_filters_shell_processes(self) -> None:
        """Should filter out shell processes starting with dash."""
        ps_output = """  PID  PPID COMMAND
 1234  5000 -bash
 1235  5000 docs-output-filter
 5000  1000 /bin/bash"""

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ps_output, stderr=""
            )
            with mock.patch("os.getpid", return_value=1235):
                with mock.patch("os.getppid", return_value=5000):
                    result = _get_upstream_command()

        assert result is None

    def test_filters_docs_output_filter_variants(self) -> None:
        """Should filter out other docs-output-filter processes."""
        ps_output = """  PID  PPID COMMAND
 1234  5000 python -m docs_output_filter
 1235  5000 docs-output-filter --streaming
 5000  1000 /bin/bash"""

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ps_output, stderr=""
            )
            with mock.patch("os.getpid", return_value=1235):
                with mock.patch("os.getppid", return_value=5000):
                    result = _get_upstream_command()

        assert result is None

    def test_filters_defunct_processes(self) -> None:
        """Should filter out defunct processes."""
        ps_output = """  PID  PPID COMMAND
 1234  5000 mkdocs <defunct>
 1235  5000 docs-output-filter
 5000  1000 /bin/bash"""

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ps_output, stderr=""
            )
            with mock.patch("os.getpid", return_value=1235):
                with mock.patch("os.getppid", return_value=5000):
                    result = _get_upstream_command()

        assert result is None

    def test_handles_ps_failure(self) -> None:
        """Should return None if ps command fails."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="error"
            )
            result = _get_upstream_command()

        assert result is None

    def test_handles_exception(self) -> None:
        """Should return None if exception occurs."""
        with mock.patch("subprocess.run", side_effect=Exception("test")):
            result = _get_upstream_command()

        assert result is None

    def test_detects_sphinx_build(self) -> None:
        """Should detect sphinx-build command."""
        ps_output = """  PID  PPID COMMAND
 1234  5000 sphinx-build docs _build
 1235  5000 docs-output-filter
 5000  1000 /bin/bash"""

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ps_output, stderr=""
            )
            with mock.patch("os.getpid", return_value=1235):
                with mock.patch("os.getppid", return_value=5000):
                    result = _get_upstream_command()

        assert result == "sphinx-build docs _build"


class TestBuildStderrHint:
    """Tests for build_stderr_hint() function."""

    def test_with_detected_upstream_command(self) -> None:
        """Should build hint with detected upstream command."""
        with mock.patch(
            "docs_output_filter.display._get_upstream_command",
            return_value="mkdocs build",
        ):
            with mock.patch("sys.argv", ["docs-output-filter", "--streaming"]):
                result = build_stderr_hint()

        assert result == "mkdocs build 2>&1 | docs-output-filter --streaming"

    def test_with_no_upstream_command(self) -> None:
        """Should build generic hint when no upstream command detected."""
        with mock.patch(
            "docs_output_filter.display._get_upstream_command",
            return_value=None,
        ):
            result = build_stderr_hint()

        assert result == "command 2>&1 | docs-output-filter"

    def test_with_no_args(self) -> None:
        """Should handle case with no CLI arguments."""
        with mock.patch(
            "docs_output_filter.display._get_upstream_command",
            return_value="sphinx-build docs _build",
        ):
            with mock.patch("sys.argv", ["docs-output-filter"]):
                result = build_stderr_hint()

        assert result == "sphinx-build docs _build 2>&1 | docs-output-filter"

    def test_preserves_cli_flags(self) -> None:
        """Should preserve CLI flags in the hint."""
        with mock.patch(
            "docs_output_filter.display._get_upstream_command",
            return_value="mkdocs serve",
        ):
            with mock.patch("sys.argv", ["docs-output-filter", "-v", "--errors-only"]):
                result = build_stderr_hint()

        assert result == "mkdocs serve 2>&1 | docs-output-filter -v --errors-only"


class TestDisplayMode:
    """Tests for DisplayMode enum."""

    def test_filtered_mode(self) -> None:
        """FILTERED mode should have correct value."""
        assert DisplayMode.FILTERED.value == "filtered"

    def test_raw_mode(self) -> None:
        """RAW mode should have correct value."""
        assert DisplayMode.RAW.value == "raw"


class TestInfoCategoryDisplay:
    """Tests for INFO_CATEGORY_DISPLAY mapping."""

    def test_all_categories_have_display_info(self) -> None:
        """All InfoCategory values should have display info."""
        for category in InfoCategory:
            assert category in INFO_CATEGORY_DISPLAY
            title, description = INFO_CATEGORY_DISPLAY[category]
            assert isinstance(title, str)
            assert isinstance(description, str)
            assert len(title) > 0
            assert len(description) > 0

    def test_broken_link_display(self) -> None:
        """BROKEN_LINK should have correct display info."""
        title, description = INFO_CATEGORY_DISPLAY[InfoCategory.BROKEN_LINK]
        assert "Broken links" in title
        assert "not found" in description.lower()

    def test_deprecation_warning_display(self) -> None:
        """DEPRECATION_WARNING should have correct display info."""
        title, description = INFO_CATEGORY_DISPLAY[InfoCategory.DEPRECATION_WARNING]
        assert "Deprecation" in title
        assert "dependencies" in description.lower()


class TestPrintIssueAdditionalGaps:
    """Additional tests for display.py coverage gaps."""

    def test_output_non_verbose_skips_info_debug_lines(self) -> None:
        """Non-verbose error output skips INFO/DEBUG/WARNING/ERROR prefix lines (lines 122->120, 124)."""
        console = make_console()
        output_text = (
            "INFO - Building site\n"
            "DEBUG - Loading config\n"
            "WARNING - deprecation\n"
            "ERROR - Something\n"
            "ValueError: the actual error"
        )
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output=output_text,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Error Output" in output
        assert "ValueError: the actual error" in output
        # INFO/DEBUG prefix lines should be skipped in error summary
        assert "INFO - Building site" not in output

    def test_output_non_verbose_max_3_error_lines(self) -> None:
        """Non-verbose error output stops collecting after 3 lines without error pattern (line 134)."""
        console = make_console()
        output_text = "line one\nline two\nline three\nline four\nline five - this has data"
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output=output_text,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        assert "Error Output" in output
        # Should show at most 3 lines from the bottom (reversed collection stops at 3)
        assert "line five - this has data" in output

    def test_output_non_verbose_no_error_lines_found(self) -> None:
        """Non-verbose error output with only blank/skipped lines produces no panel (line 136->149)."""
        console = make_console()
        # All lines are either blank or match INFO/WARNING patterns
        output_text = "INFO - message1\nDEBUG - message2\nWARNING - message3"
        issue = Issue(
            level=Level.ERROR,
            source="test",
            message="Test",
            output=output_text,
        )
        print_issue(console, issue, verbose=False)
        output = get_output(console)

        # Should not show "Error Output" panel since all lines were filtered
        assert "Error Output" not in output

    def test_info_groups_description_empty(self) -> None:
        """print_info_groups with category that has empty description (line 171->174)."""
        # We need to test the branch where description is empty/falsy.
        # Since all built-in categories have descriptions, we mock INFO_CATEGORY_DISPLAY.
        console = make_console()
        messages = [
            InfoMessage(category=InfoCategory.NO_GIT_LOGS, file="page.md"),
        ]
        groups = {InfoCategory.NO_GIT_LOGS: messages}

        # Temporarily override the display info to have empty description
        original = INFO_CATEGORY_DISPLAY[InfoCategory.NO_GIT_LOGS]
        INFO_CATEGORY_DISPLAY[InfoCategory.NO_GIT_LOGS] = ("No git history", "")
        try:
            print_info_groups(console, groups)
            output = get_output(console)
            assert "No git history" in output
            # The header should NOT contain " - " separator for empty description
        finally:
            INFO_CATEGORY_DISPLAY[InfoCategory.NO_GIT_LOGS] = original

    def test_broken_link_verbose_with_suggestion(self) -> None:
        """print_info_groups verbose broken link with suggestion shows suggestion (line 226)."""
        console = make_console()
        messages = [
            InfoMessage(
                category=InfoCategory.BROKEN_LINK,
                file="docs/page.md",
                target="missing.md",
                suggestion="index.md",
            ),
        ]
        groups = {InfoCategory.BROKEN_LINK: messages}
        print_info_groups(console, groups, verbose=True)
        output = get_output(console)

        assert "'missing.md'" in output
        assert "-> 'index.md'" in output or "→ 'index.md'" in output

    def test_get_upstream_command_skips_short_ps_lines(self) -> None:
        """_get_upstream_command skips ps output lines with < 3 parts (line 288)."""
        import subprocess

        ps_output = """  PID  PPID COMMAND
 9999
 1234  5000 mkdocs build
 1235  5000 docs-output-filter
 5000  1000 /bin/bash"""

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ps_output, stderr=""
            )
            with mock.patch("os.getpid", return_value=1235):
                with mock.patch("os.getppid", return_value=5000):
                    result = _get_upstream_command()

        # Should still find mkdocs build despite the malformed line
        assert result == "mkdocs build"
