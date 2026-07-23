import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_accumulation_v2 import (
    fisher_exact_2x2,
    build_report,
    resolve_selected_tasks,
)


def _mk_run(run_dir, dbg, val, admitted, winner_exec):
    (run_dir / "exec").mkdir(parents=True)
    for n in range(1, (winner_exec or 6) + 1):
        d = run_dir / "exec" / f"exec_{n:04d}"; d.mkdir()
        score = 1.0 if (winner_exec and n == winner_exec) else 0.0
        (d / "result.json").write_text(json.dumps({"score": score}))
    run_dir.joinpath("summary.json").write_text(json.dumps(
        {"stage_reached": "validated", "dbg_score": dbg, "val_score": val, "admitted": admitted}))


# --------------------------------------------------------------------------- #
# Fisher-exact against hand-computed values (no scipy).
# --------------------------------------------------------------------------- #
def test_fisher_exact_lady_tasting_tea():
    # Classic 2x2 [[3,1],[1,3]] two-sided Fisher p = 0.485714... (well-known value).
    assert math.isclose(fisher_exact_2x2(3, 1, 1, 3), 0.4857142857, rel_tol=1e-6)


def test_fisher_exact_full_separation():
    # [[4,0],[0,4]]: only the two extreme tables are <= p_obs -> 2/70 = 0.0285714.
    assert math.isclose(fisher_exact_2x2(4, 0, 0, 4), 2.0 / 70.0, rel_tol=1e-9)


def test_fisher_exact_degenerate_returns_one():
    assert fisher_exact_2x2(0, 0, 0, 0) == 1.0
    assert fisher_exact_2x2(5, 0, 5, 0) == 1.0  # a column margin is zero


# --------------------------------------------------------------------------- #
# Matched analysis: excludes non-test tasks, computes per-arm success + fisher_p.
# --------------------------------------------------------------------------- #
def _build_campaign(tmp_path):
    base = tmp_path / "test"
    # Selected frontier tasks: spatial_8 (warm 5/5, cold 1/5), spatial_6 (warm 4/5, cold 1/5).
    # warm strongly beats cold. One cold run is censored (never solves).
    specs = {
        "spatial_8": {
            "warm": [(1.0, 3), (1.0, 4), (1.0, 5), (1.0, 2), (1.0, 3)],
            "cold": [(1.0, 12), (0.0, None), (0.0, None), (0.0, None), (0.0, None)],
        },
        "spatial_6": {
            "warm": [(1.0, 4), (1.0, 3), (1.0, 5), (1.0, 4), (0.0, None)],
            "cold": [(1.0, 14), (0.0, None), (0.0, None), (0.0, None), (0.0, None)],
        },
    }
    for task, arms in specs.items():
        for arm, runs in arms.items():
            for rep, (dbg, winner) in enumerate(runs, 1):
                r = base / task / arm / str(rep); r.mkdir(parents=True)
                _mk_run(r, dbg, 1.0 if dbg else 0.0, ["s"] if dbg else [], winner)
    # A NON-selected task with both arms present -> must be EXCLUDED from both arms.
    for arm in ("warm", "cold"):
        for rep in (1, 2):
            r = base / "spatial_99" / arm / str(rep); r.mkdir(parents=True)
            _mk_run(r, 1.0, 1.0, ["s"], winner_exec=1)  # all-solved noise
    (tmp_path / "selected_tasks.json").write_text(json.dumps([8, 6]))
    return tmp_path


def test_resolve_selected_from_json(tmp_path):
    (tmp_path / "selected_tasks.json").write_text(json.dumps([8, 6]))
    assert resolve_selected_tasks(tmp_path) == ["spatial_8", "spatial_6"]


def test_resolve_selected_inferred_when_absent(tmp_path):
    base = tmp_path / "test"
    # spatial_5 has both warm+cold -> inferred; spatial_7 has only warm -> excluded.
    for arm in ("warm", "cold"):
        (base / "spatial_5" / arm / "1").mkdir(parents=True)
    (base / "spatial_7" / "warm" / "1").mkdir(parents=True)
    assert resolve_selected_tasks(tmp_path) == ["spatial_5"]


def test_matched_report_excludes_non_test_tasks(tmp_path):
    root = _build_campaign(tmp_path)
    rep = build_report(root)
    tasks_in_rows = {r["task"] for r in rep["rows"]}
    assert tasks_in_rows == {"spatial_8", "spatial_6"}
    assert "spatial_99" not in tasks_in_rows  # confound fix: non-selected excluded
    assert rep["selected_tasks"] == ["spatial_6", "spatial_8"]
    # 10 runs per arm (2 tasks x 5 repeats).
    assert rep["warm"]["n"] == 10 and rep["cold"]["n"] == 10


def test_matched_report_success_rates_and_fisher(tmp_path):
    root = _build_campaign(tmp_path)
    rep = build_report(root)
    # warm 9/10, cold 2/10.
    assert rep["warm"]["n_solved"] == 9
    assert rep["cold"]["n_solved"] == 2
    assert math.isclose(rep["warm"]["success_rate"], 0.9)
    assert math.isclose(rep["cold"]["success_rate"], 0.2)
    # fisher_p matches direct computation on the matched 2x2 [[9,1],[2,8]].
    assert math.isclose(rep["fisher_p"], fisher_exact_2x2(9, 1, 2, 8), rel_tol=1e-9)
    assert rep["fisher_p"] < 0.10
    assert rep["verdict"].startswith("H1")
    assert "suggestive, not conclusive at N=5/arm/task" in rep["verdict"]


def test_attempts_to_solve_censoring(tmp_path):
    root = _build_campaign(tmp_path)
    rep = build_report(root)
    # cold: only 2 solved (attempts 12, 14) -> 8 censored per arm pooled.
    assert rep["cold"]["censored"] == 8
    assert math.isclose(rep["cold"]["mean_attempts_solved_only"], (12 + 14) / 2)
    # warm: 9 solved, 1 censored.
    assert rep["warm"]["censored"] == 1


def test_null_verdict_when_no_gap(tmp_path):
    base = tmp_path / "test"
    # warm == cold (both 1/2 solved) -> H0 null with attempts delta.
    for arm in ("warm", "cold"):
        for rep, (dbg, w) in enumerate([(1.0, 3), (0.0, None)], 1):
            r = base / "spatial_8" / arm / str(rep); r.mkdir(parents=True)
            _mk_run(r, dbg, 1.0 if dbg else 0.0, ["s"] if dbg else [], w)
    (tmp_path / "selected_tasks.json").write_text(json.dumps([8]))
    rep = build_report(tmp_path)
    assert rep["warm"]["success_rate"] == rep["cold"]["success_rate"]
    assert rep["verdict"].startswith("H0")
