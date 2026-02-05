# mkdocs-filter

Filter mkdocs build output to show only warnings and errors with nice formatting.

## Features

- 🔄 **Progress spinner** - Shows current build activity while processing
- ⚠️ **Filtered output** - Only shows warnings and errors, removes noise
- 📍 **Location info** - Shows file, session, and line number for code execution errors
- 💻 **Code blocks** - Displays the failing code with syntax highlighting
- 📁 **Build info** - Shows output directory, server URL (for serve), and build time
- 🎨 **Rich formatting** - Color-coded errors vs warnings, nice panels

## Installation

```bash
# Install with uv
uv tool install mkdocs-filter

# Or with pip
pip install mkdocs-filter
```

## Usage

Pipe mkdocs output through the filter:

```bash
# Build with filtered output
mkdocs build 2>&1 | mkdocs-filter

# Serve with filtered output
mkdocs serve 2>&1 | mkdocs-filter

# Verbose mode - show full tracebacks
mkdocs build 2>&1 | mkdocs-filter -v

# Errors only - hide warnings
mkdocs build 2>&1 | mkdocs-filter -e

# Raw mode - pass through unfiltered
mkdocs build 2>&1 | mkdocs-filter --raw
```

## Options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Show full code blocks and tracebacks |
| `-e, --errors-only` | Show only errors, not warnings |
| `--no-color` | Disable colored output |
| `--no-progress` | Disable progress spinner |
| `--raw` | Pass through raw mkdocs output |
| `--version` | Show version number |

## Example Output

```
⚠ WARNING [markdown_exec] ValueError: INTENTIONAL TEST ERROR
   📍 moving-chunks.md → session 'chunks' → line 17

╭─────────────── Code Block ───────────────╮
│   1 # ... (6 lines above)                │
│   2     store=session.store,             │
│   3     path="arr",                       │
│   4     shape=(10,),                      │
│   5     chunks=(2,),                      │
│   6     dtype="i4",                       │
│   7     fill_value=-1                     │
│   8 )                                     │
│   9 arr[:] = np.arange(10)               │
│  10 print("Original:", arr[:])           │
│  11 raise ValueError("TEST ERROR")       │
╰──────────────────────────────────────────╯

────────────────────────────────────────
Summary: 1 warning(s)

📁 Output: /path/to/docs/.site
Built in 21.54s

Hint: -v for verbose output, --raw for full mkdocs output
```

## Development

```bash
# Clone the repo
git clone https://github.com/ianhi/mkdocs-filter
cd mkdocs-filter

# Install dev dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run ruff format --check .
```

## License

MIT
