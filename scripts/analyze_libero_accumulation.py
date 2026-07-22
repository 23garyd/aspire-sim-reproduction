#!/usr/bin/env python3
"""Analyze the LIBERO skill-accumulation campaign: per-run success + attempts-to-solve,
then a warm-vs-cold table + honest H1/H0 verdict. Reads run dirs written by
scripts/libero_accumulation.sh. stdlib only."""
from __future__ import annotations

import json
import re
from pathlib import Path

_EXEC = re.compile(r"exec_(\d+)$")

BUDGET_CAP = 999   # censored attempts-to-solve sentinel for aggregation


def attempts_to_solve(out_root, theta: float = 1.0):
    """The 1-based exec index of the first exec_NNNN/result.json with score >= theta,
    scanning in numeric order. None if no exec solved (censored)."""
    out_root = Path(out_root)
    execs = []
    for d in out_root.glob("exec_*"):
        m = _EXEC.search(d.name)
        if m and (d / "result.json").exists():
            execs.append((int(m.group(1)), d / "result.json"))
    for n, rf in sorted(execs):
        try:
            if float(json.loads(rf.read_text()).get("score", 0.0)) >= theta:
                return n
        except (json.JSONDecodeError, ValueError, OSError):
            continue
    return None


def run_outcome(summary: dict, theta: float = 1.0, admission_min_val: float = 0.5) -> dict:
    """Interpret an aspire.run summary line for this campaign's metrics."""
    return {
        "solved": float(summary.get("dbg_score", 0.0)) >= theta,
        "val_solved": float(summary.get("val_score", 0.0)) >= admission_min_val,
        "admitted": len(summary.get("admitted", []) or []),
    }


def read_run(run_dir, task: str, arm: str, repeat: int, theta: float = 1.0) -> dict:
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text())
    oc = run_outcome(summary, theta=theta)
    ats = attempts_to_solve(run_dir / "exec", theta=theta)
    return {"task": task, "arm": arm, "repeat": repeat, "attempts": ats,
            "attempts_censored": ats if ats is not None else BUDGET_CAP, **oc}


def _agg(rows):
    if not rows:
        return {"n": 0, "success_rate": 0.0, "mean_attempts": None}
    return {"n": len(rows),
            "success_rate": sum(r["solved"] for r in rows) / len(rows),
            "mean_attempts": sum(r["attempts_censored"] for r in rows) / len(rows),
            "mean_attempts_solved_only": (
                sum(r["attempts"] for r in rows if r["attempts"] is not None)
                / max(1, sum(1 for r in rows if r["attempts"] is not None)))}


def build_report(campaign_root) -> dict:
    root = Path(campaign_root) / "test"
    rows = []
    for task_dir in sorted(root.glob("*")):
        for arm in ("warm", "cold"):
            for rep_dir in sorted((task_dir / arm).glob("*")):
                if (rep_dir / "summary.json").exists():
                    rows.append(read_run(rep_dir, task_dir.name, arm, int(rep_dir.name)))
    warm = _agg([r for r in rows if r["arm"] == "warm"])
    cold = _agg([r for r in rows if r["arm"] == "cold"])
    # Honest, pre-registered call (suggestive at Lean N).
    if warm["n"] == 0 or cold["n"] == 0:
        verdict = "INCOMPLETE: missing an arm."
    elif warm["success_rate"] > cold["success_rate"] or (
            warm["mean_attempts"] is not None and cold["mean_attempts"] is not None
            and warm["mean_attempts"] < cold["mean_attempts"]):
        verdict = ("H1 (suggestive): warm (accumulated library) beats cold — higher success "
                   f"({warm['success_rate']:.2f} vs {cold['success_rate']:.2f}) and/or fewer "
                   f"attempts ({warm['mean_attempts']} vs {cold['mean_attempts']}). Lean N: not conclusive.")
    else:
        verdict = (f"H0 (suggestive): warm ~= cold (success {warm['success_rate']:.2f} vs "
                   f"{cold['success_rate']:.2f}; attempts {warm['mean_attempts']} vs {cold['mean_attempts']}). "
                   "No measurable accumulation benefit on this suite at Lean N.")
    return {"rows": rows, "warm": warm, "cold": cold, "verdict": verdict}


def render_table(report: dict) -> str:
    lines = ["task           arm   rep  solved  val  attempts  admitted",
             "-------------- ----- ---- ------- ---- --------- --------"]
    for r in sorted(report["rows"], key=lambda x: (x["task"], x["arm"], x["repeat"])):
        lines.append(f"{r['task']:<14} {r['arm']:<5} {r['repeat']:<4} "
                     f"{str(r['solved']):<7} {str(r['val_solved']):<4} "
                     f"{str(r['attempts']):<9} {r['admitted']}")
    lines += ["", f"WARM: {report['warm']}", f"COLD: {report['cold']}", "", "VERDICT: " + report["verdict"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="campaign root (contains test/<task>/<arm>/<rep>/)")
    args = ap.parse_args()
    report = build_report(args.root)
    (Path(args.root) / "results.json").write_text(json.dumps(report, indent=1))
    print(render_table(report))
