# Val-Pre-Registered Confirmatory Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tooling + runner for a pre-registered confirmatory campaign that scores held-out validation (`val_score`) as the primary metric and tests warm_dumpall vs cold on a mechanistically-selected overfit-band task set.

**Architecture:** Two small, unit-tested pure changes (analyzer gains `--metric`/`--alpha` and an absent-arm-robust verdict; the parallel runner gains a `--s-val` passthrough) plus one pure selection module and one bash runner that freezes a pre-registration, probes/selects tasks, runs the two-arm test, and analyzes on val.

**Tech Stack:** Python 3 (stdlib + `math.comb` Fisher helper), bash runner, cap-x `.venv-libero` (robosuite 1.4.0), pytest, existing `scripts/libero_tiling_parallel.py`.

## Global Constraints

- `.venv-libero` python = `/home/demo/cap-x/.venv-libero/bin/python`; robosuite must be 1.4.x (Phase 0 asserts). Never the main `.venv` for LIBERO.
- `aspire/` is NOT modified (val_score is already produced; only scripts change).
- Billing: every `aspire.run` invocation strips `ANTHROPIC_API_KEY` (subscription). `libero_tiling_parallel.py` already does `env.pop("ANTHROPIC_API_KEY"/"ANTHROPIC_AUTH_TOKEN")`.
- Primary metric = `val_score`; val-solved threshold = **0.5**; val seeds = **`200-204`**; debug seed = **`0`**; test budget = **`t=2`**; N = **10**; arms = **`warm_dumpall`, `cold`** (no `warm_geo`).
- Overfit band (frozen): cold dbg-rate **≥ 0.6** AND cold val-rate **≤ 0.2**; **≥2** selected or stop.
- Decision (frozen): H1 iff warm_dumpall val-rate > cold val-rate AND Fisher p **< 0.05**; else H0.
- `PREREGISTRATION.md` committed and its hash logged **before** any test run.
- Library = `~/aspire_runs/libero_tiling/tiled_library` (frozen, 8 skills / 3 locations).
- `MUJOCO_GL=egl`; idempotent DONE markers; `DRY=1`-safe.
- All tests run with `python3 -m pytest tests/ -q -p no:anyio` (the `-p no:anyio` flag is REQUIRED).

---

### Task 1: Analyzer `--metric {dbg,val}` + `--alpha` + absent-arm-robust verdict

**Files:**
- Modify: `scripts/analyze_libero_tiling.py`
- Test: `tests/aspire/test_val_confirmatory_analyzer.py`

**Interfaces:**
- Consumes: existing `read_arm_rows`, `build_tiling_report`, `_verdict`, `_agg`, `_pair_p`, `ARMS`.
- Produces: `read_arm_rows(root, heldout_tasks, prefix="spatial", metric="dbg")`; `build_tiling_report(root, heldout_tasks, prefix="spatial", metric="dbg", alpha=0.10)`; `_verdict(arms, pw, alpha=0.10, metric="dbg")` that skips arms with `n==0` and, when `warm_geo` is empty, reports **warm_dumpall vs cold** (`A_vs_C`) as the primary contrast. CLI gains `--metric {dbg,val}` (default `dbg`) and `--alpha` (default `0.10`).

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_val_confirmatory_analyzer.py
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_tiling import build_tiling_report


def _mk(root, task, arm, rep, dbg, val, winner=2):
    d = root / "test" / f"10_{task}" / arm / str(rep)
    (d / "exec").mkdir(parents=True)
    for n in range(1, (winner if dbg >= 1.0 else 3) + 1):
        e = d / "exec" / f"exec_{n:04d}"; e.mkdir()
        (e / "result.json").write_text(json.dumps({"score": 1.0 if (dbg >= 1.0 and n == winner) else 0.0}))
    d.joinpath("summary.json").write_text(json.dumps({"dbg_score": dbg, "val_score": val, "admitted": []}))


def test_metric_val_scores_on_val_score(tmp_path):
    # cold: high dbg, low val (overfit). warm_dumpall: lower dbg, higher val (generalizes).
    for rep in range(1, 6):
        _mk(tmp_path, "6", "cold", rep, dbg=1.0, val=0.0)
        _mk(tmp_path, "6", "warm_dumpall", rep, dbg=0.0, val=1.0)
    dbg_rep = build_tiling_report(tmp_path, ["6"], prefix="10", metric="dbg")
    val_rep = build_tiling_report(tmp_path, ["6"], prefix="10", metric="val")
    # dbg: cold solves, warm doesn't
    assert dbg_rep["arms"]["cold"]["success_rate"] == 1.0
    assert dbg_rep["arms"]["warm_dumpall"]["success_rate"] == 0.0
    # val: flipped
    assert val_rep["arms"]["cold"]["success_rate"] == 0.0
    assert val_rep["arms"]["warm_dumpall"]["success_rate"] == 1.0


def test_verdict_uses_warm_dumpall_when_geo_absent(tmp_path):
    # only warm_dumpall + cold present; warm_geo has zero rows
    for rep in range(1, 6):
        _mk(tmp_path, "6", "warm_dumpall", rep, dbg=0.0, val=1.0)
        _mk(tmp_path, "6", "cold", rep, dbg=1.0, val=0.0)
    rep = build_tiling_report(tmp_path, ["6"], prefix="10", metric="val", alpha=0.05)
    assert rep["arms"]["warm_geo"]["n"] == 0
    # primary contrast is A_vs_C (warm_dumpall vs cold), and it is significant here
    assert rep["pairwise"]["A_vs_C"] < 0.05
    assert "warm_dumpall" in rep["verdict"] and "warm_geo" not in rep["verdict"]
    assert "H1" in rep["verdict"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_analyzer.py -q -p no:anyio`
Expected: FAIL (`build_tiling_report() got an unexpected keyword argument 'metric'`)

- [ ] **Step 3: Thread `metric` through `read_arm_rows`**

In `scripts/analyze_libero_tiling.py`, change the row scoring:

```python
def read_arm_rows(root, heldout_tasks, prefix="spatial", metric="dbg"):
    root = Path(root)
    rows = []
    for tid in heldout_tasks:
        for arm in ARMS:
            base = root / "test" / f"{prefix}_{tid}" / arm
            if not base.is_dir():
                continue
            for rep_dir in sorted(base.glob("*")):
                sfile = rep_dir / "summary.json"
                if not sfile.is_file():
                    continue
                s = json.loads(sfile.read_text())
                if metric == "val":
                    solved = float(s.get("val_score", 0)) >= 0.5
                else:
                    solved = float(s.get("dbg_score", 0)) >= 1.0
                att = attempts_to_solve(rep_dir / "exec", theta=1.0)
                rows.append({"task": f"{prefix}_{tid}", "arm": arm,
                             "solved": solved, "attempts": att,
                             "val_score": float(s.get("val_score", 0)),
                             "dbg_score": float(s.get("dbg_score", 0))})
    return rows
```

(The raw `val_score`/`dbg_score` on each row let the FINDINGS write-up compute the
non-decisive continuous-val secondary — mean `val_score` per arm + a Mann-Whitney U on
the raw per-cell `val_score` — without new analyzer code. The pre-registered PRIMARY
remains the binary Fisher on `val_score >= 0.5`.)

- [ ] **Step 4: Thread `metric`/`alpha` through `build_tiling_report` and rewrite `_verdict`**

```python
def build_tiling_report(root, heldout_tasks, prefix="spatial", metric="dbg", alpha=0.10):
    rows = read_arm_rows(root, heldout_tasks, prefix, metric)
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    arms = {arm: _agg(by_arm[arm]) for arm in ARMS}
    pairwise = {
        "B_vs_C": _pair_p(by_arm["warm_geo"], by_arm["cold"]),
        "B_vs_A": _pair_p(by_arm["warm_geo"], by_arm["warm_dumpall"]),
        "A_vs_C": _pair_p(by_arm["warm_dumpall"], by_arm["cold"]),
    }
    by_task = {}
    for tid in heldout_tasks:
        t = f"{prefix}_{tid}"
        by_task[t] = {arm: _agg([r for r in by_arm[arm] if r["task"] == t]) for arm in ARMS}
    verdict = _verdict(arms, pairwise, alpha=alpha, metric=metric)
    return {"arms": arms, "pairwise": pairwise, "by_task": by_task,
            "rows": rows, "metric": metric, "alpha": alpha, "verdict": verdict}
```

Rewrite `_verdict` to skip empty arms and pick the present warm arm as primary:

```python
def _verdict(arms, pw, alpha=0.10, metric="dbg"):
    geo, dump, cold = arms["warm_geo"], arms["warm_dumpall"], arms["cold"]
    m = metric.upper()
    # Primary contrast: warm_geo vs cold if warm_geo ran, else warm_dumpall vs cold.
    if geo["n"] > 0:
        warm, p_primary, label = geo, pw["B_vs_C"], "warm_geo"
    else:
        warm, p_primary, label = dump, pw["A_vs_C"], "warm_dumpall"
    if warm["n"] == 0 or cold["n"] == 0:
        return f"INCONCLUSIVE ({m}): missing arm (warm n={warm['n']}, cold n={cold['n']})."
    if warm["success_rate"] > cold["success_rate"] and p_primary < alpha:
        return (f"H1 reproduced ({m}, pre-registered alpha={alpha}): {label} "
                f"{warm['success_rate']:.2f} > cold {cold['success_rate']:.2f}, "
                f"Fisher p={p_primary:.4f} < {alpha}.")
    return (f"H0 (null, {m}, alpha={alpha}): {label} {warm['success_rate']:.2f} vs "
            f"cold {cold['success_rate']:.2f}, Fisher p={p_primary:.4f} (not < {alpha}).")
```

- [ ] **Step 5: Add CLI args in `main`**

```python
    ap.add_argument("--prefix", default="spatial")
    ap.add_argument("--metric", choices=("dbg", "val"), default="dbg")
    ap.add_argument("--alpha", type=float, default=0.10)
    args = ap.parse_args()
    heldout = args.heldout.split(",")
    rep = build_tiling_report(args.root, heldout, args.prefix, args.metric, args.alpha)
```

- [ ] **Step 6: Run the new test + the existing analyzer test (stock path unchanged)**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_analyzer.py tests/aspire/test_libero_tiling_analysis.py -q -p no:anyio`
Expected: PASS (the existing 3-arm dbg tests still pass — default `metric="dbg"`, `alpha=0.10`, and when all three arms are present the primary is still `warm_geo`/`B_vs_C`).

- [ ] **Step 7: Commit**

```bash
git add scripts/analyze_libero_tiling.py tests/aspire/test_val_confirmatory_analyzer.py
git commit -m "feat(analyzer): --metric val + --alpha + absent-arm-robust primary contrast"
```

---

### Task 2: `--s-val` passthrough in the parallel runner

**Files:**
- Modify: `scripts/libero_tiling_parallel.py`
- Test: `tests/aspire/test_val_confirmatory_svalpass.py`

**Interfaces:**
- Consumes: existing `main()` globals pattern, the cmd list at the `aspire.run` build site.
- Produces: a module global `S_VAL = "100"` (default, back-compat), a `--s-val` CLI arg, use of `S_VAL` in the `aspire.run` command, and `s_val=<value>` surfaced in the campaign summary log line so `--dry` reveals it.

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_val_confirmatory_svalpass.py
import subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def test_sval_passthrough_shows_in_dry_summary():
    proc = subprocess.run(
        ["python3", "scripts/libero_tiling_parallel.py", "--dry",
         "--root", "/tmp/vc_svaltest", "--suite", "libero_10", "--tasks", "6",
         "--arms", "warm_dumpall,cold", "--reps", "1", "--t", "2",
         "--s-val", "200-204", "--library", "/tmp/nolib"],
        capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    assert "s_val=200-204" in proc.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_svalpass.py -q -p no:anyio`
Expected: FAIL (`unrecognized arguments: --s-val 200-204`)

- [ ] **Step 3: Add the global default (near the other module defaults, after `TEST_T = "2"`)**

```python
TEST_T = "2"
S_VAL = "100"          # validation seed spec passed to aspire.run --s-val (override for val campaigns)
```

- [ ] **Step 4: Register the CLI arg and bind the global in `main`**

Add `S_VAL` to the `global` line, and add the argument next to `--t`:

```python
    global ROOT, CFGDIR, TILED_LIB, XYDIR, SUITE, PREFIX, HELDOUT_TASKS, REPEATS, ARMS, TEST_T, S_VAL
    ...
    ap.add_argument("--s-val", default=S_VAL, help="aspire.run --s-val seed spec (e.g. 200-204)")
    ...
    args = ap.parse_args()
    ...
    S_VAL = args.s_val
```

(place `S_VAL = args.s_val` alongside the other `GLOBAL = args.X` assignments in `main`.)

- [ ] **Step 5: Use `S_VAL` in the command and surface it in the summary log**

At the `aspire.run` cmd build site, replace the hardcoded `"--s-val", "100"`:

```python
           "--library", str(cell["lib"]), "--s-dbg", "0", "--s-val", S_VAL,
           "--t", TEST_T]
```

In the campaign summary `log(...)` line in `main` (currently `f"campaign: root={ROOT} suite={SUITE} prefix={PREFIX} ..."`), append `s_val={S_VAL}`:

```python
    log(f"campaign: root={ROOT} suite={SUITE} prefix={PREFIX} "
        f"tasks={HELDOUT_TASKS} reps={REPEATS} arms={ARMS} t={TEST_T} s_val={S_VAL} lib={TILED_LIB}")
```

- [ ] **Step 6: Run the test + a dry run of the 3-arm default (back-compat)**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_svalpass.py -q -p no:anyio`
Expected: PASS.
Run: `python3 scripts/libero_tiling_parallel.py --dry --root /tmp/vc_bc 2>&1 | grep -o 's_val=100'`
Expected: prints `s_val=100` (default unchanged).

- [ ] **Step 7: Commit**

```bash
git add scripts/libero_tiling_parallel.py tests/aspire/test_val_confirmatory_svalpass.py
git commit -m "feat(runner): --s-val passthrough (default 100); surfaced in dry summary"
```

---

### Task 3: `val_confirmatory_select.py` — pure overfit-band selection

**Files:**
- Create: `scripts/val_confirmatory_select.py`
- Test: `tests/aspire/test_val_confirmatory_select.py`

**Interfaces:**
- Produces: `select(candidates, dbg_min=0.6, val_max=0.2, need=2) -> dict` where `candidates` is a list of `{"task": str, "suite": str, "cold_dbg_rate": float, "cold_val_rate": float}`. Returns `{"selected": [task,...], "audit": [{task, suite, cold_dbg_rate, cold_val_rate, keep: bool, reason: str}], "sufficient": bool}`. A task is kept iff `cold_dbg_rate >= dbg_min AND cold_val_rate <= val_max`; `sufficient = len(selected) >= need`.

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_val_confirmatory_select.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from val_confirmatory_select import select


def _c(task, dbg, val, suite="libero_10"):
    return {"task": task, "suite": suite, "cold_dbg_rate": dbg, "cold_val_rate": val}


def test_keeps_overfit_band_drops_floor_and_ceiling():
    cands = [_c("10_1", 0.8, 0.1),   # overfit band -> keep
             _c("10_2", 0.3, 0.0),   # floor (dbg<0.6) -> drop
             _c("10_4", 0.9, 0.6),   # ceiling (val>0.2) -> drop
             _c("10_5", 0.6, 0.2)]   # boundary inclusive -> keep
    out = select(cands)
    assert out["selected"] == ["10_1", "10_5"]
    assert out["sufficient"] is True
    reasons = {a["task"]: a["keep"] for a in out["audit"]}
    assert reasons == {"10_1": True, "10_2": False, "10_4": False, "10_5": True}


def test_insufficient_when_fewer_than_two():
    out = select([_c("10_1", 0.8, 0.1), _c("10_2", 0.2, 0.0)])
    assert out["selected"] == ["10_1"]
    assert out["sufficient"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_select.py -q -p no:anyio`
Expected: FAIL (`ModuleNotFoundError: No module named 'val_confirmatory_select'`)

- [ ] **Step 3: Implement `scripts/val_confirmatory_select.py`**

```python
#!/usr/bin/env python3
"""Pure selection for the val-confirmatory campaign: keep tasks in the frozen
overfit band (cold solves the debug seed but not held-out validation)."""
import argparse, json, sys
from pathlib import Path


def select(candidates, dbg_min=0.6, val_max=0.2, need=2):
    audit, selected = [], []
    for c in candidates:
        keep = c["cold_dbg_rate"] >= dbg_min and c["cold_val_rate"] <= val_max
        if keep:
            selected.append(c["task"])
            reason = f"overfit band (dbg {c['cold_dbg_rate']:.2f}>={dbg_min}, val {c['cold_val_rate']:.2f}<={val_max})"
        elif c["cold_dbg_rate"] < dbg_min:
            reason = f"floor (dbg {c['cold_dbg_rate']:.2f}<{dbg_min})"
        else:
            reason = f"ceiling (val {c['cold_val_rate']:.2f}>{val_max})"
        audit.append({**c, "keep": keep, "reason": reason})
    return {"selected": selected, "audit": audit, "sufficient": len(selected) >= need}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, help="path to candidates JSON list")
    ap.add_argument("--out", required=True, help="path to write selection result JSON")
    args = ap.parse_args()
    cands = json.loads(Path(args.candidates).read_text())
    res = select(cands)
    Path(args.out).write_text(json.dumps(res, indent=1))
    for a in res["audit"]:
        print(f"  {a['task']:<10} {'KEEP' if a['keep'] else 'drop':<4}  {a['reason']}")
    print(f"selected {res['selected']} (sufficient={res['sufficient']})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_select.py -q -p no:anyio`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/val_confirmatory_select.py tests/aspire/test_val_confirmatory_select.py
git commit -m "feat: pure overfit-band task selection for val-confirmatory campaign"
```

---

### Task 4: `val_confirmatory_campaign.sh` runner + pre-registration + dry test

**Files:**
- Create: `scripts/val_confirmatory_campaign.sh`
- Create: `runs/2026-07-26-val-confirmatory/PREREGISTRATION.md`
- Test: `tests/aspire/test_val_confirmatory_runner_dryrun.py`

**Interfaces:**
- Consumes: `scripts/libero_tiling_parallel.py` (`--s-val`, `--arms`, `--reps`, `--t`, `--suite`, `--tasks`, `--library`, `--no-analyze`), `scripts/val_confirmatory_select.py`, `scripts/analyze_libero_tiling.py` (`--metric val --alpha 0.05`), reused cold summaries under `~/aspire_runs/libero_tiling` and `~/aspire_runs/libero_hard`.
- Produces: an idempotent, `DRY=1`-safe runner writing `selected_tasks.json`, `selection.md`, and (post-run) `results.json`.

- [ ] **Step 1: Write `runs/2026-07-26-val-confirmatory/PREREGISTRATION.md`**

```markdown
# Pre-registration — val-confirmatory campaign (frozen 2026-07-26)

Committed BEFORE any test run; its git hash is logged by the runner at Phase 0.

- Primary metric: val_score over held-out seeds 200-204 (debug seed 0); val-solved = val_score >= 0.5.
- Arms: warm_dumpall (library = ~/aspire_runs/libero_tiling/tiled_library, frozen) vs cold.
- Test budget: t=2. N: 10 reps/arm/task.
- Candidate pool: spatial {3,6,8} + libero_10 {0..9}.
- Selection rule (overfit band): cold dbg-rate >= 0.6 AND cold val-rate <= 0.2; >=2 selected or stop.
- Decision: H1 iff warm_dumpall val-rate > cold val-rate AND Fisher p < 0.05; else H0.
- Secondary (non-decisive): dbg contrast; continuous mean val_score + Mann-Whitney.
- Known limitation: reused cold data (spatial 3,6,8; libero_10 0,3,6) estimated val on the prior
  single seed 100; freshly probed tasks use 200-204. Affects only the coarse selection filter, not
  the test (which re-measures both arms on 200-204).
```

- [ ] **Step 2: Write the failing dry-run test**

```python
# tests/aspire/test_val_confirmatory_runner_dryrun.py
import subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_lists_phases_and_pinned_params():
    proc = subprocess.run(["bash", "scripts/val_confirmatory_campaign.sh"],
                          capture_output=True, text=True, cwd=REPO,
                          env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
                               "ROOT": "/tmp/val_confirm_dry"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for tok in ("PHASE 0", "PHASE 1", "PHASE 2", "PHASE 3",
                ".venv-libero", "env -u ANTHROPIC_API_KEY", "--t 2", "--s-val 200-204",
                "warm_dumpall,cold", "--metric val", "--alpha 0.05",
                "PREREGISTRATION", "before any test run"):
        assert tok in out, f"missing {tok}"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_runner_dryrun.py -q -p no:anyio`
Expected: FAIL (`No such file or directory: scripts/val_confirmatory_campaign.sh`)

- [ ] **Step 4: Implement `scripts/val_confirmatory_campaign.sh`**

```bash
#!/bin/bash
# Val-pre-registered confirmatory campaign
# (spec: docs/superpowers/specs/2026-07-26-val-confirmatory-design.md).
# Primary metric = held-out val_score (seeds 200-204). warm_dumpall vs cold on a
# mechanistically-selected overfit-band task set. Reuses the tiled library + parallel
# runner. Subscription billing. DRY=1 prints the plan. Idempotent via DONE markers.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
PAR="$REPO/scripts/libero_tiling_parallel.py"
SEL="$REPO/scripts/val_confirmatory_select.py"
ANALYZE="$REPO/scripts/analyze_libero_tiling.py"
LIB="$HOME/aspire_runs/libero_tiling/tiled_library"
RUNS="$REPO/runs/2026-07-26-val-confirmatory"
ROOT=${ROOT:-$HOME/aspire_runs/libero_val_confirm}
DRY=${DRY:-0}
VAL_SEEDS="200-204"; TEST_T="2"; PROBE_REPS=5; TEST_REPS=10
FRESH_10=(1 2 4 5 7 8 9)                    # libero_10 tasks never tested warm-vs-cold
REUSE_SPATIAL=(3 6 8); REUSE_10=(0 3 6)     # cold data reused from prior t=2 campaigns
mkdir -p "$ROOT"

echo "=== PHASE 0: preflight + PREREGISTRATION freeze (before any test run) ==="
if [ "$DRY" = 1 ]; then
  echo "[dry] assert .venv-libero robosuite 1.4; assert $LIB has >=2 skills"
  echo "[dry] commit $RUNS/PREREGISTRATION.md and log its git hash BEFORE any test run"
else
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite not 1.4.x"; exit 1; }
  n=$($VENV -c "from aspire.skill_library import SkillLibrary; print(len(SkillLibrary('$LIB').load_all()))" 2>/dev/null || echo 0)
  [ "$n" -ge 2 ] || { echo "FATAL: tiled library $LIB has <2 skills ($n)"; exit 1; }
  git add "$RUNS/PREREGISTRATION.md" && git commit -q -m "prereg: val-confirmatory campaign frozen" || true
  PREREG_HASH=$(git rev-parse HEAD)
  echo "PREREGISTRATION committed at $PREREG_HASH (frozen before any test run)"
fi

echo "=== PHASE 1: cold probe (fresh libero_10 ${FRESH_10[*]}) + reuse -> select overfit band ==="
# cold-rate helper: reads a glob of cold summary.json, prints "dbg_rate val_rate"
cold_rates() {  # cold_rates <glob>
  $VENV - "$@" <<'PY'
import glob,json,sys
fs=[f for g in sys.argv[1:] for f in glob.glob(g)]
d=v=n=0
for f in fs:
    try: s=json.load(open(f))
    except: continue
    n+=1
    d+= float(s.get("dbg_score",0))>=1.0
    v+= float(s.get("val_score",0))>=0.5
print(f"{(d/n if n else 0):.4f} {(v/n if n else 0):.4f}")
PY
}
if [ "$DRY" = 1 ]; then
  echo "[dry] probe cold reps=$PROBE_REPS t=$TEST_T --s-val $VAL_SEEDS on fresh libero_10 ${FRESH_10[*]}"
  echo "[dry] reuse cold summaries: spatial ${REUSE_SPATIAL[*]} (libero_tiling), libero_10 ${REUSE_10[*]} (libero_hard)"
  echo "[dry] apply val_confirmatory_select.py -> selected_tasks.json + selection.md; gate >=2 or stop"
else
  # probe fresh libero_10 tasks (cold only) into the confirmatory root
  env -u ANTHROPIC_API_KEY python3 "$PAR" --root "$ROOT" --suite libero_10 \
    --tasks "$(IFS=,; echo "${FRESH_10[*]}")" --arms cold --reps "$PROBE_REPS" \
    --t "$TEST_T" --s-val "$VAL_SEEDS" --library "$LIB" --no-analyze --jobs 4
  # build candidates JSON (reused + freshly probed)
  cand="$ROOT/candidates.json"
  {
    echo "["
    first=1
    emit() { local task=$1 suite=$2 glob=$3; read dr vr < <(cold_rates "$glob")
             [ $first = 1 ] || echo ","; first=0
             printf '{"task":"%s","suite":"%s","cold_dbg_rate":%s,"cold_val_rate":%s}' "$task" "$suite" "$dr" "$vr"; }
    for t in "${REUSE_SPATIAL[@]}"; do emit "spatial_$t" libero_spatial "$HOME/aspire_runs/libero_tiling/test/spatial_$t/cold/*/summary.json"; done
    for t in "${REUSE_10[@]}"; do emit "10_$t" libero_10 "$HOME/aspire_runs/libero_hard/test/10_$t/cold/*/summary.json"; done
    for t in "${FRESH_10[@]}"; do emit "10_$t" libero_10 "$ROOT/test/10_$t/cold/*/summary.json"; done
    echo "]"
  } > "$cand"
  $VENV "$SEL" --candidates "$cand" --out "$ROOT/selection.json" | tee "$ROOT/selection.md"
  python3 -c "import json,sys; d=json.load(open('$ROOT/selection.json')); open('$ROOT/selected_tasks.json','w').write(json.dumps(d['selected'])); sys.exit(0 if d['sufficient'] else 3)" \
    || { echo "GATE FAIL: <2 overfit-band tasks. Stopping (honest null of selection)."; exit 3; }
fi

echo "=== PHASE 2: warm_dumpall vs cold on selected tasks (N=$TEST_REPS, t=$TEST_T, --s-val $VAL_SEEDS) ==="
if [ "$DRY" = 1 ]; then
  echo "[dry] group selected by suite; per suite: env -u ANTHROPIC_API_KEY python3 $PAR --root $ROOT --suite <suite> --tasks <ids> --arms warm_dumpall,cold --reps $TEST_REPS --t $TEST_T --s-val $VAL_SEEDS --library $LIB --no-analyze"
else
  # group selected tasks by suite (spatial_* vs 10_*) and run per suite
  sel=$(cat "$ROOT/selected_tasks.json")
  for suite in libero_spatial libero_10; do
    pfx=$([ "$suite" = libero_spatial ] && echo spatial || echo 10)
    ids=$(python3 -c "import json,sys; pfx='$pfx'; print(','.join(t.split('_',1)[1] for t in json.load(open('$ROOT/selected_tasks.json')) if t.startswith(pfx+'_')))")
    [ -z "$ids" ] && continue
    env -u ANTHROPIC_API_KEY python3 "$PAR" --root "$ROOT" --suite "$suite" \
      --tasks "$ids" --arms warm_dumpall,cold --reps "$TEST_REPS" --t "$TEST_T" \
      --s-val "$VAL_SEEDS" --library "$LIB" --no-analyze --jobs 4
  done
fi

echo "=== PHASE 3: analyze (primary metric = val, alpha=0.05) ==="
if [ "$DRY" = 1 ]; then
  echo "[dry] per suite: python3 $ANALYZE --root $ROOT --heldout <ids> --prefix <pfx> --metric val --alpha 0.05"
else
  for suite in libero_spatial libero_10; do
    pfx=$([ "$suite" = libero_spatial ] && echo spatial || echo 10)
    ids=$(python3 -c "import json; pfx='$pfx'; print(','.join(t.split('_',1)[1] for t in json.load(open('$ROOT/selected_tasks.json')) if t.startswith(pfx+'_')))")
    [ -z "$ids" ] && continue
    echo "--- suite $suite tasks $ids ---"
    python3 "$ANALYZE" --root "$ROOT" --heldout "$ids" --prefix "$pfx" --metric val --alpha 0.05
  done
fi
echo "=== VAL-CONFIRMATORY DONE root=$ROOT ==="
```

- [ ] **Step 5: Run the dry-run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_val_confirmatory_runner_dryrun.py -q -p no:anyio`
Expected: PASS. If a token is missing, adjust the echo lines until all appear.

- [ ] **Step 6: Full suite green**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS (prior 338 + all new tests).

- [ ] **Step 7: Commit**

```bash
git add scripts/val_confirmatory_campaign.sh runs/2026-07-26-val-confirmatory/PREREGISTRATION.md tests/aspire/test_val_confirmatory_runner_dryrun.py
git commit -m "feat: val-confirmatory runner (prereg freeze, probe+select, val-primary analysis)"
```

---

## Execution note (after all tasks built + committed)

Execute under the autonomous loop, NOT inside a task (long GPU + subscription run):

```bash
ROOT="$HOME/aspire_runs/libero_val_confirm" bash scripts/val_confirmatory_campaign.sh \
  > runs/2026-07-26-val-confirmatory/campaign.log 2>&1   # run_in_background
```

Pre-launch checks: robosuite 1.4.0 in `.venv-libero`; the tiled library exists with ≥2 skills; the subscription serves `claude -p` (`env -u ANTHROPIC_API_KEY claude -p "SUBOK" --model sonnet`). **Because billing is the Max subscription, watch for rate-limit stalls** (the parallel runner's `--jobs 4` may need dropping to `--jobs 1-2` if calls start failing). The pre-registration commit MUST land before Phase 2. Drive the loop: on completion apply the pre-registered p<0.05 decision, write `results.json` + `FINDINGS.md`, commit, and ping only at the terminal state with the actual val Fisher p.
```
