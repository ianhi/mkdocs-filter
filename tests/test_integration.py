"""Integration tests that run mkdocs builds against actual fixtures."""

from pathlib import Path

from tests.conftest import run_mkdocs_build, run_mkdocs_filter


class TestBasicSite:
    """Tests for basic site with no errors."""

    def test_no_warnings_reported(self, basic_site_dir: Path) -> None:
        """Basic site should have no warnings or errors."""
        mkdocs_output = run_mkdocs_build(basic_site_dir)
        filtered_output, exit_code = run_mkdocs_filter(mkdocs_output)

        assert "No warnings or errors" in filtered_output
        assert exit_code == 0

    def test_shows_build_info(self, basic_site_dir: Path) -> None:
        """Should show build directory and time."""
        mkdocs_output = run_mkdocs_build(basic_site_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "Output:" in filtered_output
        assert "Built in" in filtered_output


class TestMarkdownExecError:
    """Tests for markdown_exec code execution errors."""

    def test_detects_error(self, markdown_exec_error_dir: Path) -> None:
        """Should detect markdown_exec errors."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir)
        filtered_output, exit_code = run_mkdocs_filter(mkdocs_output)

        assert "WARNING" in filtered_output
        assert "markdown_exec" in filtered_output
        assert exit_code == 0  # Warnings don't cause non-zero exit

    def test_shows_error_message(self, markdown_exec_error_dir: Path) -> None:
        """Should show the error message from the code execution."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "ValueError" in filtered_output or "INTENTIONAL TEST ERROR" in filtered_output

    def test_shows_code_block(self, markdown_exec_error_dir: Path) -> None:
        """Should show the code block that caused the error."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        # Code block should contain the raise statement
        assert "raise" in filtered_output.lower()

    def test_shows_session_and_line(self, markdown_exec_error_dir: Path) -> None:
        """Should show session name and line number."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "session" in filtered_output
        assert "line" in filtered_output

    def test_verbose_shows_file_path(self, markdown_exec_error_dir: Path) -> None:
        """Verbose mode should show the source file path."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir, verbose=True)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "index.md" in filtered_output


class TestBrokenLinks:
    """Tests for broken link detection."""

    def test_detects_broken_links(self, broken_links_dir: Path) -> None:
        """Should detect broken links."""
        mkdocs_output = run_mkdocs_build(broken_links_dir)
        filtered_output, exit_code = run_mkdocs_filter(mkdocs_output)

        assert "WARNING" in filtered_output
        assert "nonexistent.md" in filtered_output or "missing" in filtered_output.lower()

    def test_shows_source_file(self, broken_links_dir: Path) -> None:
        """Should show which file contains the broken link."""
        mkdocs_output = run_mkdocs_build(broken_links_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "index.md" in filtered_output


class TestMultipleErrors:
    """Tests for sites with multiple error types."""

    def test_detects_all_error_types(self, multiple_errors_dir: Path) -> None:
        """Should detect all different types of errors."""
        mkdocs_output = run_mkdocs_build(multiple_errors_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        # Should have multiple warnings
        assert "5 warning" in filtered_output or "Summary:" in filtered_output

    def test_detects_nav_reference_error(self, multiple_errors_dir: Path) -> None:
        """Should detect missing file in nav configuration."""
        mkdocs_output = run_mkdocs_build(multiple_errors_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "nav" in filtered_output.lower()
        assert "does_not_exist.md" in filtered_output

    def test_detects_multiple_markdown_exec_errors(self, multiple_errors_dir: Path) -> None:
        """Should detect multiple markdown_exec errors."""
        mkdocs_output = run_mkdocs_build(multiple_errors_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        # Should show both errors
        assert "RuntimeError" in filtered_output
        assert "NameError" in filtered_output

    def test_detects_broken_link_and_image(self, multiple_errors_dir: Path) -> None:
        """Should detect broken link and missing image."""
        mkdocs_output = run_mkdocs_build(multiple_errors_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output)

        assert "broken_link.md" in filtered_output
        assert "missing_image.png" in filtered_output


class TestFilterOptions:
    """Tests for filter command-line options."""

    def test_errors_only_flag(self, multiple_errors_dir: Path) -> None:
        """--errors-only should show only errors, not warnings."""
        mkdocs_output = run_mkdocs_build(multiple_errors_dir)
        filtered_output, exit_code = run_mkdocs_filter(mkdocs_output, "--errors-only")

        # All issues in multiple_errors are warnings, so should be empty
        assert "No warnings or errors" in filtered_output
        assert exit_code == 0

    def test_verbose_flag(self, markdown_exec_error_dir: Path) -> None:
        """--verbose should show full traceback."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output, "-v")

        # Verbose mode should show the traceback
        assert "Traceback" in filtered_output

    def test_raw_flag(self, markdown_exec_error_dir: Path) -> None:
        """--raw should pass through unfiltered output."""
        mkdocs_output = run_mkdocs_build(markdown_exec_error_dir)
        filtered_output, _ = run_mkdocs_filter(mkdocs_output, "--raw")

        # Raw output should contain INFO lines
        assert "INFO" in filtered_output
        assert "Cleaning site directory" in filtered_output


class TestMkdocsServeRebuild:
    """Tests for mkdocs serve rebuild detection.

    CRITICAL: These tests verify that errors introduced AFTER the initial build
    are properly detected and displayed when using mkdocs serve.

    NOTE: Requires --livereload flag due to Click 8.3.x bug:
    https://github.com/mkdocs/mkdocs/issues/4032
    """

    def test_detects_rebuild_error_with_real_mkdocs_serve(
        self, markdown_exec_error_dir: Path
    ) -> None:
        """CRITICAL: Detects errors from rebuilds triggered by file changes.

        This test:
        1. Starts mkdocs serve with --livereload
        2. Waits for initial build to complete
        3. Modifies a file to trigger rebuild
        4. Verifies BOTH initial and rebuild errors appear in filtered output
        """
        import fcntl
        import os
        import subprocess
        import sys
        import time

        docs_file = markdown_exec_error_dir / "docs" / "index.md"
        original_content = docs_file.read_text()

        try:
            # Start mkdocs serve with livereload (required due to Click 8.3.x bug)
            # See: https://github.com/mkdocs/mkdocs/issues/4032
            mkdocs_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "mkdocs",
                    "serve",
                    "--livereload",  # Required for file watching with Click 8.3.x
                    "--dev-addr",
                    "127.0.0.1:8299",
                ],
                cwd=markdown_exec_error_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Start filter reading from mkdocs
            filter_proc = subprocess.Popen(
                [sys.executable, "-m", "mkdocs_filter", "--streaming", "--no-color"],
                stdin=mkdocs_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Make filter stdout non-blocking
            assert filter_proc.stdout is not None
            fd = filter_proc.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            def read_output() -> str:
                output = ""
                try:
                    while True:
                        chunk = filter_proc.stdout.read(4096)
                        if not chunk:
                            break
                        output += chunk
                except (BlockingIOError, TypeError):
                    pass
                return output

            # Wait for initial build
            time.sleep(4)
            initial_output = read_output()

            # Verify initial error is shown
            assert (
                "ValueError" in initial_output or "INTENTIONAL TEST ERROR" in initial_output
            ), f"Initial build error not shown. Output:\n{initial_output}"

            # Modify file to trigger rebuild (change ValueError to RuntimeError)
            new_content = original_content.replace("ValueError", "RuntimeError")
            docs_file.write_text(new_content)

            # Wait for rebuild (needs more time for build to complete)
            time.sleep(6)
            rebuild_output = read_output()

            # Verify rebuild error is shown (RuntimeError)
            full_output = initial_output + rebuild_output
            assert (
                "RuntimeError" in full_output
            ), f"Rebuild error not detected. Full output:\n{full_output}"

            # Verify file change was detected
            assert (
                "rebuild" in full_output.lower() or "file change" in full_output.lower()
            ), f"File change indicator not shown. Full output:\n{full_output}"

        finally:
            # Cleanup
            mkdocs_proc.terminate()
            filter_proc.terminate()
            mkdocs_proc.wait(timeout=5)
            filter_proc.wait(timeout=5)
            docs_file.write_text(original_content)
