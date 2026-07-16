import json
import sys

import pytest

from aspire.engines import CapxEngine, EngineError, FakeEngine
from aspire.schemas import ExecuteResult


def test_fake_engine_pops_scripted_results(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    eng = FakeEngine([ExecuteResult(0.2), ExecuteResult(1.0)])
    assert eng.execute(prog, [0, 1, 2]).score == 0.2
    assert eng.execute(prog, [0, 1, 2]).score == 1.0
    assert eng.calls == [(str(prog), (0, 1, 2)), (str(prog), (0, 1, 2))]


def test_fake_engine_exhausted_raises(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    with pytest.raises(EngineError, match="exhausted"):
        FakeEngine([]).execute(prog, [0])


def test_capx_engine_runs_command_and_reads_result(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    out = tmp_path / "out"
    # stub runner: writes a valid result.json into --out-dir
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json,sys,pathlib\n"
        "a=dict(zip(sys.argv[1::2],sys.argv[2::2]))\n"
        "d=pathlib.Path(a['--out-dir']); d.mkdir(parents=True,exist_ok=True)\n"
        "(d/'argv.txt').write_text(' '.join(sys.argv[1:]))\n"
        "(d/'result.json').write_text(json.dumps({'score':0.4,'raw_dir':str(d),'traces':[]}))\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=out)
    res = eng.execute(prog, [0, 1])
    assert res.score == 0.4
    argv = (out / "exec_0001" / "argv.txt").read_text()
    assert "--seeds 0,1" in argv
    flags = argv.split()
    opts = dict(zip(flags[0::2], flags[1::2]))
    assert opts["--out-dir"].endswith("exec_0001")


def test_capx_engine_timeout_raises(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    runner = tmp_path / "slow.py"
    runner.write_text("import time\ntime.sleep(5)\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)],
                     out_root=tmp_path / "o", timeout_s=1)
    with pytest.raises(EngineError, match="timed out"):
        eng.execute(prog, [0])


def test_capx_engine_missing_result_raises(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    runner = tmp_path / "noop.py"; runner.write_text("pass\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=tmp_path / "o")
    with pytest.raises(EngineError, match="result.json"):
        eng.execute(prog, [0])


def test_capx_engine_malformed_result_raises_engine_error(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    # stub runner: writes a truncated (torn) result.json into --out-dir
    runner = tmp_path / "torn.py"
    runner.write_text(
        "import sys,pathlib\n"
        "a=dict(zip(sys.argv[1::2],sys.argv[2::2]))\n"
        "d=pathlib.Path(a['--out-dir']); d.mkdir(parents=True,exist_ok=True)\n"
        "(d/'result.json').write_text('{\"trunca')\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=tmp_path / "o")
    with pytest.raises(EngineError, match="malformed"):
        eng.execute(prog, [0])


from aspire.engines import AuditedEngine
from aspire.schemas import ExecuteResult as ER


def test_audited_engine_passes_clean_program_through(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("navigate_to_pose([1, 2, 0.5])")
    inner = FakeEngine([ER(0.7)])
    res = AuditedEngine(inner).execute(prog, [0, 1])
    assert res.score == 0.7
    assert inner.calls == [(str(prog), (0, 1))]


def test_audited_engine_blocks_forbidden_program_without_executing(tmp_path):
    prog = tmp_path / "cheat.py"
    prog.write_text("q = env.handle.env.sim.data.qpos")
    inner = FakeEngine([])          # would raise if called
    res = AuditedEngine(inner).execute(prog, [0])
    assert res.score == 0.0
    assert res.traces[0].function == "audit" and res.traces[0].status == "error"
    assert "env.handle.env.sim" in res.traces[0].result_summary
    marker = prog.with_suffix(prog.suffix + ".AUDIT_REJECTED")
    assert marker.exists() and "env.handle.env.sim" in marker.read_text()


def test_audited_engine_blocks_seed_branch(tmp_path):
    prog = tmp_path / "seedy.py"; prog.write_text("if seed == 3:\n    z = 0.9")
    res = AuditedEngine(FakeEngine([])).execute(prog, [0])
    assert res.score == 0.0


def test_audited_engine_missing_program_raises(tmp_path):
    with pytest.raises(EngineError, match="cannot read"):
        AuditedEngine(FakeEngine([])).execute(tmp_path / "ghost.py", [0])


def test_audited_engine_clears_stale_marker_on_clean_rewrite(tmp_path):
    prog = tmp_path / "fix_code.py"
    prog.write_text("q = env.handle.env.sim.data.qpos")
    eng = AuditedEngine(FakeEngine([ER(0.8)]))
    eng.execute(prog, [0])                                    # rejected, marker written
    marker = prog.with_suffix(prog.suffix + ".AUDIT_REJECTED")
    assert marker.exists()
    prog.write_text("navigate_to_pose([1, 2, 0.5])")          # clean rewrite, same path
    res = eng.execute(prog, [0])
    assert res.score == 0.8
    assert not marker.exists(), "stale marker must be cleared on clean execution"


def test_engine_describe_recipes(tmp_path):
    fe = FakeEngine([ER(0.5), ER(1.0)])
    assert fe.describe() == {"type": "fake", "scores": [0.5, 1.0]}
    ce = CapxEngine(cmd_prefix=["python", "run.py"], out_root=tmp_path / "o", timeout_s=99)
    d = ce.describe()
    assert d["type"] == "capx" and d["cmd_prefix"] == ["python", "run.py"]
    assert d["out_root"].endswith("o") and d["timeout_s"] == 99
    ae = AuditedEngine(fe)
    assert ae.describe() == fe.describe()
