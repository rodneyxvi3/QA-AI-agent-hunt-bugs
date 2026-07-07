"""Streamlit demo UI: watch the agent hunt in real time.

Run with:  streamlit run app.py
"""

import os

import streamlit as st
from dotenv import load_dotenv

from bug_hunter.agent import DEFAULT_MODEL, BugHunterAgent
from bug_hunter.report import render_markdown

load_dotenv()

st.set_page_config(page_title="AI Bug Hunter", page_icon=None, layout="wide")
st.title("AI Bug Hunter")
st.caption("An agent that finds bugs and proves them with failing tests.")

with st.sidebar:
    repo = st.text_input("Repository path", value="target_repo")
    model = st.text_input("Model", value=DEFAULT_MODEL)
    max_steps = st.slider("Max agent steps", 5, 60, 30)
    focus = st.text_input("Focus (optional)", placeholder="e.g. the pricing logic")
    run_clicked = st.button("Hunt bugs", type="primary", use_container_width=True)

if run_clicked:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("Set ANTHROPIC_API_KEY in a .env file or your environment first.")
        st.stop()

    trace_col, result_col = st.columns([3, 2])

    with trace_col:
        st.subheader("Agent trace")
        status = st.status("Agent is hunting...", expanded=True)

        def on_event(kind: str, text: str) -> None:
            with status:
                if kind == "thought":
                    st.markdown(text)
                elif kind == "tool_call":
                    st.code(text, language="text")
                elif kind == "tool_result":
                    with st.expander("tool result", expanded=False):
                        st.text(text)
                else:
                    st.caption(text)

        agent = BugHunterAgent(
            repo, model=model, max_steps=max_steps, on_event=on_event
        )
        try:
            result = agent.run(focus=focus or None)
            status.update(label="Hunt complete", state="complete", expanded=False)
        except Exception as exc:
            status.update(label="Hunt failed", state="error")
            st.exception(exc)
            st.stop()

    with result_col:
        st.subheader("Findings")
        confirmed = [f for f in result["findings"] if f["status"] == "confirmed"]
        suspected = [f for f in result["findings"] if f["status"] == "suspected"]
        a, b, c = st.columns(3)
        a.metric("Confirmed", len(confirmed))
        b.metric("Suspected", len(suspected))
        c.metric("Steps", result["steps"])

        markdown = render_markdown(
            result["findings"], agent.repo_root.name, result["summary"], result["usage"]
        )
        st.markdown(markdown)
        st.download_button(
            "Download report (.md)", markdown, file_name="bug_report.md",
            use_container_width=True,
        )
else:
    st.info("Point the agent at a repo in the sidebar and click **Hunt bugs**. "
            "The default `target_repo` has three planted bugs to find.")
