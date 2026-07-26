#!/usr/bin/env python3
"""Re-analyze every existing LIBERO campaign on HELD-OUT VALIDATION (val_score >= 0.5)
vs the debug-seed metric (dbg_score >= 1.0) the original analyses scored. Pure: reads
the per-cell summary.json files already on disk; no GPU, no new runs. Fisher-exact via
the committed helper. Motivation: ASPIRE's accumulation claim is about generalization,
but every campaign scored debug-solve — this checks whether the signal was masked.

Usage: python3 scripts/reanalyze_val.py
"""
import glob, json, os, sys
from math import comb
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from analyze_libero_accumulation_v2 import fisher_exact_2x2

ROOTS = {
    "C1 libero_accum (spatial warm/cold)":       "libero_accum",
    "C2 libero_accum_v2 (frontier t=5, 5/3)":    "libero_accum_v2",
    "C2b libero_accum_v2b (frontier t=2, 8/6)":  "libero_accum_v2b",
    "C3 libero_tiling (tiling t=2, 3/6/8)":      "libero_tiling",
    "C4 libero_hard (libero_10 t=2, 0/6/3)":     "libero_hard",
}
LIB_ARMS = ("warm", "warm_dumpall")   # primary library arms (exclude bowl-limited warm_geo from the pool)


def cells(root):
    root = os.path.expanduser(f"~/aspire_runs/{root}")
    out = []
    for f in glob.glob(f"{root}/test/*/*/*/summary.json"):
        p = f.split("/test/")[1].split("/")
        if len(p) < 4:
            continue
        try:
            d = json.load(open(f))
        except Exception:
            continue
        out.append({"task": p[0], "arm": p[1],
                    "dbg": float(d.get("dbg_score", 0)) >= 1.0,
                    "val": float(d.get("val_score", 0)) >= 0.5})
    return out


def main():
    W = Wn = C = Cn = 0
    dirs = []
    for label, root in ROOTS.items():
        rows = cells(root)
        if not rows:
            continue
        print(f"\n### {label}")
        print(f"  {'arm':<13} {'n':>3}  {'dbg':>10}  {'VAL':>10}  overfit(dbg-val)")
        for arm in sorted({r['arm'] for r in rows}):
            ar = [r for r in rows if r['arm'] == arm]
            ds = sum(r['dbg'] for r in ar); vs = sum(r['val'] for r in ar); n = len(ar)
            print(f"  {arm:<13} {n:>3}  {ds:>2}/{n} ={ds/n:>4.2f}  {vs:>2}/{n} ={vs/n:>4.2f}   {ds-vs:+d}")
        cold = [r for r in rows if r['arm'] == 'cold']
        ctasks = {r['task'] for r in cold}
        for wa in [a for a in sorted({r['arm'] for r in rows}) if a != 'cold']:
            w = [r for r in rows if r['arm'] == wa and r['task'] in ctasks]
            wt = {r['task'] for r in w}
            c = [r for r in cold if r['task'] in wt]
            if not w or not c:
                continue
            a = sum(r['val'] for r in w); cc = sum(r['val'] for r in c)
            p = fisher_exact_2x2(a, len(w) - a, cc, len(c) - cc)
            print(f"    VAL {wa} {a}/{len(w)} vs cold {cc}/{len(c)} (tasks {sorted(wt)}): Fisher p={p:.4f}")
            if wa in LIB_ARMS:
                W += a; Wn += len(w); C += cc; Cn += len(c)
                wg = (sum(r['dbg'] for r in w) - a) / len(w)
                cg = (sum(r['dbg'] for r in c) - cc) / len(c)
                dirs.append(cg > wg)
    print("\n### CROSS-CAMPAIGN POOLED (primary library arms vs cold, on VAL)")
    print(f"  library {W}/{Wn} = {W/Wn:.2f}  vs  cold {C}/{Cn} = {C/Cn:.2f}   Fisher p = {fisher_exact_2x2(W, Wn-W, C, Cn-C):.4f}")
    k, n = sum(dirs), len(dirs)
    psign = min(1.0, sum(comb(n, i) for i in range(k, n + 1)) / 2**n * 2)
    print(f"  cold overfits MORE than the library in {k}/{n} campaigns (sign-test p = {psign:.4f})")
    print("  NOTE: val was NOT the pre-registered metric — this is post-hoc/exploratory; the pooled")
    print("  Fisher treats reps as independent (optimistic); the 5/5 sign test is the conservative read.")


if __name__ == "__main__":
    main()
