"""
Generate synthetic process data with deliberately planted faults, so every
tool has a known right answer to find. The validation harness
(tests/validate.py) imports PLANTED from this file, so the generator and the
checks can never disagree about what was planted.

process_data.csv  (120 runs, seed 7)
  thickness_nm      - genuine process shift at run 70: mean +1.8 nm = +1.5 sigma
  resistance_ohm    - perfectly stable (250 +/- 3), but the SPEC limits 245-252
                      are set wrong: true Cpk = 2/9 = 0.22 while the control
                      chart is quiet. The limits are the problem, not the process.
  pressure_mtorr    - healthy control case (12.0 +/- 0.25, spec 11-13: Cpk 1.33)
  implant_dose_e13  - correlated pair: dose (1e13 ions/cm^2) and sheet
  sheet_res_ohm_sq    resistance, planted Pearson rho = -0.80 (more dose,
                      lower sheet resistance). Stationary, no time trend.
  etch_rate_nm_min  - slow linear drift, -0.0135 nm/min per run (chamber
                      seasoning), no step: -1.61 nm/min = -4.0 sigma over 120 runs

doe_data.csv  (replicated 2^3 full factorial, 4 replicates = 32 runs, seed 2026,
               randomised run order)
  factors  temperature_c 350/400, chamber_pressure_torr 2.0/4.0, rf_power_w 200/300
  response deposition_rate_nm_min
  planted effects (high-level mean minus low-level mean):
    temperature_c               +8.0   main effect
    rf_power_w                  +4.0   main effect
    temperature_c:rf_power_w    +3.0   two-factor interaction
    chamber_pressure_torr        0.0   inert, and in no interaction

Run:  python make_data.py
"""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

PLANTED = {
    "n_runs": 120,
    "seed_process": 7,
    "seed_doe": 2026,
    "thickness_nm": {"mean": 100.0, "sigma": 1.2, "shift_run": 70, "shift": 1.8},
    "resistance_ohm": {"mean": 250.0, "sigma": 3.0, "lsl": 245.0, "usl": 252.0},
    # Spec for pressure is an assumption of this dataset (+/-4 sigma), so the
    # healthy case has something to be capable against.
    "pressure_mtorr": {"mean": 12.0, "sigma": 0.25, "lsl": 11.0, "usl": 13.0},
    # Detectability, n = 120: Fisher-z SE = 1/sqrt(117) = 0.092, so |r| = 0.80
    # sits ~12 SE from zero (unmistakable) yet is far from a deterministic
    # relation: 36% of sheet-resistance variance is NOT explained by dose.
    "correlated_pair": {"a": "implant_dose_e13", "b": "sheet_res_ohm_sq",
                        "a_mean": 5.00, "a_sigma": 0.10,
                        "b_mean": 85.0, "b_sigma": 1.5, "rho": -0.80},
    # Detectability: the run-to-run change (0.0135) is 3.4% of sigma, invisible
    # point to point, but the total over 120 runs is 4 sigma. The OLS slope SE
    # is sigma/sqrt(Sxx) = 0.40/379.5 = 0.00105 per run, so the slope is
    # ~13 SE from zero. The harder question is drift-versus-step: the best
    # single step always fits a line partly, and tests/derive_tolerances.py
    # shows trend_test's rule calls a 3-sigma drift "drift" only 94% of the
    # time, 4 sigma 99.5%. 4 sigma was chosen for that reason.
    "drift": {"parameter": "etch_rate_nm_min", "start": 52.0, "sigma": 0.40,
              "slope_per_run": -0.0135},
    # Detectability: SE(effect) = 2*sigma/sqrt(N) = 2*2.0/sqrt(32) = 0.707,
    # df = 32 - 8 = 24. t = 11.3 (temperature), 5.7 (rf power), 4.2 (the
    # interaction): power at alpha 0.05 is ~1.00, ~1.00 and ~0.98. The
    # interaction is the realistic "might be missed with fewer replicates"
    # case: at 2 replicates its power would drop to ~0.75.
    "doe": {
        "response": "deposition_rate_nm_min",
        "grand_mean": 45.0,
        "sigma": 2.0,
        "replicates": 4,
        "levels": {"temperature_c": (350.0, 400.0),
                   "chamber_pressure_torr": (2.0, 4.0),
                   "rf_power_w": (200.0, 300.0)},
        "effects": {"temperature_c": 8.0,
                    "chamber_pressure_torr": 0.0,
                    "rf_power_w": 4.0,
                    "temperature_c:chamber_pressure_torr": 0.0,
                    "temperature_c:rf_power_w": 3.0,
                    "chamber_pressure_torr:rf_power_w": 0.0},
    },
}


def make_process_data() -> pd.DataFrame:
    P = PLANTED
    N = P["n_runs"]
    rng = np.random.default_rng(P["seed_process"])

    # --- original three columns: these draws must stay first and unchanged,
    # so the existing columns of process_data.csv are byte-identical.
    t = P["thickness_nm"]
    thickness = rng.normal(t["mean"], t["sigma"], N)
    thickness[t["shift_run"]:] += t["shift"]                     # real shift
    r = P["resistance_ohm"]
    resistance = rng.normal(r["mean"], r["sigma"], N)            # perfectly stable
    p = P["pressure_mtorr"]
    pressure = rng.normal(p["mean"], p["sigma"], N)

    # --- new columns, drawn AFTER the originals from the same generator.
    # Correlated pair: b = rho*z1 + sqrt(1-rho^2)*z2 has unit variance and
    # correlation rho with z1, then each is scaled to its own mean and sigma.
    c = P["correlated_pair"]
    z1, z2 = rng.standard_normal((2, N))
    dose = c["a_mean"] + c["a_sigma"] * z1
    sheet = c["b_mean"] + c["b_sigma"] * (c["rho"] * z1 + np.sqrt(1 - c["rho"] ** 2) * z2)

    # Slow drift: a straight line plus white noise. No step anywhere.
    d = P["drift"]
    etch = d["start"] + d["slope_per_run"] * np.arange(N) + rng.normal(0, d["sigma"], N)

    return pd.DataFrame({
        "run": np.arange(N),
        "thickness_nm": thickness.round(3),
        "resistance_ohm": resistance.round(3),
        "pressure_mtorr": pressure.round(4),
        c["a"]: dose.round(4),
        c["b"]: sheet.round(3),
        d["parameter"]: etch.round(3),
    })


def make_doe_data() -> pd.DataFrame:
    D = PLANTED["doe"]
    rng = np.random.default_rng(PLANTED["seed_doe"])
    names = list(D["levels"])
    # Standard order of a 2^3 design, coded -1/+1, each cell repeated.
    cells = np.array([[(i >> b) & 1 for b in range(len(names))] for i in range(2 ** len(names))]) * 2 - 1
    coded = np.repeat(cells, D["replicates"], axis=0)

    # Model in coded units: coefficient = effect / 2, because moving a factor
    # from -1 to +1 is two coded units.
    y = np.full(len(coded), D["grand_mean"])
    for term, effect in D["effects"].items():
        cols = [names.index(f) for f in term.split(":")]
        y += effect / 2 * coded[:, cols].prod(axis=1)
    y += rng.normal(0, D["sigma"], len(coded))

    df = pd.DataFrame({"run": 0}, index=range(len(coded)))
    for j, f in enumerate(names):
        lo, hi = D["levels"][f]
        df[f] = np.where(coded[:, j] > 0, hi, lo)
    df[D["response"]] = y.round(3)

    # Randomise run order, as a real experiment would, then number the runs.
    df = df.iloc[rng.permutation(len(df))].reset_index(drop=True)
    df["run"] = np.arange(len(df))
    return df


if __name__ == "__main__":
    df = make_process_data()
    df.to_csv(os.path.join(HERE, "process_data.csv"), index=False)
    print("wrote process_data.csv", df.shape)
    doe = make_doe_data()
    doe.to_csv(os.path.join(HERE, "doe_data.csv"), index=False)
    print("wrote doe_data.csv", doe.shape)
