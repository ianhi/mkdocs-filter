"""Run modes for docs-output-filter: streaming, batch, interactive, URL, and wrapper.

Each function implements a different way to process documentation build output:
- run_streaming_mode(): Default mode, processes stdin line-by-line with spinner
- run_batch_mode(): Reads all input first, then processes and displays
- run_interactive_mode(): Keyboard-driven toggle between filtered/raw display
- run_url_mode(): Fetch and process a remote build log from a URL
- run_wrap_mode(): Run a command as subprocess with unbuffered output (recommended)

All modes use StreamingProcessor (from processor.py) for parsing and display
functions (from display.py) for rendering.

Update this docstring if you add a new run mode or change how modes interact
with the processor or display system.
"""

from __future__ import annotations

import argparse
import os
import select
import sys
import termios
import threading
import tty
from queue import Empty, Queue

from rich.console import Console

from docs_output_filter.backends import (
    Backend,
    BuildTool,
    detect_backend_from_lines,
    get_backend,
)
from docs_output_filter.backends.mkdocs import (
    detect_chunk_boundary as mkdocs_detect_chunk_boundary,
)
from docs_output_filter.display import (
    DisplayMode,
    build_stderr_hint,
    print_info_groups,
    print_issue,
    print_summary,
    truncate_line,
)
from docs_output_filter.processor import StreamingProcessor
from docs_output_filter.remote import fetch_remote_log
from docs_output_filter.state import get_state_file_path
from docs_output_filter.types import (
    ChunkBoundary,
    Issue,
    Level,
    deduplicate_issues,
    group_info_messages,
)


def run_batch_mode(console: Console, args: argparse.Namespace, show_spinner: bool = True) -> int:
    """Run in batch mode - read all input then display results."""
    lines: list[str] = []

    if not show_spinner:
        lines = [line.rstrip() for line in sys.stdin]
    else:
        from rich.live import Live
        from rich.spinner import Spinner

        with Live(console=console, refresh_per_second=10, transient=True) as live:
            for line in sys.stdin:
                lines.append(line.rstrip())
                display_line = truncate_line(line)
                spinner = Spinner("dots", text=f" Building... {display_line}", style="cyan")
                live.update(spinner)

    # Get backend
    tool = BuildTool(getattr(args, "tool", "auto"))
    if tool != BuildTool.AUTO:
        backend: Backend = get_backend(tool)
    else:
        backend = detect_backend_from_lines(lines)

    # Extract build info
    build_info = backend.extract_build_info(lines)

    # Parse issues
    issues = backend.parse_issues(lines)

    # Filter if errors-only
    if args.errors_only:
        issues = [i for i in issues if i.level == Level.ERROR]

    # Deduplicate
    unique_issues = deduplicate_issues(issues)

    # Parse INFO messages
    info_messages = backend.parse_info_messages(lines)
    info_groups = group_info_messages(info_messages)

    # Print issues
    if not unique_issues:
        console.print("[green]✓ No warnings or errors[/green]")
    else:
        console.print()
        for issue in unique_issues:
            print_issue(console, issue, verbose=args.verbose)

    # Print grouped INFO messages (if any)
    if info_groups:
        print_info_groups(console, info_groups, verbose=args.verbose)

    # Print summary
    print_summary(console, unique_issues, build_info, verbose=args.verbose)

    error_count = sum(1 for i in unique_issues if i.level == Level.ERROR)
    return 1 if error_count else 0


def run_streaming_mode(console: Console, args: argparse.Namespace) -> int:
    """Run in streaming mode - process and display incrementally."""
    from rich.live import Live
    from rich.spinner import Spinner

    # Check if state sharing is enabled
    write_state = getattr(args, "share_state", False)

    # Get backend from --tool flag
    tool = BuildTool(getattr(args, "tool", "auto"))
    backend: Backend | None = None
    if tool != BuildTool.AUTO:
        backend = get_backend(tool)

    processor = StreamingProcessor(
        console=console,
        verbose=args.verbose,
        errors_only=args.errors_only,
        write_state=write_state,
        backend=backend,
    )

    # Track if we've printed any issues to know if we need a newline
    issues_printed = 0
    build_output_shown = False

    # Use a spinner while processing, but let processor handle display
    spinner_active = not args.no_progress and not args.no_color
    current_activity = ""

    # Queue for issues to print after build completes
    pending_issues: list[Issue] = []

    def on_issue_queued(issue: Issue) -> None:
        pending_issues.append(issue)

    processor.on_issue = on_issue_queued

    def print_pending_issues() -> None:
        nonlocal issues_printed
        for issue in pending_issues:
            if issues_printed == 0:
                console.print()
            print_issue(console, issue, verbose=args.verbose)
            issues_printed += 1
        pending_issues.clear()

    def print_build_time_inline() -> None:
        if processor.build_info.build_time:
            console.print(f"[dim]Built in {processor.build_info.build_time}s[/dim]")
        console.print()

    server_url_printed = False

    def print_server_url_inline() -> None:
        nonlocal server_url_printed
        if server_url_printed:
            return
        if processor.build_info.server_url:
            server_url_printed = True
            console.print(f"[bold green]🌐 Server:[/bold green] {processor.build_info.server_url}")
            console.print()

    def print_info_groups_inline() -> None:
        if processor.all_info_messages:
            # group_info_messages always returns non-empty when messages exist
            info_groups = group_info_messages(processor.all_info_messages)
            print_info_groups(console, info_groups, verbose=args.verbose)

    stderr_hint_printed = False

    def print_stderr_hint_inline() -> None:
        nonlocal stderr_hint_printed
        if stderr_hint_printed:
            return
        bi = processor.build_info
        n_issues = len(processor.all_issues)
        # Check 1: build reported more warnings than we captured
        if bi.reported_warning_count is not None and bi.reported_warning_count > n_issues:
            missing = bi.reported_warning_count - n_issues
            console.print()
            console.print(
                f"[yellow bold]⚠ Build reported {bi.reported_warning_count} warning(s) "
                f"but only {n_issues} captured.[/yellow bold]"
            )
            console.print(
                f"[yellow]  {missing} warning(s) may have gone to stderr. "
                "Try [bold]2>&1 |[/bold] to capture all output:[/yellow]"
            )
            console.print(f"[dim]  {build_stderr_hint()}[/dim]")
            stderr_hint_printed = True

    def _detect_boundary_for_display(line: str) -> ChunkBoundary:
        """Detect chunk boundary for display purposes."""
        if processor.backend is not None:
            return processor.backend.detect_chunk_boundary(line, None)
        return mkdocs_detect_chunk_boundary(line, None)

    def _handle_boundary(boundary: ChunkBoundary) -> None:
        """Handle BUILD_COMPLETE/SERVER_STARTED/REBUILD_STARTED boundaries."""
        nonlocal build_output_shown, issues_printed
        if boundary in (ChunkBoundary.BUILD_COMPLETE, ChunkBoundary.SERVER_STARTED):
            if not build_output_shown:
                build_output_shown = True
                print_build_time_inline()
                print_info_groups_inline()
                print_pending_issues()
                print_stderr_hint_inline()
                print_server_url_inline()
                if write_state:
                    state_path = get_state_file_path()
                    if state_path:
                        console.print(f"[dim]💡 MCP: State shared to {state_path.resolve()}[/dim]")
                    console.print()
            elif boundary == ChunkBoundary.SERVER_STARTED:
                print_server_url_inline()
        elif boundary == ChunkBoundary.REBUILD_STARTED:
            issues_printed = 0
            build_output_shown = False

    if spinner_active:
        with Live(console=console, refresh_per_second=10, transient=True) as live:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                boundary = _detect_boundary_for_display(line)

                processor.process_line(line)

                display_line = truncate_line(line)
                if display_line != current_activity or processor.build_info.server_url:
                    current_activity = display_line
                    spinner_text = f" {current_activity}"
                    if processor.build_info.server_url:
                        spinner_text += (
                            f"  [bold green]🌐 {processor.build_info.server_url}[/bold green]"
                        )
                    spinner = Spinner("dots", text=spinner_text, style="cyan")
                    live.update(spinner)

                if boundary != ChunkBoundary.NONE:
                    live.stop()
                    _handle_boundary(boundary)
                    live.start()
    else:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            boundary = _detect_boundary_for_display(line)
            processor.process_line(line)
            _handle_boundary(boundary)

    # Finalize and get results
    all_issues, build_info = processor.finalize()

    if pending_issues:
        print_build_time_inline()
        print_info_groups_inline()
        print_pending_issues()
        print_stderr_hint_inline()
        print_server_url_inline()

    # If we never saw valid build output, something went wrong
    if not processor.saw_build_output and processor.raw_buffer:
        console.print("[red bold]Error: Build tool did not produce expected output[/red bold]")
        console.print()
        console.print("[dim]Raw output:[/dim]")
        for line in processor.raw_buffer:
            console.print(f"  {line}")
        return 1

    if processor.saw_server_error and processor.error_lines:
        console.print()
        console.print("[red bold]Server error:[/red bold]")
        for line in processor.error_lines[-20:]:
            console.print(f"  {line}")
        return 1

    if processor.in_serve_mode:
        console.print()
        console.print("[yellow]Server stopped unexpectedly.[/yellow]")

    if not all_issues:
        console.print("[green]✓ No warnings or errors[/green]")

    print_summary(
        console,
        all_issues,
        build_info,
        verbose=args.verbose,
        skip_server_url=server_url_printed,
    )

    error_count = sum(1 for i in all_issues if i.level == Level.ERROR)
    return 1 if error_count else 0


def run_interactive_mode(console: Console, args: argparse.Namespace) -> int:
    """Run in interactive mode with keyboard controls to toggle between filtered/raw."""
    if not sys.stdin.isatty() or not hasattr(termios, "tcgetattr"):
        console.print(
            "[yellow]Warning: Interactive mode requires a terminal. Falling back to streaming mode.[/yellow]"
        )
        return run_streaming_mode(console, args)

    try:
        tty_fd = os.open("/dev/tty", os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        console.print(
            "[yellow]Warning: Cannot open /dev/tty for keyboard input. Falling back to streaming mode.[/yellow]"
        )
        return run_streaming_mode(console, args)

    mode = DisplayMode.FILTERED
    line_queue: Queue[str | None] = Queue()
    raw_buffer: list[str] = []
    should_quit = threading.Event()
    input_finished = threading.Event()

    # Get backend from --tool flag
    tool = BuildTool(getattr(args, "tool", "auto"))
    backend: Backend | None = None
    if tool != BuildTool.AUTO:
        backend = get_backend(tool)

    processor = StreamingProcessor(
        console=console,
        verbose=args.verbose,
        errors_only=args.errors_only,
        backend=backend,
    )

    def stdin_reader() -> None:
        try:
            while True:
                if should_quit.is_set():  # pragma: no cover - thread race between readline calls
                    break
                line = sys.stdin.readline()
                if not line:
                    break
                line_queue.put(line)
        finally:
            line_queue.put(None)
            input_finished.set()

    def get_key_nonblocking(fd: int, timeout: float = 0.1) -> str | None:
        try:
            rlist, _, _ = select.select([fd], [], [], timeout)
            if rlist:
                return os.read(fd, 1).decode("utf-8", errors="ignore")
        except OSError:
            pass
        return None

    reader_thread = threading.Thread(target=stdin_reader, daemon=True)
    reader_thread.start()

    old_settings = termios.tcgetattr(tty_fd)
    try:
        tty.setraw(tty_fd)

        console.print(
            f"[dim]─── Interactive mode: [bold]{'FILTERED' if mode == DisplayMode.FILTERED else 'RAW'}[/bold] "
            "│ Press 'r' for raw, 'f' for filtered, 'q' to quit ───[/dim]"
        )
        console.print()

        issues_printed = 0

        while True:
            key = get_key_nonblocking(tty_fd)
            if key:
                if key.lower() == "q":
                    should_quit.set()
                    break
                elif key.lower() == "r" and mode != DisplayMode.RAW:
                    mode = DisplayMode.RAW
                    console.print()
                    console.print("[dim]─── Switched to RAW mode ───[/dim]")
                    for raw_line in raw_buffer:
                        console.print(raw_line.rstrip())
                elif key.lower() == "f" and mode != DisplayMode.FILTERED:
                    mode = DisplayMode.FILTERED
                    console.print()
                    console.print("[dim]─── Switched to FILTERED mode ───[/dim]")
                    for issue in processor.all_issues:
                        print_issue(console, issue, verbose=args.verbose)

            try:
                line = line_queue.get(timeout=0.05)
                if line is None:
                    break

                raw_buffer.append(line)
                if len(raw_buffer) > 10000:
                    raw_buffer = raw_buffer[-10000:]

                if mode == DisplayMode.RAW:
                    console.print(line.rstrip())
                else:
                    old_issue_count = len(processor.all_issues)
                    processor.process_line(line)
                    new_issue_count = len(processor.all_issues)

                    for issue in processor.all_issues[old_issue_count:new_issue_count]:
                        if issues_printed == 0:
                            console.print()
                        print_issue(console, issue, verbose=args.verbose)
                        issues_printed += 1

            except Empty:
                continue

    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_settings)
        os.close(tty_fd)

    reader_thread.join(timeout=1.0)

    all_issues, build_info = processor.finalize()

    if not all_issues:
        console.print("[green]✓ No warnings or errors[/green]")

    print_summary(console, all_issues, build_info, verbose=args.verbose)

    error_count = sum(1 for i in all_issues if i.level == Level.ERROR)
    return 1 if error_count else 0


def run_url_mode(console: Console, args: argparse.Namespace) -> int:
    """Fetch and process a remote build log from a URL."""
    url = args.url

    if not args.no_progress and not args.no_color:
        from rich.live import Live
        from rich.spinner import Spinner

        with Live(console=console, refresh_per_second=10, transient=True) as live:
            spinner = Spinner("dots", text=f" Fetching {url}", style="cyan")
            live.update(spinner)
            content = fetch_remote_log(url)
    else:
        console.print(f"[dim]Fetching {url}...[/dim]")
        content = fetch_remote_log(url)

    if content is None:
        console.print("[red]Failed to fetch build log[/red]")
        return 1

    lines = content.splitlines()
    console.print(f"[dim]Processing {len(lines)} lines...[/dim]")
    console.print()

    # Auto-detect or use specified backend
    tool = BuildTool(getattr(args, "tool", "auto"))
    if tool != BuildTool.AUTO:
        backend: Backend = get_backend(tool)
    else:
        backend = detect_backend_from_lines(lines)

    all_issues = backend.parse_issues(lines)

    if args.errors_only:
        all_issues = [i for i in all_issues if i.level == Level.ERROR]

    info_messages = backend.parse_info_messages(lines)
    info_groups = group_info_messages(info_messages)

    build_info = backend.extract_build_info(lines)

    if info_groups:
        print_info_groups(console, info_groups, verbose=args.verbose)

    for issue in all_issues:
        print_issue(console, issue, verbose=args.verbose)

    if not all_issues and not info_messages:
        console.print("[green]✓ No warnings or errors found[/green]")

    print_summary(console, all_issues, build_info, verbose=args.verbose)

    error_count = sum(1 for i in all_issues if i.level == Level.ERROR)
    return 1 if error_count else 0


def run_wrap_mode(console: Console, args: argparse.Namespace, command: list[str]) -> int:
    """Run upstream command as subprocess with unbuffered output.

    Spawns the command with PYTHONUNBUFFERED=1 to force line-buffered output,
    captures both stdout and stderr, and feeds the output to the streaming processor.
    This avoids the block-buffering issue that occurs with shell pipes.
    """
    import io
    import subprocess

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except FileNotFoundError:
        console.print(f"[red bold]Error: command not found: {command[0]}[/red bold]")
        return 127
    except PermissionError:
        console.print(f"[red bold]Error: permission denied: {command[0]}[/red bold]")
        return 126

    old_stdin = sys.stdin
    sys.stdin = io.TextIOWrapper(
        proc.stdout, encoding="utf-8", errors="replace", line_buffering=True
    )

    try:
        result = run_streaming_mode(console, args)
    finally:
        sys.stdin = old_stdin
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    return result
