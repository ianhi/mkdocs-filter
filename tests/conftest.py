"""Pytest configuration and fixtures for mkdocs-output-filter tests."""

import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def basic_site_dir(fixtures_dir: Path) -> Path:
    """Return the path to the basic_site fixture."""
    return fixtures_dir / "basic_site"


@pytest.fixture
def markdown_exec_error_dir(fixtures_dir: Path) -> Path:
    """Return the path to the markdown_exec_error fixture."""
    return fixtures_dir / "markdown_exec_error"


@pytest.fixture
def broken_links_dir(fixtures_dir: Path) -> Path:
    """Return the path to the broken_links fixture."""
    return fixtures_dir / "broken_links"


@pytest.fixture
def multiple_errors_dir(fixtures_dir: Path) -> Path:
    """Return the path to the multiple_errors fixture."""
    return fixtures_dir / "multiple_errors"


def run_mkdocs_build(site_dir: Path, verbose: bool = False) -> str:
    """Run mkdocs build in the given directory and return stdout+stderr."""
    cmd = ["mkdocs", "build", "--clean"]
    if verbose:
        cmd.append("--verbose")
    result = subprocess.run(
        cmd,
        cwd=site_dir,
        capture_output=True,
        text=True,
    )
    # Combine stdout and stderr (mkdocs outputs to both)
    return result.stdout + result.stderr


def run_mkdocs_filter(input_text: str, *args: str) -> tuple[str, int]:
    """Run mkdocs-output-filter with the given input and return (output, exit_code)."""
    cmd = ["python", "-m", "mkdocs_filter", "--no-progress", "--no-color", *args]
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr, result.returncode


@pytest.fixture
def run_build():
    """Fixture that provides a function to run mkdocs build."""
    return run_mkdocs_build


@pytest.fixture
def run_filter():
    """Fixture that provides a function to run mkdocs-output-filter."""
    return run_mkdocs_filter
