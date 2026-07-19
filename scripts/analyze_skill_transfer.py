#!/usr/bin/env python3
"""Pre-registered analysis for the skill-transfer test (arms S=seeded, E=empty).
Reuses the ablation's Mann-Whitney U and per-arm score reader — the statistic is
NOT reimplemented. Reports mean/median, P(val>=0.80), and U(S vs E) with z.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root on path
from scripts.analyze_ablation import _arm_scores, mann_whitney_u


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.home() / "aspire_runs" / "skill_transfer"
    s = _arm_scores(root / "S")
    e = _arm_scores(root / "E")
    if not s or not e:
        print(f"missing scores (S={len(s)}, E={len(e)}) under {root}")
        return 1
    u, z = mann_whitney_u(s, e)

    def summ(label, xs):
        xs = sorted(xs)
        mean = sum(xs) / len(xs)
        med = xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs)//2 - 1] + xs[len(xs)//2]) / 2
        strong = sum(1 for v in xs if v >= 0.80) / len(xs)
        print(f"{label}: n={len(xs)} mean={mean:.3f} median={med:.3f} "
              f"P(val>=0.80)={strong:.2f} scores={xs}")

    summ("S (seeded)", s)
    summ("E (empty)", e)
    print(f"Mann-Whitney U(S vs E)={u:.1f}  z={z:.3f}  "
          f"(z>0 => seeded arm ranks higher)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
