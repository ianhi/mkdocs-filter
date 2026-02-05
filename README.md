# mkdocs-output-filter

**Filter mkdocs output to show only what matters: warnings and errors.**

Includes an MCP server for AI code assistant integration (Claude Code, etc.).

## Before & After

<table>
<tr>
<th>❌ Raw mkdocs output (43 lines)</th>
<th>✅ Filtered output (15 lines)</th>
</tr>
<tr>
<td>

```
INFO    -  Building documentation...
INFO    -  Cleaning site directory
INFO    -  Log level set to INFO
INFO    -  Building documentation to directory: /project/site
INFO    -  MERMAID2  - Initialization arguments: {}
INFO    -  Generating index pages...
INFO    -  Reading page 'index.md'
INFO    -  Reading page 'guide/getting-started.md'
INFO    -  Reading page 'guide/configuration.md'
INFO    -  Reading page 'api/reference.md'
INFO    -  Copying static files from theme: material
INFO    -  Copying 'assets/stylesheets/extra.css'
INFO    -  Copying 'assets/javascripts/extra.js'
[git-revision-date-localized-plugin] has no git logs
INFO    -  Executing code blocks with markdown_exec...
WARNING -  markdown_exec: Execution of python
code block exited with errors

Code block is:

  import numpy as np
  data = np.random.rand(10, 10)
  raise ValueError("INTENTIONAL TEST ERROR")

Output is:

  Traceback (most recent call last):
    File "<code block: session test; n1>", line 3
      raise ValueError("INTENTIONAL TEST ERROR")
  ValueError: INTENTIONAL TEST ERROR

WARNING -  [git-revision] Unable to read git logs
INFO    -  Rendering 'index.md'
INFO    -  Rendering 'guide/getting-started.md'
INFO    -  Rendering 'guide/configuration.md'
INFO    -  Rendering 'api/reference.md'
INFO    -  Building search index...
INFO    -  Writing 'sitemap.xml'
INFO    -  Writing 'search/search_index.json'
INFO    -  Documentation built in 12.34 seconds
```

</td>
<td>

```
⚠ WARNING [markdown_exec] ValueError: INTENTIONAL TEST ERROR
   📍 session 'test' → line 3

╭──────────────── Code Block ─────────────────╮
│  1 import numpy as np                       │
│  2 data = np.random.rand(10, 10)            │
│  3 raise ValueError("INTENTIONAL TEST E...")│
╰─────────────────────────────────────────────╯
╭─────────── Error Output ────────────╮
│ ValueError: INTENTIONAL TEST ERROR  │
╰───────── use -v for full traceback ─╯

⚠ WARNING [git-revision] Unable to read git logs

Summary: 2 warning(s)

🌐 Server: http://127.0.0.1:8000/
📁 Output: /project/site
Built in 12.34s
```

</td>
</tr>
</table>

## Installation

```bash
# With uv (recommended)
uv tool install mkdocs-output-filter

# With pip
pip install mkdocs-output-filter
```

## Usage

```bash
# Filter build output
mkdocs build 2>&1 | mkdocs-output-filter

# Filter serve output (streaming mode, updates on file changes)
mkdocs serve --livereload 2>&1 | mkdocs-output-filter

# Process a remote build log (e.g., ReadTheDocs)
mkdocs-output-filter --url https://app.readthedocs.org/projects/myproject/builds/12345/
```

> **Note:** Use `--livereload` with `mkdocs serve` due to a [Click 8.3.x bug](https://github.com/mkdocs/mkdocs/issues/4032).

## Features

| Feature | Description |
|---------|-------------|
| **Filtered output** | Shows WARNING and ERROR messages, hides routine INFO |
| **Code blocks** | Syntax-highlighted code that caused markdown_exec errors |
| **Location info** | File, session name, and line number extraction |
| **Streaming mode** | Real-time output for `mkdocs serve` with rebuild detection |
| **Interactive mode** | Toggle between raw/filtered with keyboard (`-i`) |
| **Remote logs** | Fetch and parse build logs from ReadTheDocs and other CI |
| **MCP server** | API for AI code assistants like Claude Code |

## Options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Show full tracebacks and code blocks |
| `-e, --errors-only` | Hide warnings, show only errors |
| `--no-color` | Disable colored output |
| `--raw` | Pass through unfiltered mkdocs output |
| `-i, --interactive` | Toggle raw/filtered with keyboard |
| `--url URL` | Fetch and process a remote build log |
| `--share-state` | Write state for MCP server integration |

## MCP Server (for AI Assistants)

Enable AI code assistants to access mkdocs build issues:

```bash
# Terminal 1: Run mkdocs with state sharing
mkdocs serve --livereload 2>&1 | mkdocs-output-filter --share-state

# Terminal 2: AI assistant connects via MCP
mkdocs-output-filter --mcp --watch
```

Add to Claude Code's MCP config (`.claude/settings.local.json`):
```json
{
  "mcpServers": {
    "mkdocs-output-filter": {
      "command": "mkdocs-output-filter",
      "args": ["--mcp", "--watch"]
    }
  }
}
```

## Documentation

Full documentation: https://ianhi.github.io/mkdocs-output-filter/

## Development

```bash
git clone https://github.com/ianhi/mkdocs-output-filter
cd mkdocs-output-filter
uv sync
uv run pre-commit install
uv run pytest
```

## License

MIT
