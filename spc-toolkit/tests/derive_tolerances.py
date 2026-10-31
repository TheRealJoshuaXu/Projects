"""
Monte Carlo derivation of the tolerances that have no closed form.

Most tolerances in validate.py are 3 standard errors of an estimator with a
textbook formula. Four do not have one:

  1. how many runs the four Western Electric rules flag on an IN-CONTROL
     process (limits estimated from the first 40 points, as find_violations
     does), over 70 runs and over 120 runs;
  2. how many runs after a 1.5-sigma step at run 70 the rules take to fire;
  3. how far the least-squares changepoint lands from the true step;
  4. how often the trend_test decision rule labels the planted step "step"
     and the planted drift "drift".

This script simulates each case 20 000 times (fixed seed) using the same
rules and the same algorithm the contract specifies, and prints the 99th
percentiles that validate.py uses. It is NOT run by the test suite; rerun it
by hand if a planted magnitude in make_data.PLANTED changes:

    python tests/derive_tolerances.py
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from make_data import PLANTED

REPS = 20_000
N = PLANTED["n_runs"]
BASE = 40                      # spc_tools.BASELINE_N
rng = np.random.default_rng(12345)


def we_flags(x):
    """Union of the four Western Electric rules, vectorised over rows.
    Mirrors spc_tools.find_violations: limits from the first BASE points."""
    mu = x[:, :BASE].mean(axis=1, keepdims=True)
    sd = x[:, :BASE].std(axis=1, ddof=1, keepdims=True)
    z = (x - mu) / sd
    R, n = z.shape

    def win_count(mask, w):                # count of True in window ending at i
        c = np.cumsum(mask, axis=1)
        out = c.copy()
        out[:, w:] = c[:, w:] - c[:, :-w]
        out[:, :w - 1] = 0                 # rule only applies once window is full
        return out

    f = np.abs(z) > 3
    f |= (win_count(z > 2, 3) >= 2) | (win_count(z < -2, 3) >= 2)
    f |= (win_count(z > 1, 5) >= 4) | (win_count(z < -1, 5) >= 4)
    f |= (win_count(z > 0, 8) == 8) | (win_count(z < 0, 8) == 8)
    return f


def step_fit(x, lo=10):
    """Best single split k in [lo, n-lo] minimising SSE of two segment means."""
    R, n = x.shape
    c1 = np.cumsum(x, axis=1); c2 = np.cumsum(x ** 2, axis=1)
    best_sse = np.full(R, np.inf); best_k = np.zeros(R, int)
    for k in range(lo, n - lo + 1):        # segment 1 = x[:k], segment 2 = x[k:]
        s1, q1 = c1[:, k - 1], c2[:, k - 1]
        s2, q2 = c1[:, -1] - s1, c2[:, -1] - q1
        sse = (q1 - s1 ** 2 / k) + (q2 - s2 ** 2 / (n - k))
        better = sse < best_sse
        best_sse[better] = sse[better]; best_k[better] = k
    return best_k, best_sse


def linear_sse(x):
    t = np.arange(x.shape[1]); tc = t - t.mean()
    b = (x - x.mean(axis=1, keepdims=True)) @ tc / (tc @ tc)
    resid = x - x.mean(axis=1, keepdims=True) - np.outer(b, tc)
    return (resid ** 2).sum(axis=1)


def mk_p(x):
    """Mann-Kendall two-sided p (no-ties variance, continuity correction)."""
    from scipy.stats import norm
    n = x.shape[1]
    i, j = np.triu_indices(n, 1)
    S = np.sign(x[:, j] - x[:, i]).sum(axis=1)
    var = n * (n - 1) * (2 * n + 5) / 18
    Z = np.where(S > 0, (S - 1) / np.sqrt(var), np.where(S < 0, (S + 1) / np.sqrt(var), 0))
    return 2 * norm.sf(np.abs(Z))


def sens_slope(x):
    n = x.shape[1]
    i, j = np.triu_indices(n, 1)
    return np.median((x[:, j] - x[:, i]) / (j - i), axis=1)


def pattern(x):
    k, sse_step = step_fit(x)
    p = mk_p(x)
    lab = np.where(p >= 0.05, "none", np.where(sse_step < linear_sse(x), "step", "drift"))
    return lab, k


def main():
    th = PLANTED["thickness_nm"]
    shift_sig = th["shift"] / th["sigma"]
    t0 = th["shift_run"]

    # 1. in-control flagged runs
    f = we_flags(rng.standard_normal((REPS, N)))
    pre = f[:, :t0].sum(axis=1)
    full = f.sum(axis=1)
    print(f"in-control flagged runs in runs 0..{t0-1}: mean {pre.mean():.2f}, "
          f"P99 {np.percentile(pre, 99):.0f}")
    print(f"in-control flagged runs in runs 0..{N-1}: mean {full.mean():.2f}, "
          f"P99 {np.percentile(full, 99):.0f}")

    # 2. detection delay after a shift_sig step at t0
    x = rng.standard_normal((REPS, N)); x[:, t0:] += shift_sig
    f = we_flags(x)[:, t0:]
    delay = np.where(f.any(axis=1), f.argmax(axis=1), N)
    print(f"{shift_sig:.2f}-sigma step at {t0}: detection delay mean {delay.mean():.2f}, "
          f"P99 {np.percentile(delay, 99):.0f} runs")

    # 3/4. changepoint error and classification, batched (MK is O(n^2))
    def batched(gen, reps=REPS, size=1000):
        labs, ks, sl = [], [], []
        for _ in range(reps // size):
            xb = gen(size)
            lab, k = pattern(xb); labs.append(lab); ks.append(k); sl.append(sens_slope(xb))
        return np.concatenate(labs), np.concatenate(ks), np.concatenate(sl)

    def step_gen(m):
        xb = rng.standard_normal((m, N)); xb[:, t0:] += shift_sig; return xb
    lab, k, _ = batched(step_gen)
    err = np.abs(k - t0)
    print(f"step: P(pattern=='step') {np.mean(lab == 'step'):.4f}; "
          f"|changepoint - {t0}| P99 {np.percentile(err, 99):.0f} runs")

    d = PLANTED["drift"]
    slope_sig = d["slope_per_run"] / d["sigma"]
    def drift_gen(m):
        return rng.standard_normal((m, N)) + slope_sig * np.arange(N)
    lab, _, sl = batched(drift_gen)
    tc = np.arange(N) - (N - 1) / 2
    ols_se = 1 / np.sqrt(tc @ tc)
    print(f"drift: P(pattern=='drift') {np.mean(lab == 'drift'):.4f}; "
          f"Sen slope SD {sl.std():.5f} sigma/run vs OLS SE {ols_se:.5f} "
          f"(ratio {sl.std() / ols_se:.3f}, theory 1/sqrt(3/pi) = {1/np.sqrt(3/np.pi):.3f})")

    lab, _, _ = batched(lambda m: rng.standard_normal((m, N)))
    print(f"in-control: P(pattern=='none') {np.mean(lab == 'none'):.4f}")


if __name__ == "__main__":
    main()
