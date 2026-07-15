"""Algorithm 1 from the paper, with the paper's directory layout doubling as the
checkpoint format:
  <task>/run_001/iter_00/candidate_A/code.py + iter_summary.json  (per round)
  <task>/evosearch_best_code.py + evosearch_best_score.json       (final, Step-0 gate)
Resume rule: a round with iter_summary.json on disk is replayed from disk, not re-run.
Baseline score is checkpointed to run_dir/baseline_summary.json for the same reason.
Resume granularity is a whole round: a crash before iter_summary.json re-runs that
round's propose+execute (tokens re-spent). Deliberate tradeoff for simplicity."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from aspire.actors import ProposeContext
from aspire.config import RunConfig
from aspire.task_context import summarize_traces


class EvosearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Best:
    path: Path
    score: float


def top3(history):
    """history: list[(path_or_key, score, ...)] -> top 3 best-first. Tolerant of
    both legacy 2-tuples and G3's (path, score, summary) 3-tuples."""
    return sorted(history, key=lambda e: e[1], reverse=True)[:3]


_LEDGER_HEADER = (
    "# Task analysis ledger\n"
    "(created by orchestrator; per-round candidate outcomes. Eliminated = tried, failed on\n"
    "merit; audit-rejected = never executed. Semantic eliminated-vs-blocked judgment is the\n"
    "actor's job when reading this ledger.)\n")


def failure_note(history, max_lines=10) -> str:
    """Newest-to-oldest, dedup the "[error]" lines out of each history entry's trace
    summary. Audit-rejection lines are excluded (they live in the ledger; this note is
    runtime failure modes only). Empty when none — becomes ProposeContext.history_note."""
    lines = []
    for entry in reversed(history):
        summary = entry[2] if len(entry) > 2 else ""
        for line in summary.splitlines():
            if ": audit [error]" in line:
                continue
            if "[error]" in line and line not in lines:
                lines.append(line)
                if len(lines) >= max_lines:
                    break
        if len(lines) >= max_lines:
            break
    if not lines:
        return ""
    return "Known failure modes (newest first):\n" + "\n".join(lines)


def _first_error_line(summary: str) -> str:
    for line in summary.splitlines():
        if "[error]" in line:
            return line
    return "no failures"


def _append_ledger(run_dir: Path, i: int, entries: list) -> None:
    header = f"## iter_{i:02d}"
    ledger_path = run_dir / "task_analysis.md"
    existing = ledger_path.read_text() if ledger_path.exists() else _LEDGER_HEADER
    # newline-anchored: "## iter_10" must not match inside "## iter_100"
    if f"\n{header}\n" in f"\n{existing}":
        return
    lines = [header]
    for e in entries:
        p = Path(e["path"])
        try:
            rel = p.relative_to(run_dir.resolve())
        except ValueError:
            rel = p
        marker = p.with_suffix(p.suffix + ".AUDIT_REJECTED")
        if marker.exists():
            desc = "AUDIT_REJECTED"
        else:
            desc = _first_error_line(e.get("summary", ""))
        lines.append(f"- {rel}: {e['score']:.2f} — {desc}")
    _atomic_write(ledger_path, existing.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _load_checkpoint(path: Path):
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise EvosearchError(
            f"corrupt checkpoint {path}: delete it to re-run that round") from e


def _run_dir(task_dir: Path) -> Path:
    existing = sorted(task_dir.glob("run_*"))
    if existing:
        return existing[-1]
    d = task_dir / "run_001"
    d.mkdir()
    return d


def evosearch(task_dir: Path, engine, actor, cfg: RunConfig, skills=()) -> Best:
    task_dir = Path(task_dir)
    best_code = task_dir / "evosearch_best_code.py"
    best_meta = task_dir / "evosearch_best_score.json"
    # Paper Step 0. best_code is committed LAST, so its presence implies best_meta;
    # an orphan best_code (crash-window artifact) falls through to a fresh search.
    if best_code.exists() and best_meta.exists():
        return Best(best_code, _load_checkpoint(best_meta)["score"])

    run_dir = _run_dir(task_dir)
    baseline = task_dir / "code.py"
    base_meta = run_dir / "baseline_summary.json"
    if base_meta.exists():
        meta = _load_checkpoint(base_meta)
        history = [(baseline, meta["score"], meta.get("summary", ""))]
    else:
        r0 = engine.execute(baseline, cfg.s_dbg)
        b_summary = summarize_traces(r0.traces)
        _atomic_write(run_dir / "baseline_trace.json",
                     json.dumps([t.to_dict() for t in r0.traces], indent=1))
        _atomic_write(base_meta, json.dumps({"score": r0.score, "summary": b_summary}))
        history = [(baseline, r0.score, b_summary)]
    best = max(history, key=lambda e: e[1])

    for i in range(cfg.t):
        if best[1] >= cfg.theta:
            break
        iter_dir = run_dir / f"iter_{i:02d}"
        summary = iter_dir / "iter_summary.json"
        if summary.exists():                                   # resume from disk
            entries = _load_checkpoint(summary)
            for entry in entries:
                history.append((Path(entry["path"]), entry["score"],
                                entry.get("summary", "")))
        else:
            ctx = ProposeContext(task_dir=task_dir, iter_dir=iter_dir,
                                 top3=top3(history), skills=list(skills), k=cfg.k,
                                 history_note=failure_note(history))
            candidates = actor.propose(ctx, model=cfg.model_propose)
            entries = []
            for c in candidates:
                r = engine.execute(c, cfg.s_dbg)
                c_summary = summarize_traces(r.traces)
                c_dir = Path(c).parent
                _atomic_write(c_dir / "trace.json",
                             json.dumps([t.to_dict() for t in r.traces], indent=1))
                _atomic_write(c_dir / "trace_summary.txt", c_summary)
                history.append((c, r.score, c_summary))
                entries.append({"path": str(Path(c).resolve()), "score": r.score,
                                "summary": c_summary})
            _atomic_write(summary, json.dumps(entries, indent=1))
        _append_ledger(run_dir, i, entries)
        best = max(history, key=lambda e: e[1])

    if not Path(best[0]).exists():
        raise EvosearchError(f"best program file missing: {best[0]}")

    # Winner's trace bundle, persisted at task level so a later phase
    # (ExtractValidatedPatterns) can read it. Auxiliary: written before best_meta/
    # best_code, which is fine — the commit-order invariant only concerns those two.
    best_summary = best[2] if len(best) > 2 else ""
    if Path(best[0]) == baseline:
        src = run_dir / "baseline_trace.json"
    else:
        src = Path(best[0]).parent / "trace.json"
    if best_summary and src.exists():
        trace_text = src.read_text()
        summary_text = best_summary
    else:
        trace_text = "[]"
        summary_text = "(trace bundle unavailable: pre-G3 checkpoint)"
    _atomic_write(task_dir / "evosearch_best_trace.json", trace_text)
    _atomic_write(task_dir / "evosearch_best_summary.txt", summary_text)

    # Commit order: meta first, code last — the Step-0 gate keys on best_code, so it
    # must never exist without its meta. Both writes land atomically via os.replace.
    _atomic_write(best_meta, json.dumps({"score": best[1], "source": str(best[0])}))
    tmp_code = best_code.with_suffix(".py.tmp")
    shutil.copyfile(best[0], tmp_code)
    os.replace(tmp_code, best_code)
    return Best(best_code, best[1])
