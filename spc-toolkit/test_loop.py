"""
Offline check of the dispatch logic, no API key needed.
Fakes the model's tool_use blocks and confirms every tool runs and returns
valid JSON, including the error path for a bad argument.
Run from the repository root: the CSV paths are relative.
"""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spc_tools
import spc_server

# The MCP server is what Claude Code actually sees, so check against it
# rather than agent.py (which needs the anthropic package and API credits).
TOOLS = [{"name": t.name} for t in asyncio.run(spc_server.mcp.list_tools())]

class B:
    def __init__(s, name, inp, expect_error=False):
        s.type, s.name, s.input, s.id = "tool_use", name, inp, "t1"
        s.expect_error = expect_error

fake_calls = [
    B("load_data", {"path": "process_data.csv"}),
    B("control_limits", {"parameter": "thickness_nm"}),
    B("find_violations", {"parameter": "thickness_nm"}),
    B("capability", {"parameter": "resistance_ohm", "lsl": 245.0, "usl": 252.0}),
    B("plot_chart", {"parameter": "resistance_ohm"}),
    B("correlate_parameters", {}),
    B("trend_test", {"parameter": "thickness_nm"}),
    B("yield_summary", {"parameter": "resistance_ohm", "lsl": 245.0, "usl": 252.0}),
    B("find_violations", {"parameter": "does_not_exist"}, expect_error=True),
    # the designed experiment lives in its own file, so load it before the DOE call
    B("load_data", {"path": "doe_data.csv"}),
    B("factorial_analysis", {"response": "deposition_rate_nm_min",
                            "factors": ["temperature_c", "chamber_pressure_torr", "rf_power_w"]}),
]

names_in_schema = {t["name"] for t in TOOLS}
assert names_in_schema == set(spc_tools.REGISTRY), "MCP server and registry disagree"
print("MCP server tools match registry:", sorted(names_in_schema))
print()

for b in fake_calls:
    fn = spc_tools.REGISTRY.get(b.name)
    try:
        out = fn(**b.input); err = False
    except Exception as exc:
        out, err = json.dumps({"error": str(exc)}), True
    json.loads(out)                      # must be valid JSON for tool_result
    assert err == b.expect_error, f"{b.name} {'failed' if err else 'should have failed'}: {out}"
    tag = "ERROR(handled)" if err else "ok"
    print(f"{b.name:20} {tag:15} {out[:95]}")

print("\nall tool calls dispatched and returned valid JSON")
