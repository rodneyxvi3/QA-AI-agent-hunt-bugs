"""Run agent-written pytest files in a subprocess with a hard timeout.

This is a minimal sandbox: a separate process, a time limit, and truncated
output. It is fine for repos you trust (like the seeded demo repo). Before
pointing the agent at arbitrary third-party code, upgrade this to run inside
a container (Docker) with no network and a read-only filesystem.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MAX_OUTPUT_CHARS = 4_000


def run_pytest(test_path: Path, repo_root: Path, timeout: int = 30) -> dict:
    """Execute one pytest file. Returns {exit_code, passed, output}.

    pytest exit codes: 0 = all passed, 1 = tests failed (bug reproduced!),
    2+ = errors (collection failure, import error, crash).
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_path),
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]
    env = os.environ.copy()
    # Make the target repo importable from the test file.
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(repo_root),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "passed": False,
            "output": f"Test run timed out after {timeout}s (possible infinite loop).",
        }

    output = (proc.stdout + "\n" + proc.stderr).strip()
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... [output truncated]"

    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "output": output,
    }
