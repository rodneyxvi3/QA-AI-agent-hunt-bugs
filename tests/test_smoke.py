"""Smoke tests — run with `pytest tests/ -q`. No API key required.

A scripted fake client stands in for the real model, so the entire
pipeline is exercised offline: agent loop -> tool dispatch -> sandboxed
pytest run -> confirmation-rule enforcement -> Markdown report.
"""

import shutil
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from bug_hunter.agent import BugHunterAgent
from bug_hunter.report import render_markdown
from bug_hunter.tools import ToolBox

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPRO_TEST = """\
from inventory import apply_discount

def test_discount_applies_at_threshold():
    # Docstring: 10% off for orders of 100.00 or more
    assert apply_discount(150.0) == 135.0

def test_no_discount_below_threshold():
    assert apply_discount(50.0) == 50.0
"""


def _text(t):
    return NS(type="text", text=t)


def _tool(i, name, inp):
    return NS(type="tool_use", id=f"tu_{i}", name=name, input=inp)


def _script():
    """The fake model's turn-by-turn behavior, including one cheat attempt."""
    report = {
        "title": "Discount comparison inverted",
        "file": "inventory.py",
        "line": 12,
        "severity": "high",
        "status": "confirmed",
        "description": "apply_discount uses < instead of >= at the threshold.",
        "test_file": "test_h1.py",
    }
    cheat = dict(report, title="Cheat attempt (before running the test)")
    return [
        ("tool_use", [_text("Mapping the repo."), _tool(1, "list_files", {})]),
        ("tool_use", [_tool(2, "read_file", {"path": "inventory.py"})]),
        ("tool_use", [_tool(3, "write_test", {"filename": "test_h1.py", "content": REPRO_TEST})]),
        ("tool_use", [_tool(4, "report_bug", cheat)]),  # must be REJECTED
        ("tool_use", [_tool(5, "run_tests", {"filename": "test_h1.py"})]),
        ("tool_use", [_tool(6, "report_bug", report)]),  # now legitimate
        ("end_turn", [_text("Done. One confirmed bug in inventory.py.")]),
    ]


class FakeClient:
    def __init__(self, script):
        self._script = list(script)
        self.messages = NS(create=self._create)

    def _create(self, **kwargs):
        stop_reason, content = self._script.pop(0)
        return NS(
            content=content,
            stop_reason=stop_reason,
            usage=NS(input_tokens=100, output_tokens=50),
        )


@pytest.fixture
def repo(tmp_path):
    """A throwaway copy of the seeded demo repo (keeps the original pristine)."""
    dst = tmp_path / "repo"
    shutil.copytree(PROJECT_ROOT / "target_repo", dst)
    return dst


def test_full_loop_confirms_seeded_bug(repo):
    events = []
    agent = BugHunterAgent(
        repo, client=FakeClient(_script()), on_event=lambda k, t: events.append((k, t))
    )
    result = agent.run()

    # The seeded inventory bug was really reproduced by the sandboxed test run.
    assert len(result["findings"]) == 1
    assert result["findings"][0]["status"] == "confirmed"
    assert result["steps"] == 7

    # The premature 'confirmed' report (before running the test) was rejected.
    rejections = [t for k, t in events if k == "tool_result" and t.startswith("REJECTED")]
    assert len(rejections) == 1

    # The report renders with the finding in it.
    md = render_markdown(result["findings"], "repo", result["summary"], result["usage"])
    assert "CONFIRMED" in md and "inventory.py" in md


def test_confirmed_without_failing_test_is_rejected(repo):
    toolbox = ToolBox(repo)
    out = toolbox.dispatch(
        "report_bug",
        {
            "title": "x", "file": "inventory.py", "severity": "low",
            "status": "confirmed", "description": "no proof", "test_file": "nope.py",
        },
    )
    assert out.startswith("REJECTED")
    assert toolbox.findings == []


def test_path_traversal_is_blocked(repo):
    toolbox = ToolBox(repo)
    out = toolbox.dispatch("read_file", {"path": "../../../etc/passwd"})
    assert out.startswith("ERROR")


def test_sandbox_reports_passing_tests(repo):
    toolbox = ToolBox(repo)
    toolbox.dispatch(
        "write_test",
        {"filename": "test_ok.py", "content": "def test_true():\n    assert True\n"},
    )
    out = toolbox.dispatch("run_tests", {"filename": "test_ok.py"})
    assert "exit_code=0" in out and "NOT confirmed" in out
