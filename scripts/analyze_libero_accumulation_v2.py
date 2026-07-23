#!/usr/bin/env python3
"""Analyze the LIBERO skill-accumulation FRONTIER campaign (v2): MATCHED warm-vs-cold on
the selected frontier test tasks only, with a Fisher-exact p on the 2x2 (arm x solved)
table and attempts-to-solve. This is the confound fix over v1: it NEVER pools probe /
reject tasks into either arm -- only the matched selected test tasks are compared.

Reuses the proven pure helpers' semantics from analyze_libero_accumulation.py
(attempts_to_solve, run_outcome, read_run). stdlib only (no scipy)."""
from __future__ import annotations

import json
import math
from pathlib import Path

# Reuse the v1 pure helpers verbatim (same scripts/ dir is on sys.path).
from analyze_libero_accumulation import attempts_to_solve, run_outcome, read_run  # noqa: F401

BUDGET_CAP = 999  # censored attempts-to-solve sentinel (mirrors v1)


# --------------------------------------------------------------------------- #
# Frontier selector (pure) — kept exactly-1-of-2 solved probe tasks.
# --------------------------------------------------------------------------- #
def select_frontier(probe_results, n: int = 2) -> dict:
    """Select frontier test tasks from cold-probe results.

    probe_results maps task -> list[bool] (one entry per probe repeat, True == solved).
    Keep only tasks that solved EXACTLY 1 of their repeats (the solvability knife's
    edge): 2/2 is too easy (cold already wins), 0/2 is likely unsolvable at this budget.
    Return the first `n` qualifying tasks in iteration order.

    Returns {"selected": [...], "insufficient": bool, "n_qualified": int}. When fewer
    than `n` tasks qualify, `insufficient` is True and `selected` holds all qualifiers.
    """
    qualified = []
    for task, solved_list in probe_results.items():
        total = len(solved_list)
        n_solved = sum(1 for s in solved_list if s)
        if total == 2 and n_solved == 1:  # exactly 1-of-2 -> frontier band
            qualified.append(task)
    selected = qualified[:n]
    return {
        "selected": selected,
        "insufficient": len(qualified) < n,
        "n_qualified": len(qualified),
    }


# --------------------------------------------------------------------------- #
# Fisher-exact two-sided p on a 2x2 table (no scipy; math.comb only).
# --------------------------------------------------------------------------- #
def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher-exact p for the 2x2 table [[a, b], [c, d]].

    Sums the hypergeometric probabilities of all tables sharing the same margins whose
    probability is <= that of the observed table (with a tiny tolerance for ties)."""
    row1, row2 = a + b, c + d
    col1 = a + c
    n = a + b + c + d
    if n == 0 or row1 == 0 or row2 == 0 or col1 == 0 or (b + d) == 0:
        return 1.0

    def _p(x: int) -> float:
        # P(top-left cell == x) under the hypergeometric law with fixed margins.
        return (
            math.comb(row1, x)
            * math.comb(row2, col1 - x)
            / math.comb(n, col1)
        )

    p_obs = _p(a)
    lo = max(0, col1 - row2)
    hi = min(row1, col1)
    tol = 1e-9
    total = 0.0
    for x in range(lo, hi + 1):
        px = _p(x)
        if px <= p_obs * (1.0 + tol):
            total += px
    return min(1.0, total)


# --------------------------------------------------------------------------- #
# Selected-task resolution.
# --------------------------------------------------------------------------- #
def _dir_name(task_id) -> str:
    """Normalize a selected task id to its test-dir name (spatial_<id>)."""
    s = str(task_id)
    return s if s.startswith("spatial_") else f"spatial_{s}"


def resolve_selected_tasks(campaign_root) -> list:
    """The matched selected test tasks (as test-dir names). Prefer the
    selected_tasks.json the runner writes under <root>; else infer from which tasks
    have BOTH warm and cold subdirs."""
    root = Path(campaign_root)
    sel_file = root / "selected_tasks.json"
    if sel_file.exists():
        try:
            ids = json.loads(sel_file.read_text())
            return [_dir_name(t) for t in ids]
        except (json.JSONDecodeError, OSError):
            pass
    # Infer: tasks with BOTH warm and cold subdirs.
    inferred = []
    test_root = root / "test"
    if test_root.exists():
        for task_dir in sorted(test_root.glob("*")):
            if (task_dir / "warm").is_dir() and (task_dir / "cold").is_dir():
                inferred.append(task_dir.name)
    return inferred


# --------------------------------------------------------------------------- #
# Aggregation + report.
# --------------------------------------------------------------------------- #
def _agg(rows) -> dict:
    if not rows:
        return {"n": 0, "n_solved": 0, "success_rate": 0.0,
                "mean_attempts_solved_only": None, "censored": 0}
    solved_rows = [r for r in rows if r["attempts"] is not None]
    n_solved = sum(1 for r in rows if r["solved"])
    return {
        "n": len(rows),
        "n_solved": n_solved,
        "success_rate": n_solved / len(rows),
        "mean_attempts_solved_only": (
            sum(r["attempts"] for r in solved_rows) / len(solved_rows)
            if solved_rows else None),
        "censored": sum(1 for r in rows if r["attempts"] is None),
    }


def build_report(campaign_root, theta: float = 1.0) -> dict:
    """Matched warm-vs-cold report on the selected frontier test tasks ONLY."""
    root = Path(campaign_root)
    selected = set(resolve_selected_tasks(root))
    test_root = root / "test"
    rows = []
    if test_root.exists():
        for task_dir in sorted(test_root.glob("*")):
            if task_dir.name not in selected:
                continue  # confound fix: never pool non-selected tasks into an arm
            for arm in ("warm", "cold"):
                for rep_dir in sorted((task_dir / arm).glob("*")):
                    if (rep_dir / "summary.json").exists():
                        rows.append(read_run(rep_dir, task_dir.name, arm,
                                             int(rep_dir.name), theta=theta))
    warm_rows = [r for r in rows if r["arm"] == "warm"]
    cold_rows = [r for r in rows if r["arm"] == "cold"]
    warm = _agg(warm_rows)
    cold = _agg(cold_rows)

    # Per-task breakdown (guards a single lucky task masquerading as a pooled effect).
    by_task = {}
    for t in sorted(selected):
        by_task[t] = {
            "warm": _agg([r for r in warm_rows if r["task"] == t]),
            "cold": _agg([r for r in cold_rows if r["task"] == t]),
        }

    # 2x2: rows = arm (warm/cold), cols = solved/unsolved.
    a = warm["n_solved"]
    b = warm["n"] - warm["n_solved"]
    c = cold["n_solved"]
    d = cold["n"] - cold["n_solved"]
    fisher_p = fisher_exact_2x2(a, b, c, d)

    # Pre-registered verdict.
    if warm["n"] == 0 or cold["n"] == 0:
        verdict = "INCOMPLETE: a matched arm is missing (no runs for warm or cold)."
    elif warm["success_rate"] > cold["success_rate"] and fisher_p < 0.10:
        verdict = (
            "H1 (reproduced, suggestive): warm (accumulated library) beats cold on "
            f"matched held-out success ({warm['success_rate']:.2f} vs "
            f"{cold['success_rate']:.2f}), Fisher p={fisher_p:.4f} < 0.10. "
            "Labeled suggestive, not conclusive at N=5/arm/task.")
    else:
        wa = warm["mean_attempts_solved_only"]
        ca = cold["mean_attempts_solved_only"]
        delta = (ca - wa) if (wa is not None and ca is not None) else None
        verdict = (
            "H0 (null): accumulation did not change matched held-out solvability at "
            f"this budget (warm {warm['success_rate']:.2f} vs cold "
            f"{cold['success_rate']:.2f}, Fisher p={fisher_p:.4f}). "
            f"Attempts-to-solve delta (cold-warm, solved runs): {delta}.")

    return {
        "rows": rows,
        "selected_tasks": sorted(selected),
        "warm": warm,
        "cold": cold,
        "by_task": by_task,
        "fisher_p": fisher_p,
        "verdict": verdict,
    }


def render_table(report: dict) -> str:
    lines = [
        f"selected test tasks: {report['selected_tasks']}",
        "",
        "task           arm   rep  solved  val   attempts  admitted",
        "-------------- ----- ---- ------- ----- --------- --------",
    ]
    for r in sorted(report["rows"], key=lambda x: (x["task"], x["arm"], x["repeat"])):
        lines.append(
            f"{r['task']:<14} {r['arm']:<5} {r['repeat']:<4} "
            f"{str(r['solved']):<7} {str(r['val_solved']):<5} "
            f"{str(r['attempts']):<9} {r['admitted']}")
    lines += [""]
    for t, tt in report["by_task"].items():
        lines.append(f"  {t}: warm {tt['warm']['success_rate']:.2f} "
                     f"({tt['warm']['n_solved']}/{tt['warm']['n']}) vs "
                     f"cold {tt['cold']['success_rate']:.2f} "
                     f"({tt['cold']['n_solved']}/{tt['cold']['n']})")
    lines += ["",
              f"WARM: {report['warm']}",
              f"COLD: {report['cold']}",
              f"FISHER p (matched 2x2): {report['fisher_p']:.4f}",
              "",
              "VERDICT: " + report["verdict"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True,
                    help="campaign root (contains test/<task>/<arm>/<rep>/ and "
                         "optionally selected_tasks.json)")
    args = ap.parse_args()
    report = build_report(args.root)
    (Path(args.root) / "results.json").write_text(json.dumps(report, indent=1))
    print(render_table(report))
