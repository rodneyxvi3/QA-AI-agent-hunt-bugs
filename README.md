# AI Bug Hunter

An autonomous QA agent that hunts for bugs in Python repositories — and **proves** every bug it reports by writing a failing test.

The core idea: LLMs confidently hallucinate bugs that don't exist. So this agent is only allowed to mark a bug as *confirmed* if it wrote a pytest test asserting the correct behavior and watched that test **fail** against the current code. Unproven findings are downgraded to *suspected*. The rule is enforced mechanically in code (`report_bug` rejects unverified "confirmed" claims), not just in the prompt.

## How it works

```
repo/PR  ->  triage  ->  hypothesize  ->  verify in sandbox  ->  report
                              ^                  |
                              +---- refuted -----+
```

The agent is a single tool-use loop (`bug_hunter/agent.py`, ~100 lines). The model gets six tools and decides on its own which to call and when:

| Tool | What it does |
|---|---|
| `list_files` | Map the repository |
| `read_file` | Read a file with line numbers |
| `search_code` | Regex search across the repo |
| `write_test` | Write a pytest file into an isolated workspace |
| `run_tests` | Run it in a sandboxed subprocess with a timeout |
| `report_bug` | Record a finding (confirmed claims require a failing test run) |

## Quickstart

```bash
pip install -r requirements.txt
pytest tests/ -q            # smoke test — verifies everything works, no API key needed
cp .env.example .env        # then paste your Anthropic API key into .env

python run.py               # hunt in the seeded demo repo (target_repo/)
streamlit run app.py        # or watch it live in a UI
```

The smoke test uses a scripted fake model to exercise the full pipeline offline — the agent loop, tool dispatch, the sandboxed pytest run against a seeded bug, the confirmation-rule enforcement (including rejecting a premature "confirmed" claim), and report rendering.

Point it at any local Python repo:

```bash
python run.py path/to/repo --focus "the payment logic"
```

## The seeded demo repo

`target_repo/` contains three deliberately planted bugs so you can watch the full hypothesize→verify loop work end to end.

<details>
<summary>Spoilers — the three planted bugs</summary>

1. `calculator.py` — `sum_up_to(n)` uses `range(1, n)`, excluding `n` (off-by-one).
2. `inventory.py` — `apply_discount` uses `<` instead of `>=`, discounting small orders and charging big ones full price (inverted comparison).
3. `utils.py` — `normalize_name` calls `.strip()` on input that is documented to allow `None` (unhandled `None` → `AttributeError`).

</details>

## Project structure

```
bug_hunter/
  agent.py      # the tool-use loop (the heart of the project)
  tools.py      # tool schemas + implementations, path-safety, confirmation rule
  sandbox.py    # subprocess pytest runner with timeout
  prompts.py    # system prompt encoding the QA methodology
  report.py     # Markdown report generation
run.py          # CLI with live trace
app.py          # Streamlit demo UI
target_repo/    # seeded buggy repo for the demo
```

## Design decisions worth asking me about

- **Verification over vibes.** A finding is only "confirmed" with a failing repro test. This turns the LLM's biggest weakness (hallucination) into the project's central feature.
- **Mechanical enforcement.** The confirmation rule lives in `ToolBox._tool_report_bug`, so even a misbehaving model can't inflate a suspicion into a confirmed bug.
- **Sandboxing.** Tests run in a separate process with a hard timeout and truncated output. For arbitrary third-party repos, upgrade to a Docker container with no network (on the roadmap).
- **Cost control.** Tool outputs are truncated before they re-enter the context; a `max_steps` cap bounds every run. A full hunt on the demo repo typically costs a few cents.

## Roadmap

- [ ] **PR mode** — feed only a diff plus surrounding context instead of a whole repo
- [ ] **Docker sandbox** — no-network, read-only-FS container for untrusted repos
- [ ] **Quantitative evals** — check out commits just *before* known bug fixes in open-source repos and measure precision/recall of the agent's findings
- [ ] **GitHub Action** — comment findings directly on pull requests

## Swapping providers

Only `agent.py` touches the model API. To use a different provider, replace `_call_api` and the tool-schema format in `tools.py`; the loop, sandbox, and reporting are provider-agnostic.

<img width="796" height="396" alt="image" src="https://github.com/user-attachments/assets/58c6d864-eb44-4584-b11e-e0d7dc0792a0" />


<img width="959" height="1320" alt="image" src="https://github.com/user-attachments/assets/1384a70e-7518-4904-b3d8-a92a8d98ed6b" />
