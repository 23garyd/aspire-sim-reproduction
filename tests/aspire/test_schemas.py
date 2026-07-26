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


def test_actor_report_unknown_skill_key_is_ignored(tmp_path):
    # The repair actor sometimes emits extra keys on a proposed skill (e.g.
    # "provenance"). These MUST be filtered, not crash the whole run — an
    # unknown-key TypeError here previously failed entire runs and, because the
    # warm (library) arms emit skills more often, selectively biased them.
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "x", "code_path": "c.py",
                             "proposed_skills": [{"name": "n", "category": "c",
                                                  "failure_signature": "f", "when_to_apply": "w",
                                                  "strategy": "s", "bogus": 1}]}))
    r = ActorReport.load(p)
    assert r.proposed_skills[0].name == "n"
    assert r.proposed_skills[0].category == "c"
    assert not hasattr(r.proposed_skills[0], "bogus")  # unknown key dropped, not leaked


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


def test_actor_report_errors_name_the_actual_file(tmp_path):
    p = tmp_path / "extraction_report.json"
    p.write_text(json.dumps({"outcome": "fail"}))         # missing required fields
    with pytest.raises(ReportError, match="extraction_report.json"):
        ActorReport.load(p)
    q = tmp_path / "other_report.json"
    q.write_text("{not json")
    with pytest.raises(ReportError, match="other_report.json"):
        ActorReport.load(q)


def test_actor_report_malformed_rate_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "d", "code_path": "c.py",
                             "debug_validation_rate": "high"}))
    with pytest.raises(ReportError, match="debug_validation_rate"):
        ActorReport.load(p)


def _report_with(seed_attempts, tmp_path, name="report.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"outcome": "fail", "diagnosis": "d", "code_path": "c.py",
                             "seed_attempts": seed_attempts}))
    return p


def test_seed_attempts_normalizes_live_actor_dict_payload(tmp_path):
    # R3 live crash: the actor wrote this rich dict shape; old code iterated the
    # DICT KEYS into 1-tuples (("0",),), so coordinator.py's sa[1] IndexError'd.
    live_payload = {"0": [{"attempt": 1, "code": "fix.py", "score": 1.0,
                           "result": "pass"}]}
    r = ActorReport.load(_report_with(live_payload, tmp_path))
    assert r.seed_attempts == ((0, 1),)


def test_seed_attempts_normalizes_dict_of_counts(tmp_path):
    r = ActorReport.load(_report_with({"0": 2, "1": 1}, tmp_path))
    assert r.seed_attempts == ((0, 2), (1, 1))


def test_seed_attempts_accepts_spec_list_form(tmp_path):
    r = ActorReport.load(_report_with([[0, 5], [1, 1]], tmp_path))
    assert r.seed_attempts == ((0, 5), (1, 1))


def test_seed_attempts_wrong_arity_raises(tmp_path):
    with pytest.raises(ReportError, match="seed_attempts"):
        ActorReport.load(_report_with([[0]], tmp_path))


def test_seed_attempts_non_numeric_raises(tmp_path):
    with pytest.raises(ReportError, match="seed_attempts"):
        ActorReport.load(_report_with([["x", "y"]], tmp_path))
