"""
Regenerate the README figures from the tools' own output.

Every number drawn here comes from a spc_tools function, the same calls
Claude makes, so the figures follow the project's rule: no hand-computed
statistics. Run from the repository root:

    python docs/make_figures.py
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import spc_tools as t
from make_data import PLANTED

OUT = os.path.join(ROOT, "docs", "images")
os.makedirs(OUT, exist_ok=True)

DATA, FIT, MUTED, INK, INK2, SURFACE = "#2a78d6", "#eb6834", "#a3a29c", "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": "#d6d5d0", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
})


def call(fn, *args):
    return json.loads(fn(*args))


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=150)
    plt.close(fig)


call(t.load_data, "process_data.csv")
df = t.DATA["df"]
x = df.index.values

# 1. Step change: control chart + the step trend_test found
p = "thickness_nm"
cl, vi, tr = call(t.control_limits, p), call(t.find_violations, p), call(t.trend_test, p)
flagged = sorted({i for v in vi["violations"].values() for i in v})
k = tr["step_changepoint_run"]
fig, ax = plt.subplots(figsize=(9, 3.4))
for key in ("ucl_3s", "lcl_3s"):
    ax.axhline(cl[key], color=MUTED, lw=1, ls="--")
ax.axhline(cl["center"], color=MUTED, lw=1)
ax.plot(x, df[p], color=DATA, lw=1.2, marker="o", ms=3.5)
ax.scatter(flagged, df[p].iloc[flagged], s=36, facecolor="none", edgecolor=FIT, lw=1.5, zorder=3,
           label="Western Electric flag")
before, after = df[p].iloc[:k].mean(), df[p].iloc[k:].mean()
ax.plot([0, k - 0.5, k - 0.5, x[-1]], [before, before, after, after], color=FIT, lw=2, label="step found by trend_test")
ax.text(x[-1], cl["ucl_3s"], " 3σ limits", va="center", color=INK2, fontsize=9)
ax.set_title(f"Step change found at run {k}  (planted at run {PLANTED['thickness_nm']['shift_run']})")
ax.set_xlabel("run"); ax.set_ylabel("thickness (nm)")
ax.legend(frameon=False, loc="upper left", fontsize=9)
save(fig, "step_change.png")

# 2. Slow drift: data + Sen's slope from trend_test
p = "etch_rate_nm_min"
tr = call(t.trend_test, p)
fig, ax = plt.subplots(figsize=(9, 3.4))
ax.plot(x, df[p], color=DATA, lw=1.2, marker="o", ms=3.5)
mid = np.median(df[p] - tr["sens_slope_per_run"] * x)
ax.plot(x, mid + tr["sens_slope_per_run"] * x, color=FIT, lw=2, label=f"drift {tr['sens_slope_per_run']:+.4f} nm/min per run")
ax.set_title(f"Slow drift, classified as '{tr['pattern']}' rather than a step  (Mann-Kendall p = {tr['p_value']:.1g})")
ax.set_xlabel("run"); ax.set_ylabel("etch rate (nm/min)")
ax.legend(frameon=False, loc="upper right", fontsize=9)
save(fig, "slow_drift.png")

# 3. Wrong spec limits: histogram vs spec window and natural +/-3 sigma
p, lsl, usl = "resistance_ohm", 245.0, 252.0
cap, vi = call(t.capability, p, lsl, usl), call(t.find_violations, p)
fig, ax = plt.subplots(figsize=(9, 3.4))
ax.hist(df[p], bins=20, color=DATA, edgecolor=SURFACE, lw=2, zorder=2)
ax.axvspan(lsl, usl, color=FIT, alpha=0.12, lw=0, zorder=0)
for v in (lsl, usl):
    ax.axvline(v, color=FIT, lw=2)
for v in (cap["mean"] - 3 * cap["sigma"], cap["mean"] + 3 * cap["sigma"]):
    ax.axvline(v, color=MUTED, lw=1, ls="--")
top = ax.get_ylim()[1]
ax.text((lsl + usl) / 2, top * 0.93, f"spec {lsl:g}–{usl:g}", ha="center", color=INK, fontsize=9)
ax.text(cap["mean"] + 3 * cap["sigma"], top * 0.93, " process ±3σ", color=INK2, fontsize=9)
ax.set_title(f"Cpk {cap['cpk']} but only {vi['total_flags']} control flags: the limits are wrong, not the process")
ax.set_xlabel("resistance (ohm)"); ax.set_ylabel("runs")
save(fig, "wrong_limits.png")

# 4. DOE effects: recovered vs planted
call(t.load_data, "doe_data.csv")
fa = call(t.factorial_analysis, "deposition_rate_nm_min", ["temperature_c", "chamber_pressure_torr", "rf_power_w"])
planted = PLANTED["doe"]["effects"]
effects = list(reversed(fa["effects"]))
labels = [e["term"].replace("_c", "").replace("_torr", "").replace("_w", "").replace(":", " × ").replace("_", " ")
          for e in effects]
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.barh(labels, [e["effect"] for e in effects], height=0.6,
        color=[DATA if e["significant"] else MUTED for e in effects])
ys = [i for i, e in enumerate(effects) if e["term"] in planted]
ax.scatter([planted[effects[i]["term"]] for i in ys], ys, marker="|", s=400, color=FIT, lw=2.5,
           label="planted value", zorder=3)
ax.axvline(0, color=INK2, lw=0.8)
ax.set_title("DOE: effects on deposition rate (blue = significant, p < 0.05)")
ax.set_xlabel("effect, low → high setting (nm/min)")
ax.legend(frameon=False, loc="lower right", fontsize=9)
save(fig, "doe_effects.png")

print("figures written to", OUT)
