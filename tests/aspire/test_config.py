from aspire.config import RunConfig


def test_defaults_match_spec_reconstructed_values():
    cfg = RunConfig()
    assert cfg.k == 3 and cfg.t == 5 and cfg.theta == 1.0
    assert cfg.debug_rounds == 2
    assert cfg.s_dbg and cfg.s_val
    assert not (set(cfg.s_dbg) & set(cfg.s_val)), "debug and validation seeds must not overlap"
    assert cfg.model_repair == "opus"
    assert cfg.model_propose == "sonnet"


def test_to_dict_round_trip():
    cfg = RunConfig(k=5, s_dbg=[1, 2], s_val=[9])
    assert RunConfig(**cfg.to_dict()) == cfg
