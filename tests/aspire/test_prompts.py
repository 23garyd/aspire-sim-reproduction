from pathlib import Path

PROMPTS = Path("prompts")


def test_prompt_files_exist():
    for f in ("actor_debug.md", "actor_evosearch.md", "coordinator_admission.md"):
        assert (PROMPTS / f).exists(), f


def test_actor_prompts_state_report_contract():
    for f in ("actor_debug.md", "actor_evosearch.md"):
        text = (PROMPTS / f).read_text()
        assert "report.json" in text
        assert "fix_code.py" in text or "candidate_" in text
        assert "seed-specific" in text.lower()


def test_debug_prompt_carries_forbidden_wall():
    text = (PROMPTS / "actor_debug.md").read_text()
    for token in ("env.handle.env.sim", ".bddl", ".urdf"):
        assert token in text


def test_debug_prompt_states_replay_affordance():
    text = (PROMPTS / "actor_debug.md").read_text()
    assert "./replay" in text
    assert "3 attempts" in text


def test_debug_prompt_pins_seed_attempts_shape():
    # R3 live crash: an actor wrote a rich dict shape for seed_attempts instead of
    # the spec's [[seed, attempts], ...] pairs, which crashed the coordinator's
    # discipline check. Pin a concrete example so actors match the accepted shape.
    text = (PROMPTS / "actor_debug.md").read_text()
    assert "[[0, 1], [1, 2]]" in text


def test_evosearch_prompt_requires_reading_top_programs():
    text = (PROMPTS / "actor_evosearch.md").read_text().lower()
    assert "read" in text and "top" in text  # actors get PATHS; must be told to read them


def test_admission_prompt_demands_admit_line():
    text = (PROMPTS / "coordinator_admission.md").read_text()
    assert "ADMIT:" in text


def test_extract_prompt_exists_with_contract():
    text = (PROMPTS / "extract_patterns.md").read_text()
    assert "extraction_report.json" in text
    assert "winner/trace.json" in text or "winner/" in text
    assert ">=2 task types" in text
    assert "env.handle.env.sim" in text
