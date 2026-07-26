#!/usr/bin/env python3
"""Three-arm tiling analyzer: warm_geo (B) vs warm_dumpall (A) vs cold (C).
Pairwise Fisher-exact: B_vs_C (headline reproduction), B_vs_A (retrieval effect),
A_vs_C (naive tiling). Reuses the v2 analyzer's pure helpers."""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_libero_accumulation_v2 import fisher_exact_2x2   # Fisher lives in v2
from analyze_libero_accumulation import attempts_to_solve      # attempts_to_solve lives in v1

ARMS = ("warm_geo", "warm_dumpall", "cold")


def read_arm_rows(root, heldout_tasks, prefix="spatial", metric="dbg"):
    root = Path(root)
    rows = []
    for tid in heldout_tasks:
        for arm in ARMS:
            base = root / "test" / f"{prefix}_{tid}" / arm
            if not base.is_dir():
                continue
            for rep_dir in sorted(base.glob("*")):
                sfile = rep_dir / "summary.json"
                if not sfile.is_file():
                    continue
                s = json.loads(sfile.read_text())
                if metric == "val":
                    solved = float(s.get("val_score", 0)) >= 0.5
                else:
                    solved = float(s.get("dbg_score", 0)) >= 1.0
                att = attempts_to_solve(rep_dir / "exec", theta=1.0)
                rows.append({"task": f"{prefix}_{tid}", "arm": arm,
                             "solved": solved, "attempts": att,
                             "val_score": float(s.get("val_score", 0)),
                             "dbg_score": float(s.get("dbg_score", 0))})
    return rows


def _agg(rows):
    solved = [r for r in rows if r["solved"]]
    atts = [r["attempts"] for r in solved if r["attempts"] is not None]
    return {"n": len(rows), "n_solved": len(solved),
            "success_rate": (len(solved) / len(rows)) if rows else 0.0,
            "mean_attempts_solved_only": (sum(atts) / len(atts)) if atts else None}


def _pair_p(arm_rows_x, arm_rows_y):
    a = sum(1 for r in arm_rows_x if r["solved"]); b = len(arm_rows_x) - a
    c = sum(1 for r in arm_rows_y if r["solved"]); d = len(arm_rows_y) - c
    return fisher_exact_2x2(a, b, c, d)


def build_tiling_report(root, heldout_tasks, prefix="spatial", metric="dbg", alpha=0.10):
    rows = read_arm_rows(root, heldout_tasks, prefix, metric)
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    arms = {arm: _agg(by_arm[arm]) for arm in ARMS}
    pairwise = {
        "B_vs_C": _pair_p(by_arm["warm_geo"], by_arm["cold"]),
        "B_vs_A": _pair_p(by_arm["warm_geo"], by_arm["warm_dumpall"]),
        "A_vs_C": _pair_p(by_arm["warm_dumpall"], by_arm["cold"]),
    }
    by_task = {}
    for tid in heldout_tasks:
        t = f"{prefix}_{tid}"
        by_task[t] = {arm: _agg([r for r in by_arm[arm] if r["task"] == t]) for arm in ARMS}
    verdict = _verdict(arms, pairwise, alpha=alpha, metric=metric)
    return {"arms": arms, "pairwise": pairwise, "by_task": by_task,
            "rows": rows, "metric": metric, "alpha": alpha, "verdict": verdict}


def _verdict(arms, pw, alpha=0.10, metric="dbg"):
    geo, dump, cold = arms["warm_geo"], arms["warm_dumpall"], arms["cold"]
    m = metric.upper()
    # Primary contrast: warm_geo vs cold if warm_geo ran, else warm_dumpall vs cold.
    if geo["n"] > 0:
        warm, p_primary, label = geo, pw["B_vs_C"], "warm_geo"
    else:
        warm, p_primary, label = dump, pw["A_vs_C"], "warm_dumpall"
    if warm["n"] == 0 or cold["n"] == 0:
        return f"INCONCLUSIVE ({m}): missing arm (warm n={warm['n']}, cold n={cold['n']})."
    if warm["success_rate"] > cold["success_rate"] and p_primary < alpha:
        return (f"H1 reproduced ({m}, pre-registered alpha={alpha}): {label} "
                f"{warm['success_rate']:.2f} > cold {cold['success_rate']:.2f}, "
                f"Fisher p={p_primary:.4f} < {alpha}.")
    return (f"H0 (null, {m}, alpha={alpha}): {label} {warm['success_rate']:.2f} vs "
            f"cold {cold['success_rate']:.2f}, Fisher p={p_primary:.4f} (not < {alpha}).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--heldout", required=True, help="comma-separated task ids, e.g. 3,6,8")
    ap.add_argument("--prefix", default="spatial")
    ap.add_argument("--metric", choices=("dbg", "val"), default="dbg")
    ap.add_argument("--alpha", type=float, default=0.10)
    args = ap.parse_args()
    heldout = args.heldout.split(",")
    rep = build_tiling_report(args.root, heldout, args.prefix, args.metric, args.alpha)
    (Path(args.root) / "results.json").write_text(json.dumps(rep, indent=1))
    for arm in ARMS:
        a = rep["arms"][arm]
        print(f"  {arm}: {a['success_rate']:.2f} ({a['n_solved']}/{a['n']}), "
              f"mean_attempts={a['mean_attempts_solved_only']}")
    print("  pairwise Fisher p:", rep["pairwise"])
    print("VERDICT:", rep["verdict"])


if __name__ == "__main__":
    main()
