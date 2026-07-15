import json

import pytest

from aspire.actors import FakeActor
from aspire.config import RunConfig
from aspire.engines import FakeEngine
from aspire.evosearch import EvosearchError, evosearch, top3
from aspire.schemas import ExecuteResult, TraceRecord


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


def _fail_tr(msg, step=1, fn="navigate_to_pose"):
    return TraceRecord(step=step, function=fn, args={}, status="error",
                       result_summary=msg, duration_ms=1.0, media=[])


def test_history_note_collects_deduped_error_lines():
    from aspire.evosearch import failure_note
    from aspire.task_context import summarize_traces
    s1 = summarize_traces([_fail_tr("PLANNING_ERROR near table")])
    s2 = summarize_traces([_fail_tr("PLANNING_ERROR near table")])   # duplicate
    s3 = summarize_traces([_fail_tr("GRIPPER_SLIP on lid", fn="grasp_object")])
    note = failure_note([("a", 0.1, s1), ("b", 0.2, s2), ("c", 0.3, s3)])
    assert note.startswith("Known failure modes (newest first):")
    assert note.count("PLANNING_ERROR") == 1          # deduped
    assert note.index("GRIPPER_SLIP") < note.index("PLANNING_ERROR")  # newest first
    assert failure_note([("a", 1.0, "step 1: x [ok] fine\nFAILURES: 0")]) == ""


def test_failure_note_excludes_audit_lines():
    from aspire.evosearch import failure_note
    from aspire.task_context import summarize_traces
    # audit rejections live in the ledger; history_note is runtime failures only
    audit_only = summarize_traces([_fail_tr("forbidden qpos access", step=0, fn="audit")])
    assert failure_note([("a", 0.0, audit_only)]) == ""
    mixed = summarize_traces([_fail_tr("forbidden qpos access", step=0, fn="audit"),
                              _fail_tr("PLANNING_ERROR near table")])
    note = failure_note([("a", 0.0, mixed)])
    assert "PLANNING_ERROR" in note and "audit" not in note


def test_candidate_bundles_and_ledger_written(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([
        ExecuteResult(0.0, traces=[_fail_tr("BASE_FAIL")]),
        ExecuteResult(0.5, traces=[_fail_tr("CAND_A_FAIL")]),
        ExecuteResult(1.0)])
    actor = FakeActor(candidate_sources=[["a_src", "b_src"]])
    best = evosearch(task, engine, actor, _cfg())
    run = task / "run_001"
    # baseline bundle + summary in checkpoint
    assert "BASE_FAIL" in (run / "baseline_trace.json").read_text()
    assert "summary" in json.loads((run / "baseline_summary.json").read_text())
    # candidate bundle
    cand_a = run / "iter_00" / "candidate_A"
    assert "CAND_A_FAIL" in (cand_a / "trace.json").read_text()
    assert "FAILURES: 1" in (cand_a / "trace_summary.txt").read_text()
    # iter summary carries summaries
    entries = json.loads((run / "iter_00" / "iter_summary.json").read_text())
    assert "CAND_A_FAIL" in entries[0]["summary"]
    # ledger
    ledger = (run / "task_analysis.md").read_text()
    assert "## iter_00" in ledger and "CAND_A_FAIL" in ledger
    assert "candidate_B/code.py: 1.00 — no failures" in ledger
    # winner bundle at task level (candidate_B won)
    assert (task / "evosearch_best_trace.json").exists()
    assert "FAILURES: 0" in (task / "evosearch_best_summary.txt").read_text()
    assert best.score == 1.0


def test_history_note_reaches_proposer(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0, traces=[_fail_tr("UNIQUE_FAILURE_XYZ")]),
                         ExecuteResult(1.0)])
    actor = FakeActor(candidate_sources=[["src"]])
    evosearch(task, engine, actor, _cfg(k=1))
    assert any("UNIQUE_FAILURE_XYZ" in str(call) for call in actor.propose_calls)


def test_findings_written_after_search(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(0.5), ExecuteResult(1.0)])
    actor = FakeActor(candidate_sources=[["v1", "v2"]])
    evosearch(task, engine, actor, _cfg())
    text = (task / "findings.md").read_text()
    assert "best score: 1.00" in text
    assert "task_analysis.md" in text
    # Step-0 short-circuit must NOT rewrite findings:
    (task / "findings.md").write_text("SENTINEL")
    evosearch(task, FakeEngine([]), FakeActor(), _cfg())
    assert (task / "findings.md").read_text() == "SENTINEL"


def test_resume_tolerates_pre_g3_checkpoints(tmp_path):
    task = _task(tmp_path)
    run = task / "run_001"; it = run / "iter_00"; it.mkdir(parents=True)
    (run / "baseline_summary.json").write_text('{"score": 0.0}')     # pre-G3: no summary
    (it / "iter_summary.json").write_text(
        '[{"path": "%s", "score": 0.3}]' % str(it / "candidate_A" / "code.py").replace("\\", "/"))
    ca = it / "candidate_A"; ca.mkdir(); (ca / "code.py").write_text("old")
    engine = FakeEngine([ExecuteResult(0.9), ExecuteResult(0.2)])    # iter_01 only
    actor = FakeActor(candidate_sources=[["new1", "new2"]])
    best = evosearch(task, engine, actor, _cfg(t=2))
    assert best.score == 0.9
    assert len(engine.calls) == 2, "baseline + iter_00 replayed from disk"
