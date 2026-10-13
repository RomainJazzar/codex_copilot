# CodexPilot Code

A minimal AI coding agent for the terminal, written in plain Python with no agent framework.
It is a small version of tools like Claude Code or Codex CLI: **an LLM + a loop + a few tools.**

## Quick start (under 5 minutes)

```bash
git clone https://github.com/<you>/codex-pilot-code
cd codex-pilot-code
pip install -r requirements.txt
cp .env.example .env        # then put your API key in .env
python agent.py
```

Try: `read agent.py and explain it`, `list the files`, `run git log --oneline -5`.

Safe mode, where shell commands and file edits are only simulated:

```bash
python agent.py --dry-run
```

## Architecture

```
codex-pilot-code/
├── agent.py           # the REPL + the agentic loop
├── tools.py           # the tools, their schemas, and the router
├── system_prompt.md   # instructions given to the LLM at startup
├── .env.example       # API key / model configuration
└── requirements.txt
```

### The agentic loop

```
 you ──> history ──> LLM ──┬── text answer ──> printed, back to you
              ^            │
              │            └── "call tool X with args Y"
              │                        │
              └──── tool result <── run_tool() runs X
```

1. Your message is added to the **history** (a Python list kept on our side: the API is stateless).
2. The full history + the list of tools is sent to the LLM.
3. If the LLM asks for a tool, `run_tool()` runs it and adds the result to the history.
4. Back to step 2, until the LLM answers with plain text.

### Tools

| Tool | What it does | Safety |
|---|---|---|
| `read_file` | read a file | read-only |
| `list_files` | list a folder | read-only |
| `edit_file` | replace text in a file / create a file | exact single match required, dry-run |
| `run_shell` | run a shell command | forbidden list, dry-run, user confirmation |
| `git_status` | `git status --short` | read-only |

Adding a tool = write a function, add its `schema(...)`, add one line to `FUNCTIONS`.

### Error handling

- A failing tool never crashes the program: the error is sent back to the LLM as text, so it can try something else.
- A failing API call (no internet, bad key) is printed and the REPL keeps running.

## LLM provider

Any OpenAI-compatible API works, configured in `.env` (`API_KEY`, `BASE_URL`, `MODEL`).
Default: [OpenRouter](https://openrouter.ai) with a GLM model.
