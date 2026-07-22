import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_accumulation import attempts_to_solve, run_outcome


def _mk_exec(root, n, score):
    d = root / f"exec_{n:04d}"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"score": score, "raw_dir": "", "traces": []}))


def test_attempts_to_solve_first_winner(tmp_path):
    # execs 1..14 score 0, exec 15 scores 1.0 -> attempts_to_solve == 15
    for n in range(1, 15):
        _mk_exec(tmp_path, n, 0.0)
    _mk_exec(tmp_path, 15, 1.0)
    _mk_exec(tmp_path, 16, 0.0)
    _mk_exec(tmp_path, 17, 1.0)
    assert attempts_to_solve(tmp_path, theta=1.0) == 15


def test_attempts_to_solve_censored_when_unsolved(tmp_path):
    for n in range(1, 6):
        _mk_exec(tmp_path, n, 0.0)
    assert attempts_to_solve(tmp_path, theta=1.0) is None


def test_run_outcome_solved_validated_admitted():
    s = {"stage_reached": "validated", "dbg_score": 1.0, "val_score": 1.0, "admitted": ["a", "b"]}
    assert run_outcome(s) == {"solved": True, "val_solved": True, "admitted": 2}


def test_run_outcome_failed_run():
    s = {"stage_reached": "validated", "dbg_score": 0.0, "val_score": 0.0, "admitted": []}
    assert run_outcome(s) == {"solved": False, "val_solved": False, "admitted": 0}
