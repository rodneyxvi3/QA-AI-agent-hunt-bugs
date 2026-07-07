"""The agent loop: call the model, execute its tool calls, feed results back.

This ~100-line loop is the heart of the project. The model decides which
tools to use and when; we just execute them and return the results until
the model stops asking for tools (or we hit the step limit).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import anthropic

from .prompts import SYSTEM_PROMPT, build_task_prompt
from .tools import TOOL_SCHEMAS, ToolBox

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

# on_event(kind, text) receives a live trace of the run.
# kinds: "thought" | "tool_call" | "tool_result" | "info" | "done"
EventHandler = Callable[[str, str], None]


class BugHunterAgent:
    def __init__(
        self,
        repo_root: str | Path,
        model: str = DEFAULT_MODEL,
        max_steps: int = 30,
        on_event: EventHandler | None = None,
        client: anthropic.Anthropic | None = None,
    ):
        self.repo_root = Path(repo_root)
        self.model = model
        self.max_steps = max_steps
        self.on_event = on_event or (lambda kind, text: None)
        self.client = client or anthropic.Anthropic()
        self.toolbox = ToolBox(self.repo_root)
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    # ---- public API ------------------------------------------------------

    def run(self, focus: str | None = None) -> dict:
        """Run the hunt. Returns findings, the model's summary, and usage."""
        task = build_task_prompt(
            f"It is a Python project located at '{self.repo_root.name}'.", focus
        )
        messages: list[dict] = [{"role": "user", "content": task}]
        summary_parts: list[str] = []

        step = 0
        for step in range(1, self.max_steps + 1):
            response = self._call_api(messages)
            self.usage["input_tokens"] += response.usage.input_tokens
            self.usage["output_tokens"] += response.usage.output_tokens

            # The assistant turn goes back into history verbatim.
            messages.append({"role": "assistant", "content": response.content})

            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self.on_event("thought", block.text.strip())
                    summary_parts = [block.text.strip()]  # keep the latest text

            if response.stop_reason != "tool_use":
                break  # the agent is done

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                self.on_event("tool_call", f"{block.name}({_short(block.input)})")
                output = self.toolbox.dispatch(block.name, block.input)
                self.on_event("tool_result", _truncate(output, 600))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        else:
            self.on_event("info", f"Stopped: reached max_steps={self.max_steps}.")

        self.on_event("done", f"Finished in {step} step(s).")
        return {
            "findings": self.toolbox.findings,
            "summary": summary_parts[0] if summary_parts else "",
            "steps": step,
            "usage": dict(self.usage),
        }

    # ---- internals ---------------------------------------------------------

    def _call_api(self, messages: list[dict]):
        """One API call with basic retry on rate limits / transient errors."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
            except (anthropic.RateLimitError, anthropic.APIStatusError) as exc:
                last_exc = exc
                wait = 2 ** (attempt + 1)
                self.on_event("info", f"API error ({exc.__class__.__name__}), retrying in {wait}s...")
                time.sleep(wait)
        raise RuntimeError(f"API call failed after retries: {last_exc}")


def _short(tool_input: dict, limit: int = 120) -> str:
    parts = []
    for key, value in tool_input.items():
        text = str(value).replace("\n", " ")
        if len(text) > limit:
            text = text[:limit] + "..."
        parts.append(f"{key}={text!r}")
    return ", ".join(parts)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n... [truncated in trace]"
