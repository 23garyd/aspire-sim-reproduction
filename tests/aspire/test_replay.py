import json
import pytest
from pathlib import Path

from aspire import replay
from aspire.schemas import ExecuteResult, TraceRecord


def _setup(tmp_path, scores=(0.5,), s_dbg=(0, 1, 2), cap=3):
    (tmp_path / "replay.json").write_text(json.dumps(
        {"engine": {"type": "fake", "scores": list(scores)},
         "s_dbg": list(s_dbg), "max_attempts_per_seed": cap}))
    (tmp_path / "fix.py").write_text("navigate_to_pose([1,2,0])")
    return tmp_path


def test_replay_happy_path(tmp_path, monkeypatch, capsys):
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = replay.main(["fix.py", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "score: 0.5" in out
    assert (tmp_path / "replays" / "seed1_attempt1" / "trace.json").exists()
    assert json.loads((tmp_path / "replays" / "attempts.json").read_text()) == {"1": 1}


def test_replay_seed_guard(tmp_path, monkeypatch, capsys):
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert replay.main(["fix.py", "100"]) == 3
    assert "off-limits" in capsys.readouterr().err
    assert not (tmp_path / "replays").exists() or \
           not (tmp_path / "replays" / "attempts.json").exists()


def test_replay_attempt_cap(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, scores=(0.1, 0.2, 0.3), cap=3)
    monkeypatch.chdir(tmp_path)
    for i in range(3):
        assert replay.main(["fix.py", "0"]) == 0
    assert replay.main(["fix.py", "0"]) == 4
    assert "attempt cap reached for seed 0 (3/3)" in capsys.readouterr().err
    assert (tmp_path / "replays" / "seed0_attempt3").exists()
    assert not (tmp_path / "replays" / "seed0_attempt4").exists()


def test_replay_audits_cheating_program(tmp_path, monkeypatch, capsys):
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cheat.py").write_text("q = env.handle.env.sim.data.qpos")
    rc = replay.main(["cheat.py", "0"])
    assert rc == 0                              # audit-reject is DATA (score 0), not an error
    assert "score: 0.0" in capsys.readouterr().out
    # M1: executed as a COPY inside the attempt dir, so the marker lands there too,
    # not polluting the task-dir namespace the coordinator manages.
    assert (tmp_path / "replays" / "seed0_attempt1" / "cheat.py.AUDIT_REJECTED").exists()
    assert not (tmp_path / "cheat.py.AUDIT_REJECTED").exists()


def test_replay_executes_a_copy_not_the_original(tmp_path, monkeypatch):
    # M3: path-escape via ../ or absolute program args is harmless because the
    # executed artifact always lives inside the attempt dir.
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = replay.main(["fix.py", "1"])
    assert rc == 0
    exec_copy = tmp_path / "replays" / "seed1_attempt1" / "fix.py"
    assert exec_copy.exists()
    assert exec_copy.read_text() == (tmp_path / "fix.py").read_text()


def test_replay_missing_program_exits_2(tmp_path, monkeypatch, capsys):
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = replay.main(["ghost.py", "0"])
    assert rc == 2
    assert "ghost.py" in capsys.readouterr().err
    assert not (tmp_path / "replays" / "attempts.json").exists()


def test_replay_corrupt_replay_json_exits_2(tmp_path, monkeypatch, capsys):
    (tmp_path / "replay.json").write_text("{not valid json")
    (tmp_path / "fix.py").write_text("navigate_to_pose([1,2,0])")
    monkeypatch.chdir(tmp_path)
    rc = replay.main(["fix.py", "0"])
    assert rc == 2
    assert "replay.json" in capsys.readouterr().err


def test_replay_corrupt_attempts_json_exits_2(tmp_path, monkeypatch, capsys):
    _setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "replays").mkdir()
    (tmp_path / "replays" / "attempts.json").write_text("{not valid json")
    rc = replay.main(["fix.py", "0"])
    assert rc == 2
    assert "attempts.json" in capsys.readouterr().err


def test_replay_usage_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert replay.main(["fix.py", "0"]) == 2          # no replay.json
    _setup(tmp_path)
    assert replay.main(["fix.py", "notanint"]) == 2
    assert replay.main(["fix.py"]) == 2


def test_replay_crash_consumed_attempt(tmp_path, monkeypatch):
    # attempt is recorded BEFORE execution: an engine failure still burns one
    (tmp_path / "replay.json").write_text(json.dumps(
        {"engine": {"type": "fake", "scores": []},     # exhausted -> EngineError
         "s_dbg": [0], "max_attempts_per_seed": 3}))
    (tmp_path / "fix.py").write_text("x()")
    monkeypatch.chdir(tmp_path)
    assert replay.main(["fix.py", "0"]) == 5
    assert json.loads((tmp_path / "replays" / "attempts.json").read_text()) == {"0": 1}
