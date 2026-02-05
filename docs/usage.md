# Usage

## Basic Usage

Pipe mkdocs output through the filter:

```bash
# Build with filtered output
mkdocs build 2>&1 | mkdocs-output-filter

# Serve with filtered output (streaming mode auto-detected)
mkdocs serve --livereload 2>&1 | mkdocs-output-filter
```

!!! warning "Click 8.3.x Bug"
    Due to a [bug in Click 8.3.x](https://github.com/mkdocs/mkdocs/issues/4032),
    you must use `--livereload` flag for file watching to work properly with
    `mkdocs serve`.

## Command-Line Options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Show full code blocks and tracebacks |
| `-e, --errors-only` | Show only errors, not warnings |
| `--no-color` | Disable colored output |
| `--no-progress` | Disable progress spinner |
| `--raw` | Pass through raw mkdocs output |
| `--streaming` | Force streaming mode (for `mkdocs serve`) |
| `--batch` | Force batch mode (process all input then display) |
| `-i, --interactive` | Interactive mode with keyboard controls |
| `--version` | Show version number |

## Modes

### Batch Mode (default for `mkdocs build`)

Reads all mkdocs output, parses it, then displays a summary. Shows a progress spinner while processing.

```bash
mkdocs build 2>&1 | mkdocs-output-filter
```

### Streaming Mode (default for `mkdocs serve`)

Processes output in real-time, detecting chunk boundaries like build completion and file changes. Shows issues as they occur.

```bash
mkdocs serve --livereload 2>&1 | mkdocs-output-filter --streaming
```

When a file change triggers a rebuild, you'll see:

```
─── File change detected, rebuilding... ───
```

### Interactive Mode

Toggle between filtered and raw output using keyboard controls:

```bash
mkdocs serve --livereload 2>&1 | mkdocs-output-filter -i
```

**Keyboard controls:**

- `r` - Switch to raw mode (show all output)
- `f` - Switch to filtered mode (show only warnings/errors)
- `q` - Quit

!!! note
    Interactive mode requires a TTY. When piped or in non-interactive terminals, it falls back to streaming mode.

## Examples

### Verbose Output

Show full tracebacks for debugging:

```bash
mkdocs build 2>&1 | mkdocs-output-filter -v
```

### Errors Only

Hide warnings, show only errors:

```bash
mkdocs build 2>&1 | mkdocs-output-filter -e
```

### CI/CD Integration

For CI environments, disable colors and progress:

```bash
mkdocs build 2>&1 | mkdocs-output-filter --no-color --no-progress
```

The exit code is:
- `0` - No errors (warnings are OK)
- `1` - One or more errors found

### Raw Passthrough

Sometimes you need the full mkdocs output:

```bash
mkdocs build 2>&1 | mkdocs-output-filter --raw
```
