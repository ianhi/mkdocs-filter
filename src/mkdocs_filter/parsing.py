"""Parsing functions for mkdocs output.

This module contains all parsing logic used by both the CLI and MCP server.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Level(Enum):
    """Log level for issues."""

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass
class Issue:
    """A warning or error from mkdocs output."""

    level: Level
    source: str
    message: str
    file: str | None = None
    code: str | None = None
    output: str | None = None


@dataclass
class BuildInfo:
    """Information extracted from the build output."""

    server_url: str | None = None
    build_dir: str | None = None
    build_time: str | None = None


@dataclass
class StreamingState:
    """State for streaming processor."""

    buffer: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    build_info: BuildInfo = field(default_factory=BuildInfo)
    seen_issues: set[tuple[Level, str]] = field(default_factory=set)
    in_markdown_exec_block: bool = False


class ChunkBoundary(Enum):
    """Types of chunk boundaries in mkdocs output."""

    BUILD_COMPLETE = "build_complete"  # "Documentation built in X seconds"
    SERVER_STARTED = "server_started"  # "Serving on http://..."
    REBUILD_STARTED = "rebuild_started"  # "Detected file changes" or timestamp restart
    ERROR_BLOCK_END = "error_block_end"  # End of multi-line error block
    NONE = "none"


def detect_chunk_boundary(line: str, prev_line: str | None = None) -> ChunkBoundary:
    """Detect if a line marks a chunk boundary."""
    stripped = line.strip()

    # Build completion
    if re.search(r"Documentation built in [\d.]+ seconds", line):
        return ChunkBoundary.BUILD_COMPLETE

    # Server started
    if re.search(r"Serving on https?://", line):
        return ChunkBoundary.SERVER_STARTED

    # Rebuild detection - file changes detected
    if "Detected file changes" in line or "Reloading docs" in line:
        return ChunkBoundary.REBUILD_STARTED

    # Rebuild detection - timestamp with "Building documentation"
    if re.match(r"^\d{4}-\d{2}-\d{2}", stripped) and "Building documentation" in line:
        return ChunkBoundary.REBUILD_STARTED

    # If we see a new INFO/WARNING/ERROR after blank lines following error content
    if prev_line is not None and not prev_line.strip():
        if re.match(r"^(INFO|WARNING|ERROR)\s*-", stripped):
            return ChunkBoundary.ERROR_BLOCK_END
        if re.match(r"^\d{4}-\d{2}-\d{2}.*?(INFO|WARNING|ERROR)", stripped):
            return ChunkBoundary.ERROR_BLOCK_END

    return ChunkBoundary.NONE


def is_in_multiline_block(lines: list[str]) -> bool:
    """Check if we're currently in a multi-line block (like markdown_exec output)."""
    if not lines:
        return False

    # Look for unclosed markdown_exec blocks
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if "markdown_exec" in line and ("WARNING" in line or "ERROR" in line):
            # Found start of markdown_exec block - check if it's closed
            # A block is closed when we see a new INFO/WARNING/ERROR line
            for j in range(i + 1, len(lines)):
                check_line = lines[j].strip()
                if (
                    check_line
                    and not check_line.startswith(" ")
                    and not check_line.startswith("\t")
                ):
                    if re.match(r"^(INFO|WARNING|ERROR)\s*-", check_line):
                        return False  # Block is closed
                    if re.match(r"^\d{4}-\d{2}-\d{2}.*?(INFO|WARNING|ERROR)", check_line):
                        return False  # Block is closed
            return True  # Block still open
    return False


def extract_build_info(lines: list[str]) -> BuildInfo:
    """Extract server URL, build directory, and timing from mkdocs output."""
    info = BuildInfo()
    for line in lines:
        # Server URL: "Serving on http://127.0.0.1:8000/"
        if match := re.search(r"Serving on (https?://\S+)", line):
            info.server_url = match.group(1)
        # Build time: "Documentation built in 78.99 seconds"
        if match := re.search(r"Documentation built in ([\d.]+) seconds", line):
            info.build_time = match.group(1)
        # Build directory from site_dir config or default
        if match := re.search(r"Building documentation to directory: (.+)", line):
            info.build_dir = match.group(1).strip()
    return info


def parse_mkdocs_output(lines: list[str]) -> list[Issue]:
    """Parse mkdocs output and extract warnings/errors."""
    issues: list[Issue] = []
    i = 0
    # Track lines that are part of markdown_exec output to skip them
    skip_until = -1

    while i < len(lines):
        if i < skip_until:
            i += 1
            continue

        line = lines[i]

        # Match WARNING or ERROR lines
        if "WARNING" in line or "ERROR" in line:
            # Determine level
            level = Level.ERROR if "ERROR" in line else Level.WARNING

            # Check if this is a markdown_exec error with code block
            if "markdown_exec" in line:
                issue, end_idx = parse_markdown_exec_issue(lines, i, level)
                if issue:
                    issues.append(issue)
                    skip_until = end_idx
                    i = end_idx
                    continue

            # Skip lines that look like they're part of a traceback
            stripped = line.strip()
            if stripped.startswith("raise ") or stripped.startswith("File "):
                i += 1
                continue

            # Regular warning/error
            message = line
            message = re.sub(r"^\[stderr\]\s*", "", message)
            message = re.sub(r"^\d{4}-\d{2}-\d{2}.*?-\s*", "", message)
            message = re.sub(r"^(WARNING|ERROR)\s*-?\s*", "", message)

            if message.strip():
                # Try to extract file path from message
                file_path = None
                if file_match := re.search(r"'([^']+\.md)'", message):
                    file_path = file_match.group(1)
                elif file_match := re.search(r'"([^"]+\.md)"', message):
                    file_path = file_match.group(1)

                issues.append(
                    Issue(level=level, source="mkdocs", message=message.strip(), file=file_path)
                )

        i += 1

    return issues


def parse_markdown_exec_issue(
    lines: list[str], start: int, level: Level
) -> tuple[Issue | None, int]:
    """Parse a markdown_exec warning/error block. Returns (issue, end_index)."""
    # Look backwards to find which file was being processed
    file_path = None
    for j in range(start - 1, max(-1, start - 50), -1):
        prev_line = lines[j]
        # Look for verbose mode "Reading: file.md" message (most reliable)
        if match := re.search(r"DEBUG\s*-\s*Reading:\s*(\S+\.md)", prev_line):
            file_path = match.group(1)
            break
        # Look for breadcrumb that mentions the file
        if match := re.search(r"Generated breadcrumb string:.*\[([^\]]+)\]\(/([^)]+)\)", prev_line):
            potential_file = match.group(2) + ".md"
            file_path = potential_file
            break
        # Or Doc file message
        if match := re.search(r"Doc file '([^']+\.md)'", prev_line):
            file_path = match.group(1)
            break

    # Collect the code block and output sections
    code_lines: list[str] = []
    output_lines: list[str] = []
    in_code = False
    in_output = False
    session_info = None
    line_number = None

    i = start + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect section markers
        if stripped == "Code block is:":
            in_code = True
            in_output = False
            i += 1
            continue
        if stripped == "Output is:":
            in_code = False
            in_output = True
            i += 1
            continue

        # Stop conditions: any log line (INFO/DEBUG/WARNING/ERROR)
        if re.match(r"^(INFO|DEBUG|WARNING|ERROR)\s*-", stripped):
            break
        if re.match(r"^\d{4}-\d{2}-\d{2}", stripped):
            break
        if re.match(r"^\[stderr\]", stripped):
            break

        # Collect content
        if in_code and stripped:
            code_lines.append(line.rstrip())
        elif in_output and stripped:
            output_lines.append(line.rstrip())
            # Extract session and line info from traceback
            if match := re.search(
                r'File "<code block: session ([^;]+); n(\d+)>", line (\d+)', stripped
            ):
                session_info = match.group(1)
                line_number = match.group(3)

        i += 1

    # Find the actual error message
    error_msg: str = "Code execution failed"
    for line in reversed(output_lines):
        line = line.strip()
        if line and ("Error:" in line or "Exception:" in line) and not line.startswith("File "):
            error_msg = line
            break

    # Build location string
    location_parts: list[str] = []
    if file_path:
        location_parts.append(file_path)
    if session_info:
        location_parts.append(f"session '{session_info}'")
    if line_number:
        location_parts.append(f"line {line_number}")

    return (
        Issue(
            level=level,
            source="markdown_exec",
            message=error_msg,
            file=" → ".join(location_parts) if location_parts else None,
            code="\n".join(code_lines) if code_lines else None,
            output="\n".join(output_lines) if output_lines else None,
        ),
        i,
    )


def dedent_code(code: str) -> str:
    """Remove consistent leading whitespace from code."""
    lines = code.split("\n")
    if not lines:
        return code

    min_indent = float("inf")
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            min_indent = min(min_indent, indent)

    if min_indent < float("inf"):
        return "\n".join(
            line[int(min_indent) :] if len(line) > min_indent else line for line in lines
        )
    return code
