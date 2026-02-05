# mkdocs-filter

**Filter mkdocs output to show only what matters: warnings and errors.**

## Before & After

<div class="comparison">
<div class="comparison-item">
<div class="comparison-header bad">Raw mkdocs output ✗</div>

```
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /path/to/site
INFO    -  Doc file 'page1.md' contains a link 'image.png'...
INFO    -  Doc file 'page2.md' contains a link 'other.md'...
WARNING -  markdown_exec: Execution of python code block
           exited with errors

Code block is:

  x = 1
  y = 2
  raise ValueError("test error")

Output is:

  Traceback (most recent call last):
    File "<code block: session test; n1>", line 3, in <module>
      raise ValueError("test error")
  ValueError: test error

INFO    -  Documentation built in 1.23 seconds
```

</div>
<div class="comparison-item">
<div class="comparison-header good">Filtered output ✓</div>

```
Built in 1.23s

⚠ WARNING [markdown_exec] ValueError: test error
   📍 session 'test' → line 3

╭──────────── Code Block ────────────╮
│   1 x = 1                          │
│   2 y = 2                          │
│   3 raise ValueError("test error") │
╰────────────────────────────────────╯
╭────── Error Output ──────╮
│ ValueError: test error   │
╰── use -v for full trace ─╯

────────────────────────────────────
Summary: 1 warning(s)

Built in 1.23s

Hint: -v for verbose output, --raw for full mkdocs output
```

</div>
</div>

## Install

```bash
uv tool install mkdocs-filter
```

## Use

```bash
mkdocs build 2>&1 | mkdocs-output-filter
mkdocs serve --livereload 2>&1 | mkdocs-output-filter
```

## Features

| Feature | Description |
|---------|-------------|
| **Filtered output** | Only shows warnings and errors |
| **Code blocks** | Syntax-highlighted code that caused errors |
| **Location info** | File, session, and line number |
| **Streaming mode** | Real-time output for `mkdocs serve` |
| **Interactive mode** | Toggle raw/filtered with keyboard |
| **MCP server** | API for AI code assistants |

## Options

```
-v, --verbose      Show full tracebacks
-e, --errors-only  Hide warnings, show only errors
--no-color         Disable colored output
--raw              Pass through unfiltered
-i, --interactive  Keyboard toggle mode
```
