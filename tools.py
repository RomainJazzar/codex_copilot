"""
The tools the LLM can use.

Each tool is two things:
    1. a normal Python function (what actually runs on our machine)
    2. a "schema" (a description in JSON so the LLM knows the tool exists
       and which arguments to give)

The LLM NEVER runs anything itself. It only says "please call read_file
with path=X". Our code decides whether to do it, then sends back the result.
"""

import json
import subprocess
from pathlib import Path

DRY_RUN = False  # set to True by agent.py with --dry-run

# Commands we refuse no matter what (simple text search in the command).
FORBIDDEN = ["rm -rf", "sudo", "mkfs", "shutdown", "reboot", "format", "dd if=", ":(){"]


# --- 1. The tool functions ---------------------------------------------------
def read_file(path):
    """Return the text content of a file."""
    return Path(path).read_text(encoding="utf-8")


def list_files(path="."):
    """List what is inside a folder (folders end with '/')."""
    items = sorted(Path(path).iterdir())
    return "\n".join(p.name + ("/" if p.is_dir() else "") for p in items)


def edit_file(path, old_text, new_text):
    """Replace old_text with new_text in a file.
    If old_text is empty, the file is created (or overwritten) with new_text."""
    if DRY_RUN:
        return f"[dry-run] would edit {path}"

    file = Path(path)
    if old_text == "":
        file.write_text(new_text, encoding="utf-8")
        return f"Wrote {path}"

    content = file.read_text(encoding="utf-8")
    # We require exactly one match, so the LLM can't edit the wrong place by accident.
    if content.count(old_text) != 1:
        return "Error: old_text must appear exactly once in the file."
    file.write_text(content.replace(old_text, new_text), encoding="utf-8")
    return f"Edited {path}"


def run_shell(command):
    """Run a shell command, with 3 safety layers:
    forbidden list -> dry-run -> user confirmation."""
    if any(bad in command for bad in FORBIDDEN):
        return "Refused: this command is forbidden."
    if DRY_RUN:
        return f"[dry-run] would run: {command}"
    if input(f"  Run `{command}` ? (y/n) ").strip().lower() != "y":
        return "The user refused to run this command."

    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    return (result.stdout + result.stderr) or f"(no output, exit code {result.returncode})"


def git_status():
    """Show the git status of the current folder (read-only, so no confirmation)."""
    result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
    return (result.stdout + result.stderr) or "Nothing to commit, working tree clean."


# --- 2. The schemas (what the LLM sees) --------------------------------------
def schema(name, description, **params):
    """Small helper to build a tool description in the OpenAI format.
    Each extra argument becomes a text parameter: name="its description"."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {p: {"type": "string", "description": d} for p, d in params.items()},
                "required": list(params),
            },
        },
    }


TOOLS_SCHEMA = [
    schema("read_file", "Read a text file.", path="Path of the file"),
    schema("list_files", "List files in a folder.", path="Folder path, '.' for current"),
    schema("edit_file", "Replace old_text by new_text in a file. Empty old_text creates the file.",
           path="Path of the file", old_text="Exact text to replace", new_text="New text"),
    schema("run_shell", "Run a shell command (the user must confirm).", command="The command"),
    schema("git_status", "Show the git status of the project."),
]


# --- 3. The orchestrator (router) --------------------------------------------
# A dictionary: tool name -> Python function. Adding a tool = one more line here.
FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "edit_file": edit_file,
    "run_shell": run_shell,
    "git_status": git_status,
}


def run_tool(name, json_args):
    """Find the right function, call it, and ALWAYS return a string.
    If anything fails, the error goes back to the LLM as text: the program never crashes,
    and the LLM can read the error and try something else."""
    try:
        args = json.loads(json_args or "{}")   # '{"path": "a.txt"}' -> {"path": "a.txt"}
        result = FUNCTIONS[name](**args)        # unknown name -> KeyError, caught below
    except Exception as error:
        result = f"Error: {type(error).__name__}: {error}"
    return str(result)[:10_000]  # cut very long outputs so we don't flood the context
