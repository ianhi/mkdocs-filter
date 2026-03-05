"""Display and formatting functions for docs-output-filter output.

Contains all Rich-based rendering: issue display, info message grouping,
build summary, and helper utilities for text truncation and stderr hints.

Key functions:
- print_issue(): Render a single warning/error with code blocks and tracebacks
- print_info_groups(): Render grouped INFO messages (broken links, deprecation, etc.)
- print_summary(): Render the build summary footer with counts, build info, hints
- truncate_line(): Truncate a line for spinner display

Also contains:
- DisplayMode enum (FILTERED/RAW for interactive mode)
- INFO_CATEGORY_DISPLAY: mapping of InfoCategory to display names/icons

Update this docstring if you add new display/formatting functions or change
the rendering approach (e.g., switching from Rich to another library).
"""

from __future__ import annotations

import os
import re
import sys
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from docs_output_filter.types import (
    BuildInfo,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
    dedent_code,
    group_info_messages,
)


class DisplayMode(Enum):
    """Display mode for interactive mode."""

    FILTERED = "filtered"
    RAW = "raw"


# Category display names and icons
INFO_CATEGORY_DISPLAY = {
    InfoCategory.BROKEN_LINK: ("🔗 Broken links", "Link target not found"),
    InfoCategory.ABSOLUTE_LINK: ("🔗 Absolute links", "Left as-is, may not work"),
    InfoCategory.UNRECOGNIZED_LINK: ("🔗 Unrecognized links", "Could not resolve"),
    InfoCategory.MISSING_NAV: ("📄 Pages not in nav", "Not included in navigation"),
    InfoCategory.NO_GIT_LOGS: ("📅 No git history", "git-revision plugin warning"),
    InfoCategory.DEPRECATION_WARNING: ("⚠️  Deprecation warnings", "From dependencies"),
}


def print_issue(console: Console, issue: Issue, verbose: bool = False) -> None:
    """Print an issue with rich formatting."""
    style = "red bold" if issue.level == Level.ERROR else "yellow bold"
    icon = "✗" if issue.level == Level.ERROR else "⚠"

    # Header
    header = Text()
    header.append(f"{icon} ", style=style)
    header.append(f"{issue.level.value}", style=style)
    header.append(f" [{issue.source}] ", style="dim")
    header.append(issue.message)
    # Show warning code if present (Sphinx)
    if issue.warning_code:
        header.append(f" [{issue.warning_code}]", style="dim")
    console.print(header)

    # Show file/location if available
    if issue.file:
        location = f"   📍 {issue.file}"
        if issue.line_number is not None:
            location += f":{issue.line_number}"
        console.print(location, style="cyan")

    # For markdown_exec issues, always show code (truncated if not verbose)
    if issue.code:
        console.print()
        code_to_show = issue.code

        if not verbose:
            code_lines = issue.code.split("\n")
            if len(code_lines) > 10:
                code_to_show = f"  # ... ({len(code_lines) - 10} lines above)\n" + "\n".join(
                    code_lines[-10:]
                )

        code_to_show = dedent_code(code_to_show)

        syntax = Syntax(
            code_to_show,
            "python",
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
        )
        console.print(Panel(syntax, title="Code Block", border_style="cyan", expand=False))

    # Show output/traceback
    if issue.output:
        # Strip ANSI escape codes — remote build logs (e.g., ReadTheDocs) often
        # contain colorized tracebacks that cause Rich to hang during rendering
        clean_output = re.sub(r"\x1b\[[0-9;]*m", "", issue.output)
        output_lines = [line for line in clean_output.split("\n") if line.strip()]

        if verbose:
            if len(output_lines) > 15:
                output_text = "\n".join(output_lines[-15:])
                output_text = f"... ({len(output_lines) - 15} lines omitted)\n" + output_text
            else:
                output_text = clean_output
            output_text = dedent_code(output_text)
            console.print(Panel(output_text, title="Traceback", border_style="red", expand=False))
        else:
            error_lines: list[str] = []
            for line in reversed(output_lines):
                stripped = line.strip()
                if re.match(r"^(INFO|DEBUG|WARNING|ERROR)\s+-", stripped):
                    continue

                error_lines.insert(0, stripped)
                if (
                    re.match(r"^[A-Z][a-zA-Z]*Error:", stripped)
                    or re.match(r"^[A-Z][a-zA-Z]*Exception:", stripped)
                    or re.match(r"^[A-Z][a-zA-Z]*Warning:", stripped)
                ):
                    break
                if len(error_lines) >= 3:
                    break

            if error_lines:
                error_summary = "\n".join(error_lines)
                console.print(
                    Panel(
                        error_summary,
                        title="Error Output",
                        border_style="red",
                        expand=False,
                        subtitle="use -v for full traceback",
                        subtitle_align="right",
                    )
                )

    console.print()


def print_info_groups(
    console: Console,
    groups: dict[InfoCategory, list[InfoMessage]],
    verbose: bool = False,
    max_files_shown: int = 3,
    max_targets_shown: int = 5,
) -> None:
    """Print grouped INFO messages with compact display."""
    from rich.tree import Tree

    if not groups:
        return

    for category, messages in groups.items():
        title, description = INFO_CATEGORY_DISPLAY.get(category, (category.value, ""))
        count = len(messages)

        # Create a tree for this category
        header = f"[cyan]{title}[/cyan] [dim]({count})[/dim]"
        if description:
            header += f" [dim]- {description}[/dim]"

        tree = Tree(header)

        if category == InfoCategory.DEPRECATION_WARNING:
            # Group deprecation warnings by package (stored in file field)
            by_package: dict[str, list[InfoMessage]] = {}
            for msg in messages:
                pkg = msg.file
                if pkg not in by_package:
                    by_package[pkg] = []
                by_package[pkg].append(msg)

            sorted_packages = sorted(by_package.items(), key=lambda x: (-len(x[1]), x[0]))
            pkgs_to_show = sorted_packages if verbose else sorted_packages[:max_targets_shown]
            remaining = len(sorted_packages) - len(pkgs_to_show)

            for pkg, pkg_msgs in pkgs_to_show:
                pkg_count = len(pkg_msgs)
                if verbose:
                    branch = tree.add(f"[yellow]{pkg}[/yellow] [dim]({pkg_count})[/dim]")
                    for msg in pkg_msgs:
                        warning_text = f"[dim]{msg.target}: {msg.suggestion}[/dim]"
                        branch.add(warning_text)
                else:
                    tree.add(f"[yellow]{pkg}[/yellow] [dim]({pkg_count} warnings)[/dim]")

            if remaining > 0:
                tree.add(f"[dim]... and {remaining} more packages[/dim]")

        elif category in (
            InfoCategory.BROKEN_LINK,
            InfoCategory.ABSOLUTE_LINK,
            InfoCategory.UNRECOGNIZED_LINK,
        ):
            # Group by target
            by_target: dict[str, list[InfoMessage]] = {}
            for msg in messages:
                target = msg.target or "unknown"
                if target not in by_target:
                    by_target[target] = []
                by_target[target].append(msg)

            sorted_targets = sorted(by_target.items(), key=lambda x: (-len(x[1]), x[0]))
            targets_to_show = sorted_targets if verbose else sorted_targets[:max_targets_shown]
            remaining_targets = len(sorted_targets) - len(targets_to_show)

            for target, target_msgs in targets_to_show:
                target_count = len(target_msgs)
                suggestion = target_msgs[0].suggestion

                if verbose:
                    target_label = f"[yellow]'{target}'[/yellow]"
                    if suggestion:
                        target_label += f" [dim]→ '{suggestion}'[/dim]"
                    target_label += f" [dim]({target_count})[/dim]"
                    branch = tree.add(target_label)
                    for msg in target_msgs:
                        branch.add(f"[dim]{msg.file}[/dim]")
                else:
                    target_label = f"[yellow]'{target}'[/yellow] [dim]({target_count} files)[/dim]"
                    if suggestion:
                        target_label += f" [dim]→ '{suggestion}'[/dim]"
                    tree.add(target_label)

            if remaining_targets > 0:
                tree.add(f"[dim]... and {remaining_targets} more targets[/dim]")
        else:
            # Simple list of files
            files_to_show = messages if verbose else messages[:max_files_shown]
            for msg in files_to_show:
                tree.add(f"[dim]{msg.file}[/dim]")
            if not verbose and len(messages) > max_files_shown:
                tree.add(f"[dim]... and {len(messages) - max_files_shown} more[/dim]")

        console.print(tree)
        console.print()


def truncate_line(line: str, max_len: int = 60, pad: bool = True) -> str:
    """Truncate line for display, keeping useful part."""
    line = line.strip()
    line = re.sub(r"^\[stderr\]\s*", "", line)
    line = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s*-\s*", "", line)
    line = re.sub(r"^[\w.]+\s*-\s*(INFO|WARNING|ERROR)\s*-\s*", "", line)
    if len(line) > max_len:
        return line[:max_len] + "..."
    if pad:
        return line.ljust(max_len)
    return line


def _get_upstream_command() -> str | None:
    """Try to detect the command piping into us (our sibling process).

    In a pipe like `sphinx-build docs _build | docs-output-filter`, both processes
    are children of the same shell. We find our parent's other children to get
    the upstream command.
    """
    import subprocess as sp

    try:
        our_pid = os.getpid()
        ppid = os.getppid()
        result = sp.run(
            ["ps", "-eo", "pid,ppid,command"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            pid, parent_pid, cmd = int(parts[0]), int(parts[1]), parts[2]
            if parent_pid == ppid and pid != our_pid:
                # Skip shell processes, our own variants, and defunct processes
                if (
                    cmd.startswith("-")
                    or "docs-output-filter" in cmd
                    or "docs_output_filter" in cmd
                    or "<defunct>" in cmd
                ):
                    continue
                return cmd
    except Exception:
        pass
    return None


def build_stderr_hint() -> str:
    """Build the hint string suggesting 2>&1, using the actual upstream command if detectable."""
    upstream = _get_upstream_command()
    if upstream:
        # Get our own args (excluding the program name)
        our_args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
        our_cmd = "docs-output-filter"
        if our_args:
            our_cmd += f" {our_args}"
        return f"{upstream} 2>&1 | {our_cmd}"
    return "command 2>&1 | docs-output-filter"


def print_summary(
    console: Console,
    issues: list[Issue],
    build_info: BuildInfo,
    verbose: bool = False,
    skip_server_url: bool = False,
) -> None:
    """Print the summary footer with build info and hints."""
    error_count = sum(1 for i in issues if i.level == Level.ERROR)
    warning_count = sum(1 for i in issues if i.level == Level.WARNING)

    if issues:
        console.print("─" * 40, style="dim")
        summary = Text("Summary: ")
        if error_count:
            summary.append(f"{error_count} error(s)", style="red bold")
            if warning_count:
                summary.append(", ")
        if warning_count:
            summary.append(f"{warning_count} warning(s)", style="yellow bold")
        console.print(summary)

    # Always show build info at the end
    console.print()
    if build_info.server_url and not skip_server_url:
        console.print(f"[bold green]🌐 Server:[/bold green] {build_info.server_url}")
    if build_info.build_dir:
        console.print(f"[bold blue]📁 Output:[/bold blue] {build_info.build_dir}")
    if build_info.build_time:
        console.print(f"[dim]Built in {build_info.build_time}s[/dim]")

    # Show hint for seeing more details
    if issues:
        console.print()
        hints = []
        if not verbose:
            hints.append("[dim]-v[/dim] for verbose output")
        hints.append("[dim]--raw[/dim] for full build output")
        console.print(f"[dim]Hint: {', '.join(hints)}[/dim]")

        missing_file_context = any(
            i.source == "markdown_exec" and i.file and "session" in i.file and ".md" not in i.file
            for i in issues
        )
        if missing_file_context:
            console.print(
                "[dim]Tip: Use [/dim][dim italic]mkdocs build --verbose[/dim italic]"
                "[dim] to see which file contains code block errors[/dim]"
            )

    # Detect missing stderr: build tool reported more warnings than we captured
    if build_info.reported_warning_count is not None and build_info.reported_warning_count > len(
        issues
    ):
        missing = build_info.reported_warning_count - len(issues)
        console.print()
        console.print(
            f"[yellow bold]⚠ Build reported {build_info.reported_warning_count} warning(s) "
            f"but only {len(issues)} captured.[/yellow bold]"
        )
        console.print(
            f"[yellow]  {missing} warning(s) may have gone to stderr. "
            "Try [bold]2>&1 |[/bold] to capture all output:[/yellow]"
        )
        suggested = build_stderr_hint()
        console.print(f"[dim]  {suggested}[/dim]")


def _issue_to_dict(issue: Issue, verbose: bool = False) -> dict[str, Any]:
    """Convert an Issue to a JSON-serializable dict."""
    result: dict[str, Any] = {
        "level": issue.level.value,
        "source": issue.source,
        "message": issue.message,
    }
    if issue.file:
        result["file"] = issue.file
    if issue.line_number is not None:
        result["line_number"] = issue.line_number
    if issue.warning_code:
        result["warning_code"] = issue.warning_code
    if issue.code:
        result["code"] = issue.code
    if issue.output:
        result["output"] = issue.output
    return result


def format_issues_json(
    issues: list[Issue],
    info_messages: list[InfoMessage],
    build_info: BuildInfo,
    verbose: bool = False,
) -> dict[str, Any]:
    """Format issues, info messages, and build info as a JSON-serializable dict.

    Produces structured output suitable for machine consumption (LLMs, scripts).
    """
    error_count = sum(1 for i in issues if i.level == Level.ERROR)
    warning_count = sum(1 for i in issues if i.level == Level.WARNING)

    response: dict[str, Any] = {
        "total": len(issues),
        "errors": error_count,
        "warnings": warning_count,
        "issues": [_issue_to_dict(i, verbose=verbose) for i in issues],
    }

    if info_messages:
        groups = group_info_messages(info_messages)
        info_summary: dict[str, int] = {}
        for cat, msgs in groups.items():
            info_summary[cat.value] = len(msgs)
        info_summary["total"] = len(info_messages)
        response["info_summary"] = info_summary

    build_info_dict: dict[str, str] = {}
    if build_info.server_url:
        build_info_dict["server_url"] = build_info.server_url
    if build_info.build_dir:
        build_info_dict["build_dir"] = build_info.build_dir
    if build_info.build_time:
        build_info_dict["build_time"] = build_info.build_time
    if build_info_dict:
        response["build_info"] = build_info_dict

    return response
