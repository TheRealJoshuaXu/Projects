"""
A minimal agentic loop over the statistical process control tools.

The point of this file: the model is NOT doing the statistics. It decides
which tool to call, on which parameter, in what order, and when it has
enough to draw a conclusion. Each cycle is

    request -> model picks a tool -> this code runs it -> result returned -> request again

and it repeats until the model answers with no further tool call. That is
what makes the loop agentic rather than a fixed script.

Run:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python agent.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spc_tools
from anthropic import Anthropic

MODEL = "claude-sonnet-4-5"      # any current model works; check the docs for names
MAX_TURNS = 25

# ---- Tool schemas. Name, description, and a JSON Schema for the inputs. ----
# The description is what the model reads to decide whether a tool applies,
# so it is worth writing carefully.
TOOLS = [
    {
        "name": "load_data",
        "description": (
            "Load a CSV of process measurements into memory. Call this first. "
            "Returns the row count and the list of measured parameters available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the CSV file."}},
            "required": ["path"],
        },
    },
    {
        "name": "control_limits",
        "description": (
            "Compute the centre line and the 1, 2 and 3 sigma control limits for one "
            "parameter, using the first 40 runs as the baseline period. Use this before "
            "interpreting violations so you know how large a deviation actually is."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"parameter": {"type": "string"}},
            "required": ["parameter"],
        },
    },
    {
        "name": "find_violations",
        "description": (
            "Apply the four standard Western Electric rules to one parameter and return "
            "the run indices that violate each rule. Rule 1 is a point beyond 3 sigma, "
            "rule 2 is two of three beyond 2 sigma on one side, rule 3 is four of five "
            "beyond 1 sigma on one side, rule 4 is eight consecutive points on one side "
            "of the centre line. Many rule 3 and rule 4 flags starting at the same run "
            "usually indicate a sustained shift rather than isolated noise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"parameter": {"type": "string"}},
            "required": ["parameter"],
        },
    },
    {
        "name": "capability",
        "description": (
            "Compute Cp and Cpk for one parameter against supplied specification limits, "
            "plus the count of points outside those limits. Use this to tell whether a "
            "parameter that looks bad is actually an incapable process or a specification "
            "limit set in the wrong place."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string"},
                "lsl": {"type": "number", "description": "Lower specification limit."},
                "usl": {"type": "number", "description": "Upper specification limit."},
            },
            "required": ["parameter", "lsl", "usl"],
        },
    },
    {
        "name": "plot_chart",
        "description": "Write an individuals control chart PNG for one parameter and return the filename.",
        "input_schema": {
            "type": "object",
            "properties": {"parameter": {"type": "string"}},
            "required": ["parameter"],
        },
    },
]

SYSTEM = """You are a process engineer triaging statistical process control data.

Work through the parameters in the dataset. For each one, establish the control
limits, check the Western Electric rules, and decide whether anything you see is
a real process shift or an artifact of how the parameter is being measured or
specified.

Be sceptical of specification limits. A parameter can be perfectly stable and
still show terrible capability if its limits are wrong, and the correct action
in that case is to fix the limit, not the process. Say which case you think each
parameter is, and say what evidence made you think so.

Finish with a short written summary: one line per parameter, the verdict, and
what you would do next. Do not do arithmetic yourself; use the tools."""


def run(prompt: str) -> None:
    client = Anthropic()          # reads ANTHROPIC_API_KEY
    messages = [{"role": "user", "content": prompt}]

    for turn in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        # Show the model's reasoning text as it goes.
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                print(block.text)

        if resp.stop_reason != "tool_use":
            print("\n--- done, no further tool calls ---")
            return

        # Append the assistant turn, then run every tool it asked for.
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            fn = spc_tools.REGISTRY.get(block.name)
            print(f"  [tool] {block.name}({json.dumps(block.input)})")
            try:
                out = fn(**block.input) if fn else json.dumps({"error": "unknown tool"})
                is_error = False
            except Exception as exc:                 # hand errors back, don't crash
                out, is_error = json.dumps({"error": str(exc)}), True
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": out,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    print("\n--- hit MAX_TURNS ---")


if __name__ == "__main__":
    run(
        "Review every parameter in process_data.csv. The engineering specification "
        "for resistance_ohm is 245 to 252 ohms. Flag what is out of control, and tell "
        "me which problems are real process shifts and which are measurement or "
        "specification artifacts."
    )
