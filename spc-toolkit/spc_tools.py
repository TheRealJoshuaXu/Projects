"""
Deterministic statistical process control calculations.

These are the TOOLS the agent calls. The model never does the arithmetic:
it decides WHICH of these to run, on which parameter, and in what order,
then interprets what comes back. Keeping the maths here and the judgement
in the model is the whole design point.
"""

import itertools
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats   # distribution functions only (t / normal cdf, sf, ppf)

DATA = {}          # filled by load_data()
BASELINE_N = 40    # points used to establish control limits


def load_data(path: str) -> str:
    """Load a CSV of process measurements. First column is the run index."""
    df = pd.read_csv(path)
    DATA["df"] = df
    params = [c for c in df.columns if c.lower() not in ("run", "index", "lot", "wafer")]
    return json.dumps({
        "rows": int(len(df)),
        "parameters": params,
        "preview": df.head(3).to_dict(orient="records"),
    }, default=str)


def _series(parameter: str) -> pd.Series:
    if "df" not in DATA:
        raise RuntimeError("call load_data first")
    if parameter not in DATA["df"].columns:
        raise KeyError(f"no such parameter: {parameter}")
    return DATA["df"][parameter].astype(float)


def control_limits(parameter: str) -> str:
    """Centre line and 1/2/3-sigma limits from the first BASELINE_N points."""
    s = _series(parameter)
    base = s.iloc[:BASELINE_N]
    mu, sd = float(base.mean()), float(base.std(ddof=1))
    return json.dumps({
        "parameter": parameter,
        "baseline_points": int(len(base)),
        "center": round(mu, 6),
        "sigma": round(sd, 6),
        "ucl_3s": round(mu + 3 * sd, 6), "lcl_3s": round(mu - 3 * sd, 6),
        "ucl_2s": round(mu + 2 * sd, 6), "lcl_2s": round(mu - 2 * sd, 6),
        "ucl_1s": round(mu + 1 * sd, 6), "lcl_1s": round(mu - 1 * sd, 6),
    })


def find_violations(parameter: str) -> str:
    """Apply the four standard Western Electric rules. Returns flagged run indices."""
    s = _series(parameter)
    base = s.iloc[:BASELINE_N]
    mu, sd = float(base.mean()), float(base.std(ddof=1))
    if sd == 0:
        return json.dumps({"parameter": parameter, "error": "zero baseline sigma"})

    z = (s - mu) / sd
    n = len(z)
    hits = {"rule1_beyond_3s": [], "rule2_2of3_beyond_2s": [],
            "rule3_4of5_beyond_1s": [], "rule4_8_same_side": []}

    for i in range(n):
        if abs(z.iloc[i]) > 3:
            hits["rule1_beyond_3s"].append(i)
        if i >= 2:
            w = z.iloc[i - 2:i + 1]
            for sign in (1, -1):
                if ((w * sign) > 2).sum() >= 2:
                    hits["rule2_2of3_beyond_2s"].append(i); break
        if i >= 4:
            w = z.iloc[i - 4:i + 1]
            for sign in (1, -1):
                if ((w * sign) > 1).sum() >= 4:
                    hits["rule3_4of5_beyond_1s"].append(i); break
        if i >= 7:
            w = z.iloc[i - 7:i + 1]
            if (w > 0).all() or (w < 0).all():
                hits["rule4_8_same_side"].append(i)

    total = sum(len(v) for v in hits.values())
    return json.dumps({"parameter": parameter, "total_flags": total, "violations": hits})


def capability(parameter: str, lsl: float, usl: float) -> str:
    """Cp and Cpk against supplied specification limits."""
    s = _series(parameter)
    mu, sd = float(s.mean()), float(s.std(ddof=1))
    if sd == 0:
        return json.dumps({"parameter": parameter, "error": "zero sigma"})
    cp = (usl - lsl) / (6 * sd)
    cpk = min((usl - mu) / (3 * sd), (mu - lsl) / (3 * sd))
    return json.dumps({
        "parameter": parameter, "mean": round(mu, 6), "sigma": round(sd, 6),
        "lsl": lsl, "usl": usl, "cp": round(cp, 3), "cpk": round(cpk, 3),
        "out_of_spec_points": int(((s < lsl) | (s > usl)).sum()),
    })


def plot_chart(parameter: str) -> str:
    """Write a control chart PNG. Returns the filename."""
    s = _series(parameter)
    base = s.iloc[:BASELINE_N]
    mu, sd = float(base.mean()), float(base.std(ddof=1))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(s.index, s.values, marker="o", ms=3, lw=1, color="#333")
    for k, style in ((3, "-"), (2, "--"), (1, ":")):
        ax.axhline(mu + k * sd, ls=style, lw=0.8, color="#c0392b")
        ax.axhline(mu - k * sd, ls=style, lw=0.8, color="#c0392b")
    ax.axhline(mu, lw=1, color="#2980b9")
    ax.axvline(BASELINE_N - 0.5, lw=0.8, color="#888", ls="-.")
    ax.set_title(f"{parameter} — individuals chart")
    ax.set_xlabel("run"); ax.set_ylabel(parameter)
    fname = f"chart_{parameter}.png"
    fig.tight_layout(); fig.savefig(fname, dpi=110); plt.close(fig)
    return json.dumps({"parameter": parameter, "file": fname})


# ---------------------------------------------------------------------------
# Design of experiments, correlation, trend and yield.
# scipy is used ONLY for distribution functions (t / normal tail areas and
# quantiles). Every statistic itself is written out below in numpy/pandas.
# ---------------------------------------------------------------------------

def _frame() -> pd.DataFrame:
    if "df" not in DATA:
        raise RuntimeError("call load_data first")
    return DATA["df"]


def _plain(v):
    """numpy scalar -> plain Python value so json.dumps accepts it."""
    return v.item() if isinstance(v, np.generic) else v


def _p(p: float) -> float:
    """Round a p-value to 3 significant figures (fixed decimals would turn 1e-9 into 0)."""
    return float(f"{p:.3g}")


def factorial_analysis(response: str, factors: list[str]) -> str:
    """Two-level factorial DOE: main effects, two-factor interactions, ranking.

    Each factor column must hold exactly two settings; the lower is coded -1
    and the higher +1. For every main effect and every two-factor
    interaction (product of the two coded columns) the effect is
        mean(response at +1) - mean(response at -1),
    i.e. how much the response moves when that term goes from low to high.
    Terms are ranked by |effect| so the engineer sees which knobs matter.

    Significance:
      * Replicated design (every factor combination run at least twice):
        pure error s^2 is pooled from the spread of replicates within each
        cell; SE(effect) = s*sqrt(1/n_plus + 1/n_minus), the standard error
        of a difference of two means (equal to 2s/sqrt(N) when balanced);
        t = effect/SE with N - cells degrees of freedom; significant if
        two-sided p < 0.05.
      * Unreplicated: Lenth's pseudo standard error. Assumes most effects
        are inert ("effect sparsity"), so the small effects stand in for
        noise. PSE is computed from ALL m = 2^k - 1 contrasts, including the
        three-factor and higher interactions that are not reported, because
        those are the contrasts most likely to be pure noise.
        margin = t(0.975, m/3) * PSE; significant if |effect| > margin.

    Assumptions: independent runs in randomised order, constant noise
    variance across cells, and a balanced orthogonal design (equal runs per
    cell). Violations are reported in "notes", not hidden. Three-factor and
    higher interactions are not reported; in the replicated test they are
    left in the pure-error model, not pooled into noise, and in the
    unreplicated case they feed only the Lenth noise estimate.
    """
    df = _frame()
    if not 2 <= len(factors) <= 4:
        raise ValueError("factorial_analysis needs 2 to 4 factors")
    if len(set(factors)) != len(factors) or response in factors:
        raise ValueError("factors must be distinct and must not include the response")
    _series(response)                                   # existence check
    for f in factors:
        if f not in df.columns:
            raise KeyError(f"no such parameter: {f}")

    notes = []
    d = df[[response] + factors].dropna()
    if len(d) < len(df):
        notes.append(f"{len(df) - len(d)} rows with missing values were dropped")
    y = d[response].astype(float).to_numpy()
    N = len(y)

    coded, levels = {}, {}
    for f in factors:
        vals = sorted(d[f].unique())
        if len(vals) != 2:
            raise ValueError(f"factor {f} has {len(vals)} distinct values; a two-level design needs exactly 2")
        low, high = vals
        levels[f] = {"low": _plain(low), "high": _plain(high)}
        coded[f] = np.where(d[f].to_numpy() == high, 1.0, -1.0)

    terms = [(f, "main", coded[f]) for f in factors]
    terms += [(f"{a}:{b}", "interaction", coded[a] * coded[b])
              for a, b in itertools.combinations(factors, 2)]
    def effect_of(x):
        return float(y[x > 0].mean() - y[x < 0].mean())
    effects = {name: effect_of(x) for name, _, x in terms}

    # cells = distinct factor-level combinations actually run
    cell_ids = d[factors].astype(str).agg("|".join, axis=1).to_numpy()
    cell_names, counts = np.unique(cell_ids, return_counts=True)
    n_cells, full = len(cell_names), 2 ** len(factors)
    if n_cells < full:
        notes.append(f"only {n_cells} of {full} factor combinations were run; "
                     "some effects are aliased (confounded) and cannot be separated")
    if counts.min() != counts.max():
        notes.append(f"unbalanced design (runs per cell range {counts.min()}-{counts.max()}); "
                     "effects are no longer independent of each other, treat them as approximate")

    stats_by_term = {}
    if n_cells == full and counts.min() >= 2:
        method = "replicated_t_test"
        cell_mean = pd.Series(y).groupby(cell_ids).transform("mean").to_numpy()
        dof = N - n_cells
        s2 = float(((y - cell_mean) ** 2).sum() / dof)  # pooled within-cell variance
        for name, _, x in terms:
            se = np.sqrt(s2 * (1 / (x > 0).sum() + 1 / (x < 0).sum()))
            if se == 0:
                stats_by_term[name] = (None, None, effects[name] != 0)
            else:
                t = effects[name] / se
                p = 2 * stats.t.sf(abs(t), dof)
                stats_by_term[name] = (round(t, 3), _p(p), bool(p < 0.05))
        if s2 == 0:
            notes.append("replicates are identical (zero within-cell variance), so no t-test is possible; "
                         "every non-zero effect is marked significant. Check gauge resolution")
        notes.append(f"pure error estimated from replicates with {dof} degrees of freedom; "
                     f"{len(effects)} terms tested at alpha 0.05 without multiple-comparison adjustment")
    else:
        method = "lenth_pse"
        # every contrast in the 2^k design: products of 1, 2, ..., k coded columns
        contrasts = []
        for r in range(1, len(factors) + 1):
            for combo in itertools.combinations(factors, r):
                x = np.prod([coded[f] for f in combo], axis=0)
                if (x > 0).any() and (x < 0).any():   # constant only in incomplete designs
                    contrasts.append(effect_of(x))
        m = len(contrasts)
        abs_eff = np.abs(np.array(contrasts))
        s0 = 1.5 * np.median(abs_eff)
        pse = 1.5 * np.median(abs_eff[abs_eff < 2.5 * s0]) if (abs_eff < 2.5 * s0).any() else 0.0
        margin = stats.t.ppf(0.975, m / 3) * pse
        for name in effects:
            stats_by_term[name] = (None, None, bool(abs(effects[name]) > margin))
        notes.append("unreplicated: Lenth method assumes most effects are inert; "
                     "if many effects are real, the noise estimate is inflated and real effects are missed")
        notes.append(f"Lenth pseudo standard error {round(float(pse), 6)} "
                     f"from all {m} contrasts (including unreported higher-order interactions), "
                     f"significance margin {round(float(margin), 6)} on {round(m / 3, 3)} degrees of freedom")
        if m < 6:
            notes.append(f"only {m} effects available to estimate noise; the Lenth margin is very wide "
                         "and only very large effects can be detected. Replicate the design")

    order = sorted(effects, key=lambda k: -abs(effects[k]))
    rows = []
    for rank, name in enumerate(order, start=1):
        kind = next(t for n_, t, _ in terms if n_ == name)
        t_stat, p_value, sig = stats_by_term[name]
        rows.append({"term": name, "type": kind, "effect": round(effects[name], 6),
                     "rank": rank, "t_stat": t_stat, "p_value": p_value, "significant": sig})

    return json.dumps({
        "response": response, "factors": factors, "runs": N, "cells": n_cells,
        "replicates_per_cell": int(counts.min()), "method": method, "alpha": 0.05,
        "levels": levels, "grand_mean": round(float(y.mean()), 6),
        "effects": rows, "notes": notes,
    })


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    dx, dy = x - x.mean(), y - y.mean()
    return float((dx * dy).sum() / np.sqrt((dx ** 2).sum() * (dy ** 2).sum()))


def correlate_parameters(parameters: list[str] | None = None) -> str:
    """Pairwise correlation: do two measurements move together?

    For each pair: Pearson r (strength of a straight-line relationship,
    -1 to +1), its two-sided p-value from t = r*sqrt((n-2)/(1-r^2)) on
    n-2 degrees of freedom, and Spearman rho (Pearson r of the ranks, so it
    captures any monotonic relationship and resists outliers). Pairs are
    sorted strongest first; strength is "strong" for |r| >= 0.7,
    "moderate" for |r| >= 0.4, else "weak".

    Meaning: a strong correlation says two parameters share a cause or one
    drives the other; it does not say which. Assumptions behind the
    p-value: independent observations and a roughly linear, bivariate-normal
    relationship. Time-ordered process data is often autocorrelated and two
    parameters that both drift will correlate through time alone, so the
    p-value is optimistic; a large Pearson/Spearman gap is flagged in notes.
    """
    df = _frame()
    if parameters is None:
        parameters = [c for c in df.columns
                      if c.lower() not in ("run", "index", "lot", "wafer")
                      and pd.api.types.is_numeric_dtype(df[c])]
    if len(parameters) < 2 or len(set(parameters)) != len(parameters):
        raise ValueError("need at least two distinct parameters to correlate")
    for p in parameters:
        _series(p)                                     # existence + numeric check

    notes = []
    d = df[parameters].astype(float).dropna()
    if len(d) < len(df):
        notes.append(f"{len(df) - len(d)} rows with missing values were dropped")
    n = len(d)
    if n < 3:
        raise ValueError("need at least 3 complete rows to correlate")
    for p in parameters:
        if d[p].std() == 0:
            raise ValueError(f"parameter {p} is constant; correlation is undefined")

    ranks = d.rank()                                   # average ranks for ties
    pairs = []
    for a, b in itertools.combinations(parameters, 2):
        r = _pearson(d[a].to_numpy(), d[b].to_numpy())
        rho = _pearson(ranks[a].to_numpy(), ranks[b].to_numpy())
        if abs(r) >= 1:
            pval = 0.0
        else:
            t = r * np.sqrt((n - 2) / (1 - r ** 2))
            pval = 2 * stats.t.sf(abs(t), n - 2)
        strength = "strong" if abs(r) >= 0.7 else "moderate" if abs(r) >= 0.4 else "weak"
        pairs.append({"a": a, "b": b, "pearson_r": round(r, 3), "p_value": _p(pval),
                      "spearman_rho": round(rho, 3), "strength": strength})
        if abs(abs(r) - abs(rho)) > 0.2:
            notes.append(f"{a} vs {b}: Pearson {r:.3f} and Spearman {rho:.3f} disagree; "
                         "the relationship is curved or driven by a few outliers, plot it")
    pairs.sort(key=lambda q: -abs(q["pearson_r"]))

    notes.insert(0, "correlation is not causation: a strong pair may share a common cause")
    notes.append("p-values assume independent runs; autocorrelated or jointly drifting "
                 "process data makes them optimistic")
    if len(pairs) > 1:
        notes.append(f"{len(pairs)} pairs tested; expect about 1 in 20 unrelated pairs to show p < 0.05 by chance")
    return json.dumps({"n": n, "pairs": pairs, "notes": notes})


def trend_test(parameter: str) -> str:
    """Is there a slow drift, a sudden step, or neither?

    Mann-Kendall: S = sum over all pairs i<j of sign(x_j - x_i). A rising
    series gives large positive S. Var(S) = [n(n-1)(2n+5) - sum over tie
    groups t(t-1)(2t+5)] / 18; Z = (S -/+ 1)/sqrt(Var) with continuity
    correction; two-sided p from the normal distribution. Sen's slope is
    the median of all pairwise slopes (x_j - x_i)/(j - i): a robust drift
    rate in units per run.

    MK only says "the level changes monotonically", which is true of both a
    drift and a step. To tell them apart, the best single step (split k in
    [10, n-10] minimising the SSE about two segment means) is compared with
    a least-squares straight line. pattern = "none" if MK p >= 0.05,
    "step" if the step fits better, otherwise "drift". Run numbers are
    0-based positions, as in find_violations.

    Assumptions: independent observations (positive autocorrelation makes MK
    over-report trends) and at most one step. The step model gets to choose
    its split point, which gives it a small advantage in the comparison.
    """
    s = _series(parameter)
    notes = []
    if s.isna().any():
        notes.append(f"{int(s.isna().sum())} missing values were dropped; runs renumbered by position")
    x = s.dropna().to_numpy()
    n = len(x)
    if n < 20:
        raise ValueError("trend_test needs at least 20 points (10 each side of a step)")
    t = np.arange(n, dtype=float)

    # Mann-Kendall
    i, j = np.triu_indices(n, k=1)                    # every pair with i < j
    S = int(np.sign(x[j] - x[i]).sum())
    _, tie_sizes = np.unique(x, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - (tie_sizes * (tie_sizes - 1) * (2 * tie_sizes + 5)).sum()) / 18
    z = (S - np.sign(S)) / np.sqrt(var) if var > 0 else 0.0
    pval = 2 * stats.norm.sf(abs(z))
    sens = float(np.median((x[j] - x[i]) / (j - i)))

    # straight line by least squares
    b = ((t - t.mean()) * (x - x.mean())).sum() / ((t - t.mean()) ** 2).sum()
    a = x.mean() - b * t.mean()
    sse_lin = float(((x - (a + b * t)) ** 2).sum())

    # best single step
    best_k, sse_step = None, np.inf
    for k in range(10, n - 10 + 1):
        left, right = x[:k], x[k:]
        sse = ((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum()
        if sse < sse_step:
            best_k, sse_step = k, float(sse)
    step = float(x[best_k:].mean() - x[:best_k].mean())

    if pval >= 0.05:
        pattern = "none"
        msg = f"No significant monotonic trend in {parameter} (Mann-Kendall p = {_p(pval)})."
    elif sse_step < sse_lin:
        pattern = "step"
        msg = (f"{parameter} changed level abruptly at run {best_k} by {step:+.4g}; "
               "a single step explains the data better than a steady drift.")
    else:
        pattern = "drift"
        msg = (f"{parameter} drifts steadily at about {sens:+.4g} per run "
               f"({sens * (n - 1):+.4g} over the record); a straight line fits better than a single step.")
    notes.append("p-value assumes independent runs; autocorrelated data over-reports trends")

    return json.dumps({
        "parameter": parameter, "n": n, "mann_kendall_s": S,
        "z": round(float(z), 3), "p_value": _p(pval),
        "sens_slope_per_run": round(sens, 6),
        "total_change_linear": round(sens * (n - 1), 6),
        "step_changepoint_run": best_k, "step_size": round(step, 6),
        "sse_linear": round(sse_lin, 6), "sse_step": round(sse_step, 6),
        "pattern": pattern, "interpretation": msg, "notes": notes,
    })


def yield_summary(parameter: str, lsl: float, usl: float, window: int = 20) -> str:
    """Observed pass/fail against spec limits, overall and per window of runs.

    Pass means lsl <= x <= usl. Runs are cut into consecutive windows of
    `window` runs (the last may be shorter) so a yield loss that starts
    partway through the record stands out; worst_window is the window with
    the lowest yield (earliest on a tie). fail_low / fail_high split the
    failures by side, which tells the engineer whether to move the mean
    up or down.

    This is a count of what happened, not a prediction: it makes no
    normality assumption (unlike Cpk), but a window of 20 runs can only
    show yield in 5% steps. Run numbers are 0-based positions.
    """
    s = _series(parameter)
    if not lsl < usl:
        raise ValueError("lsl must be below usl")
    if int(window) != window or window < 1:
        raise ValueError("window must be a positive whole number of runs")
    window = int(window)
    notes = []
    if s.isna().any():
        notes.append(f"{int(s.isna().sum())} missing values were excluded from the counts")
    x = s.to_numpy()
    valid = ~np.isnan(x)
    ok = (x >= lsl) & (x <= usl)

    def summary(lo, hi):
        v, good = valid[lo:hi], ok[lo:hi]
        cnt = int(v.sum())
        fails = int((v & ~good).sum())
        return {"start_run": lo, "end_run": hi - 1, "n": cnt, "fail": fails,
                "yield_pct": round(100 * (cnt - fails) / cnt, 2) if cnt else None}

    windows = [summary(lo, min(lo + window, len(x))) for lo in range(0, len(x), window)]
    scored = [w for w in windows if w["yield_pct"] is not None]
    worst = min(scored, key=lambda w: w["yield_pct"]) if scored else None
    if windows and windows[-1]["n"] < window:
        notes.append(f"last window has only {windows[-1]['n']} runs; its yield is less certain")

    n = int(valid.sum())
    n_pass = int((valid & ok).sum())
    return json.dumps({
        "parameter": parameter, "lsl": lsl, "usl": usl, "n": n,
        "pass": n_pass, "fail": n - n_pass,
        "yield_pct": round(100 * n_pass / n, 2) if n else None,
        "window": window, "windows": windows, "worst_window": worst,
        "fail_low": int((x < lsl).sum()), "fail_high": int((x > usl).sum()),
        "notes": notes,
    })


# name -> callable, used by the agent loop
REGISTRY = {
    "load_data": load_data,
    "control_limits": control_limits,
    "find_violations": find_violations,
    "capability": capability,
    "plot_chart": plot_chart,
    "factorial_analysis": factorial_analysis,
    "correlate_parameters": correlate_parameters,
    "trend_test": trend_test,
    "yield_summary": yield_summary,
}
