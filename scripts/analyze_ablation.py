#!/usr/bin/env python3
"""Pre-registered analysis for the traces-vs-retry ablation. Reads per-arm held-out
validation scores and reports mean/median, P(val>=0.80), and a rank-sum Mann-Whitney
U with tie-corrected normal-approximation z. Stdlib only. The decision rule is fixed
BEFORE the campaign runs; this script is run identically whichever way the data falls.
"""
import json
import math
import sys
from pathlib import Path


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based mid-rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def mann_whitney_u(a, b):
    """Return (U_a, z). U_a = rank-sum U for sample a vs b; z = tie-corrected
    normal approximation (negative when a tends below b)."""
    n, m = len(a), len(b)
    ranks = _ranks(list(a) + list(b))
    r_a = sum(ranks[:n])
    u_a = r_a - n * (n + 1) / 2
    mu = n * m / 2
    # tie-corrected variance
    all_vals = list(a) + list(b)
    counts = {}
    for v in all_vals:
        counts[v] = counts.get(v, 0) + 1
    tie = sum(t**3 - t for t in counts.values())
    N = n + m
    var = (n * m / 12) * ((N + 1) - tie / (N * (N - 1))) if N > 1 else 0.0
    z = (u_a - mu) / math.sqrt(var) if var > 0 else 0.0
    return u_a, z


def _arm_scores(arm_dir: Path):
    scores = []
    for done in sorted(arm_dir.glob("rep_*/robosuite/two_arm_lift/VALIDATION_DONE")):
        scores.append(json.loads(done.read_text())["score"])
    return scores


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.home() / "aspire_runs" / "traces_ablation"
    t = _arm_scores(root / "T")
    c = _arm_scores(root / "C")
    if not t or not c:
        print(f"missing scores (T={len(t)}, C={len(c)}) under {root}")
        return 1
    u, z = mann_whitney_u(t, c)

    def summ(label, xs):
        s = sorted(xs)
        mean = sum(s) / len(s)
        med = s[len(s) // 2] if len(s) % 2 else (s[len(s)//2 - 1] + s[len(s)//2]) / 2
        strong = sum(1 for v in s if v >= 0.80) / len(s)
        print(f"{label}: n={len(s)} mean={mean:.3f} median={med:.3f} "
              f"P(val>=0.80)={strong:.2f} scores={s}")

    summ("T (traces)", t)
    summ("C (retry)", c)
    print(f"Mann-Whitney U(T vs C)={u:.1f}  z={z:.3f}  "
          f"(z>0 => traces arm ranks higher)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
