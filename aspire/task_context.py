"""Materializes the actor's task-dir context: traces/ (per-primitive TraceRecords +
keyframes), task.md (runtime task language), skills.md (coordinator-retrieved skill
library entries). Written by the coordinator around each engine execute() call so the
actor prompt's claims about task-dir contents are true (gap-fix G2)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from aspire.skill_library import render_skill

_NO_LANGUAGE = ("(not yet captured from engine — dir name is the only identity; "
                "runtime language capture arrives with the real engine integration)")


def summarize_traces(traces) -> str:
    lines = [f"step {t.step}: {t.function} [{t.status}] {t.result_summary}"
             for t in traces]
    failures = sum(1 for t in traces if t.status == "error")
    lines.append(f"FAILURES: {failures}")
    return "\n".join(lines)


def write_execution_context(task_dir, result) -> None:
    task_dir = Path(task_dir)
    traces_dir = task_dir / "traces"
    media_dir = traces_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    (traces_dir / "trace.json").write_text(
        json.dumps([t.to_dict() for t in result.traces], indent=1))
    (traces_dir / "summary.txt").write_text(summarize_traces(result.traces))

    raw_dir = Path(result.raw_dir) if result.raw_dir else None
    for t in result.traces:
        for m in t.media:
            if raw_dir is None:
                continue
            src = raw_dir / m
            if src.exists():
                dst = media_dir / m
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)


def write_task_metadata(task_dir, task_language: str = "") -> None:
    task_dir = Path(task_dir)
    suite, name = task_dir.parent.name, task_dir.name
    body = task_language or _NO_LANGUAGE
    (task_dir / "task.md").write_text(
        f"# Task: {suite}/{name}\n\n## Runtime task language\n\n{body}\n")


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def relevant_skills(library, traces, cap: int = 10) -> list:
    keywords = set()
    for t in traces:
        if t.status != "error":
            continue
        for field in (t.result_summary, t.function):
            for tok in _TOKEN_RE.findall(field.lower()):
                if len(tok) >= 4:
                    keywords.add(tok)
    hits = []
    if keywords:
        hits = library.retrieve(keywords=keywords)
    if not hits:
        hits = library.load_all()
    return hits[:cap]


def write_skills_context(task_dir, skills) -> None:
    task_dir = Path(task_dir)
    if skills:
        body = "\n---\n".join(render_skill(s) for s in skills)
    else:
        body = "(none)\n"
    (task_dir / "skills.md").write_text("# Retrieved skills\n\n" + body)
