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
        "(d/'result.json').write_text(json.dumps({'score':0.4,'raw_dir':str(d),'traces':[]}))\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=out)
    res = eng.execute(prog, [0, 1])
    assert res.score == 0.4


def test_capx_engine_missing_result_raises(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    runner = tmp_path / "noop.py"; runner.write_text("pass\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=tmp_path / "o")
    with pytest.raises(EngineError, match="result.json"):
        eng.execute(prog, [0])
