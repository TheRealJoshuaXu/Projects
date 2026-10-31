"""
MCP server exposing the statistical process control tools to Claude Code.

Claude Code starts this automatically from .mcp.json at the repository root.
To register it by hand instead:

    claude mcp add --transport stdio spc -- python spc_server.py

The maths lives in spc_tools.py and is completely deterministic. This file
only describes those functions to the model: a name, a plain-English
description, and typed arguments. The description is what Claude reads to
decide when a tool is worth calling, so it is doing the job a docstring
does for a human. Each wrapper passes its arguments straight through and
returns the JSON unchanged; there is no logic here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer
import spc_tools

mcp = MCPServer("spc")


@mcp.tool()
def load_data(path: str) -> str:
    """Load a CSV of process measurements and report its parameters.

    Call this first: every other tool works on the most recently loaded file.
    Load process_data.csv for run-by-run production data, or doe_data.csv
    before factorial_analysis. Returns the row count, the measured parameter
    names (use these exact names as arguments elsewhere) and a short preview.
    """
    return spc_tools.load_data(path)


@mcp.tool()
def control_limits(parameter: str) -> str:
    """Compute the centre line and the 1, 2 and 3 sigma control limits for one
    parameter, using the first 40 runs as the baseline period.

    Use when you need the numeric limits themselves, e.g. to state where the
    process normally sits or to compare natural spread against a spec window.
    To judge whether the parameter is in control, call find_violations.
    """
    return spc_tools.control_limits(parameter)


@mcp.tool()
def find_violations(parameter: str) -> str:
    """Apply the four standard Western Electric rules to one parameter and
    return the run indices that break each rule.

    Use this to decide whether a parameter is in statistical control. A
    handful of scattered flags is normal noise. Many flags clustered after a
    particular run suggest a real process shift; the first flagged run
    approximates when it happened. A slow drift can also trip these rules, so
    if flags build up gradually rather than starting abruptly, confirm with
    trend_test before calling it a step change.
    """
    return spc_tools.find_violations(parameter)


@mcp.tool()
def capability(parameter: str, lsl: float, usl: float) -> str:
    """Compute Cp and Cpk for one parameter against a lower and upper
    specification limit, and count how many points fall outside spec.

    Use when the user gives spec limits or asks whether a process can meet
    them. Cpk below about 1.33 is generally considered not capable; Cp much
    larger than Cpk means the process is off-centre. Read it together with
    find_violations: a low Cpk with few control chart violations usually
    means the limits are wrong (tighter than the stable process can hold)
    rather than the process being out of control.
    """
    return spc_tools.capability(parameter, lsl, usl)


@mcp.tool()
def plot_chart(parameter: str) -> str:
    """Write an individuals control chart for one parameter to a PNG file and
    return the filename.

    Use when the user wants to see the data or needs a figure for a report.
    It adds no new numbers; base conclusions on the other tools.
    """
    return spc_tools.plot_chart(parameter)


@mcp.tool()
def factorial_analysis(response: str, factors: list[str]) -> str:
    """Analyse a two-level factorial designed experiment (DOE): main effect
    of each factor, every two-factor interaction, ranked by size, with a
    significance call on each.

    Use only on designed-experiment data where each factor column is set at
    exactly two levels (load doe_data.csv first; production run data will
    not work). Pass the measured output as `response` and 2 to 4 factor
    column names. An effect is the average change in the response when that
    factor moves from its low to its high level. A significant interaction
    (term "A:B") means A's effect depends on the setting of B, so do not
    recommend a setting for A without stating B. Check `method` and `notes`:
    with replicates the p-values come from a t-test; without replicates
    significance uses Lenth's method, which assumes most effects are inert.
    """
    return spc_tools.factorial_analysis(response, factors)


@mcp.tool()
def correlate_parameters(parameters: list[str] | None = None) -> str:
    """Compute pairwise Pearson r (with p-value) and Spearman rho between
    parameters, sorted strongest first.

    Use when asking whether two measurements move together, e.g. to see if a
    problem in one parameter shows up in another or whether one measurement
    could stand in for another. Omit `parameters` to test every pair. A
    strong r with a small p-value means a real linear association, not that
    one causes the other. Spearman much stronger than Pearson suggests a
    monotonic but non-linear relationship or an outlier pulling Pearson down.
    """
    return spc_tools.correlate_parameters(parameters)


@mcp.tool()
def trend_test(parameter: str) -> str:
    """Test one parameter for a monotonic trend (Mann-Kendall) and classify it
    as a slow drift, a step change, or neither.

    Use when find_violations shows a run of same-side flags or the user asks
    whether something is drifting, and before reporting a shift: a gradual
    drift (tool wear, consumable depletion) and an abrupt step (a recipe or
    hardware change at one run) have different root causes. Read `pattern`:
    "drift" gives sens_slope_per_run as the rate; "step" gives
    step_changepoint_run and step_size as when and how much; "none" means no
    significant trend.
    """
    return spc_tools.trend_test(parameter)


@mcp.tool()
def yield_summary(parameter: str, lsl: float, usl: float, window: int = 20) -> str:
    """Count pass and fail against specification limits for one parameter,
    overall and in consecutive windows of runs (default 20), and identify the
    worst window.

    Use when the question is about yield or scrap rather than statistical
    control: how many parts failed, when, and on which side of spec.
    Failures concentrated in late windows point to a shift or drift (check
    trend_test); failures spread evenly across windows point to a process
    that is too wide for the spec (check capability). fail_low and fail_high
    show which limit is being hit.
    """
    return spc_tools.yield_summary(parameter, lsl, usl, window)


if __name__ == "__main__":
    mcp.run()
