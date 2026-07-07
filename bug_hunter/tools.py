"""Tool definitions (API schemas) and implementations for the agent.

The ToolBox binds every tool to a single repo root and refuses to read or
write outside it (path-traversal safety). Agent-written tests go into a
separate workspace directory so the target repo is never modified.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .sandbox import run_pytest

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".agent_workspace"}
MAX_FILE_CHARS = 20_000

TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": (
            "List all source files in the repository as relative paths. "
            "Call this first to get an overview of the codebase."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from the repository. Returns the content with line numbers. "
            "Path must be relative to the repo root, e.g. 'src/utils.py'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative file path"}},
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Search all repository files for a regular expression. Returns matching "
            "lines as 'path:line_number: line'. Useful for finding where a function "
            "is defined or called."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "description": "Python regex"}},
            "required": ["pattern"],
        },
    },
    {
        "name": "write_test",
        "description": (
            "Write a pytest file into the agent workspace (NOT into the repo). "
            "The test must assert the CORRECT behavior per the spec/docstrings, so it "
            "fails against buggy code. The target repo's modules are importable "
            "directly, e.g. 'import calculator'. Use a filename like "
            "'test_hypothesis_1.py'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "e.g. test_hypothesis_1.py"},
                "content": {"type": "string", "description": "Full pytest file content"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": (
            "Run a previously written test file with pytest in a sandboxed subprocess. "
            "Exit code 1 with assertion failures means the bug is REPRODUCED (the code "
            "does not meet the spec). Exit code 0 means your hypothesis was wrong. "
            "Exit code 2+ means your test itself has an error — fix and retry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string", "description": "Test file to run"}},
            "required": ["filename"],
        },
    },
    {
        "name": "report_bug",
        "description": (
            "Record a finding. Use status 'confirmed' ONLY if a test you wrote failed "
            "against the current code, proving the bug. Otherwise use 'suspected'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "One-line summary"},
                "file": {"type": "string", "description": "File containing the bug"},
                "line": {"type": "integer", "description": "Approximate line number"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "status": {"type": "string", "enum": ["confirmed", "suspected"]},
                "description": {
                    "type": "string",
                    "description": "What is wrong, what the correct behavior is, and how it was verified",
                },
                "test_file": {
                    "type": "string",
                    "description": "The failing test that proves it (required for confirmed)",
                },
            },
            "required": ["title", "file", "severity", "status", "description"],
        },
    },
]


class ToolBox:
    """Executes tool calls against one repository."""

    def __init__(self, repo_root: Path, workspace: Path | None = None):
        self.repo_root = repo_root.resolve()
        if not self.repo_root.is_dir():
            raise ValueError(f"Repo root does not exist: {self.repo_root}")
        self.workspace = (workspace or self.repo_root.parent / ".agent_workspace").resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.findings: list[dict] = []
        self.tests_written: dict[str, Path] = {}
        self.test_runs: dict[str, dict] = {}  # filename -> last run result

    # ---- dispatch -------------------------------------------------------

    def dispatch(self, name: str, tool_input: dict) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"ERROR: unknown tool '{name}'"
        try:
            return handler(**tool_input)
        except TypeError as exc:
            return f"ERROR: bad arguments for {name}: {exc}"
        except Exception as exc:  # surface errors to the model, don't crash the loop
            return f"ERROR: {type(exc).__name__}: {exc}"

    # ---- path safety ----------------------------------------------------

    def _safe_repo_path(self, rel: str) -> Path:
        path = (self.repo_root / rel).resolve()
        if self.repo_root not in path.parents and path != self.repo_root:
            raise PermissionError(f"Path escapes repo root: {rel}")
        return path

    # ---- tools ----------------------------------------------------------

    def _tool_list_files(self) -> str:
        files = []
        for path in sorted(self.repo_root.rglob("*")):
            if path.is_dir():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(str(path.relative_to(self.repo_root)))
        return "\n".join(files) if files else "(repository is empty)"

    def _tool_read_file(self, path: str) -> str:
        target = self._safe_repo_path(path)
        if not target.is_file():
            return f"ERROR: no such file: {path}"
        text = target.read_text(errors="replace")
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n... [truncated]"
        lines = text.splitlines()
        return "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines))

    def _tool_search_code(self, pattern: str) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"ERROR: invalid regex: {exc}"
        hits = []
        for path in sorted(self.repo_root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(self.repo_root)
            for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel}:{i}: {line.strip()}")
                if len(hits) >= 100:
                    return "\n".join(hits) + "\n... [more matches truncated]"
        return "\n".join(hits) if hits else "(no matches)"

    def _tool_write_test(self, filename: str, content: str) -> str:
        if "/" in filename or "\\" in filename or not filename.endswith(".py"):
            return "ERROR: filename must be a bare .py filename, e.g. test_hypothesis_1.py"
        path = self.workspace / filename
        path.write_text(content)
        self.tests_written[filename] = path
        return f"Wrote {filename} ({len(content)} chars) to the workspace."

    def _tool_run_tests(self, filename: str) -> str:
        path = self.tests_written.get(filename)
        if path is None:
            return f"ERROR: no test named {filename} has been written yet."
        result = run_pytest(path, self.repo_root)
        self.test_runs[filename] = result
        verdict = (
            "ALL TESTS PASSED — hypothesis NOT confirmed."
            if result["passed"]
            else "TESTS FAILED — if failures are assertion errors, the bug is reproduced."
        )
        return f"exit_code={result['exit_code']}\n{verdict}\n\n{result['output']}"

    def _tool_report_bug(
        self,
        title: str,
        file: str,
        severity: str,
        status: str,
        description: str,
        line: int | None = None,
        test_file: str | None = None,
    ) -> str:
        # Enforce the confirmation rule mechanically, not just by prompt.
        if status == "confirmed":
            run = self.test_runs.get(test_file or "")
            if run is None or run["passed"]:
                return (
                    "REJECTED: 'confirmed' requires a test_file that you ran and that "
                    "FAILED. Run a failing test first, or report as 'suspected'."
                )
        finding = {
            "title": title,
            "file": file,
            "line": line,
            "severity": severity,
            "status": status,
            "description": description,
            "test_file": test_file,
        }
        self.findings.append(finding)
        return f"Recorded {status} bug #{len(self.findings)}: {title}"

    # ---- persistence ----------------------------------------------------

    def save_findings(self, path: Path) -> None:
        path.write_text(json.dumps(self.findings, indent=2))
