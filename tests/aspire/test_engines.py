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
