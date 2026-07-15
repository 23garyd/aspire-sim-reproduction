import json

import pytest

from aspire.schemas import ActorReport, ExecuteResult, ProposedSkill, ReportError, TraceRecord


def make_trace(**kw):
    d = dict(step=1, function="grasp_object", args={"arm": 0}, status="ok",
             result_summary="in_hand=True", duration_ms=812.5, media=["kf_001.png"])
    d.update(kw)
    return TraceRecord(**d)


def test_trace_round_trip():
    tr = make_trace()
    assert TraceRecord.from_dict(tr.to_dict()) == tr


def test_execute_result_json_round_trip(tmp_path):
    res = ExecuteResult(score=0.6, traces=[make_trace(), make_trace(step=2, status="error")],
                        raw_dir="runs/x")
    p = tmp_path / "result.json"
    p.write_text(res.to_json())
    loaded = ExecuteResult.from_json(p.read_text())
    assert loaded == res
    assert json.loads(res.to_json())["score"] == 0.6  # plain-JSON contract for capx_execute.py


def test_actor_report_load(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({
        "outcome": "success", "diagnosis": "goal pose inside collision buffer",
        "code_path": "fix_code.py",
        "proposed_skills": [{
            "name": "multi-angle-approach", "category": "navigation",
            "failure_signature": "repeated PLANNING_ERROR near obstacle",
            "when_to_apply": "nav goals fall inside collision-avoidance buffer",
            "strategy": "rotate approach vector by 45/90/180 deg", "code_sketch": "for a in ..."}],
    }))
    r = ActorReport.load(p)
    assert r.outcome == "success"
    assert r.proposed_skills[0].category == "navigation"


def test_actor_report_missing_field_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail"}))
    with pytest.raises(ReportError, match="missing"):
        ActorReport.load(p)


def test_actor_report_bad_outcome_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "maybe", "diagnosis": "x", "code_path": "c.py"}))
    with pytest.raises(ReportError, match="outcome"):
        ActorReport.load(p)


def test_actor_report_bad_skill_entry_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "x", "code_path": "c.py",
                             "proposed_skills": [{"name": "n"}]}))
    with pytest.raises(ReportError, match="proposed_skill"):
        ActorReport.load(p)


def test_actor_report_unknown_skill_key_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "x", "code_path": "c.py",
                             "proposed_skills": [{"name": "n", "category": "c",
                                                  "failure_signature": "f", "when_to_apply": "w",
                                                  "strategy": "s", "bogus": 1}]}))
    with pytest.raises(ReportError, match="proposed_skill"):
        ActorReport.load(p)


def test_actor_report_optional_appendix_fields(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "success", "diagnosis": "d",
                             "code_path": "fix_code.py",
                             "debug_validation_rate": 0.67,
                             "seed_attempts": [[0, 1], [1, 3]]}))
    r = ActorReport.load(p)
    assert r.debug_validation_rate == 0.67
    assert r.seed_attempts == ((0, 1), (1, 3))


def test_actor_report_fields_default_when_absent(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "d", "code_path": "c.py"}))
    r = ActorReport.load(p)
    assert r.debug_validation_rate == -1.0 and r.seed_attempts == ()


def test_actor_report_malformed_rate_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "d", "code_path": "c.py",
                             "debug_validation_rate": "high"}))
    with pytest.raises(ReportError, match="debug_validation_rate"):
        ActorReport.load(p)
