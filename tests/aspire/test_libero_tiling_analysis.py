import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_tiling import build_tiling_report


def _mk(root, task, arm, rep, solved, winner=2):
    d = root / "test" / f"spatial_{task}" / arm / str(rep)
    (d / "exec").mkdir(parents=True)
    for n in range(1, (winner if solved else 3) + 1):
        e = d / "exec" / f"exec_{n:04d}"; e.mkdir()
        sc = 1.0 if (solved and n == winner) else 0.0
        (e / "result.json").write_text(json.dumps({"score": sc}))
    d.joinpath("summary.json").write_text(json.dumps(
        {"dbg_score": 1.0 if solved else 0.0, "val_score": 0.0, "admitted": []}))


def test_three_arm_success_and_pairwise(tmp_path):
    # warm_geo solves all; cold solves few; warm_dumpall middling — across 3 tasks
    plan = {"warm_geo": [1,1,1,1,1], "cold": [0,0,1,0,0], "warm_dumpall": [1,0,1,0,1]}
    for task in ("3","6","8"):
        for arm, reps in plan.items():
            for i, sv in enumerate(reps, 1):
                _mk(tmp_path, task, arm, i, bool(sv))
    rep = build_tiling_report(tmp_path, ["3","6","8"])
    assert rep["arms"]["warm_geo"]["success_rate"] == 1.0
    assert rep["arms"]["cold"]["success_rate"] < 0.3
    # B_vs_C = warm_geo vs cold: strongly separated -> small p
    assert rep["pairwise"]["B_vs_C"] < 0.10
    assert "verdict" in rep


def test_excludes_non_heldout_tasks(tmp_path):
    for arm in ("warm_geo", "cold", "warm_dumpall"):
        for i in range(1, 6):
            _mk(tmp_path, "8", arm, i, True)
            _mk(tmp_path, "99", arm, i, False)   # not in heldout -> excluded
    rep = build_tiling_report(tmp_path, ["8"])
    assert rep["arms"]["warm_geo"]["n"] == 5      # only task 8
