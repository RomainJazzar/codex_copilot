"""
CodexPilot Code - a minimal AI agent in the terminal.

The whole idea in one sentence:
    an agent = an LLM + a loop + a few tools.

How it works:
    1. You type a message (the REPL).
    2. We send the WHOLE conversation history to the LLM
       (the server is stateless: it remembers nothing between calls).
    3. If the LLM asks to use a tool, we run it ourselves and send back the result.
    4. We repeat step 3 until the LLM answers with plain text.
    5. The history is saved in history.json so it survives a restart.

Run:
    python agent.py
    python agent.py --dry-run
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

import tools


# --- Configuration -----------------------------------------------------------

load_dotenv()

BASE_DIR = Path(__file__).parent

client = OpenAI(
    base_url=os.getenv("BASE_URL", "https://openrouter.ai/api/v1"),
    api_key=os.getenv("API_KEY"),
)

MODEL = os.getenv("MODEL", "z-ai/glm-5.3-flash")

# --dry-run simulates edits and shell commands instead of really doing them.
tools.DRY_RUN = "--dry-run" in sys.argv

# Load the system prompt.
SYSTEM_PROMPT = (BASE_DIR / "system_prompt.md").read_text(encoding="utf-8")

# File used to remember the conversation between program restarts.
HISTORY_FILE = BASE_DIR / "history.json"


# --- Persistent history ------------------------------------------------------

def load_history():
    """Load previous conversation history from history.json."""
    if not HISTORY_FILE.exists():
        return []

    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

        # The file should contain a list of messages.
        if isinstance(history, list):
            return history

    except Exception as error:
        print(f"[history] Could not load history: {error}")

    return []


def save_history(messages):
    """Save the conversation history to history.json.

    We do not save the system prompt because it is loaded separately
    from system_prompt.md every time the program starts.
    """
    try:
        HISTORY_FILE.write_text(
            json.dumps(messages[1:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as error:
        print(f"[history] Could not save history: {error}")


# --- The agentic loop --------------------------------------------------------

def agent_turn(messages):
    """Let the LLM work until it gives a final text answer.

    messages contains the conversation history.
    """

    while True:

        # 1. Send the history and available tools to the LLM.
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools.TOOLS_SCHEMA,
        )

        message = response.choices[0].message

        # 2. Add the LLM answer to the history.
        messages.append(
            message.model_dump(exclude_none=True)
        )

        # Save immediately so the new message is remembered.
        save_history(messages)

        # 3. If no tool was requested, we have the final answer.
        if not message.tool_calls:
            print(f"\n{message.content}")
            return

        # 4. Otherwise execute every requested tool.
        for call in message.tool_calls:
            name = call.function.name
            args = call.function.arguments

            print(f"  [tool] {name} {args}")

            result = tools.run_tool(name, args)

            # Add the tool result to the history.
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

            save_history(messages)

        # The loop starts again so the LLM can read the tool results.


# --- The REPL (Read - Eval - Print - Loop) ----------------------------------

def main():

    if not os.getenv("API_KEY"):
        sys.exit(
            "Missing API_KEY. Copy .env.example to .env and put your key in it."
        )

    print(
        f"CodexPilot Code - model: {MODEL}"
        + ("  [DRY-RUN]" if tools.DRY_RUN else "")
    )

    # Load old messages from history.json.
    old_history = load_history()

    # System prompt is always the first message.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *old_history,
    ]

    print(f"History loaded: {len(old_history)} messages.")
    print("Type 'exit' to quit.")

    while True:

        try:
            user_input = input("\n> ").strip()

        except (KeyboardInterrupt, EOFError):
            break

        if user_input in ("exit", "quit"):
            break

        if not user_input:
            continue

        # Add the user's message.
        messages.append({
            "role": "user",
            "content": user_input,
        })

        # Save it immediately.
        save_history(messages)

        try:
            agent_turn(messages)

        except Exception as error:
            print(f"\n[API error] {error}")

            # Keep whatever history we have even if the API failed.
            save_history(messages)

    print("Bye!")


if __name__ == "__main__":
    main()