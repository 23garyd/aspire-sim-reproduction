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


def read_arm_rows(root, heldout_tasks, prefix="spatial"):
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
                solved = float(s.get("dbg_score", 0)) >= 1.0
                att = attempts_to_solve(rep_dir / "exec", theta=1.0)
                rows.append({"task": f"{prefix}_{tid}", "arm": arm,
                             "solved": solved, "attempts": att})
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


def build_tiling_report(root, heldout_tasks, prefix="spatial"):
    rows = read_arm_rows(root, heldout_tasks, prefix)
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
    verdict = _verdict(arms, pairwise)
    return {"arms": arms, "pairwise": pairwise, "by_task": by_task,
            "rows": rows, "verdict": verdict}


def _verdict(arms, pw):
    b, a, c = arms["warm_geo"], arms["warm_dumpall"], arms["cold"]
    lines = []
    if b["success_rate"] > c["success_rate"] and pw["B_vs_C"] < 0.10:
        lines.append(f"H1-COVERAGE reproduced (suggestive, N=5/arm/task): warm_geo "
                     f"{b['success_rate']:.2f} > cold {c['success_rate']:.2f}, "
                     f"Fisher p(B,C)={pw['B_vs_C']:.4f} < 0.10.")
    if b["success_rate"] > a["success_rate"] and pw["B_vs_A"] < 0.10:
        lines.append(f"H1-RETRIEVAL is the bottleneck (suggestive): warm_geo "
                     f"{b['success_rate']:.2f} > warm_dumpall {a['success_rate']:.2f}, "
                     f"Fisher p(B,A)={pw['B_vs_A']:.4f} < 0.10.")
    if not lines:
        lines.append(f"H0 (null, N=5/arm/task): no arm pair separated at p<0.10 "
                     f"(warm_geo {b['success_rate']:.2f}, warm_dumpall "
                     f"{a['success_rate']:.2f}, cold {c['success_rate']:.2f}; "
                     f"p(B,C)={pw['B_vs_C']:.4f}, p(B,A)={pw['B_vs_A']:.4f}).")
    return " ".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--heldout", required=True, help="comma-separated task ids, e.g. 3,6,8")
    ap.add_argument("--prefix", default="spatial")
    args = ap.parse_args()
    heldout = args.heldout.split(",")
    rep = build_tiling_report(args.root, heldout, args.prefix)
    (Path(args.root) / "results.json").write_text(json.dumps(rep, indent=1))
    for arm in ARMS:
        a = rep["arms"][arm]
        print(f"  {arm}: {a['success_rate']:.2f} ({a['n_solved']}/{a['n']}), "
              f"mean_attempts={a['mean_attempts_solved_only']}")
    print("  pairwise Fisher p:", rep["pairwise"])
    print("VERDICT:", rep["verdict"])


if __name__ == "__main__":
    main()
