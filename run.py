"""CLI entry point.

Usage:
    python run.py                       # hunt bugs in the seeded demo repo
    python run.py path/to/some/repo    # hunt bugs in any local Python repo
    python run.py --focus "the pricing logic"
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from bug_hunter.agent import DEFAULT_MODEL, BugHunterAgent
from bug_hunter.report import render_markdown, save_report

PREFIX = {
    "thought": "\n[agent] ",
    "tool_call": "  -> ",
    "tool_result": "  <- ",
    "info": "  [!] ",
    "done": "\n[done] ",
}


def on_event(kind: str, text: str) -> None:
    indent = " " * len(PREFIX[kind].lstrip("\n"))
    body = text.replace("\n", "\n" + indent)
    print(f"{PREFIX[kind]}{body}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI bug-hunting agent")
    parser.add_argument("repo", nargs="?", default="target_repo", help="Path to the repo to hunt in")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--focus", default=None, help="Optional area to focus on")
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: set ANTHROPIC_API_KEY in your environment or a .env file.")
        return 1

    agent = BugHunterAgent(
        args.repo, model=args.model, max_steps=args.max_steps, on_event=on_event
    )
    result = agent.run(focus=args.focus)

    markdown = render_markdown(
        result["findings"], agent.repo_root.name, result["summary"], result["usage"]
    )
    path = save_report(markdown)
    confirmed = sum(1 for f in result["findings"] if f["status"] == "confirmed")
    print(f"\n{confirmed} confirmed / {len(result['findings'])} total findings.")
    print(f"Report written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
