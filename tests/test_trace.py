"""TDD for the trace logger — ASPIRE's per-primitive trace record + trace.json."""
import json

from robot_engine.trace import TraceRecord, TraceLogger


def test_logger_assigns_sequential_steps():
    log = TraceLogger(trial_dir="/tmp/unused")
    assert log.next_step() == 1
    assert log.next_step() == 2
    assert log.next_step() == 3


def test_emit_collects_records():
    log = TraceLogger(trial_dir="/tmp/unused")
    log.emit(TraceRecord(step=1, function="move_to_joints", args={"n": 7},
                         duration_ms=12.3, result={"reached": True},
                         status="ok", keyframe_saved=False))
    assert len(log.records) == 1
    assert log.records[0].function == "move_to_joints"


def test_write_produces_valid_trace_json(tmp_path):
    log = TraceLogger(trial_dir=str(tmp_path))
    log.emit(TraceRecord(step=1, function="segment_text_prompt",
                         args={"rgb_shape": [512, 800, 3], "text_prompt": "bowl"},
                         duration_ms=1463.8,
                         result={"num_masks": 200, "mask_0_score": 0.917},
                         status="ok", keyframe_saved=True))
    log.write()

    data = json.loads((tmp_path / "trace.json").read_text())
    assert data[0]["step"] == 1
    assert data[0]["function"] == "segment_text_prompt"
    assert data[0]["args"]["text_prompt"] == "bowl"
    assert data[0]["status"] == "ok"
    assert data[0]["keyframe_saved"] is True
