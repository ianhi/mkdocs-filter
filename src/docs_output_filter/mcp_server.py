"""MCP Server for docs-output-filter.

Provides tools for code agents to get documentation build issues and collaborate on fixes.
Supports both MkDocs and Sphinx projects.

Usage:
    # Watch mode (recommended): Read state from running docs-output-filter CLI
    docs-output-filter --mcp --watch

    # Subprocess mode: Server manages builds internally
    docs-output-filter --mcp --project-dir /path/to/project

    # Pipe mode: Receive build output via stdin
    mkdocs build 2>&1 | docs-output-filter --mcp --pipe
    sphinx-build docs build 2>&1 | docs-output-filter --mcp --pipe
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from docs_output_filter.backends import BuildTool, detect_backend_from_lines
from docs_output_filter.state import (
    find_project_root,
    get_state_file_path,
    read_state_file,
)
from docs_output_filter.types import (
    BuildInfo,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
    deduplicate_issues,
    group_info_messages,
)


def _detect_project_type(project_dir: Path) -> BuildTool:
    """Detect whether a project uses MkDocs or Sphinx."""
    if (project_dir / "mkdocs.yml").exists():
        return BuildTool.MKDOCS
    if (project_dir / "conf.py").exists():
        return BuildTool.SPHINX
    return BuildTool.MKDOCS  # Default fallback


class DocsFilterServer:
    """MCP server for docs-output-filter.

    Provides tools for code agents to interact with documentation build issues.
    Supports both MkDocs and Sphinx projects.
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        pipe_mode: bool = False,
        watch_mode: bool = False,
    ):
        self.project_dir = project_dir
        self.pipe_mode = pipe_mode
        self.watch_mode = watch_mode
        self.issues: list[Issue] = []
        self.info_messages: list[InfoMessage] = []
        self.build_info = BuildInfo()
        self.raw_output: list[str] = []
        self._issue_ids: dict[str, str] = {}
        self._last_state_timestamp: float = 0
        self._build_status: str = "complete"
        self._build_started_at: float | None = None

        # Detect project type if project_dir is set
        if project_dir:
            self._project_type = _detect_project_type(project_dir)
        else:
            self._project_type = BuildTool.AUTO

        self._server = Server("docs-filter")
        self._setup_tools()

    def _setup_tools(self) -> None:
        """Set up MCP tool handlers."""

        @self._server.list_tools()
        async def list_tools() -> list[Tool]:  # pragma: no cover - async MCP protocol wrapper
            return self._list_tools()

        @self._server.call_tool()
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:  # pragma: no cover - async MCP protocol wrapper
            return self._call_tool(name, arguments)

    def _list_tools(self) -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_issues",
                description="Get current warnings and errors from the last documentation build. Also returns info_summary with counts of INFO-level messages (broken links, missing nav, etc.) — use get_info for details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filter": {
                            "type": "string",
                            "enum": ["all", "errors", "warnings"],
                            "default": "all",
                            "description": "Filter issues by type",
                        },
                        "verbose": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include full code blocks and tracebacks",
                        },
                    },
                },
            ),
            Tool(
                name="get_issue_details",
                description="Get detailed information about a specific issue by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "issue_id": {
                            "type": "string",
                            "description": "The issue ID to get details for",
                        },
                    },
                    "required": ["issue_id"],
                },
            ),
            Tool(
                name="rebuild",
                description="Trigger a new documentation build and return updated issues",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "verbose": {
                            "type": "boolean",
                            "default": False,
                            "description": "Run build with verbose output for more file context",
                        },
                    },
                },
            ),
            Tool(
                name="get_build_info",
                description="Get information about the last build (server URL, build dir, time)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="get_raw_output",
                description="Get the raw build output from the last build",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "last_n_lines": {
                            "type": "integer",
                            "default": 100,
                            "description": "Number of lines to return (from the end)",
                        },
                    },
                },
            ),
            Tool(
                name="get_info",
                description="Get INFO-level messages like broken links, missing nav entries, absolute links, deprecation warnings",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [
                                "all",
                                "broken_link",
                                "absolute_link",
                                "unrecognized_link",
                                "missing_nav",
                                "no_git_logs",
                                "deprecation_warning",
                            ],
                            "default": "all",
                            "description": "Filter by category",
                        },
                        "grouped": {
                            "type": "boolean",
                            "default": True,
                            "description": "Group messages by category",
                        },
                    },
                },
            ),
            Tool(
                name="fetch_build_log",
                description="Fetch and process a remote build log from a URL (e.g., ReadTheDocs)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the build log to fetch",
                        },
                        "verbose": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include full code blocks and tracebacks",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        if name == "get_issues":
            return self._handle_get_issues(arguments)
        elif name == "get_issue_details":
            return self._handle_get_issue_details(arguments)
        elif name == "rebuild":
            return self._handle_rebuild(arguments)
        elif name == "get_build_info":
            return self._handle_get_build_info()
        elif name == "get_raw_output":
            return self._handle_get_raw_output(arguments)
        elif name == "get_info":
            return self._handle_get_info(arguments)
        elif name == "fetch_build_log":
            return self._handle_fetch_build_log(arguments)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    def _refresh_from_state_file(self) -> bool:
        """Refresh issues from state file if in watch mode."""
        if not self.watch_mode:
            return False

        state = read_state_file(self.project_dir)
        if state is None:
            return False

        self._build_status = state.build_status
        self._build_started_at = state.build_started_at

        if state.timestamp <= self._last_state_timestamp:
            return False

        self._last_state_timestamp = state.timestamp
        self.issues = state.issues
        self.info_messages = state.info_messages
        self.build_info = state.build_info
        self.raw_output = state.raw_output
        return True

    def _get_build_in_progress_response(self) -> list[TextContent] | None:
        """Check if a build is in progress and return a response if so."""
        import time

        if self._build_status != "building":
            return None

        elapsed = ""
        if self._build_started_at:
            seconds = int(time.time() - self._build_started_at)
            elapsed = f" (started {seconds} seconds ago)"

        response = {
            "status": "building",
            "message": f"Build in progress{elapsed}. Please wait and try again.",
            "hint": "The build is currently running. Query again in a few seconds to get the results.",
        }
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    def _handle_get_issues(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle get_issues tool call."""
        self._refresh_from_state_file()

        building_response = self._get_build_in_progress_response()
        if building_response:
            return building_response

        filter_type = arguments.get("filter", "all")
        verbose = arguments.get("verbose", False)

        issues = self.issues

        if filter_type == "errors":
            issues = [i for i in issues if i.level == Level.ERROR]
        elif filter_type == "warnings":
            issues = [i for i in issues if i.level == Level.WARNING]

        issue_dicts = [self._issue_to_dict(i, verbose=verbose) for i in issues]

        error_count = sum(1 for i in issues if i.level == Level.ERROR)
        warning_count = sum(1 for i in issues if i.level == Level.WARNING)

        response: dict[str, Any] = {
            "total": len(issue_dicts),
            "errors": error_count,
            "warnings": warning_count,
            "issues": issue_dicts,
        }

        # Include INFO message summary so agent knows they exist
        if self.info_messages:
            groups = group_info_messages(self.info_messages)
            info_summary = {cat.value: len(msgs) for cat, msgs in groups.items()}
            info_summary["total"] = len(self.info_messages)
            response["info_summary"] = info_summary

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    def _handle_get_issue_details(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle get_issue_details tool call."""
        self._refresh_from_state_file()

        issue_id = arguments.get("issue_id", "")

        for issue in self.issues:
            if self._get_issue_id(issue) == issue_id:
                issue_dict = self._issue_to_dict(issue, verbose=True)
                return [TextContent(type="text", text=json.dumps(issue_dict, indent=2))]

        return [TextContent(type="text", text=f"Issue not found: {issue_id}")]

    def _handle_rebuild(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle rebuild tool call."""
        if self.pipe_mode:
            return [
                TextContent(
                    type="text",
                    text="Error: Cannot rebuild in pipe mode. Run the build manually and pipe output.",
                )
            ]

        if self.watch_mode:
            refreshed = self._refresh_from_state_file()
            if not refreshed:
                return [
                    TextContent(
                        type="text",
                        text="No new build data. Save a file to trigger a rebuild, "
                        "or check that docs-output-filter is running with --share-state.",
                    )
                ]
            return self._handle_get_issues(arguments)

        if not self.project_dir:
            return [TextContent(type="text", text="Error: No project directory configured")]

        verbose = arguments.get("verbose", False)

        lines, return_code = self._run_build(verbose=verbose)

        self._parse_output("\n".join(lines))

        error_count = sum(1 for i in self.issues if i.level == Level.ERROR)
        warning_count = sum(1 for i in self.issues if i.level == Level.WARNING)

        response = {
            "success": return_code == 0 or (return_code == 1 and error_count == 0),
            "return_code": return_code,
            "total_issues": len(self.issues),
            "errors": error_count,
            "warnings": warning_count,
            "build_time": self.build_info.build_time,
            "issues": [self._issue_to_dict(i) for i in self.issues],
        }

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    def _handle_get_build_info(self) -> list[TextContent]:
        """Handle get_build_info tool call."""
        refreshed = self._refresh_from_state_file()

        if self.watch_mode:
            project_root = find_project_root()
            state_path = get_state_file_path(self.project_dir)

            diag = {
                "watch_mode": True,
                "state_file_found": refreshed or self._last_state_timestamp > 0,
                "project_root": str(project_root) if project_root else None,
                "state_file_path": str(state_path) if state_path else None,
                "cwd": str(Path.cwd()),
            }
            if not (refreshed or self._last_state_timestamp > 0):
                diag["hint"] = (
                    "No state file found. Make sure docs-output-filter is running with --share-state flag "
                    "in a directory containing mkdocs.yml or conf.py"
                )

            build_info = json.loads(self._get_build_info_json())
            build_info["diagnostics"] = diag
            return [TextContent(type="text", text=json.dumps(build_info, indent=2))]

        return [TextContent(type="text", text=self._get_build_info_json())]

    def _handle_get_raw_output(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle get_raw_output tool call."""
        last_n = arguments.get("last_n_lines", 100)
        lines = self.raw_output[-last_n:] if last_n > 0 else self.raw_output
        return [TextContent(type="text", text="\n".join(lines))]

    def _handle_get_info(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle get_info tool call for INFO-level messages."""
        self._refresh_from_state_file()

        building_response = self._get_build_in_progress_response()
        if building_response:
            return building_response

        category_filter = arguments.get("category", "all")
        grouped = arguments.get("grouped", True)

        messages = self.info_messages

        if category_filter != "all":
            try:
                cat = InfoCategory(category_filter)
                messages = [m for m in messages if m.category == cat]
            except ValueError:
                return [TextContent(type="text", text=f"Unknown category: {category_filter}")]

        if not messages:
            return [
                TextContent(
                    type="text", text=json.dumps({"info_messages": [], "count": 0}, indent=2)
                )
            ]

        if grouped:
            groups = group_info_messages(messages)
            result: dict[str, Any] = {
                "info_messages": {},
                "count": len(messages),
            }
            for cat, msgs in groups.items():
                result["info_messages"][cat.value] = [
                    {
                        "file": m.file,
                        "target": m.target,
                        "suggestion": m.suggestion,
                    }
                    for m in msgs
                ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            result_list = [
                {
                    "category": m.category.value,
                    "file": m.file,
                    "target": m.target,
                    "suggestion": m.suggestion,
                }
                for m in messages
            ]
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"info_messages": result_list, "count": len(messages)}, indent=2
                    ),
                )
            ]

    def _handle_fetch_build_log(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle fetch_build_log tool call."""
        url = arguments.get("url", "")
        verbose = arguments.get("verbose", False)

        if not url:
            return [TextContent(type="text", text="Error: URL is required")]

        from docs_output_filter.remote import fetch_remote_log

        content = fetch_remote_log(url)
        if content is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Failed to fetch build log from {url}"}, indent=2),
                )
            ]

        lines = content.splitlines()
        backend = detect_backend_from_lines(lines)

        all_issues = backend.parse_issues(lines)
        unique_issues = deduplicate_issues(all_issues)

        info_messages = backend.parse_info_messages(lines)
        build_info = backend.extract_build_info(lines)

        error_count = sum(1 for i in unique_issues if i.level == Level.ERROR)
        warning_count = sum(1 for i in unique_issues if i.level == Level.WARNING)

        response: dict[str, Any] = {
            "url": url,
            "lines_processed": len(lines),
            "total_issues": len(unique_issues),
            "errors": error_count,
            "warnings": warning_count,
            "issues": [self._issue_to_dict(i, verbose=verbose) for i in unique_issues],
        }

        if info_messages:
            groups = group_info_messages(info_messages)
            response["info_messages"] = {}
            for cat, msgs in groups.items():
                response["info_messages"][cat.value] = [
                    {
                        "file": m.file,
                        "target": m.target,
                        "suggestion": m.suggestion,
                    }
                    for m in msgs
                ]
            response["info_count"] = len(info_messages)

        if build_info.server_url:
            response["server_url"] = build_info.server_url
        if build_info.build_dir:
            response["build_dir"] = build_info.build_dir
        if build_info.build_time:
            response["build_time"] = build_info.build_time

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    def _parse_output(self, output: str) -> None:
        """Parse build output and extract issues and build info."""
        lines = output.splitlines()
        self.raw_output = lines

        backend = detect_backend_from_lines(lines, fallback_tool=self._project_type)

        all_issues = backend.parse_issues(lines)
        self.issues = deduplicate_issues(all_issues)
        self.build_info = backend.extract_build_info(lines)

    def _run_build(self, verbose: bool = False) -> tuple[list[str], int]:
        """Run documentation build and capture output."""
        if not self.project_dir:
            return [], 1

        project_type = _detect_project_type(self.project_dir)

        if project_type == BuildTool.SPHINX:
            # Sphinx build
            cmd = ["sphinx-build"]
            # Try to find source and build dirs from conf.py location
            source_dir = str(self.project_dir)
            build_dir = str(self.project_dir / "_build")
            cmd.extend([source_dir, build_dir])
            if verbose:
                cmd.append("-v")
        else:
            # MkDocs build
            cmd = ["mkdocs", "build", "--clean"]
            if verbose:
                cmd.append("--verbose")

        result = subprocess.run(
            cmd,
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )

        output = result.stdout + result.stderr
        lines = output.splitlines()

        return lines, result.returncode

    def _get_issue_id(self, issue: Issue) -> str:
        """Get a stable ID for an issue."""
        content = f"{issue.level.value}:{issue.source}:{issue.message}"
        if issue.file:
            content += f":{issue.file}"

        if content not in self._issue_ids:
            hash_bytes = hashlib.sha256(content.encode()).digest()
            self._issue_ids[content] = hash_bytes[:4].hex()

        return f"issue-{self._issue_ids[content]}"

    def _issue_to_dict(self, issue: Issue, verbose: bool = False) -> dict[str, Any]:
        """Convert an Issue to a JSON-serializable dict."""
        result: dict[str, Any] = {
            "id": self._get_issue_id(issue),
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

        if verbose:
            if issue.code:
                result["code"] = issue.code
            if issue.output:
                result["traceback"] = issue.output

        return result

    def _get_build_info_json(self) -> str:
        """Get build info as JSON string."""
        result: dict[str, Any] = {}
        if self.build_info.server_url:
            result["server_url"] = self.build_info.server_url
        if self.build_info.build_dir:
            result["build_dir"] = self.build_info.build_dir
        if self.build_info.build_time:
            result["build_time"] = self.build_info.build_time
        return json.dumps(result, indent=2)

    async def run(self) -> None:  # pragma: no cover - MCP stdio server runner
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream, write_stream, self._server.create_initialization_options()
            )


# Keep old name as alias for backward compat
MkdocsFilterServer = DocsFilterServer


def run_mcp_server(
    project_dir: str | None = None,
    pipe_mode: bool = False,
    watch_mode: bool = False,
    initial_build: bool = False,
    state_dir: str | None = None,
) -> int:
    """Run the MCP server with the given configuration."""
    import asyncio

    mode_count = sum([bool(project_dir and not watch_mode), pipe_mode, watch_mode])
    if mode_count == 0:
        print(
            "Error: Specify one of --watch, --project-dir, or --pipe",
            file=sys.stderr,
        )
        return 1

    if mode_count > 1 and not (watch_mode and project_dir):
        print(
            "Error: Cannot combine --pipe with other modes",
            file=sys.stderr,
        )
        return 1

    project_path = None
    if project_dir:
        project_path = Path(project_dir)
        if not project_path.exists():
            print(f"Error: Project directory does not exist: {project_dir}", file=sys.stderr)
            return 1
        # Accept either mkdocs.yml or conf.py
        if not (project_path / "mkdocs.yml").exists() and not (project_path / "conf.py").exists():
            print(
                f"Error: No mkdocs.yml or conf.py found in {project_dir}",
                file=sys.stderr,
            )
            return 1

    server = DocsFilterServer(
        project_dir=project_path,
        pipe_mode=pipe_mode,
        watch_mode=watch_mode,
    )

    if pipe_mode:
        lines = []
        for line in sys.stdin:
            lines.append(line.rstrip())
        server._parse_output("\n".join(lines))
    elif watch_mode:
        server._refresh_from_state_file()
    elif initial_build and project_path:
        lines, _ = server._run_build()
        server._parse_output("\n".join(lines))

    asyncio.run(server.run())

    return 0


def main() -> int:
    """Main entry point for the MCP server CLI (legacy entry point)."""
    import warnings

    warnings.warn(
        "mkdocs-output-filter-mcp is deprecated. Use 'docs-output-filter --mcp' instead.",
        DeprecationWarning,
        stacklevel=1,
    )

    parser = argparse.ArgumentParser(
        description="MCP Server for docs-output-filter - provides tools for code agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
NOTE: This entry point is deprecated. Use 'docs-output-filter --mcp' instead.

Examples:
    docs-output-filter --mcp --watch
    docs-output-filter --mcp --project-dir /path/to/project
    mkdocs build 2>&1 | docs-output-filter --mcp --pipe
        """,
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        help="Path to project directory (for subprocess mode or watch mode)",
    )
    parser.add_argument(
        "--pipe",
        action="store_true",
        help="Read build output from stdin (pipe mode)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: read state from .docs-output-filter/state.json written by CLI",
    )
    parser.add_argument(
        "--initial-build",
        action="store_true",
        help="Run an initial build on startup (subprocess mode only)",
    )
    args = parser.parse_args()

    return run_mcp_server(
        project_dir=args.project_dir,
        pipe_mode=args.pipe,
        watch_mode=args.watch,
        initial_build=args.initial_build,
    )


if __name__ == "__main__":
    sys.exit(main())
