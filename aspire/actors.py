"""Actor = one headless Claude Code run in a task dir. The actor's ONLY output contract
is report.json (ActorReport) plus code files it writes; the orchestrator never parses
free text. Judge = one-shot admission decision (paper's coordinator-guided admission)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aspire.schemas import ActorReport, ProposedSkill, ReportError

_CAND_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class ActorError(RuntimeError):
    pass


@dataclass
class ProposeContext:
    task_dir: Path
    iter_dir: Path
    top3: list                 # list[tuple[program_path, score]] best-first
    skills: list               # list[Skill] injected by coordinator
    k: int = 3
    history_note: str = ""     # short summary of eliminated/blocked branches


class Actor(Protocol):
    def run_debug(self, task_dir: Path, model: str) -> ActorReport: ...
    def propose(self, ctx: ProposeContext, model: str) -> list: ...


class Judge(Protocol):
    def admit(self, skill: ProposedSkill) -> bool: ...


class FakeActor:
    def __init__(self, reports=(), candidate_sources=()):
        self._reports = list(reports)
        self._sources = list(candidate_sources)
        self.debug_calls, self.propose_calls = [], []

    def run_debug(self, task_dir: Path, model: str) -> ActorReport:
        self.debug_calls.append((str(task_dir), model))
        if not self._reports:
            raise ActorError("FakeActor: no scripted reports left")
        return self._reports.pop(0)

    def propose(self, ctx: ProposeContext, model: str) -> list:
        self.propose_calls.append((str(ctx.iter_dir), model, ctx.k))
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

    def admit(self, skill: ProposedSkill) -> bool:
        if not self._d:
            raise ActorError("FakeJudge: no scripted decisions left")
        return self._d.pop(0)


def _run_claude(prompt: str, cwd: Path, model: str, timeout_s: int) -> str:
    try:
        proc = subprocess.run(["claude", "-p", prompt, "--model", model],
                              cwd=cwd, capture_output=True, text=True,
                              errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise ActorError(f"claude timed out after {timeout_s}s") from e
    if proc.returncode != 0:
        raise ActorError(f"claude exited {proc.returncode}: {proc.stderr[-800:]}")
    return proc.stdout


class ClaudeCodeActor:
    def __init__(self, prompt_file: str, timeout_s: int = 7200):
        self._prompt_file = prompt_file
        self._timeout = timeout_s

    def _prompt(self) -> str:
        return Path(self._prompt_file).read_text()

    def run_debug(self, task_dir: Path, model: str) -> ActorReport:
        _run_claude(self._prompt(), task_dir, model, self._timeout)
        report = task_dir / "report.json"
        if not report.exists():
            raise ActorError("actor finished without writing report.json")
        try:
            return ActorReport.load(report)
        except ReportError as e:
            raise ActorError(str(e)) from e

    def propose(self, ctx: ProposeContext, model: str) -> list:
        ctx.iter_dir.mkdir(parents=True, exist_ok=True)
        extra = (f"\n\n## This round\nWrite exactly {ctx.k} candidates to "
                 f"{ctx.iter_dir}/candidate_<LETTER>/code.py (A..). "
                 f"Top programs so far: {[(str(p), s) for p, s in ctx.top3]}. "
                 f"{ctx.history_note}")
        _run_claude(self._prompt() + extra, ctx.task_dir, model, self._timeout)
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

    def admit(self, skill: ProposedSkill) -> bool:
        prompt = (Path(self._prompt_file).read_text()
                  + "\n\n## Candidate skill\n" + str(skill.to_dict()))
        out = _run_claude(prompt, self._workdir, self._model, self._timeout)
        for line in out.splitlines():
            low = line.strip().lower()
            if low.startswith("admit:"):
                verdict = low.split("admit:", 1)[1].strip()
                if verdict.startswith("yes"):
                    return True
                if verdict.startswith("no"):
                    return False
                # unrecognized verdict token: keep scanning remaining lines
        raise ActorError(f"judge reply had no ADMIT line: {out[-400:]}")
