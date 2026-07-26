from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from val_confirmatory_select import select


def _c(task, dbg, val, suite="libero_10"):
    return {"task": task, "suite": suite, "cold_dbg_rate": dbg, "cold_val_rate": val}


def test_keeps_overfit_band_drops_floor_and_ceiling():
    cands = [_c("10_1", 0.8, 0.1),   # overfit band -> keep
             _c("10_2", 0.3, 0.0),   # floor (dbg<0.6) -> drop
             _c("10_4", 0.9, 0.6),   # ceiling (val>0.2) -> drop
             _c("10_5", 0.6, 0.2)]   # boundary inclusive -> keep
    out = select(cands)
    assert out["selected"] == ["10_1", "10_5"]
    assert out["sufficient"] is True
    reasons = {a["task"]: a["keep"] for a in out["audit"]}
    assert reasons == {"10_1": True, "10_2": False, "10_4": False, "10_5": True}


def test_insufficient_when_fewer_than_two():
    out = select([_c("10_1", 0.8, 0.1), _c("10_2", 0.2, 0.0)])
    assert out["selected"] == ["10_1"]
    assert out["sufficient"] is False
