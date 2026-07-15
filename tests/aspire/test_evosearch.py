import json

import pytest

from aspire.actors import FakeActor
from aspire.config import RunConfig
from aspire.engines import FakeEngine
from aspire.evosearch import EvosearchError, evosearch, top3
from aspire.schemas import ExecuteResult


def _cfg(**kw):
    return RunConfig(**{**dict(k=2, t=3, theta=1.0, s_dbg=[0, 1]), **kw})


def _task(tmp_path):
    task = tmp_path / "suite" / "task"
    task.mkdir(parents=True)
    (task / "code.py").write_text("baseline")
    return task


def test_top3_orders_by_score():
    h = [("a", 0.1), ("b", 0.9), ("c", 0.5), ("d", 0.8)]
    assert [p for p, _ in top3(h)] == ["b", "d", "c"]


def test_early_stop_at_theta(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),                    # baseline on S_dbg
                         ExecuteResult(0.5), ExecuteResult(1.0)])  # iter_00 candidates
    actor = FakeActor(candidate_sources=[["v1", "v2"], ["never", "never"]])
    best = evosearch(task, engine, actor, _cfg())
    assert best.score == 1.0
    assert len(actor.propose_calls) == 1, "must stop after hitting theta"
    assert (task / "evosearch_best_code.py").read_text() == "v2"


def test_budget_exhaustion_keeps_best(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0)] +
                        [ExecuteResult(s) for s in (0.2, 0.4, 0.4, 0.6, 0.1, 0.3)])
    actor = FakeActor(candidate_sources=[["a", "b"], ["c", "d"], ["e", "f"]])
    best = evosearch(task, engine, actor, _cfg())
    assert best.score == 0.6
    assert len(actor.propose_calls) == 3  # T rounds, never reached theta


def test_existing_best_short_circuits(tmp_path):
    task = _task(tmp_path)
    (task / "evosearch_best_code.py").write_text("done")
    (task / "evosearch_best_score.json").write_text(json.dumps({"score": 0.9}))
    engine = FakeEngine([])   # any execute() would raise
    best = evosearch(task, engine, FakeActor(), _cfg())
    assert best.score == 0.9 and best.path.name == "evosearch_best_code.py"


def test_resume_skips_completed_iters(tmp_path):
    task = _task(tmp_path)
    engine1 = FakeEngine([ExecuteResult(0.0), ExecuteResult(0.3), ExecuteResult(0.2)])
    actor1 = FakeActor(candidate_sources=[["a", "b"]])
    try:
        evosearch(task, engine1, actor1, _cfg(t=2))   # iter_00 done, then actor exhausts
    except Exception:
        pass
    run_dirs = list(task.glob("run_*"))
    assert run_dirs and (run_dirs[0] / "iter_00" / "iter_summary.json").exists()
    # resume: baseline + iter_00 come from disk; only iter_01 executes
    engine2 = FakeEngine([ExecuteResult(0.7), ExecuteResult(0.5)])
    actor2 = FakeActor(candidate_sources=[["c", "d"]])
    best = evosearch(task, engine2, actor2, _cfg(t=2))
    assert best.score == 0.7
    assert len(engine2.calls) == 2, "resume must not re-execute finished iterations"


def test_orphan_best_code_without_meta_recovers(tmp_path):
    task = _task(tmp_path)
    (task / "evosearch_best_code.py").write_text("orphan")   # crash-window artifact
    engine = FakeEngine([ExecuteResult(1.0)])                 # baseline passes
    best = evosearch(task, engine, FakeActor(), _cfg())
    assert best.score == 1.0                                  # searched, not crashed
    assert (task / "evosearch_best_score.json").exists()


def test_corrupt_iter_summary_raises_clear_error(tmp_path):
    task = _task(tmp_path)
    run = task / "run_001"; it = run / "iter_00"; it.mkdir(parents=True)
    (run / "baseline_summary.json").write_text('{"score": 0.0}')
    (it / "iter_summary.json").write_text('{"trunca')          # simulated torn write
    with pytest.raises(EvosearchError, match="iter_summary"):
        evosearch(task, FakeEngine([]), FakeActor(), _cfg())
