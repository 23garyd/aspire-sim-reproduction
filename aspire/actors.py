"""Actor = one headless Claude Code run in a task dir. The actor's ONLY output contract
is report.json (ActorReport) plus code files it writes; the orchestrator never parses
free text. Judge = one-shot admission decision (paper's coordinator-guided admission)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aspire.schemas import ActorReport, ProposedSkill, ReportError
from aspire.skill_library import Skill, render_skill

_CAND_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Narrowly-scoped permission for the replay affordance (R2): run_debug ONLY grants
# Bash execution of the coordinator-materialized ./replay shim (App E inner loop);
# propose/extract do not get it. acceptEdits alone does not grant Bash execution.
REPLAY_ALLOWED_TOOLS = "Bash(./replay:*)"


class ActorError(RuntimeError):
    pass


@dataclass
class ProposeContext:
    task_dir: Path
    iter_dir: Path
    top3: list                 # list[tuple[program_path, score, trace_summary]] best-first
    skills: list               # list[Skill] injected by coordinator
    k: int = 3
    history_note: str = ""     # short summary of eliminated/blocked branches


class Actor(Protocol):
    def run_debug(self, task_dir: Path, model: str) -> ActorReport: ...
    def propose(self, ctx: ProposeContext, model: str) -> list: ...
    def extract(self, task_dir: Path, model: str) -> ActorReport: ...


class Judge(Protocol):
    def admit(self, skill: ProposedSkill, existing=()) -> bool: ...


class FakeActor:
    def __init__(self, reports=(), candidate_sources=(), extraction_reports=()):
        self._reports = list(reports)
        self._sources = list(candidate_sources)
        self._extraction_reports = list(extraction_reports)
        self.debug_calls, self.propose_calls, self.extract_calls = [], [], []

    def run_debug(self, task_dir: Path, model: str) -> ActorReport:
        self.debug_calls.append((str(task_dir), model))
        if not self._reports:
            raise ActorError("FakeActor: no scripted reports left")
        return self._reports.pop(0)

    def extract(self, task_dir: Path, model: str) -> ActorReport:
        self.extract_calls.append((str(task_dir), model))
        if not self._extraction_reports:
            raise ActorError("FakeActor: no scripted extraction reports left")
        return self._extraction_reports.pop(0)

    def propose(self, ctx: ProposeContext, model: str) -> list:
        self.propose_calls.append((str(ctx.iter_dir), model, ctx.k, ctx.history_note))
        if not self._sources:
            raise ActorError("FakeActor: no scripted candidate sources left")
        sources = self._sources.pop(0)
        paths = []
        for i, src in enumerate(sources[:ctx.k]):
            d = ctx.iter_dir / f"candidate_{_CAND_LETTERS[i]}"
            d.mkdir(parents=True, exist_ok=True)
            p = d / "code.py"
            p.write_text(src)
            paths.append(p)
        return paths


class FakeJudge:
    def __init__(self, decisions):
        self._d = list(decisions)
        self.admit_calls = []

    def admit(self, skill: ProposedSkill, existing=()) -> bool:
        self.admit_calls.append((skill.name, tuple(s.name for s in existing)))
        if not self._d:
            raise ActorError("FakeJudge: no scripted decisions left")
        return self._d.pop(0)


def _run_claude(prompt: str, cwd: Path, model: str, timeout_s: int,
                extra_args=()) -> str:
    try:
        # acceptEdits: headless actors must write report.json / fix_code.py in cwd
        # without interactive permission prompts (they run unattended on the GPU box).
        proc = subprocess.run(["claude", "-p", prompt, "--model", model,
                               "--permission-mode", "acceptEdits", *extra_args],
                              cwd=cwd, capture_output=True, text=True,
                              errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise ActorError(f"claude timed out after {timeout_s}s") from e
    if proc.returncode != 0:
        raise ActorError(f"claude exited {proc.returncode}: {proc.stderr[-800:]}")
    return proc.stdout


class ClaudeCodeActor:
    def __init__(self, prompt_file: str, propose_prompt_file: str = None,
                 extract_prompt_file: str = None, timeout_s: int = 7200):
        self._prompt_file = prompt_file
        self._propose_prompt_file = propose_prompt_file
        self._extract_prompt_file = extract_prompt_file
        self._timeout = timeout_s

    def _prompt(self) -> str:
        return Path(self._prompt_file).read_text()

    def _propose_prompt(self) -> str:
        return Path(self._propose_prompt_file or self._prompt_file).read_text()

    def _extract_prompt(self) -> str:
        # No fallback to the debug prompt: it demands report.json, which would
        # clobber Stage-1's artifact and never produce extraction_report.json.
        if self._extract_prompt_file is None:
            raise ActorError("extract_prompt_file not configured")
        return Path(self._extract_prompt_file).read_text()

    def run_debug(self, task_dir: Path, model: str) -> ActorReport:
        _run_claude(self._prompt(), task_dir, model, self._timeout,
                   extra_args=["--allowedTools", REPLAY_ALLOWED_TOOLS])
        report = task_dir / "report.json"
        if not report.exists():
            raise ActorError("actor finished without writing report.json")
        try:
            return ActorReport.load(report)
        except ReportError as e:
            raise ActorError(str(e)) from e

    def extract(self, task_dir: Path, model: str) -> ActorReport:
        _run_claude(self._extract_prompt(), task_dir, model, self._timeout)
        report = task_dir / "extraction_report.json"
        if not report.exists():
            raise ActorError("actor finished without writing extraction_report.json")
        try:
            return ActorReport.load(report)
        except ReportError as e:
            raise ActorError(str(e)) from e

    def propose(self, ctx: ProposeContext, model: str) -> list:
        ctx.iter_dir.mkdir(parents=True, exist_ok=True)
        extra = (f"\n\n## This round\nWrite exactly {ctx.k} candidates to "
                 f"{ctx.iter_dir}/candidate_<LETTER>/code.py (A..). "
                 f"Top programs so far: {[(str(p), s) for p, s, *_ in ctx.top3]}. "
                 f"{ctx.history_note}\n"
                 f"Read the task analysis ledger first: "
                 f"{ctx.iter_dir.parent / 'task_analysis.md'}")
        if ctx.skills:
            extra += "\nRelevant skills:\n" + "\n".join(
                f"- {s.name}: {' '.join(s.when_to_apply.split())}" for s in ctx.skills)
        _run_claude(self._propose_prompt() + extra, ctx.task_dir, model, self._timeout)
        paths = sorted(ctx.iter_dir.glob("candidate_*/code.py"),
                       key=lambda p: p.parent.name.casefold())
        if not paths:
            raise ActorError("proposer wrote no candidate_*/code.py files")
        return paths[:ctx.k]


class ClaudeJudge:
    """One-shot admission: reply must contain a line starting 'ADMIT: yes' or 'ADMIT: no'."""

    def __init__(self, prompt_file: str, workdir: Path, model: str = "opus",
                 timeout_s: int = 600):
        self._prompt_file, self._workdir = prompt_file, Path(workdir)
        self._model, self._timeout = model, timeout_s

    def admit(self, skill: ProposedSkill, existing=()) -> bool:
        # render the candidate like-for-like with existing entries (markdown)
        candidate_md = render_skill(
            Skill.from_proposed(skill, provenance="(candidate, not yet admitted)"))
        prompt = (Path(self._prompt_file).read_text()
                  + "\n\n## Candidate skill\n" + candidate_md)
        if existing:
            prompt += ("\n\n## Existing library entries (reject near-duplicates)\n"
                      + "\n---\n".join(render_skill(s) for s in existing))
        out = _run_claude(prompt, self._workdir, self._model, self._timeout)
        for line in out.splitlines():
            low = line.strip().lower()
            if low.startswith("admit:"):
                verdict = low.split("admit:", 1)[1].strip()
                parts = verdict.split()
                tok = parts[0].strip(".,;:!—-") if parts else ""
                if tok == "yes":
                    return True
                if tok == "no":
                    return False
                # unrecognized verdict token: keep scanning remaining lines
        raise ActorError(f"judge reply had no ADMIT line: {out[-400:]}")
