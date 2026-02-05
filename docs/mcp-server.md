# MCP Server

mkdocs-filter includes an MCP (Model Context Protocol) server that allows AI code assistants like Claude Code to programmatically access mkdocs build issues.

## Overview

The MCP server provides tools for:

- **`get_issues`** - Get current warnings and errors from the last build
- **`get_issue_details`** - Get detailed information about a specific issue
- **`rebuild`** - Trigger a new mkdocs build and get updated issues

## Setup

### With Claude Code

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "mkdocs-filter": {
      "command": "mkdocs-filter-mcp",
      "args": ["--project-dir", "/path/to/your/mkdocs/project"]
    }
  }
}
```

Or for a specific project, add to `.claude/settings.local.json` in the project root:

```json
{
  "mcpServers": {
    "mkdocs-filter": {
      "command": "mkdocs-filter-mcp",
      "args": ["--project-dir", "."]
    }
  }
}
```

### Modes

#### Subprocess Mode (Recommended)

The MCP server manages mkdocs internally:

```bash
mkdocs-filter-mcp --project-dir /path/to/project
```

#### Pipe Mode

Receive mkdocs output via stdin (for advanced use cases):

```bash
mkdocs build 2>&1 | mkdocs-filter-mcp --pipe
```

## Tools

### `get_issues`

Get current warnings and errors.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `filter` | `string` | Filter issues: `"all"`, `"errors"`, or `"warnings"` |
| `verbose` | `boolean` | Include full tracebacks |

**Returns:** JSON array of issues

```json
[
  {
    "id": "issue-abc123",
    "level": "WARNING",
    "source": "markdown_exec",
    "message": "ValueError: test error",
    "file": "docs/index.md",
    "session": "test",
    "line": 42,
    "code": "raise ValueError('test')"
  }
]
```

### `get_issue_details`

Get detailed information about a specific issue.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `issue_id` | `string` | The issue ID from `get_issues` |

**Returns:** Full issue object with traceback

### `rebuild`

Trigger a new mkdocs build.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `verbose` | `boolean` | Run mkdocs with verbose flag |

**Returns:** Updated issues list and build info

```json
{
  "issues": [...],
  "build_info": {
    "build_dir": "/path/to/site",
    "build_time": "1.23",
    "success": true
  }
}
```

## Use Cases

### Automated Error Fixing

When working on documentation, AI assistants can:

1. Call `rebuild` to build the docs
2. Call `get_issues` to check for errors
3. Read the relevant file and fix the issue
4. Call `rebuild` again to verify the fix

### CI Integration

Use the MCP server in automated workflows to:

- Get structured issue data (JSON) instead of parsing text
- Track issues across builds
- Generate reports with issue details
