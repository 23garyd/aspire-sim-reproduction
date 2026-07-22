import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_accumulation import read_run, build_report


def _mk_run(run_dir, dbg, val, admitted, winner_exec):
    (run_dir / "exec").mkdir(parents=True)
    for n in range(1, (winner_exec or 6) + 1):
        d = run_dir / "exec" / f"exec_{n:04d}"; d.mkdir()
        score = 1.0 if (winner_exec and n == winner_exec) else 0.0
        (d / "result.json").write_text(json.dumps({"score": score}))
    run_dir.joinpath("summary.json").write_text(json.dumps(
        {"stage_reached": "validated", "dbg_score": dbg, "val_score": val, "admitted": admitted}))


def test_read_run_extracts_fields(tmp_path):
    r = tmp_path / "test" / "spatial_6" / "warm" / "1"
    r.mkdir(parents=True)
    _mk_run(r, dbg=1.0, val=1.0, admitted=["s"], winner_exec=8)
    out = read_run(r, task="spatial_6", arm="warm", repeat=1)
    assert out["solved"] and out["attempts"] == 8 and out["arm"] == "warm"


def test_build_report_warm_beats_cold(tmp_path):
    base = tmp_path / "test"
    # warm solves both tasks fast (attempts 5); cold slow/one unsolved
    for task in ("spatial_6", "spatial_8"):
        for rep in (1, 2):
            w = base / task / "warm" / str(rep); w.mkdir(parents=True)
            _mk_run(w, 1.0, 1.0, ["s"], winner_exec=5)
    for task, cold_specs in (("spatial_6", [(1.0, 12), (1.0, 14)]), ("spatial_8", [(0.0, None), (1.0, 15)])):
        for rep, (dbg, winner) in enumerate(cold_specs, 1):
            c = base / task / "cold" / str(rep); c.mkdir(parents=True)
            _mk_run(c, dbg, 1.0 if dbg else 0.0, ["s"] if dbg else [], winner_exec=winner)
    rep = build_report(tmp_path)
    assert rep["warm"]["success_rate"] == 1.0
    assert rep["warm"]["mean_attempts"] < rep["cold"]["mean_attempts"]
    assert "H1" in rep["verdict"] or "warm" in rep["verdict"].lower()
