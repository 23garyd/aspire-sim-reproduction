import json

from aspire.schemas import ExecuteResult, TraceRecord


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
