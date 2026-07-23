from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_accumulation_v2 import select_frontier


def test_keeps_exactly_one_of_two():
    probe = {"spatial_8": [True, False], "spatial_6": [False, True]}
    out = select_frontier(probe, n=2)
    assert out["selected"] == ["spatial_8", "spatial_6"]
    assert out["insufficient"] is False
    assert out["n_qualified"] == 2


def test_skips_zero_of_two_and_two_of_two():
    probe = {
        "spatial_0": [False, False],  # 0/2 -> too hard, skip
        "spatial_1": [True, True],    # 2/2 -> too easy, skip
        "spatial_2": [True, False],   # 1/2 -> frontier, keep
        "spatial_3": [False, True],   # 1/2 -> frontier, keep
    }
    out = select_frontier(probe, n=2)
    assert out["selected"] == ["spatial_2", "spatial_3"]
    assert out["insufficient"] is False


def test_returns_first_two_in_order():
    probe = {
        "a": [True, False],
        "b": [True, False],
        "c": [True, False],
    }
    out = select_frontier(probe, n=2)
    assert out["selected"] == ["a", "b"]  # first 2 qualifiers only


def test_insufficient_when_fewer_than_two_qualify():
    probe = {
        "spatial_0": [False, False],
        "spatial_1": [True, True],
        "spatial_2": [True, False],  # only one 1-of-2
    }
    out = select_frontier(probe, n=2)
    assert out["selected"] == ["spatial_2"]
    assert out["insufficient"] is True
    assert out["n_qualified"] == 1
