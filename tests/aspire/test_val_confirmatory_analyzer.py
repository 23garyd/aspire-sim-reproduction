import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_tiling import build_tiling_report


def _mk(root, task, arm, rep, dbg, val, winner=2):
    d = root / "test" / f"10_{task}" / arm / str(rep)
    (d / "exec").mkdir(parents=True)
    for n in range(1, (winner if dbg >= 1.0 else 3) + 1):
        e = d / "exec" / f"exec_{n:04d}"; e.mkdir()
        (e / "result.json").write_text(json.dumps({"score": 1.0 if (dbg >= 1.0 and n == winner) else 0.0}))
    d.joinpath("summary.json").write_text(json.dumps({"dbg_score": dbg, "val_score": val, "admitted": []}))


def test_metric_val_scores_on_val_score(tmp_path):
    # cold: high dbg, low val (overfit). warm_dumpall: lower dbg, higher val (generalizes).
    for rep in range(1, 6):
        _mk(tmp_path, "6", "cold", rep, dbg=1.0, val=0.0)
        _mk(tmp_path, "6", "warm_dumpall", rep, dbg=0.0, val=1.0)
    dbg_rep = build_tiling_report(tmp_path, ["6"], prefix="10", metric="dbg")
    val_rep = build_tiling_report(tmp_path, ["6"], prefix="10", metric="val")
    # dbg: cold solves, warm doesn't
    assert dbg_rep["arms"]["cold"]["success_rate"] == 1.0
    assert dbg_rep["arms"]["warm_dumpall"]["success_rate"] == 0.0
    # val: flipped
    assert val_rep["arms"]["cold"]["success_rate"] == 0.0
    assert val_rep["arms"]["warm_dumpall"]["success_rate"] == 1.0


def test_verdict_uses_warm_dumpall_when_geo_absent(tmp_path):
    # only warm_dumpall + cold present; warm_geo has zero rows
    for rep in range(1, 6):
        _mk(tmp_path, "6", "warm_dumpall", rep, dbg=0.0, val=1.0)
        _mk(tmp_path, "6", "cold", rep, dbg=1.0, val=0.0)
    rep = build_tiling_report(tmp_path, ["6"], prefix="10", metric="val", alpha=0.05)
    assert rep["arms"]["warm_geo"]["n"] == 0
    # primary contrast is A_vs_C (warm_dumpall vs cold), and it is significant here
    assert rep["pairwise"]["A_vs_C"] < 0.05
    assert "warm_dumpall" in rep["verdict"] and "warm_geo" not in rep["verdict"]
    assert "H1" in rep["verdict"]
