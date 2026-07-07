"""Turn the agent's findings into a Markdown bug report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_STATUS_ORDER = {"confirmed": 0, "suspected": 1}


def render_markdown(findings: list[dict], repo_name: str, summary: str, usage: dict) -> str:
    confirmed = [f for f in findings if f["status"] == "confirmed"]
    suspected = [f for f in findings if f["status"] == "suspected"]
    ordered = sorted(
        findings,
        key=lambda f: (_STATUS_ORDER[f["status"]], _SEVERITY_ORDER.get(f["severity"], 3)),
    )

    lines = [
        f"# Bug report: `{repo_name}`",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} — "
        f"{len(confirmed)} confirmed, {len(suspected)} suspected. "
        f"Tokens used: {usage.get('input_tokens', 0):,} in / {usage.get('output_tokens', 0):,} out.",
        "",
    ]

    for i, f in enumerate(ordered, 1):
        badge = "CONFIRMED" if f["status"] == "confirmed" else "Suspected"
        location = f["file"] + (f", line {f['line']}" if f.get("line") else "")
        lines += [
            f"## {i}. [{badge}] {f['title']}",
            "",
            f"- **Location:** `{location}`",
            f"- **Severity:** {f['severity']}",
        ]
        if f.get("test_file"):
            lines.append(f"- **Proven by:** `{f['test_file']}` (failing test)")
        lines += ["", f["description"], ""]

    if summary:
        lines += ["---", "", "## Agent summary", "", summary, ""]

    return "\n".join(lines)


def save_report(markdown: str, out_dir: str | Path = "reports") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"bug_report_{datetime.now():%Y%m%d_%H%M%S}.md"
    path.write_text(markdown)
    return path
