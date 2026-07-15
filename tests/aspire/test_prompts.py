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


def test_evosearch_prompt_requires_reading_top_programs():
    text = (PROMPTS / "actor_evosearch.md").read_text().lower()
    assert "read" in text and "top" in text  # actors get PATHS; must be told to read them


def test_admission_prompt_demands_admit_line():
    text = (PROMPTS / "coordinator_admission.md").read_text()
    assert "ADMIT:" in text
