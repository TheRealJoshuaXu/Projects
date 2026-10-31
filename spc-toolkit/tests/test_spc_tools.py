"""
Unit tests for the statistics in spc_tools.py.

Every test builds a tiny dataset whose answer can be worked out by hand,
writes it to a temporary CSV, loads it through load_data (the same path the
agent uses) and checks the function returns that answer.
Run from the repo root:  python -m unittest tests.test_spc_tools -v
"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from scipy import stats
import spc_tools as T


def load(columns: dict):
    """Write the columns to a temp CSV and load it, as the agent would."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.csv")
        df = pd.DataFrame(columns)
        df.insert(0, "run", range(len(df)))
        df.to_csv(path, index=False)
        T.load_data(path)


def by_term(result):
    return {e["term"]: e for e in result["effects"]}


class FactorialAnalysis(unittest.TestCase):

    def test_replicated_2x2_recovers_effects_and_t(self):
        # y = 10 + 3A + 1B + 0.5AB (coded), so effects (2 x coefficient) are
        # A = 6, B = 2, A:B = 1. Each cell is run twice at mean +/- 0.5, so
        # pooled s^2 = 8 * 0.25 / (8 - 4) = 0.5 and SE = 2*sqrt(0.5)/sqrt(8) = 0.5.
        # Hence t = 12, 4, 2 on 4 degrees of freedom.
        rows = []
        for a in (-1, 1):
            for b in (-1, 1):
                mean = 10 + 3 * a + 1 * b + 0.5 * a * b
                rows += [(a, b, mean + 0.5), (a, b, mean - 0.5)]
        temp = [150 if a > 0 else 100 for a, _, _ in rows]      # real units
        load({"temp_c": temp, "gas": [b for _, b, _ in rows], "rate": [y for *_, y in rows]})
        r = json.loads(T.factorial_analysis("rate", ["temp_c", "gas"]))

        self.assertEqual(r["method"], "replicated_t_test")
        self.assertEqual((r["runs"], r["cells"], r["replicates_per_cell"]), (8, 4, 2))
        self.assertEqual(r["levels"]["temp_c"], {"low": 100, "high": 150})
        self.assertAlmostEqual(r["grand_mean"], 10)
        e = by_term(r)
        for term, effect, t in (("temp_c", 6, 12), ("gas", 2, 4), ("temp_c:gas", 1, 2)):
            self.assertAlmostEqual(e[term]["effect"], effect)
            self.assertAlmostEqual(e[term]["t_stat"], t)
            self.assertAlmostEqual(e[term]["p_value"], 2 * stats.t.sf(t, 4), places=3)
        self.assertEqual([x["term"] for x in r["effects"]], ["temp_c", "gas", "temp_c:gas"])
        self.assertEqual([x["rank"] for x in r["effects"]], [1, 2, 3])
        self.assertEqual(e["temp_c:gas"]["type"], "interaction")
        self.assertTrue(e["temp_c"]["significant"] and e["gas"]["significant"])
        self.assertFalse(e["temp_c:gas"]["significant"])        # p = 0.116

    def test_unreplicated_2x3_uses_lenth(self):
        # Effects planted exactly, including the unreported A:B:C = 0.5.
        # Lenth uses all 7 contrasts: |c| = 10, .4, .2, .3, .1, .2, .5
        # -> median 0.3, s0 = 0.45, trim at 1.125 drops only A,
        # PSE = 1.5 * median(.4,.2,.3,.1,.2,.5) = 1.5 * 0.25 = 0.375,
        # margin = t(.975, 7/3) * 0.375. (Using only the 6 reported terms
        # would give PSE 0.3, so this proves the 3-factor contrast is used.)
        planted = {"A": 10, "B": 0.4, "C": -0.2, "A:B": 0.3, "A:C": -0.1, "B:C": 0.2, "A:B:C": 0.5}
        cols = {"A": [], "B": [], "C": [], "y": []}
        for a in (-1, 1):
            for b in (-1, 1):
                for c in (-1, 1):
                    x = {"A": a, "B": b, "C": c, "A:B": a * b, "A:C": a * c, "B:C": b * c,
                         "A:B:C": a * b * c}
                    cols["A"].append(a); cols["B"].append(b); cols["C"].append(c)
                    cols["y"].append(50 + sum(planted[k] / 2 * x[k] for k in planted))
        load(cols)
        r = json.loads(T.factorial_analysis("y", ["A", "B", "C"]))
        self.assertEqual(r["method"], "lenth_pse")
        e = by_term(r)
        self.assertEqual(len(e), 6)                    # A:B:C feeds PSE, is not reported
        self.assertNotIn("A:B:C", e)
        for k in e:
            self.assertAlmostEqual(e[k]["effect"], planted[k])
            self.assertIsNone(e[k]["p_value"])
        self.assertEqual([k for k in e if e[k]["significant"]], ["A"])
        notes = " ".join(r["notes"])
        self.assertIn("pseudo standard error 0.375 from all 7 contrasts", notes)
        self.assertIn(f"margin {round(stats.t.ppf(0.975, 7 / 3) * 0.375, 6)}", notes)

    def test_unbalanced_replicated_uses_per_term_se(self):
        # Cells (A,B): (-,-) 1,3  (-,+) 4,6  (+,-) 7,9  (+,+) 10,11,12.
        # Within-cell SS = 2+2+2+2 = 8 on 9-4 = 5 df -> s^2 = 1.6.
        # A: high runs 7,9,10,11,12 (mean 9.8), low 1,3,4,6 (mean 3.5) -> effect 6.3,
        # SE = sqrt(1.6*(1/5 + 1/4)) = sqrt(0.72), t = 6.3/sqrt(0.72).
        load({"A": [-1, -1, -1, -1, 1, 1, 1, 1, 1], "B": [-1, -1, 1, 1, -1, -1, 1, 1, 1],
              "y": [1, 3, 4, 6, 7, 9, 10, 11, 12]})
        r = json.loads(T.factorial_analysis("y", ["A", "B"]))
        self.assertEqual(r["method"], "replicated_t_test")
        a = by_term(r)["A"]
        self.assertAlmostEqual(a["effect"], 6.3)
        self.assertAlmostEqual(a["t_stat"], round(6.3 / 0.72 ** 0.5, 3))
        self.assertIn("unbalanced", " ".join(r["notes"]))

    def test_unbalanced_and_incomplete_designs_are_flagged(self):
        load({"A": [-1, -1, 1, 1, 1], "B": [-1, 1, -1, 1, 1], "y": [1, 2, 3, 4, 5]})
        notes = " ".join(json.loads(T.factorial_analysis("y", ["A", "B"]))["notes"])
        self.assertIn("unbalanced", notes)
        load({"A": [-1, 1, 1], "B": [-1, -1, 1], "y": [1, 2, 3]})
        notes = " ".join(json.loads(T.factorial_analysis("y", ["A", "B"]))["notes"])
        self.assertIn("aliased", notes)

    def test_errors(self):
        load({"A": [1, 2, 3, 1], "B": [0, 0, 1, 1], "y": [1, 2, 3, 4]})
        with self.assertRaises(ValueError):          # three levels
            T.factorial_analysis("y", ["A", "B"])
        with self.assertRaises(ValueError):          # one factor
            T.factorial_analysis("y", ["B"])
        with self.assertRaises(ValueError):          # five factors
            T.factorial_analysis("y", ["A", "B", "C", "D", "E"])
        with self.assertRaises(KeyError):
            T.factorial_analysis("y", ["B", "nope"])
        with self.assertRaises(KeyError):
            T.factorial_analysis("nope", ["A", "B"])


class CorrelateParameters(unittest.TestCase):

    def test_known_correlations(self):
        x = [1, 2, 3, 4, 5, 6]
        load({"x": x,
              "lin": [2 * v + 1 for v in x],        # r = +1 exactly
              "neg": [-v for v in x],               # r = -1 exactly
              "cube": [v ** 3 for v in x],          # monotonic, curved: rho = 1, r < 1
              "flat": [1, -1, -1, -1, -1, 1]})      # U shape: zero covariance with x
        r = json.loads(T.correlate_parameters())
        self.assertEqual(r["n"], 6)
        self.assertEqual(len(r["pairs"]), 10)       # 5 choose 2
        p = {(q["a"], q["b"]): q for q in r["pairs"]}
        self.assertEqual(p[("x", "lin")]["pearson_r"], 1.0)
        self.assertEqual(p[("x", "lin")]["p_value"], 0.0)
        self.assertEqual(p[("x", "neg")]["pearson_r"], -1.0)
        self.assertEqual(p[("x", "cube")]["spearman_rho"], 1.0)
        self.assertLess(p[("x", "cube")]["pearson_r"], 1.0)
        self.assertEqual(p[("x", "flat")]["pearson_r"], 0.0)
        self.assertEqual(p[("x", "flat")]["p_value"], 1.0)
        self.assertEqual(p[("x", "flat")]["strength"], "weak")
        self.assertGreaterEqual(abs(r["pairs"][0]["pearson_r"]), abs(r["pairs"][-1]["pearson_r"]))
        self.assertIn("causation", r["notes"][0])

    def test_p_value_matches_t_formula(self):
        # x = 1..5, y = 1,3,2,5,4: Sxy = 8, Sxx = Syy = 10 -> r = 0.8 exactly.
        load({"x": [1, 2, 3, 4, 5], "y": [1, 3, 2, 5, 4]})
        q = json.loads(T.correlate_parameters(["x", "y"]))["pairs"][0]
        t = 0.8 * (3 / (1 - 0.64)) ** 0.5
        self.assertEqual(q["pearson_r"], 0.8)
        self.assertAlmostEqual(q["p_value"], 2 * stats.t.sf(t, 3), places=3)
        self.assertEqual(q["spearman_rho"], 0.8)      # data are already ranks
        self.assertEqual(q["strength"], "strong")

    def test_errors(self):
        load({"x": [1, 2, 3], "c": [5, 5, 5]})
        with self.assertRaises(ValueError):
            T.correlate_parameters(["x"])
        with self.assertRaises(ValueError):          # constant column
            T.correlate_parameters(["x", "c"])
        with self.assertRaises(KeyError):
            T.correlate_parameters(["x", "nope"])


class TrendTest(unittest.TestCase):

    def test_perfect_linear_drift(self):
        # Every pair rises: S = n(n-1)/2 = 435, Var = 30*29*65/18, Z = (S-1)/sqrt(Var).
        load({"v": [2 + 0.5 * t for t in range(30)]})
        r = json.loads(T.trend_test("v"))
        self.assertEqual(r["mann_kendall_s"], 435)
        self.assertAlmostEqual(r["z"], 434 / (30 * 29 * 65 / 18) ** 0.5, places=3)
        self.assertAlmostEqual(r["sens_slope_per_run"], 0.5)
        self.assertAlmostEqual(r["total_change_linear"], 14.5)
        self.assertAlmostEqual(r["sse_linear"], 0)
        self.assertGreater(r["sse_step"], 0)
        self.assertEqual(r["pattern"], "drift")

    def test_exact_step(self):
        # 18 points at 0 then 12 at 5. Only before/after pairs rise: S = 18*12 = 216.
        # Ties: Var = (30*29*65 - 18*17*41 - 12*11*29)/18 = 2232. Sen's slope is 0
        # because 219 of 435 pairwise slopes are zero - it describes drift, not steps.
        load({"v": [0.0] * 18 + [5.0] * 12})
        r = json.loads(T.trend_test("v"))
        self.assertEqual(r["mann_kendall_s"], 216)
        self.assertAlmostEqual(r["z"], 215 / 2232 ** 0.5, places=3)
        self.assertEqual(r["step_changepoint_run"], 18)
        self.assertAlmostEqual(r["step_size"], 5)
        self.assertAlmostEqual(r["sse_step"], 0)
        self.assertEqual(r["sens_slope_per_run"], 0)
        self.assertEqual(r["pattern"], "step")

    def test_no_trend(self):
        # Alternating 0,1: (0 before 1) pairs = 15+14+...+1 = 120,
        # (1 before 0) pairs = 14+...+0 = 105, so S = 15 - far from significant.
        load({"v": [t % 2 for t in range(30)]})
        r = json.loads(T.trend_test("v"))
        self.assertEqual(r["mann_kendall_s"], 15)
        self.assertGreater(r["p_value"], 0.05)
        self.assertEqual(r["pattern"], "none")

    def test_errors(self):
        load({"v": list(range(19))})
        with self.assertRaises(ValueError):          # too short to search a step
            T.trend_test("v")
        with self.assertRaises(KeyError):
            T.trend_test("nope")


class YieldSummary(unittest.TestCase):

    def test_counts_and_windows(self):
        # 25 runs; spec 0..10. Window 0-9: two lows. Window 10-19: clean.
        # Window 20-24 (short): one high.
        v = [5.0] * 25
        v[3], v[7], v[22] = -1.0, -0.5, 11.0
        v[12] = 10.0                                  # on the limit counts as pass
        load({"v": v})
        r = json.loads(T.yield_summary("v", 0, 10, window=10))
        self.assertEqual((r["n"], r["pass"], r["fail"]), (25, 22, 3))
        self.assertEqual(r["yield_pct"], 88.0)
        self.assertEqual((r["fail_low"], r["fail_high"]), (2, 1))
        self.assertEqual(r["windows"], [
            {"start_run": 0, "end_run": 9, "n": 10, "fail": 2, "yield_pct": 80.0},
            {"start_run": 10, "end_run": 19, "n": 10, "fail": 0, "yield_pct": 100.0},
            {"start_run": 20, "end_run": 24, "n": 5, "fail": 1, "yield_pct": 80.0}])
        self.assertEqual(r["worst_window"]["start_run"], 0)   # tie -> earliest
        self.assertIn("last window", r["notes"][0])

    def test_errors(self):
        load({"v": [1.0, 2.0]})
        with self.assertRaises(ValueError):
            T.yield_summary("v", 5, 1)
        with self.assertRaises(ValueError):
            T.yield_summary("v", 0, 5, window=0)
        with self.assertRaises(KeyError):
            T.yield_summary("nope", 0, 5)

    def test_requires_load(self):
        T.DATA.clear()
        with self.assertRaises(RuntimeError):
            T.yield_summary("v", 0, 5)
        with self.assertRaises(RuntimeError):
            T.factorial_analysis("y", ["A", "B"])


class Registry(unittest.TestCase):
    def test_new_tools_registered(self):
        for name in ("factorial_analysis", "correlate_parameters", "trend_test", "yield_summary"):
            self.assertIs(T.REGISTRY[name], getattr(T, name))


if __name__ == "__main__":
    unittest.main()
