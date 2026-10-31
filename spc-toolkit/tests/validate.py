"""
Validation harness: does each tool recover the fault planted in the data?

    python make_data.py          # regenerate the CSVs (only if PLANTED changed)
    python tests/validate.py     # print planted vs recovered, exit 1 on any FAIL

The planted truth is imported from make_data.PLANTED, never retyped here.

How tolerances are set
----------------------
A tool run on a finite sample does not return the planted population value
exactly; it returns an estimate with sampling error. Each tolerance below is
the band an estimate falls in with ~99% or better probability IF THE TOOL IS
CORRECT, derived from the estimator's standard error at this sample size
(3 SE ~ 99.7% for normal-ish estimators). Where no formula exists (Western
Electric run lengths, changepoint location, the step-versus-drift decision),
the bound is the 99th percentile from tests/derive_tolerances.py, a seeded
Monte Carlo of the same rules. So a FAIL means either the tool is wrong or a
~1-in-100 sampling event happened, and the table says which number missed.
Tolerances are fixed by these derivations and are never widened to pass.
"""
import json, math, os, sys, tempfile
from dataclasses import dataclass
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scipy.stats import norm

import spc_tools
from make_data import PLANTED, make_process_data, make_doe_data

PROCESS_CSV = os.path.join(ROOT, "process_data.csv")
DOE_CSV = os.path.join(ROOT, "doe_data.csv")
N = PLANTED["n_runs"]
BASE = spc_tools.BASELINE_N
TH, RES, PRS = PLANTED["thickness_nm"], PLANTED["resistance_ohm"], PLANTED["pressure_mtorr"]
PAIR, DRIFT, DOE = PLANTED["correlated_pair"], PLANTED["drift"], PLANTED["doe"]

# ---------------------------------------------------------------- tolerances
# Monte Carlo 99th percentiles (tests/derive_tolerances.py, 20 000 reps each,
# limits from the first 40 points exactly as find_violations computes them):
WE_FLAGS_P99_70 = 8     # flagged runs among 70 in-control runs   (mean 1.25)
WE_FLAGS_P99_120 = 13   # flagged runs among 120 in-control runs  (mean 2.79)
WE_DELAY_P99 = 15       # runs from a 1.5-sigma step to first flag (mean 3.56)
CHANGEPOINT_P99 = 10    # |estimated - true| changepoint, 1.5-sigma step
# The same simulation gives the probability trend_test labels each case
# correctly: step 0.994, 4-sigma drift 0.996, in-control "none" 0.951 (= 1 - alpha).

# Control-chart centre from 40 baseline points: SE(mean) = sigma/sqrt(40).
# Baseline sigma: SE(s) ~= sigma/sqrt(2(n-1)) for normal data, n = 40.
CENTER_TOL = 3 * PRS["sigma"] / math.sqrt(BASE)
SIGMA_TOL = 3 * PRS["sigma"] / math.sqrt(2 * (BASE - 1))


def cp_true(spec):
    return (spec["usl"] - spec["lsl"]) / (6 * spec["sigma"])


def cpk_true(spec):
    return min(spec["usl"] - spec["mean"], spec["mean"] - spec["lsl"]) / (3 * spec["sigma"])


def cpk_tol(cpk, n=N):
    # Bissell (1990): SE(Cpk) ~= sqrt(1/(9n) + Cpk^2 / (2(n-1)))
    return 3 * math.sqrt(1 / (9 * n) + cpk ** 2 / (2 * (n - 1)))


def cp_tol(cp, n=N):
    # Cp = const/s, so SE(Cp) ~= Cp * SE(s)/sigma = Cp / sqrt(2(n-1))
    return 3 * cp / math.sqrt(2 * (n - 1))


# Step size = mean(after) - mean(before): SE = sigma*sqrt(1/70 + 1/50).
STEP_TOL = 3 * TH["sigma"] * math.sqrt(1 / TH["shift_run"] + 1 / (N - TH["shift_run"]))

# Sen's slope: OLS slope SE is sigma/sqrt(Sxx), Sxx = n(n^2-1)/12 for runs
# 0..n-1. Sen's slope has asymptotic efficiency 3/pi vs OLS under normal
# noise, so its SE is larger by 1/sqrt(3/pi) = 1.023 (the Monte Carlo
# measured 1.030; we use the measured, larger factor).
SXX = N * (N ** 2 - 1) / 12
SEN_TOL = 3 * 1.030 * DRIFT["sigma"] / math.sqrt(SXX)

# Correlation: Fisher z = atanh(r) is ~normal with SD 1/sqrt(n-3) for Pearson
# and sqrt(1.06/(n-3)) for Spearman (Fieller, Hartley & Pearson 1957). Band =
# planted value +/- 3 SD in z space, mapped back with tanh (asymmetric in r).
# Spearman's population value for bivariate normal data is (6/pi)asin(rho/2).
def fisher_band(rho, sd):
    z = math.atanh(rho)
    return math.tanh(z - 3 * sd), math.tanh(z + 3 * sd)


PEARSON_BAND = fisher_band(PAIR["rho"], 1 / math.sqrt(N - 3))
SPEARMAN_TRUE = 6 / math.pi * math.asin(PAIR["rho"] / 2)
SPEARMAN_BAND = fisher_band(SPEARMAN_TRUE, math.sqrt(1.06 / (N - 3)))

# DOE effect = difference of two means of N/2 runs: SE = 2*sigma/sqrt(N).
DOE_N = 2 ** len(DOE["levels"]) * DOE["replicates"]
EFFECT_TOL = 3 * 2 * DOE["sigma"] / math.sqrt(DOE_N)

# Yield against spec, normal model: expected fail fraction
# p = Phi((lsl-mu)/sigma) + Phi((mu-usl)/sigma); observed fraction has
# binomial SE sqrt(p(1-p)/n).
def fail_frac(spec):
    return (norm.cdf((spec["lsl"] - spec["mean"]) / spec["sigma"])
            + norm.cdf((spec["mean"] - spec["usl"]) / spec["sigma"]))


RES_FAIL = fail_frac(RES)
RES_FAIL_TOL = 3 * math.sqrt(RES_FAIL * (1 - RES_FAIL) / N)
# Pressure: p = 2*Phi(-4) = 6.3e-5, so P(any fail in 120) = 0.76% < 1%:
# the 99% bound on the fail count is 0.
PRS_FAIL = fail_frac(PRS)


# ------------------------------------------------------------------ plumbing
@dataclass
class Row:
    tool: str
    check: str
    planted: str
    recovered: str
    tolerance: str
    passed: bool


@lru_cache(maxsize=None)
def _cached(path, tool, args_json):
    spc_tools.load_data(path)
    return json.loads(getattr(spc_tools, tool)(**json.loads(args_json)))


def call(path, tool, **kw):
    """Load the file, run the tool, parse its JSON. Cached per argument set."""
    return _cached(path, tool, json.dumps(kw, sort_keys=True))


def f(x, d=4):
    return f"{x:.{d}g}" if isinstance(x, float) else str(x)


def within(tool, check, planted, got, tol, d=4):
    return Row(tool, check, f(planted, d), f(got, d), f"+/- {tol:.2g}",
               abs(got - planted) <= tol)


def flagged_runs(parameter):
    v = call(PROCESS_CSV, "find_violations", parameter=parameter)["violations"]
    return sorted({i for runs in v.values() for i in runs})


def effect(term):
    out = call(DOE_CSV, "factorial_analysis", response=DOE["response"],
               factors=list(DOE["levels"]))
    for e in out["effects"]:
        if e["term"] == term:
            return e
    raise KeyError(f"term {term!r} not in factorial_analysis output")


def pair_row():
    out = call(PROCESS_CSV, "correlate_parameters")
    for rank, p in enumerate(out["pairs"], 1):
        if {p["a"], p["b"]} == {PAIR["a"], PAIR["b"]}:
            return rank, p
    raise KeyError("planted pair missing from correlate_parameters output")


CHECKS = []          # (id, function) in table order


def check(fn):
    CHECKS.append((fn.__name__, fn))
    return fn


# -------------------------------------------------------------------- checks
@check
def data_files_current():
    # Byte comparison: the CSVs on disk are exactly what PLANTED generates.
    same = all(open(path).read() == gen().to_csv(index=False)
               for path, gen in ((PROCESS_CSV, make_process_data), (DOE_CSV, make_doe_data)))
    return Row("make_data", "CSVs match generator", "PLANTED", "match" if same else "STALE",
               "exact", same)


@check
def load_data_process():
    out = json.loads(spc_tools.load_data(PROCESS_CSV))
    return Row("load_data", "process rows/params", f"{N}/6",
               f"{out['rows']}/{len(out['parameters'])}", "exact",
               out["rows"] == N and len(out["parameters"]) == 6)


@check
def control_limits_pressure_center():
    out = call(PROCESS_CSV, "control_limits", parameter="pressure_mtorr")
    return within("control_limits", "pressure centre", PRS["mean"], out["center"], CENTER_TOL)


@check
def control_limits_pressure_sigma():
    out = call(PROCESS_CSV, "control_limits", parameter="pressure_mtorr")
    return within("control_limits", "pressure sigma", PRS["sigma"], out["sigma"], SIGMA_TOL)


@check
def find_violations_thickness_detects_shift():
    t0 = TH["shift_run"]
    after = [i for i in flagged_runs("thickness_nm") if i >= t0]
    first = after[0] if after else None
    return Row("find_violations", "thickness first flag >= shift", f"shift @ {t0}",
               f"run {first}", f"<= {t0}+{WE_DELAY_P99}",
               first is not None and first - t0 <= WE_DELAY_P99)


@check
def find_violations_thickness_quiet_before_shift():
    pre = [i for i in flagged_runs("thickness_nm") if i < TH["shift_run"]]
    return Row("find_violations", "thickness flags before shift", "0 (in control)",
               f"{len(pre)} {pre}", f"<= {WE_FLAGS_P99_70}", len(pre) <= WE_FLAGS_P99_70)


@check
def find_violations_resistance_few():
    runs = flagged_runs("resistance_ohm")
    return Row("find_violations", "resistance flagged runs", "0 (stable)",
               f"{len(runs)} {runs}", f"<= {WE_FLAGS_P99_120}", len(runs) <= WE_FLAGS_P99_120)


@check
def find_violations_pressure_few():
    runs = flagged_runs("pressure_mtorr")
    return Row("find_violations", "pressure flagged runs", "0 (healthy)",
               f"{len(runs)} {runs}", f"<= {WE_FLAGS_P99_120}", len(runs) <= WE_FLAGS_P99_120)


@check
def capability_resistance_cpk():
    out = call(PROCESS_CSV, "capability", parameter="resistance_ohm", lsl=RES["lsl"], usl=RES["usl"])
    c = cpk_true(RES)
    return within("capability", "resistance Cpk (bad spec)", c, out["cpk"], cpk_tol(c), 3)


@check
def capability_resistance_cp():
    out = call(PROCESS_CSV, "capability", parameter="resistance_ohm", lsl=RES["lsl"], usl=RES["usl"])
    c = cp_true(RES)
    return within("capability", "resistance Cp", c, out["cp"], cp_tol(c), 3)


@check
def capability_pressure_cpk():
    out = call(PROCESS_CSV, "capability", parameter="pressure_mtorr", lsl=PRS["lsl"], usl=PRS["usl"])
    c = cpk_true(PRS)
    return within("capability", "pressure Cpk (healthy)", c, out["cpk"], cpk_tol(c), 3)


@check
def plot_chart_writes_png():
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            spc_tools.load_data(PROCESS_CSV)
            out = json.loads(spc_tools.plot_chart("thickness_nm"))
            with open(out["file"], "rb") as fh:
                ok = fh.read(8) == b"\x89PNG\r\n\x1a\n"
        finally:
            os.chdir(cwd)
    return Row("plot_chart", "thickness chart written", "PNG file", "PNG" if ok else "not PNG",
               "exact", ok)


@check
def trend_test_thickness_is_step():
    out = call(PROCESS_CSV, "trend_test", parameter="thickness_nm")
    return Row("trend_test", "thickness pattern", "step", out["pattern"], "P(ok)=0.994",
               out["pattern"] == "step")


@check
def trend_test_thickness_changepoint():
    out = call(PROCESS_CSV, "trend_test", parameter="thickness_nm")
    t0 = out["step_changepoint_run"]
    return Row("trend_test", "thickness changepoint run", str(TH["shift_run"]), str(t0),
               f"+/- {CHANGEPOINT_P99}",
               t0 is not None and abs(t0 - TH["shift_run"]) <= CHANGEPOINT_P99)


@check
def trend_test_thickness_step_size():
    out = call(PROCESS_CSV, "trend_test", parameter="thickness_nm")
    return within("trend_test", "thickness step size", TH["shift"], out["step_size"], STEP_TOL)


@check
def trend_test_drift_is_drift():
    out = call(PROCESS_CSV, "trend_test", parameter=DRIFT["parameter"])
    return Row("trend_test", "etch_rate pattern", "drift", out["pattern"], "P(ok)=0.996",
               out["pattern"] == "drift")


@check
def trend_test_drift_slope():
    out = call(PROCESS_CSV, "trend_test", parameter=DRIFT["parameter"])
    return within("trend_test", "etch_rate Sen slope/run", DRIFT["slope_per_run"],
                  out["sens_slope_per_run"], SEN_TOL)


@check
def trend_test_pressure_none():
    out = call(PROCESS_CSV, "trend_test", parameter="pressure_mtorr")
    return Row("trend_test", "pressure pattern", "none", out["pattern"], "P(ok)=0.95",
               out["pattern"] == "none")


@check
def correlate_pair_pearson():
    _, p = pair_row()
    lo, hi = PEARSON_BAND
    return Row("correlate_parameters", "dose~sheet_res Pearson r", f(PAIR["rho"]),
               f(p["pearson_r"]), f"[{lo:.3f}, {hi:.3f}]", lo <= p["pearson_r"] <= hi)


@check
def correlate_pair_spearman():
    _, p = pair_row()
    lo, hi = SPEARMAN_BAND
    return Row("correlate_parameters", "dose~sheet_res Spearman", f(SPEARMAN_TRUE, 3),
               f(p["spearman_rho"]), f"[{lo:.3f}, {hi:.3f}]", lo <= p["spearman_rho"] <= hi)


@check
def correlate_pair_ranked_first():
    rank, p = pair_row()
    return Row("correlate_parameters", "planted pair rank/strength", "1/strong",
               f"{rank}/{p['strength']}", "exact", rank == 1 and p["strength"] == "strong")


def _effect_check(term):
    def fn():
        e = effect(term)
        return within("factorial_analysis", f"effect {term}", float(DOE["effects"][term]),
                      e["effect"], EFFECT_TOL)
    fn.__name__ = "factorial_effect_" + term.replace(":", "_x_")
    return fn


for _term in DOE["effects"]:
    check(_effect_check(_term))


@check
def factorial_active_terms_significant():
    active = [t for t, v in DOE["effects"].items() if v != 0]
    sig = [t for t in active if effect(t)["significant"]]
    p = ", ".join(f"{effect(t)['p_value']:.2g}" for t in active)
    return Row("factorial_analysis", "active terms significant", f"{len(active)} sig",
               f"{len(sig)} sig (p {p})", "p < 0.05", len(sig) == len(active))


@check
def factorial_inert_factor_not_significant():
    e = effect("chamber_pressure_torr")
    return Row("factorial_analysis", "inert chamber_pressure", "not sig",
               f"{'SIG' if e['significant'] else 'not sig'} (p {e['p_value']:.2g})",
               "P(ok)=0.95", not e["significant"])


@check
def factorial_largest_effect_ranked_first():
    e = effect("temperature_c")
    return Row("factorial_analysis", "temperature_c rank", "1", str(e["rank"]), "exact",
               e["rank"] == 1)


@check
def yield_resistance_fail_fraction():
    out = call(PROCESS_CSV, "yield_summary", parameter="resistance_ohm",
               lsl=RES["lsl"], usl=RES["usl"])
    return within("yield_summary", "resistance fail fraction", RES_FAIL, out["fail"] / out["n"],
                  RES_FAIL_TOL, 3)


@check
def yield_pressure_no_fails():
    out = call(PROCESS_CSV, "yield_summary", parameter="pressure_mtorr",
               lsl=PRS["lsl"], usl=PRS["usl"])
    return Row("yield_summary", "pressure fail count", f"{PRS_FAIL * N:.3f} expected",
               str(out["fail"]), "<= 0 (99%)", out["fail"] == 0)


# --------------------------------------------------------------------- report
def run_check(fn):
    try:
        return fn()
    except AttributeError as exc:
        return Row(fn.__name__, "", "", f"MISSING: {exc}", "", False)
    except Exception as exc:
        return Row(fn.__name__, "", "", f"ERROR {type(exc).__name__}: {exc}", "", False)


HEADER = ("tool", "check", "planted", "recovered", "tolerance", "result")


def table(rows):
    cells = [HEADER] + [(r.tool, r.check, r.planted, r.recovered, r.tolerance,
                         "PASS" if r.passed else "FAIL") for r in rows]
    w = [max(len(c[i]) for c in cells) for i in range(len(HEADER))]
    line = lambda c: " | ".join(s.ljust(w[i]) for i, s in enumerate(c)).rstrip()
    out = [line(cells[0]), "-+-".join("-" * x for x in w)]
    out += [line(c) for c in cells[1:]]
    return "\n".join(out)


def main():
    rows = [run_check(fn) for _, fn in CHECKS]
    print(table(rows))
    failed = [r for r in rows if not r.passed]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} checks passed")
    for r in failed:
        print(f"FAIL: {r.tool} {r.check}: planted {r.planted}, recovered {r.recovered}, "
              f"tolerance {r.tolerance}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
