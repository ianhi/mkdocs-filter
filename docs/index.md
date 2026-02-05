# mkdocs-filter

Filter mkdocs build output to show only warnings and errors with nice formatting.

## Why?

When building large MkDocs sites, the output can be verbose and noisy. `mkdocs-filter` filters the output to show only what matters: warnings, errors, and key build information.

**Before** (raw mkdocs output):
```
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /path/to/site
INFO    -  Doc file 'page1.md' contains a link 'image.png', but the target is not found
INFO    -  Doc file 'page2.md' contains a link 'other.md', but the target is not found
WARNING -  markdown_exec: Execution of python code block exited with errors
Code block is:

  x = 1
  y = 2
  raise ValueError("INTENTIONAL ERROR")

Output is:

  Traceback (most recent call last):
    File "<code block: session test; n1>", line 3, in <module>
      raise ValueError("INTENTIONAL ERROR")
  ValueError: INTENTIONAL ERROR

INFO    -  Documentation built in 1.23 seconds
```

**After** (filtered output):
```
⚠ WARNING [markdown_exec] ValueError: INTENTIONAL ERROR
   📍 session 'test' → line 3

╭────────────────── Code Block ──────────────────╮
│   1 x = 1                                      │
│   2 y = 2                                      │
│   3 raise ValueError("INTENTIONAL ERROR")      │
╰────────────────────────────────────────────────╯

────────────────────────────────────────
Summary: 1 warning(s)

Built in 1.23s

Hint: -v for verbose output, --raw for full mkdocs output
```

## Features

- **Progress spinner** - Shows current build activity while processing
- **Filtered output** - Only shows warnings and errors, removes noise
- **Location info** - Shows file, session, and line number for code execution errors
- **Code blocks** - Displays the failing code with syntax highlighting
- **Build info** - Shows output directory, server URL (for serve), and build time
- **Rich formatting** - Color-coded errors vs warnings, nice panels
- **Streaming mode** - Real-time output for `mkdocs serve` with rebuild detection
- **Interactive mode** - Toggle between filtered and raw output on-the-fly

## Installation

```bash
# Install with uv (recommended)
uv tool install mkdocs-filter

# Or with pip
pip install mkdocs-filter

# Or with pipx
pipx install mkdocs-filter
```
