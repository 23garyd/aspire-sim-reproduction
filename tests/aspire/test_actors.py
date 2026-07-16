import json
import os
import stat

import pytest

from aspire.actors import (ActorError, ClaudeCodeActor, ClaudeJudge, FakeActor,
                           FakeJudge, ProposeContext)
from aspire.schemas import ActorReport, ProposedSkill


def _report_dict(outcome="success"):
    return {"outcome": outcome, "diagnosis": "d", "code_path": "fix_code.py",
            "proposed_skills": []}


def test_fake_actor_writes_report_and_candidates(tmp_path):
    rep = ActorReport(outcome="fail", diagnosis="d", code_path="code.py")
    actor = FakeActor(reports=[rep], candidate_sources=[["print(1)", "print(2)"]])
    assert actor.run_debug(tmp_path, model="opus") == rep
    ctx = ProposeContext(task_dir=tmp_path, iter_dir=tmp_path / "iter_00",
                         top3=[], skills=[], k=2)
    paths = actor.propose(ctx, model="sonnet")
    assert [p.read_text() for p in paths] == ["print(1)", "print(2)"]
    assert paths[0].parent.name == "candidate_A" and paths[1].parent.name == "candidate_B"


def _make_shim(tmp_path, body):
    shim = tmp_path / "bin" / "claude"
    shim.parent.mkdir(exist_ok=True)
    shim.write_text("#!/bin/bash\n" + body)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return shim.parent


def test_claude_actor_invokes_cli_and_loads_report(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"
    prompt.write_text("do the thing PROMPT_SENTINEL_XYZ")
    bin_dir = _make_shim(
        tmp_path,
        'echo "$@" > cli_args.txt\n'
        f"echo '{json.dumps(_report_dict())}' > report.json\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=30)
    rep = actor.run_debug(task, model="opus")
    assert rep.outcome == "success"
    args = (task / "cli_args.txt").read_text()
    assert "--model opus" in args and "-p" in args
    assert "--permission-mode acceptEdits" in args
    assert "PROMPT_SENTINEL_XYZ" in args


def test_claude_actor_no_report_raises(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(tmp_path, "true\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=30)
    with pytest.raises(ActorError, match="report.json"):
        actor.run_debug(task, model="opus")


def test_fake_judge_and_claude_judge_parse(tmp_path, monkeypatch):
    skill = ProposedSkill(name="n", category="c", failure_signature="f",
                          when_to_apply="w", strategy="s")
    assert FakeJudge([True]).admit(skill) is True
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(tmp_path, "echo 'ADMIT: yes — reusable navigation pattern'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    assert ClaudeJudge(prompt_file=str(prompt),
                       workdir=tmp_path).admit(skill) is True


def _skill():
    return ProposedSkill(name="n", category="c", failure_signature="f",
                         when_to_apply="w", strategy="s")


def test_claude_judge_no_with_yes_in_justification(tmp_path, monkeypatch):
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(
        tmp_path, "echo 'ADMIT: no — reusable? yes, but duplicated'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    judge = ClaudeJudge(prompt_file=str(prompt), workdir=tmp_path)
    assert judge.admit(_skill()) is False


def test_claude_judge_plain_no(tmp_path, monkeypatch):
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(tmp_path, "echo 'ADMIT: no'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    judge = ClaudeJudge(prompt_file=str(prompt), workdir=tmp_path)
    assert judge.admit(_skill()) is False


def test_claude_judge_yes_prefixed_word_is_not_yes(tmp_path, monkeypatch):
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(
        tmp_path, "echo 'ADMIT: yesterday I would have said no'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    judge = ClaudeJudge(prompt_file=str(prompt), workdir=tmp_path)
    with pytest.raises(ActorError, match="no ADMIT line"):
        judge.admit(_skill())


def test_claude_judge_unrecognized_verdict_raises(tmp_path, monkeypatch):
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(tmp_path, "echo 'ADMIT: absolutely'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    judge = ClaudeJudge(prompt_file=str(prompt), workdir=tmp_path)
    with pytest.raises(ActorError, match="no ADMIT line"):
        judge.admit(_skill())


def test_claude_actor_timeout_raises(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(tmp_path, "sleep 5\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=1)
    with pytest.raises(ActorError, match="timed out"):
        actor.run_debug(task, model="opus")


def test_claude_actor_nonzero_exit_raises(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    bin_dir = _make_shim(tmp_path, "exit 3\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=30)
    with pytest.raises(ActorError, match="exited 3"):
        actor.run_debug(task, model="opus")


def test_claude_propose_truncates_to_k_and_casefold_sorts(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    iter_dir = tmp_path / "iter_00"
    body = "".join(
        f"mkdir -p '{iter_dir}/candidate_{n}'\n"
        f"echo 'print({i})' > '{iter_dir}/candidate_{n}/code.py'\n"
        for i, n in enumerate(["A", "b", "C"]))
    bin_dir = _make_shim(tmp_path, body)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=30)
    ctx = ProposeContext(task_dir=task, iter_dir=iter_dir,
                         top3=[], skills=[], k=2)
    paths = actor.propose(ctx, model="sonnet")
    assert [p.parent.name for p in paths] == ["candidate_A", "candidate_b"]


def test_claude_propose_happy_path(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    iter_dir = tmp_path / "iter_00"
    body = "".join(
        f"mkdir -p '{iter_dir}/candidate_{n}'\n"
        f"echo 'print({i})' > '{iter_dir}/candidate_{n}/code.py'\n"
        for i, n in enumerate(["A", "B"]))
    bin_dir = _make_shim(tmp_path, body)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=30)
    ctx = ProposeContext(task_dir=task, iter_dir=iter_dir,
                         top3=[], skills=[], k=2)
    paths = actor.propose(ctx, model="sonnet")
    assert [p.parent.name for p in paths] == ["candidate_A", "candidate_B"]
    assert [p.read_text().strip() for p in paths] == ["print(0)", "print(1)"]


def test_claude_propose_uses_propose_prompt_file_not_debug_prompt(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    debug_prompt = tmp_path / "debug.md"
    debug_prompt.write_text("DEBUG_PROMPT_MARK")
    evo_prompt = tmp_path / "evo.md"
    evo_prompt.write_text("EVOSEARCH_PROMPT_MARK")
    iter_dir = tmp_path / "iter_00"
    body = (
        'echo "$@" > cli_args.txt\n'
        f"mkdir -p '{iter_dir}/candidate_A'\n"
        f"echo 'print(0)' > '{iter_dir}/candidate_A/code.py'\n")
    bin_dir = _make_shim(tmp_path, body)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(debug_prompt),
                            propose_prompt_file=str(evo_prompt), timeout_s=30)
    ctx = ProposeContext(task_dir=task, iter_dir=iter_dir,
                         top3=[], skills=[], k=1)
    actor.propose(ctx, model="sonnet")
    args = (task / "cli_args.txt").read_text()
    assert "EVOSEARCH_PROMPT_MARK" in args
    assert "DEBUG_PROMPT_MARK" not in args


def test_claude_propose_falls_back_to_debug_prompt_when_no_propose_prompt(
        tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    debug_prompt = tmp_path / "debug.md"
    debug_prompt.write_text("DEBUG_PROMPT_MARK")
    iter_dir = tmp_path / "iter_00"
    body = (
        'echo "$@" > cli_args.txt\n'
        f"mkdir -p '{iter_dir}/candidate_A'\n"
        f"echo 'print(0)' > '{iter_dir}/candidate_A/code.py'\n")
    bin_dir = _make_shim(tmp_path, body)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(debug_prompt), timeout_s=30)
    ctx = ProposeContext(task_dir=task, iter_dir=iter_dir,
                         top3=[], skills=[], k=1)
    actor.propose(ctx, model="sonnet")
    args = (task / "cli_args.txt").read_text()
    assert "DEBUG_PROMPT_MARK" in args


def test_claude_judge_receives_existing_entries(tmp_path, monkeypatch):
    from aspire.skill_library import Skill
    skill = ProposedSkill(name="new-nav", category="navigation", failure_signature="f",
                          when_to_apply="w", strategy="s")
    existing = [Skill(name="multi-angle-approach", category="navigation",
                      failure_signature="PLANNING_ERROR", when_to_apply="near obstacle",
                      strategy="rotate approach")]
    prompt = tmp_path / "p.md"; prompt.write_text("judge prompt")
    bin_dir = _make_shim(tmp_path,
                         'echo "$@" > judge_args.txt\n'
                         "echo 'ADMIT: no — duplicate'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    judge = ClaudeJudge(prompt_file=str(prompt), workdir=tmp_path)
    assert judge.admit(skill, existing=existing) is False
    args = (tmp_path / "judge_args.txt").read_text()
    assert "multi-angle-approach" in args and "Existing library entries" in args


def test_fake_actor_extract_records_and_pops(tmp_path):
    rep = ActorReport(outcome="success", diagnosis="d", code_path="code.py")
    actor = FakeActor(extraction_reports=[rep])
    assert actor.extract(tmp_path, model="opus") == rep
    assert actor.extract_calls == [(str(tmp_path), "opus")]
    with pytest.raises(ActorError, match="extraction"):
        actor.extract(tmp_path, model="opus")


def test_claude_actor_extract_uses_extract_prompt_and_distinct_report(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    dbg = tmp_path / "d.md"; dbg.write_text("DEBUG_MARK")
    ext = tmp_path / "e.md"; ext.write_text("EXTRACT_MARK")
    bin_dir = _make_shim(
        tmp_path,
        'echo "$@" > cli_args.txt\n'
        "echo '" + json.dumps({"outcome": "success", "diagnosis": "d",
                               "code_path": "w.py", "proposed_skills": []})
        + "' > extraction_report.json\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(dbg), extract_prompt_file=str(ext),
                            timeout_s=30)
    rep = actor.extract(task, model="opus")
    assert rep.outcome == "success"
    args = (task / "cli_args.txt").read_text()
    assert "EXTRACT_MARK" in args and "DEBUG_MARK" not in args


def test_claude_actor_extract_without_prompt_file_raises(tmp_path):
    p = tmp_path / "p.md"; p.write_text("x")
    actor = ClaudeCodeActor(prompt_file=str(p), timeout_s=30)
    with pytest.raises(ActorError, match="extract_prompt_file not configured"):
        actor.extract(tmp_path, model="opus")


def test_claude_actor_extract_missing_report_raises(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    p = tmp_path / "p.md"; p.write_text("x")
    bin_dir = _make_shim(tmp_path, "true\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(p), extract_prompt_file=str(p), timeout_s=30)
    with pytest.raises(ActorError, match="extraction_report.json"):
        actor.extract(task, model="opus")


def test_claude_propose_injects_coordinator_skills_into_prompt(tmp_path, monkeypatch):
    from aspire.skill_library import Skill
    task = tmp_path / "task"; task.mkdir()
    prompt = tmp_path / "p.md"; prompt.write_text("do the thing")
    iter_dir = tmp_path / "iter_00"
    body = (
        'echo "$@" > cli_args.txt\n'
        f"mkdir -p '{iter_dir}/candidate_A'\n"
        f"echo 'print(0)' > '{iter_dir}/candidate_A/code.py'\n")
    bin_dir = _make_shim(tmp_path, body)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file=str(prompt), timeout_s=30)
    skill = Skill(name="multi-angle-approach", category="navigation",
                  failure_signature="PLANNING_ERROR",
                  when_to_apply="near\nobstacle\tboundary",
                  strategy="rotate approach")
    ctx = ProposeContext(task_dir=task, iter_dir=iter_dir,
                         top3=[], skills=[skill], k=1)
    actor.propose(ctx, model="sonnet")
    args = (task / "cli_args.txt").read_text()
    assert "multi-angle-approach" in args
    # multiline/tabbed skill text is collapsed onto one bullet with single spaces
    assert "near obstacle boundary" in args
