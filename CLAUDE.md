# mkdocs-output-filter Development Guide

## Project Overview

`mkdocs-output-filter` is a CLI tool that filters mkdocs build/serve output to show only warnings and errors with nice formatting. It's designed to be piped after mkdocs commands:

```bash
mkdocs build 2>&1 | mkdocs-output-filter
mkdocs serve 2>&1 | mkdocs-output-filter --streaming
```

## Key Features

- **Streaming mode** for `mkdocs serve` - processes output incrementally, shows errors after each build/rebuild
- **Progress spinner** during build with current activity shown
- **Filtered output** showing only WARNING and ERROR level messages
- **Code block display** for markdown_exec errors with syntax highlighting
- **Error output panel** showing the actual exception (condensed by default, full with `-v`)
- **Location info** including file, session name, and line number
- **Build info** (output dir, server URL, build time)
- **Interactive mode** (`-i`) for toggling between filtered/raw output during serve
- **MCP server** for code agent integration

## Commands

```bash
# Install globally for testing
uv tool install --force -e .

# Run tests
uv run pytest

# Run specific test
uv run pytest tests/test_cli.py -k "streaming" -v

# Linting
uv run ruff check .
uv run ruff format .

# Build package
uv build
```

## Manual Testing

**IMPORTANT:** Due to a [Click 8.3.x bug](https://github.com/mkdocs/mkdocs/issues/4032), you must use `--livereload` flag for file watching to work:

```bash
mkdocs serve --livereload 2>&1 | mkdocs-output-filter --streaming
```

Test with the markdown_exec error fixture:

```bash
# Test streaming mode with mkdocs serve (recommended)
cd tests/fixtures/markdown_exec_error && mkdocs serve --livereload 2>&1 | mkdocs-output-filter --streaming

# Test batch mode with mkdocs build
cd tests/fixtures/markdown_exec_error && mkdocs build 2>&1 | mkdocs-output-filter

# Test verbose mode (shows full traceback)
cd tests/fixtures/markdown_exec_error && mkdocs build 2>&1 | mkdocs-output-filter -v

# Test interactive mode
cd tests/fixtures/markdown_exec_error && mkdocs serve 2>&1 | mkdocs-output-filter -i
```

When testing streaming mode with `mkdocs serve`:
1. The initial build error should appear immediately
2. Edit `docs/index.md` and save to trigger a rebuild
3. The error should appear again after the rebuild completes

## Architecture

### File Structure

```
src/mkdocs_filter/
├── __init__.py      # Main CLI, streaming/batch modes, display logic
├── parsing.py       # Shared parsing logic (Issue, BuildInfo, parsers)
└── mcp_server.py    # MCP server for code agent integration
```

### Key Classes (in parsing.py)

- `Level`: Enum for ERROR/WARNING
- `Issue`: Dataclass holding parsed issue info (level, source, message, file, code, output)
- `BuildInfo`: Dataclass for server URL, build dir, build time
- `StreamingProcessor`: Stateful processor for incremental parsing
- `ChunkBoundary`: Enum for detecting build completion, server start, rebuild

### Key Functions

- `parse_mkdocs_output()`: Main parsing loop for batch mode
- `parse_markdown_exec_issue()`: Handles markdown_exec code execution errors
- `extract_build_info()`: Extracts server URL, build dir, timing
- `detect_chunk_boundary()`: Detects when to display output in streaming mode

### Streaming Mode

Uses `sys.stdin.readline()` (not `for line in sys.stdin`) to avoid potential read-ahead buffering issues. Output is displayed when chunk boundaries are detected:
- `BUILD_COMPLETE`: "Documentation built in X seconds"
- `SERVER_STARTED`: "Serving on http://..."
- `REBUILD_STARTED`: "Detected file changes"

## Test Fixtures

```
tests/fixtures/
├── basic_site/           # Clean site with no errors
├── markdown_exec_error/  # Site with intentional ValueError in code block
├── broken_links/         # Site with broken internal links
└── multiple_errors/      # Site with various error types
```

## CLI Flags

- `--streaming`: Process output incrementally (for mkdocs serve)
- `--batch`: Force batch mode (wait for all input)
- `-i, --interactive`: Toggle between filtered/raw with keyboard
- `-v, --verbose`: Show full tracebacks and file paths
- `--errors-only`: Only show errors, not warnings
- `--no-progress`: Disable spinner
- `--no-color`: Disable colors
- `--raw`: Pass through raw output without filtering

## MCP Server

For code agent integration:

```bash
# Run MCP server (subprocess mode)
mkdocs-output-filter-mcp --project-dir /path/to/project

# Run MCP server (pipe mode)
mkdocs build 2>&1 | mkdocs-output-filter-mcp --pipe
```

Tools provided:
- `get_issues`: Get current warnings/errors
- `get_issue_details`: Get specific issue details
- `rebuild`: Trigger mkdocs build and get new issues

## Notes for Development

- Always test with real mkdocs output using the fixtures
- The spinner uses Rich's Live display - `transient=True` prevents output interference
- Use `--no-progress` flag when debugging to see cleaner output
- Parsing must handle multi-line blocks (markdown_exec errors span many lines)
- Use `mkdocs build --verbose` to get file paths in error output
