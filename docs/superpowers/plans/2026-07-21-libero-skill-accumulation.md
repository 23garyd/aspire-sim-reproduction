# ASPIRE LIBERO skill-accumulation campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the warm-vs-cold skill-accumulation experiment on `libero_spatial`, testing whether a curriculum-accumulated skill library helps held-out tasks — the distinctive ASPIRE claim.

**Architecture:** A committed campaign runner (`libero_accumulation.sh`) drives the *unchanged* `aspire/` pipeline over generated `libero_spatial` privileged configs in cap-x's `.venv-libero`; an analysis script extracts per-run success + attempts-to-solve from the run artifacts and emits a warm-vs-cold verdict. No `aspire/` changes.

**Tech Stack:** bash (runner), Python 3 stdlib (analysis + tests), pytest. Reuses `aspire.run`, `scripts/capx_execute.py`, cap-x `.venv-libero` (robosuite 1.4.0), LIBERO privileged configs.

## Global Constraints

- **`.venv-libero` ONLY for LIBERO**, with a **preflight assert that `robosuite.__version__` starts with `1.4`** — abort loudly otherwise (the main `.venv` is robosuite 1.5.1 and silently produces garbage on LIBERO). Runner python for the engine: `/home/demo/cap-x/.venv-libero/bin/python`. Orchestration (`python3 -m aspire.run`) runs in system python3 from the repo root; only the `--capx-cmd` uses `.venv-libero`.
- **No `aspire/` changes.** Reuse coordinator/actor/evosearch/skill_library/capx_execute verbatim.
- **Privileged configs** generated from `/home/demo/cap-x/env_configs/libero/franka_libero_spatial_0_privileged.yaml` by setting `task_id` (the only edit: `task_id: 0` → `task_id: N`).
- **Fixed run parameters:** `--s-dbg 0 --s-val 100`; Phase-1 accumulate + Phase-2b test `--t 5`; Phase-2a cold calibration `--t 3`. `theta` and `admission_min_val` are the config defaults (1.0 and 0.5).
- **Accumulate task_ids `2,1,0`** (shared library); **held-out shortlist `8,6,5,3`** (cold calibration picks 2). Same generic naive baseline (`black_bowl` grasp-place, no committed descent → fails) for every task.
- **Idempotent:** per-run `DONE` markers so a re-run resumes.
- **Metrics:** `attempts-to-solve` = the integer `NNNN` of the first `exec_NNNN/result.json` with `score >= theta`, else censored; `solved` from the run's summary (`dbg_score >= theta`); `admitted` count from the summary.
- **Test command:** `python3 -m pytest <path> -q -p no:anyio` (REQUIRED flag). Work from `/home/demo/aspire_robot_engine` on branch `aspire_original_sim`.

---

### Task 1: Analysis core — per-run extraction (`attempts_to_solve`, `run_outcome`)

**Files:**
- Create: `scripts/analyze_libero_accumulation.py`
- Test: `tests/aspire/test_libero_accum_analysis.py`

**Interfaces:**
- Produces: `attempts_to_solve(out_root: Path, theta: float = 1.0) -> int | None` (first `exec_NNNN` with score≥theta, in numeric order; `None` if none); `run_outcome(summary: dict, theta: float = 1.0, admission_min_val: float = 0.5) -> dict` returning `{"solved": bool, "val_solved": bool, "admitted": int}`.

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_libero_accum_analysis.py`:

```python
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_accumulation import attempts_to_solve, run_outcome


def _mk_exec(root, n, score):
    d = root / f"exec_{n:04d}"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"score": score, "raw_dir": "", "traces": []}))


def test_attempts_to_solve_first_winner(tmp_path):
    # execs 1..14 score 0, exec 15 scores 1.0 -> attempts_to_solve == 15
    for n in range(1, 15):
        _mk_exec(tmp_path, n, 0.0)
    _mk_exec(tmp_path, 15, 1.0)
    _mk_exec(tmp_path, 16, 0.0)
    _mk_exec(tmp_path, 17, 1.0)
    assert attempts_to_solve(tmp_path, theta=1.0) == 15


def test_attempts_to_solve_censored_when_unsolved(tmp_path):
    for n in range(1, 6):
        _mk_exec(tmp_path, n, 0.0)
    assert attempts_to_solve(tmp_path, theta=1.0) is None


def test_run_outcome_solved_validated_admitted():
    s = {"stage_reached": "validated", "dbg_score": 1.0, "val_score": 1.0, "admitted": ["a", "b"]}
    assert run_outcome(s) == {"solved": True, "val_solved": True, "admitted": 2}


def test_run_outcome_failed_run():
    s = {"stage_reached": "validated", "dbg_score": 0.0, "val_score": 0.0, "admitted": []}
    assert run_outcome(s) == {"solved": False, "val_solved": False, "admitted": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_accum_analysis.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: analyze_libero_accumulation`.

- [ ] **Step 3: Write the implementation**

Create `scripts/analyze_libero_accumulation.py`:

```python
#!/usr/bin/env python3
"""Analyze the LIBERO skill-accumulation campaign: per-run success + attempts-to-solve,
then a warm-vs-cold table + honest H1/H0 verdict. Reads run dirs written by
scripts/libero_accumulation.sh. stdlib only."""
from __future__ import annotations

import json
import re
from pathlib import Path

_EXEC = re.compile(r"exec_(\d+)$")


def attempts_to_solve(out_root, theta: float = 1.0):
    """The 1-based exec index of the first exec_NNNN/result.json with score >= theta,
    scanning in numeric order. None if no exec solved (censored)."""
    out_root = Path(out_root)
    execs = []
    for d in out_root.glob("exec_*"):
        m = _EXEC.search(d.name)
        if m and (d / "result.json").exists():
            execs.append((int(m.group(1)), d / "result.json"))
    for n, rf in sorted(execs):
        try:
            if float(json.loads(rf.read_text()).get("score", 0.0)) >= theta:
                return n
        except (json.JSONDecodeError, ValueError, OSError):
            continue
    return None


def run_outcome(summary: dict, theta: float = 1.0, admission_min_val: float = 0.5) -> dict:
    """Interpret an aspire.run summary line for this campaign's metrics."""
    return {
        "solved": float(summary.get("dbg_score", 0.0)) >= theta,
        "val_solved": float(summary.get("val_score", 0.0)) >= admission_min_val,
        "admitted": len(summary.get("admitted", []) or []),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_accum_analysis.py -q -p no:anyio`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_libero_accumulation.py tests/aspire/test_libero_accum_analysis.py
git commit -m "feat(libero): accumulation analysis core — attempts-to-solve + run outcome"
```

---

### Task 2: Analysis CLI — warm-vs-cold table + verdict

**Files:**
- Modify: `scripts/analyze_libero_accumulation.py` (append the campaign reader + CLI)
- Test: `tests/aspire/test_libero_accum_report.py`

**Interfaces:**
- Consumes: `attempts_to_solve`, `run_outcome` (Task 1).
- Produces: `read_run(run_dir) -> dict` (one Phase-2 run: reads `summary.json` + `exec/`, returns `{task, arm, repeat, solved, val_solved, attempts, admitted}`); `build_report(campaign_root) -> dict` (scans `test/<task>/<arm>/<repeat>/` runs, aggregates warm-vs-cold success rate + mean attempts (censored = budget_cap), returns the results dict + a `verdict` string); `render_table(report) -> str`. A `--root <campaign_dir>` CLI writes `<root>/results.json` and prints the table.

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_libero_accum_report.py`:

```python
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_accumulation import read_run, build_report


def _mk_run(run_dir, dbg, val, admitted, winner_exec):
    (run_dir / "exec").mkdir(parents=True)
    for n in range(1, (winner_exec or 6) + 1):
        d = run_dir / "exec" / f"exec_{n:04d}"; d.mkdir()
        score = 1.0 if (winner_exec and n == winner_exec) else 0.0
        (d / "result.json").write_text(json.dumps({"score": score}))
    run_dir.joinpath("summary.json").write_text(json.dumps(
        {"stage_reached": "validated", "dbg_score": dbg, "val_score": val, "admitted": admitted}))


def test_read_run_extracts_fields(tmp_path):
    r = tmp_path / "test" / "spatial_6" / "warm" / "1"
    r.mkdir(parents=True)
    _mk_run(r, dbg=1.0, val=1.0, admitted=["s"], winner_exec=8)
    out = read_run(r, task="spatial_6", arm="warm", repeat=1)
    assert out["solved"] and out["attempts"] == 8 and out["arm"] == "warm"


def test_build_report_warm_beats_cold(tmp_path):
    base = tmp_path / "test"
    # warm solves both tasks fast (attempts 5); cold slow/one unsolved
    for task in ("spatial_6", "spatial_8"):
        for rep in (1, 2):
            w = base / task / "warm" / str(rep); w.mkdir(parents=True)
            _mk_run(w, 1.0, 1.0, ["s"], winner_exec=5)
    for task, cold_specs in (("spatial_6", [(1.0, 12), (1.0, 14)]), ("spatial_8", [(0.0, None), (1.0, 15)])):
        for rep, (dbg, winner) in enumerate(cold_specs, 1):
            c = base / task / "cold" / str(rep); c.mkdir(parents=True)
            _mk_run(c, dbg, 1.0 if dbg else 0.0, ["s"] if dbg else [], winner_exec=winner)
    rep = build_report(tmp_path)
    assert rep["warm"]["success_rate"] == 1.0
    assert rep["warm"]["mean_attempts"] < rep["cold"]["mean_attempts"]
    assert "H1" in rep["verdict"] or "warm" in rep["verdict"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_accum_report.py -q -p no:anyio`
Expected: FAIL — `ImportError: cannot import name 'read_run'`.

- [ ] **Step 3: Append the implementation to `scripts/analyze_libero_accumulation.py`**

```python
BUDGET_CAP = 999   # censored attempts-to-solve sentinel for aggregation


def read_run(run_dir, task: str, arm: str, repeat: int, theta: float = 1.0) -> dict:
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text())
    oc = run_outcome(summary, theta=theta)
    ats = attempts_to_solve(run_dir / "exec", theta=theta)
    return {"task": task, "arm": arm, "repeat": repeat, "attempts": ats,
            "attempts_censored": ats if ats is not None else BUDGET_CAP, **oc}


def _agg(rows):
    if not rows:
        return {"n": 0, "success_rate": 0.0, "mean_attempts": None}
    solved = [r for r in rows]
    return {"n": len(rows),
            "success_rate": sum(r["solved"] for r in rows) / len(rows),
            "mean_attempts": sum(r["attempts_censored"] for r in solved) / len(solved),
            "mean_attempts_solved_only": (
                sum(r["attempts"] for r in rows if r["attempts"] is not None)
                / max(1, sum(1 for r in rows if r["attempts"] is not None)))}


def build_report(campaign_root) -> dict:
    root = Path(campaign_root) / "test"
    rows = []
    for task_dir in sorted(root.glob("*")):
        for arm in ("warm", "cold"):
            for rep_dir in sorted((task_dir / arm).glob("*")):
                if (rep_dir / "summary.json").exists():
                    rows.append(read_run(rep_dir, task_dir.name, arm, int(rep_dir.name)))
    warm = _agg([r for r in rows if r["arm"] == "warm"])
    cold = _agg([r for r in rows if r["arm"] == "cold"])
    # Honest, pre-registered call (suggestive at Lean N).
    if warm["n"] == 0 or cold["n"] == 0:
        verdict = "INCOMPLETE: missing an arm."
    elif warm["success_rate"] > cold["success_rate"] or (
            warm["mean_attempts"] is not None and cold["mean_attempts"] is not None
            and warm["mean_attempts"] < cold["mean_attempts"]):
        verdict = ("H1 (suggestive): warm (accumulated library) beats cold — higher success "
                   f"({warm['success_rate']:.2f} vs {cold['success_rate']:.2f}) and/or fewer "
                   f"attempts ({warm['mean_attempts']} vs {cold['mean_attempts']}). Lean N: not conclusive.")
    else:
        verdict = (f"H0 (suggestive): warm ~= cold (success {warm['success_rate']:.2f} vs "
                   f"{cold['success_rate']:.2f}; attempts {warm['mean_attempts']} vs {cold['mean_attempts']}). "
                   "No measurable accumulation benefit on this suite at Lean N.")
    return {"rows": rows, "warm": warm, "cold": cold, "verdict": verdict}


def render_table(report: dict) -> str:
    lines = ["task           arm   rep  solved  val  attempts  admitted",
             "-------------- ----- ---- ------- ---- --------- --------"]
    for r in sorted(report["rows"], key=lambda x: (x["task"], x["arm"], x["repeat"])):
        lines.append(f"{r['task']:<14} {r['arm']:<5} {r['repeat']:<4} "
                     f"{str(r['solved']):<7} {str(r['val_solved']):<4} "
                     f"{str(r['attempts']):<9} {r['admitted']}")
    lines += ["", f"WARM: {report['warm']}", f"COLD: {report['cold']}", "", "VERDICT: " + report["verdict"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="campaign root (contains test/<task>/<arm>/<rep>/)")
    args = ap.parse_args()
    report = build_report(args.root)
    (Path(args.root) / "results.json").write_text(json.dumps(report, indent=1))
    print(render_table(report))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_accum_report.py -q -p no:anyio`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_libero_accumulation.py tests/aspire/test_libero_accum_report.py
git commit -m "feat(libero): accumulation report — warm-vs-cold table + honest verdict"
```

---

### Task 3: The generic baseline + the campaign runner (`libero_accumulation.sh`)

**Files:**
- Create: `runs/2026-07-21-libero-accumulation/baseline_grasp_place.py`
- Create: `scripts/libero_accumulation.sh`
- Test: `tests/aspire/test_libero_accum_runner_dryrun.py`

**Interfaces:**
- Consumes: `scripts/capx_execute.py`, `aspire.run`, `scripts/analyze_libero_accumulation.py`, cap-x `.venv-libero` + the privileged template.
- Produces: the runner with `DRY=1` (prints the planned per-phase `aspire.run` commands + the generated config task_ids, does NOT run/require GPU), and a live mode that executes the campaign into `$ROOT` (default `$HOME/aspire_runs/libero_accum`).

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_libero_accum_runner_dryrun.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_run_lists_phases_and_tasks():
    proc = subprocess.run(["bash", "scripts/libero_accumulation.sh"],
                          capture_output=True, text=True, cwd=REPO,
                          env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
                               "ROOT": "/tmp/libero_accum_dryrun"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "PHASE 1" in out and "PHASE 2" in out
    # accumulate task_ids 2,1,0 and the held-out calibration shortlist 8,6,5,3 appear
    for tid in ("task_id: 2", "task_id: 1", "task_id: 0", "task_id: 8", "task_id: 6"):
        assert tid in out, f"missing {tid}"
    assert ".venv-libero" in out and "--t 5" in out and "--t 3" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_accum_runner_dryrun.py -q -p no:anyio`
Expected: FAIL — the runner script does not exist.

- [ ] **Step 3: Write the baseline program**

Create `runs/2026-07-21-libero-accumulation/baseline_grasp_place.py`:

```python
# Generic naive baseline for libero_spatial (every task = grasp the black bowl, place on
# the plate). Grasps at a single hover waypoint with no committed descent and no place ->
# fails, triggering trace-guided repair. Same program for all spatial tasks (shared object).
open_gripper()
gpos, gquat = sample_grasp_pose("black_bowl")
goto_pose(gpos, gquat, z_approach=0.05)
close_gripper()
```

- [ ] **Step 4: Write the runner**

Create `scripts/libero_accumulation.sh`:

```bash
#!/bin/bash
# ASPIRE LIBERO skill-accumulation campaign (spec: docs/superpowers/specs/2026-07-21-libero-skill-accumulation-design.md).
# Warm-vs-cold on libero_spatial. Reuses aspire/ unchanged; runs LIBERO via cap-x .venv-libero.
# DRY=1 prints the plan without running (no GPU/credits). Idempotent via per-run DONE markers.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="$REPO/scripts/capx_execute.py"
TMPL=/home/demo/cap-x/env_configs/libero/franka_libero_spatial_0_privileged.yaml
RUNS="$REPO/runs/2026-07-21-libero-accumulation"
BASELINE="$RUNS/baseline_grasp_place.py"
ROOT=${ROOT:-$HOME/aspire_runs/libero_accum}
CFGDIR="$ROOT/configs"
ACCUM_LIB="$ROOT/accumulated_library"
DRY=${DRY:-0}
ACCUM_TASKS=(2 1 0)          # curriculum: bank the grasp-place skill
CALIB_SHORTLIST=(8 6 5 3)    # held-out candidates; cold calibration picks 2
REPEATS=2

mkdir -p "$ROOT" "$CFGDIR"

gen_cfg() { local tid=$1; local out="$CFGDIR/spatial_$tid.yaml"; sed "s/task_id: 0/task_id: $tid/" "$TMPL" > "$out"; echo "$out"; }

# run_one <task_id> <library> <sub> <t>  -> one aspire.run into $ROOT/<sub>
run_one() {
  local tid=$1 lib=$2 sub=$3 t=$4
  local cfg; cfg=$(gen_cfg "$tid")
  local rdir="$ROOT/$sub" task="$ROOT/$sub/task" out="$ROOT/$sub/exec"
  if [ -f "$rdir/DONE" ]; then echo "skip $sub (DONE)"; return; fi
  local capxcmd="$VENV $CAPX --workdir /home/demo/cap-x --config-path $cfg"
  if [ "$DRY" = 1 ]; then
    echo "[dry] $sub: aspire.run --task-dir $task --engine capx --capx-cmd \"$capxcmd\" --library $lib --s-dbg 0 --s-val 100 --t $t   ($(grep -o 'task_id: [0-9]*' "$cfg"))"
    return
  fi
  mkdir -p "$task" "$out"; cp "$BASELINE" "$task/code.py"
  MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx --capx-cmd "$capxcmd" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 100 --t "$t" \
    2>&1 | tee "$rdir/log.txt" | tail -1 > "$rdir/summary.json"
  touch "$rdir/DONE"
}

skill_count() { $VENV -c "from aspire.skill_library import SkillLibrary; print(len(SkillLibrary('$1').load_all()))" 2>/dev/null || echo 0; }

echo "=== PHASE 0: preflight guard + config gen ==="
if [ "$DRY" != 1 ]; then
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite is not 1.4.x (LIBERO requires 1.4.0). Aborting."; exit 1; }
fi
for tid in "${ACCUM_TASKS[@]}" "${CALIB_SHORTLIST[@]}"; do gen_cfg "$tid" >/dev/null; done

echo "=== PHASE 1: accumulate (shared library $ACCUM_LIB) ==="
mkdir -p "$ACCUM_LIB"
for tid in "${ACCUM_TASKS[@]}"; do run_one "$tid" "$ACCUM_LIB" "accumulate/spatial_$tid" 5; done
if [ "$DRY" != 1 ]; then
  n=$(skill_count "$ACCUM_LIB")
  echo "=== accumulated skills: $n ==="
  [ "$n" -ge 1 ] || { echo "GATE FAIL: Phase 1 admitted 0 skills -> warm==cold trivially. Stopping before Phase 2."; exit 2; }
fi

echo "=== PHASE 2a: cold calibration (--t 3) over held-out shortlist -> pick 2 solvable ==="
SELECTED=()
for tid in "${CALIB_SHORTLIST[@]}"; do
  run_one "$tid" "$ROOT/calib/empty_$tid" "test/spatial_$tid/cold/1" 3    # empty lib per task; this IS cold repeat 1
  if [ "$DRY" != 1 ]; then
    solved=$(python3 -c "import json; s=json.load(open('$ROOT/test/spatial_$tid/cold/1/summary.json')); print(1 if float(s.get('dbg_score',0))>=1.0 else 0)" 2>/dev/null || echo 0)
    [ "$solved" = 1 ] && SELECTED+=("$tid")
  else
    echo "[dry] calibrate held-out task_id $tid (cold, --t 3); solvable ones become test tasks"
  fi
  [ "${#SELECTED[@]}" -ge 2 ] && break
done
if [ "$DRY" = 1 ]; then SELECTED=(8 6); fi
echo "=== SELECTED TEST TASKS: ${SELECTED[*]:-none} ==="
if [ "$DRY" != 1 ] && [ "${#SELECTED[@]}" -lt 2 ]; then
  echo "GATE FAIL: <2 held-out tasks solvable in calibration. Widen CALIB_SHORTLIST or budget."; exit 3; fi

echo "=== PHASE 2b: warm vs cold on selected tasks (2 repeats/arm; cold repeat 1 = calibration) ==="
for tid in "${SELECTED[@]}"; do
  for rep in $(seq 1 $REPEATS); do
    warm_lib="$ROOT/test/spatial_$tid/warm/$rep/lib"; mkdir -p "$warm_lib"
    [ "$DRY" = 1 ] || cp -r "$ACCUM_LIB/." "$warm_lib/" 2>/dev/null
    run_one "$tid" "$warm_lib" "test/spatial_$tid/warm/$rep" 5             # WARM: copy of frozen accumulated lib
    if [ "$rep" -ge 2 ]; then run_one "$tid" "$ROOT/test/spatial_$tid/cold/$rep/lib" "test/spatial_$tid/cold/$rep" 5; fi  # COLD repeat 2 (rep1 = calibration)
  done
done

echo "=== ANALYZE ==="
if [ "$DRY" != 1 ]; then python3 "$REPO/scripts/analyze_libero_accumulation.py" --root "$ROOT"; else echo "[dry] python3 scripts/analyze_libero_accumulation.py --root $ROOT"; fi
echo "=== CAMPAIGN DONE ($(date -u +%FT%TZ)) root=$ROOT ==="
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_accum_runner_dryrun.py -q -p no:anyio`
Expected: PASS — `DRY=1` prints PHASE 1/2, the accumulate task_ids (2,1,0), the calibration shortlist (8,6,...), and the `.venv-libero` / `--t 5` / `--t 3` markers, exiting 0 with no GPU.

- [ ] **Step 6: Commit**

```bash
chmod +x scripts/libero_accumulation.sh
git add scripts/libero_accumulation.sh runs/2026-07-21-libero-accumulation/baseline_grasp_place.py tests/aspire/test_libero_accum_runner_dryrun.py
git commit -m "feat(libero): skill-accumulation campaign runner (warm-vs-cold, guarded, idempotent)"
```

---

### Task 4: Full-suite gate + execute the campaign

**Files:** none (verification + execution)

- [ ] **Step 1: Full-suite gate**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — prior suite + the 3 new analysis/runner tests; no `aspire/` regression (this campaign added no `aspire/` code).

- [ ] **Step 2: Dry-run the campaign end-to-end (no GPU/credits)**

Run: `DRY=1 bash scripts/libero_accumulation.sh`
Expected: prints Phase 0/1/2 plan — the generated configs' task_ids, the accumulate loop (2,1,0 sharing the library), the cold calibration over {8,6,5,3}, the warm/cold test loop, and the analyze step; exits 0.

- [ ] **Step 3: Execute the campaign (LIVE — GPU + credits; long)**

Confirm the LLM proxy is up (`curl -s http://127.0.0.1:8110/ >/dev/null && echo up`). Then run in the background (it is ~1 day of GPU + modest credits):

```bash
nohup bash scripts/libero_accumulation.sh > runs/2026-07-21-libero-accumulation/campaign.log 2>&1 &
```

Watch: Phase 1 must print `accumulated skills: N` with `N>=1` (else it stops at the gate); Phase 2a prints `SELECTED TEST TASKS`; Phase 2b runs warm/cold; the final `ANALYZE` prints the warm-vs-cold table + verdict. Artifacts land under `$HOME/aspire_runs/libero_accum` and the results table is echoed at the end.

- [ ] **Step 4: Record the result**

Copy the final `results.json` + table into `runs/2026-07-21-libero-accumulation/` and commit:

```bash
cp "$HOME/aspire_runs/libero_accum/results.json" runs/2026-07-21-libero-accumulation/results.json
git add runs/2026-07-21-libero-accumulation/results.json
git commit -m "results(libero): skill-accumulation warm-vs-cold — <one-line honest verdict>"
```

---

## Self-review notes (spec coverage)

- Preflight robosuite-1.4 guard + config generation (task_id) → Task 3 runner Phase 0.
- Phase 1 accumulate (2,1,0, shared library) + skill-count gate → Task 3 Phase 1.
- Phase 2a cold-calibration test-task selection (arm-neutral; calibration = cold repeat 1) → Task 3 Phase 2a.
- Phase 2b warm(copy of frozen lib) vs cold(empty), 2 repeats, `--t 5` → Task 3 Phase 2b.
- Metrics: attempts-to-solve (first exec≥theta, censored) + solved (dbg_score≥theta) + admitted → Tasks 1–2.
- Warm-vs-cold table + pre-registered honest H1/H0 verdict → Task 2.
- No `aspire/` changes; reuse coordinator/actor/evosearch/skill_library/capx_execute → Global Constraints (runner only calls `aspire.run`).
- `.venv-libero` only, `MUJOCO_GL=egl`, idempotent DONE markers, privileged configs → Task 3 runner.
- Execute as a committed script → Task 4.
- **Honest boundary:** Lean N → results reported "suggestive," extensible to Standard/Thorough tiers.
