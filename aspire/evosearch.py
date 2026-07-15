"""Algorithm 1 from the paper, with the paper's directory layout doubling as the
checkpoint format:
  <task>/run_001/iter_00/candidate_A/code.py + iter_summary.json  (per round)
  <task>/evosearch_best_code.py + evosearch_best_score.json       (final, Step-0 gate)
Resume rule: a round with iter_summary.json on disk is replayed from disk, not re-run.
Baseline score is checkpointed to run_dir/baseline_summary.json for the same reason."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from aspire.actors import ProposeContext
from aspire.config import RunConfig


@dataclass(frozen=True)
class Best:
    path: Path
    score: float


def top3(history):
    """history: list[(path_or_key, score)] -> top 3 best-first."""
    return sorted(history, key=lambda e: e[1], reverse=True)[:3]


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
    if best_code.exists():                                     # paper Step 0
        return Best(best_code, json.loads(best_meta.read_text())["score"])

    run_dir = _run_dir(task_dir)
    baseline = task_dir / "code.py"
    base_meta = run_dir / "baseline_summary.json"
    if base_meta.exists():
        history = [(baseline, json.loads(base_meta.read_text())["score"])]
    else:
        r0 = engine.execute(baseline, cfg.s_dbg)
        base_meta.write_text(json.dumps({"score": r0.score}))
        history = [(baseline, r0.score)]
    best = max(history, key=lambda e: e[1])

    for i in range(cfg.t):
        if best[1] >= cfg.theta:
            break
        iter_dir = run_dir / f"iter_{i:02d}"
        summary = iter_dir / "iter_summary.json"
        if summary.exists():                                   # resume from disk
            for entry in json.loads(summary.read_text()):
                history.append((Path(entry["path"]), entry["score"]))
        else:
            ctx = ProposeContext(task_dir=task_dir, iter_dir=iter_dir,
                                 top3=top3(history), skills=list(skills), k=cfg.k)
            candidates = actor.propose(ctx, model=cfg.model_propose)
            entries = []
            for c in candidates:
                r = engine.execute(c, cfg.s_dbg)
                history.append((c, r.score))
                entries.append({"path": str(c), "score": r.score})
            summary.write_text(json.dumps(entries, indent=1))
        best = max(history, key=lambda e: e[1])

    shutil.copyfile(best[0], best_code)
    best_meta.write_text(json.dumps({"score": best[1], "source": str(best[0])}))
    return Best(best_code, best[1])
