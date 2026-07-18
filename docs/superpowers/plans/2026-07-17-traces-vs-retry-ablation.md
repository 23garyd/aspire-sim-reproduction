# Traces-vs-retry Ablation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ablate_traces` mode that runs the ASPIRE repair loop with the actor's per-primitive traces replaced by a scalar reward, so a trace-vs-retry A/B campaign on `two_arm_lift` can test whether traces are causally responsible for the repair gains.

**Architecture:** The ablation is entirely about *what context the repair actor sees*. A single config flag (`RunConfig.ablate_traces`) fans out to four touch points: (1) `write_execution_context` writes a scalar `outcome.txt` instead of `traces/`; (2) `replay.py` prints only the score; (3) the CLI selects a trace-blind repair prompt; (4) evosearch is disabled (`t=0`) so the comparison isolates the repair actor. The engine still produces full traces internally — only the actor-facing surface changes — so records, winner bundles, and extraction are unaffected and symmetric across arms.

**Tech Stack:** Python 3 (stdlib only for `capx_execute.py`/`replay.py`), pytest (`-p no:anyio` on simhost), bash launcher, Claude Code headless actors.

## Global Constraints

- `capx_execute.py` and `aspire/replay.py` must stay **stdlib-only** (they run in the cap-x venv / any venv).
- Config parameters are `[RECONSTRUCTED]` and **must be logged per run** — `RunConfig.to_dict()` is emitted on the CLI's JSON result line; every new field rides along automatically.
- Tests run with `python3 -m pytest tests/ -q -p no:anyio` (the `-p no:anyio` flag is required on simhost).
- Frozen dataclass `RunConfig`: **never** construct it positionally; new fields go before `s_dbg`/`s_val` only if all construction is keyword-based (it is — verified).
- Follow the existing `admission_min_val` precedent (commit `f306e65`) for a config-flag + CLI-override + coordinator-gate feature.
- The ablation must change **only** the actor-facing surface: engine-internal traces, `winner/` bundles, and extraction stay identical across arms (symmetric ⇒ no confound).
- Both A/B arms run with evosearch OFF (`t=0`); the single manipulated variable is `ablate_traces`.

---

### Task 1: Config flag `RunConfig.ablate_traces`

**Files:**
- Modify: `aspire/config.py`
- Test: `tests/aspire/test_config.py`

**Interfaces:**
- Produces: `RunConfig.ablate_traces: bool = False`, surfaced in `RunConfig().to_dict()["ablate_traces"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/aspire/test_config.py` (create the file if absent, with `from aspire.config import RunConfig` at top):

```python
def test_ablate_traces_defaults_false_and_is_logged():
    cfg = RunConfig()
    assert cfg.ablate_traces is False
    assert cfg.to_dict()["ablate_traces"] is False
    assert RunConfig(ablate_traces=True).ablate_traces is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_config.py::test_ablate_traces_defaults_false_and_is_logged -q -p no:anyio`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'ablate_traces'`

- [ ] **Step 3: Write minimal implementation**

In `aspire/config.py`, add the field immediately after `admission_min_val` (before `s_dbg`):

```python
    ablate_traces: bool = False   # [RECONSTRUCTED] ablation: when True the repair
                                  # actor sees a scalar reward (outcome.txt / scalar
                                  # replay) instead of per-primitive traces. Used to
                                  # test whether traces are causal. Does NOT change
                                  # engine-internal traces, winner/ bundles, or extraction.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_config.py::test_ablate_traces_defaults_false_and_is_logged -q -p no:anyio`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aspire/config.py tests/aspire/test_config.py
git commit -m "feat(aspire): RunConfig.ablate_traces flag (trace-vs-retry ablation)"
```

---

### Task 2: Scalar `outcome.txt` in `write_execution_context`

**Files:**
- Modify: `aspire/task_context.py:26` (`write_execution_context`)
- Test: `tests/aspire/test_task_context.py`

**Interfaces:**
- Consumes: `ExecuteResult` (`.score: float`, `.traces: tuple`, `.raw_dir: str`).
- Produces: `write_execution_context(task_dir, result, ablate_traces: bool = False) -> None`. When `ablate_traces=True`, writes `task_dir/outcome.txt` (single line `score: <float>`) and writes **no** `traces/` directory. When `False`, behaviour is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/aspire/test_task_context.py` (create with imports `from pathlib import Path`, `from aspire.task_context import write_execution_context`, `from aspire.schemas import ExecuteResult, TraceRecord` if absent):

```python
def test_ablate_traces_writes_scalar_outcome_no_traces(tmp_path):
    tr = TraceRecord(step=0, function="grasp", args={}, status="error",
                     result_summary="PLANNING_ERROR", duration_ms=1.0, media=[])
    result = ExecuteResult(0.3333333333333333, traces=[tr])
    write_execution_context(tmp_path, result, ablate_traces=True)
    assert (tmp_path / "outcome.txt").read_text().strip() == "score: 0.3333333333333333"
    assert not (tmp_path / "traces").exists()          # no per-primitive leak
    assert "PLANNING_ERROR" not in (tmp_path / "outcome.txt").read_text()

def test_default_still_writes_full_traces(tmp_path):
    tr = TraceRecord(step=0, function="grasp", args={}, status="error",
                     result_summary="PLANNING_ERROR", duration_ms=1.0, media=[])
    write_execution_context(tmp_path, ExecuteResult(0.0, traces=[tr]))
    assert (tmp_path / "traces" / "trace.json").exists()
    assert "PLANNING_ERROR" in (tmp_path / "traces" / "summary.txt").read_text()
    assert not (tmp_path / "outcome.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_task_context.py -q -p no:anyio -k ablate_traces_writes or default_still`
Expected: FAIL — `TypeError: write_execution_context() got an unexpected keyword argument 'ablate_traces'`

- [ ] **Step 3: Write minimal implementation**

Replace the head of `write_execution_context` in `aspire/task_context.py`:

```python
def write_execution_context(task_dir, result, ablate_traces: bool = False) -> None:
    task_dir = Path(task_dir)
    if ablate_traces:
        # Ablation: the repair actor sees ONLY the scalar reward, never per-primitive
        # traces. Per-seed granularity is still reachable via scalar replay (replay.py
        # prints the seed's score under the same ablation flag).
        (task_dir / "outcome.txt").write_text(f"score: {result.score}\n")
        return
    traces_dir = task_dir / "traces"
    media_dir = traces_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    # ... (rest of the existing function body unchanged) ...
```

Keep every existing line below `media_dir.mkdir(...)` exactly as-is.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_task_context.py -q -p no:anyio -k ablate_traces_writes or default_still`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add aspire/task_context.py tests/aspire/test_task_context.py
git commit -m "feat(aspire): scalar outcome.txt when ablate_traces (no per-primitive leak)"
```

---

### Task 3: Coordinator wiring — scalar context, ablation flag in replay.json, evosearch off at t=0

**Files:**
- Modify: `aspire/coordinator.py` (calls to `write_execution_context`; `_materialize_replay`; evosearch guard)
- Test: `tests/aspire/test_coordinator.py`

**Interfaces:**
- Consumes: `RunConfig.ablate_traces`, `RunConfig.t`.
- Produces: coordinator passes `ablate_traces=self.cfg.ablate_traces` to all `write_execution_context` calls; `replay.json` gains `"ablate_traces": <bool>`; evosearch fallback runs only when `self.cfg.t > 0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/aspire/test_coordinator.py`:

```python
def test_t_zero_disables_evosearch(tmp_path):
    # dbg never reaches theta; with t=0 evosearch must NOT run — the debug-best
    # program goes straight to validation. FakeEngine scripts exactly: S0, one
    # failing fix, then S_val. A 4th engine call (evo) would raise (list exhausted).
    task = _task(tmp_path)
    cfg = RunConfig(k=2, t=0, theta=1.0, debug_rounds=1, s_dbg=[0, 1],
                    s_val=[100, 101])
    engine = FakeEngine([ExecuteResult(0.0),   # Stage 0
                         ExecuteResult(0.5),   # fix, still < theta
                         ExecuteResult(0.9)])  # Stage 2 (proves no evosearch calls between)
    (task / "fix_code.py").write_text("still_bad()")
    actor = FakeActor(reports=[_skillful_report()],
                      extraction_reports=[_extraction_report()])
    lib = SkillLibrary(tmp_path / "lib")
    result = TaskPipeline(task, engine, actor, FakeJudge([True, True]), lib, cfg).run()
    assert result.val_score == 0.9
    assert not (task / "evosearch_best_score.json").exists()

def test_ablate_traces_writes_scalar_context_and_replay_flag(tmp_path):
    task = _task(tmp_path)
    cfg = RunConfig(k=2, t=0, theta=1.0, debug_rounds=1, s_dbg=[0, 1],
                    s_val=[100, 101], ablate_traces=True)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(0.9), ExecuteResult(0.9)])
    (task / "fix_code.py").write_text("clean_fix()")
    actor = FakeActor(reports=[_skillful_report()],
                      extraction_reports=[_extraction_report()])
    lib = SkillLibrary(tmp_path / "lib")
    TaskPipeline(task, engine, actor, FakeJudge([True, True]), lib, cfg).run()
    assert (task / "outcome.txt").exists()
    assert not (task / "traces").exists()
    replay_recipe = json.loads((task / "replay.json").read_text())
    assert replay_recipe["ablate_traces"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/aspire/test_coordinator.py -q -p no:anyio -k "t_zero_disables or ablate_traces_writes_scalar_context"`
Expected: FAIL — `test_t_zero_disables_evosearch` fails because evosearch runs and exhausts the engine list; `test_ablate_traces_writes_scalar_context_and_replay_flag` fails on missing `outcome.txt` / missing `ablate_traces` key.

- [ ] **Step 3: Write minimal implementation**

In `aspire/coordinator.py`:

(a) In `_materialize_replay`, add the flag to the `replay.json` payload:

```python
        _atomic_write(self.task_dir / "replay.json", json.dumps(
            {"engine": recipe, "s_dbg": list(self.cfg.s_dbg),
             "max_attempts_per_seed": self.cfg.max_seed_attempts,
             "ablate_traces": self.cfg.ablate_traces}, indent=1))
```

(b) Pass `ablate_traces` to both `write_execution_context` call sites — `aspire/coordinator.py:170` (initial, after Stage-0) and `:194` (refresh at the end of each debug round). Each currently reads `write_execution_context(self.task_dir, r)`; change both to:

```python
        write_execution_context(self.task_dir, r,
                                ablate_traces=self.cfg.ablate_traces)
```

(c) Guard the evosearch fallback on `t > 0`:

```python
        evosearch_ran = False
        if self.cfg.t > 0 and dbg_score < self.cfg.theta:   # evosearch fallback
            evosearch_ran = True
            best = evosearch(self.task_dir, self.engine, self.actor, self.cfg,
                             skills=relevant_skills(self.library, latest.traces))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/aspire/test_coordinator.py -q -p no:anyio -k "t_zero_disables or ablate_traces_writes_scalar_context"`
Expected: PASS (both)

- [ ] **Step 5: Run the full coordinator suite (guard against regressions)**

Run: `python3 -m pytest tests/aspire/test_coordinator.py -q -p no:anyio`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add aspire/coordinator.py tests/aspire/test_coordinator.py
git commit -m "feat(aspire): coordinator wiring for ablate_traces + t=0 evosearch guard"
```

---

### Task 4: Scalar-only `replay.py`

**Files:**
- Modify: `aspire/replay.py` (read `ablate_traces` from recipe; scalar-only output path)
- Test: `tests/aspire/test_replay.py`

**Interfaces:**
- Consumes: `replay.json` key `ablate_traces` (bool, default False).
- Produces: when `ablate_traces=True`, `replay.py` prints exactly `score: <float>` to stdout and writes **no** `trace.json`, `summary.txt`, or `media/` in the attempt dir; exit code and attempt-counter semantics unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/aspire/test_replay.py` (reuse the file's existing fixtures for building a `replay.json` with a fake-engine recipe; model the new test on the nearest existing "successful replay" test). Minimal shape:

```python
def test_ablated_replay_prints_score_only(tmp_path, monkeypatch):
    # Build a fake replay.json with ablate_traces=True and a fake engine recipe that
    # scores seed 0 = 1.0. (Mirror the recipe construction of the existing
    # happy-path replay test in this file.)
    recipe = _fake_replay_json(tmp_path, scores=[1.0], s_dbg=[0],
                               ablate_traces=True)   # helper analogous to existing tests
    (tmp_path / "code.py").write_text("pass")
    rc = replay_main(["code.py", "0"], cwd=tmp_path)   # match this file's invocation style
    assert rc == 0
    out = _last_stdout()                               # match this file's capture style
    assert out.strip() == "score: 1.0"
    attempt = tmp_path / "replays" / "seed0_attempt1"
    assert not (attempt / "trace.json").exists()
    assert not (attempt / "summary.txt").exists()
    assert not (attempt / "media").exists()
```

If `test_replay.py` has no `_fake_replay_json`/`_last_stdout` helpers, follow the exact construction and capture pattern the existing passing tests in that file use; only add `"ablate_traces": True` to the written `replay.json`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_replay.py -q -p no:anyio -k ablated_replay_prints_score_only`
Expected: FAIL — trace files still written / stdout includes the trace summary.

- [ ] **Step 3: Write minimal implementation**

In `aspire/replay.py`, read the flag just after `recipe = json.loads(recipe_path.read_text())` (line ~71); the parsed `replay.json` dict is named `recipe` in this file:

```python
    ablate_traces = bool(recipe.get("ablate_traces", False))
```

Then replace the output block (currently lines ~138-159, from `media_dir = out / "media"` through `return 0`) with:

```python
    if ablate_traces:
        # Ablation: scalar feedback only — no per-primitive trace, summary, or media.
        print(f"score: {result.score}")
        return 0

    media_dir = out / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(out / "trace.json",
                 json.dumps([t.to_dict() for t in result.traces], indent=1))
    summary = summarize_traces(result.traces)
    _atomic_write(out / "summary.txt", summary)

    raw_dir = Path(result.raw_dir) if result.raw_dir else None
    for t in result.traces:
        for m in t.media:
            if raw_dir is None:
                continue
            src = raw_dir / m
            if not src.exists():
                continue
            dst = media_dir / m
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())

    print(f"score: {result.score}")
    print(summary)
    return 0
```

(`recipe` is the dict already parsed from `replay.json` at line ~71.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_replay.py -q -p no:anyio`
Expected: PASS (new test + all existing replay tests)

- [ ] **Step 5: Commit**

```bash
git add aspire/replay.py tests/aspire/test_replay.py
git commit -m "feat(aspire): scalar-only replay output under ablate_traces"
```

---

### Task 5: Trace-blind repair prompt

**Files:**
- Create: `prompts/actor_debug_blind.md`
- Test: `tests/aspire/test_prompts.py`

**Interfaces:**
- Produces: a repair prompt that yields the SAME output contract as `actor_debug.md` (writes `fix_code.py` + `report.json`/`ActorReport`) but instructs the actor from `outcome.txt` (scalar) + scalar `./replay`, never from `traces/`.

- [ ] **Step 1: Write the failing test**

Append to `tests/aspire/test_prompts.py`:

```python
from pathlib import Path

def test_blind_debug_prompt_is_trace_free_but_keeps_contract():
    text = Path("prompts/actor_debug_blind.md").read_text()
    low = text.lower()
    # keeps the output contract
    assert "fix_code.py" in text
    assert "report.json" in text
    # references the scalar surface, not the trace surface
    assert "outcome.txt" in text
    assert "traces/" not in text
    assert "summary.txt" not in text
    assert "keyframe" not in low and "trace.json" not in low
    # still allows the (scalar) replay affordance
    assert "./replay" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_prompts.py::test_blind_debug_prompt_is_trace_free_but_keeps_contract -q -p no:anyio`
Expected: FAIL — `FileNotFoundError: prompts/actor_debug_blind.md`

- [ ] **Step 3: Write the prompt**

Create `prompts/actor_debug_blind.md`. Base it on `actor_debug.md` (open it for the exact `report.json`/`ActorReport` field contract and copy that section verbatim), but replace all trace-facing guidance. Content:

```markdown
# Repair task (reward-only / trace-blind)

You are repairing a robot control program. Your program is `code.py` in this
directory. It currently fails some of the debugging seeds.

## What you can see

- `code.py` — the current program.
- `outcome.txt` — a single line `score: <float>`: the fraction of debugging seeds
  the current program passes (0.0 = all fail, 1.0 = all pass). This is your ONLY
  feedback on the program's behaviour. There are no execution traces, images, or
  per-step diagnostics available for this task.
- `skills.md` — any retrieved library skills (may be empty).
- `task.md` — the task identity.

## The replay affordance (reward-only)

You may test a candidate program on a single debugging seed:

    ./replay <program_path> <seed>

It prints one line, `score: <float>`, for that seed and nothing else. You have a
bounded number of replays per seed (over-use is audited). Use them to check
whether a change helps, judging only by the returned score.

## What to do

1. Reason about likely failure causes from the program text and the scalar score.
2. Write your fixed program to `fix_code.py`. It must generalise across seeds
   (no per-seed branching — that is audited and rejected).
3. Write `report.json` with the ActorReport fields exactly as specified below
   (copy the field list and format verbatim from actor_debug.md: outcome,
   diagnosis, code_path, seed_attempts, proposed_skills).

Do not attempt to read, reconstruct, or fabricate execution traces — none exist
for this run. Base every decision on the scalar score alone.
```

When writing, open `prompts/actor_debug.md`, copy its exact `report.json`/ActorReport field specification into step 3 so the contract matches byte-for-byte.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_prompts.py::test_blind_debug_prompt_is_trace_free_but_keeps_contract -q -p no:anyio`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add prompts/actor_debug_blind.md tests/aspire/test_prompts.py
git commit -m "feat(prompts): trace-blind repair prompt (reward-only actor)"
```

---

### Task 6: CLI `--ablate-traces` and `--t`; blind-prompt selection

**Files:**
- Modify: `aspire/run.py` (argparse flags; override wiring; `_build_capx_actors` blind-prompt branch)
- Test: `tests/aspire/test_run.py`

**Interfaces:**
- Consumes: `RunConfig.ablate_traces`, `RunConfig.t`.
- Produces: CLI flags `--ablate-traces` (store_true) and `--t INT`; when `--ablate-traces` is set, `_build_capx_actors` builds `ClaudeCodeActor` with `prompt_file="{prompts}/actor_debug_blind.md"`. Both flags reach `cfg` and appear in the logged config.

- [ ] **Step 1: Write the failing test**

Append to `tests/aspire/test_run.py` (fake engine, no GPU):

```python
def test_cli_ablate_traces_and_t_reach_config(tmp_path):
    task = tmp_path / "robosuite" / "lift"
    task.mkdir(parents=True); (task / "code.py").write_text("pass")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "fake", "--fake-scores", "1.0,0.9",
         "--library", str(tmp_path / "lib"),
         "--ablate-traces", "--t", "0"],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["config"]["ablate_traces"] is True
    assert summary["config"]["t"] == 0
```

Also add a fast unit test that `_build_capx_actors` picks the blind prompt (import it directly):

```python
def test_build_actors_uses_blind_prompt_when_ablated():
    from aspire.run import _build_capx_actors
    actor, _ = _build_capx_actors("prompts", ".", ablate_traces=True)
    assert actor._prompt_file.endswith("actor_debug_blind.md")
    actor2, _ = _build_capx_actors("prompts", ".", ablate_traces=False)
    assert actor2._prompt_file.endswith("actor_debug.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/aspire/test_run.py -q -p no:anyio -k "ablate_traces_and_t or build_actors_uses_blind"`
Expected: FAIL — unknown CLI arg `--ablate-traces`; `_build_capx_actors()` takes no `ablate_traces` kwarg.

- [ ] **Step 3: Write minimal implementation**

In `aspire/run.py`:

(a) Add flags next to `--admission-min-val`:

```python
    ap.add_argument("--ablate-traces", action="store_true",
                    help="repair actor sees a scalar reward instead of traces "
                         "(trace-vs-retry ablation)")
    ap.add_argument("--t", type=int, default=None,
                    help="override RunConfig.t (evosearch max rounds; 0 disables evosearch)")
```

(b) Wire overrides (next to the `admission_min_val` block):

```python
    if args.t is not None:
        overrides["t"] = args.t
    if args.ablate_traces:
        overrides["ablate_traces"] = True
```

(c) Change `_build_capx_actors` to accept and act on the flag:

```python
def _build_capx_actors(prompts_dir: str, task_dir, ablate_traces: bool = False):
    """Actor: debug prompt for run_debug, evosearch prompt for propose.
    Under ablate_traces the debug prompt is the trace-blind (reward-only) variant."""
    debug_prompt = ("actor_debug_blind.md" if ablate_traces else "actor_debug.md")
    actor = ClaudeCodeActor(
        prompt_file=f"{prompts_dir}/{debug_prompt}",
        propose_prompt_file=f"{prompts_dir}/actor_evosearch.md",
        extract_prompt_file=f"{prompts_dir}/extract_patterns.md")
    judge = ClaudeJudge(prompt_file=f"{prompts_dir}/coordinator_admission.md",
                        workdir=Path(task_dir))
    return actor, judge
```

(d) Update both `_build_capx_actors(...)` call sites (single-task path near line 208, campaign path near line 139) to pass `cfg.ablate_traces`:

```python
            actor, judge = _build_capx_actors(args.prompts, task_dir,
                                              ablate_traces=cfg.ablate_traces)
```
```python
        actor, judge = _build_capx_actors(args.prompts, args.task_dir,
                                          ablate_traces=cfg.ablate_traces)
```

(Confirm `cfg` is in scope at each call site; it is constructed before both dispatch branches.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/aspire/test_run.py -q -p no:anyio -k "ablate_traces_and_t or build_actors_uses_blind"`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add aspire/run.py tests/aspire/test_run.py
git commit -m "feat(aspire): CLI --ablate-traces/--t; select blind prompt when ablated"
```

---

### Task 7: A/B campaign launcher

**Files:**
- Create: `scripts/traces_ablation.sh`
- Create: `~/start_traces_ablation.sh` (detached launcher, NOT in repo)

**Interfaces:**
- Produces: a script that runs `N` isolated repeats of arm T (traces) and arm C (`--ablate-traces`), both with `--t 0`, on `two_arm_lift`, into `~/aspire_runs/traces_ablation/{T,C}/rep_NN/`, logging to `campaign.log`. Idempotent/resumable (skip a repeat whose task dir has `VALIDATION_DONE`).

- [ ] **Step 1: Write the launcher**

Create `scripts/traces_ablation.sh` (model exactly on `scripts/lift_repeats.sh`):

```bash
#!/bin/bash
# Traces-vs-retry ablation A/B campaign on two_arm_lift. Two arms, single manipulated
# variable: arm T sees traces, arm C is --ablate-traces. Both run --t 0 (evosearch off,
# Stage-1 repair only) so the comparison isolates the repair actor. Spec:
# docs/superpowers/specs/2026-07-17-traces-vs-retry-ablation-design.md
set -u
cd "$(dirname "$0")/.."

N=${N:-8}
ROOT=${ROOT:-$HOME/aspire_runs/traces_ablation}
BASELINE=$HOME/aspire_runs/m1_baseline/claude-opus-4-8/two_arm_lift/trial_01_sandboxrc_0_reward_0.026_taskcompleted_0/code.py
CFG=/home/demo/cap-x/env_configs/two_arm_lift/franka_robosuite_two_arm_lift_privileged.yaml
CAPX_CMD="/home/demo/cap-x/.venv/bin/python $PWD/scripts/capx_execute.py --workdir /home/demo/cap-x --config-path $CFG"

[ -f "$BASELINE" ] || { echo "FATAL: baseline missing: $BASELINE"; exit 1; }
mkdir -p "$ROOT"

run_arm() {           # $1 = arm label (T|C), $2 = extra aspire.run flags
  local arm="$1" extra="$2"
  for i in $(seq -w 1 "$N"); do
    local rep="$ROOT/$arm/rep_$i" task="$ROOT/$arm/rep_$i/robosuite/two_arm_lift"
    echo "=== ABLATION arm=$arm rep=$i/$N $(date -u +%FT%TZ) ==="
    if [ -f "$task/VALIDATION_DONE" ]; then echo "=== $arm/rep_$i done, skip ==="; continue; fi
    if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:8110/; then
      echo "=== $arm/rep_$i SKIPPED: LLM proxy :8110 down ==="; continue; fi
    mkdir -p "$task" "$rep/skill_library" "$rep/exec"
    cp "$BASELINE" "$task/code.py"
    MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
      --task-dir "$task" --engine capx --capx-cmd "$CAPX_CMD" \
      --out-root "$rep/exec" --library "$rep/skill_library" \
      --s-val 100-119 --t 0 $extra
    echo "=== $arm/rep_$i exit=$? ==="
  done
}

run_arm T ""
run_arm C "--ablate-traces"
echo "=== ABLATION DONE $(date -u +%FT%TZ) ==="
```

Create `~/start_traces_ablation.sh` (mirror `~/start_lift_repeats.sh`, pidfile `/tmp/traces_ablation.pid`, log `~/aspire_runs/traces_ablation/campaign.log`).

- [ ] **Step 2: Syntax-check both scripts**

Run: `bash -n scripts/traces_ablation.sh && bash -n ~/start_traces_ablation.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Dry-run structural check (no spend)**

Run: `N=1 ROOT=/tmp/ablation_dry bash -c 'grep -q "\-\-ablate-traces" scripts/traces_ablation.sh && grep -q "\-\-t 0" scripts/traces_ablation.sh && echo WIRED'`
Expected: `WIRED` (confirms both arms differ only by `--ablate-traces` and both pass `--t 0`)

- [ ] **Step 4: Commit (repo script only)**

```bash
chmod +x scripts/traces_ablation.sh
git add scripts/traces_ablation.sh
git commit -m "scripts: traces-vs-retry A/B campaign launcher (two_arm_lift, --t 0 both arms)"
```

---

### Task 8: Pre-registered analysis helper

**Files:**
- Create: `scripts/analyze_ablation.py`
- Test: `tests/aspire/test_analyze_ablation.py`

**Interfaces:**
- Produces: `mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]` returning `(U, z)` (rank-sum U for sample `a` vs `b`, with tie-corrected normal-approx `z`); and a `main()` that reads the two arms' `VALIDATION_DONE` scores from a `traces_ablation/` tree and prints per-arm mean/median, `U`, `z`, and `P(val>=0.80)` for each arm. Stdlib only (no scipy).

- [ ] **Step 1: Write the failing test**

Create `tests/aspire/test_analyze_ablation.py`:

```python
from scripts.analyze_ablation import mann_whitney_u

def test_u_of_clearly_separated_samples():
    # b strictly greater than a: U for a should be 0 (no a beats any b)
    U, z = mann_whitney_u([0.0, 0.1, 0.2], [0.8, 0.9, 1.0])
    assert U == 0.0
    assert z < 0            # a ranks below b

def test_u_symmetry_and_midranks():
    # identical samples: U = n*m/2, z = 0
    U, z = mann_whitney_u([0.5, 0.5], [0.5, 0.5])
    assert U == 2.0         # n*m/2 = 2*2/2
    assert abs(z) < 1e-9
```

(Ensure `scripts/__init__.py` exists so `scripts.analyze_ablation` imports; create an empty one if needed and `git add` it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_analyze_ablation.py -q -p no:anyio`
Expected: FAIL — `ModuleNotFoundError: scripts.analyze_ablation`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/analyze_ablation.py`:

```python
#!/usr/bin/env python3
"""Pre-registered analysis for the traces-vs-retry ablation. Reads per-arm held-out
validation scores and reports mean/median, P(val>=0.80), and a rank-sum Mann-Whitney
U with tie-corrected normal-approximation z. Stdlib only. The decision rule is fixed
BEFORE the campaign runs; this script is run identically whichever way the data falls.
"""
import json
import math
import sys
from pathlib import Path


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based mid-rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def mann_whitney_u(a, b):
    """Return (U_a, z). U_a = rank-sum U for sample a vs b; z = tie-corrected
    normal approximation (negative when a tends below b)."""
    n, m = len(a), len(b)
    ranks = _ranks(list(a) + list(b))
    r_a = sum(ranks[:n])
    u_a = r_a - n * (n + 1) / 2
    mu = n * m / 2
    # tie-corrected variance
    all_vals = list(a) + list(b)
    counts = {}
    for v in all_vals:
        counts[v] = counts.get(v, 0) + 1
    tie = sum(t**3 - t for t in counts.values())
    N = n + m
    var = (n * m / 12) * ((N + 1) - tie / (N * (N - 1))) if N > 1 else 0.0
    z = (u_a - mu) / math.sqrt(var) if var > 0 else 0.0
    return u_a, z


def _arm_scores(arm_dir: Path):
    scores = []
    for done in sorted(arm_dir.glob("rep_*/robosuite/two_arm_lift/VALIDATION_DONE")):
        scores.append(json.loads(done.read_text())["score"])
    return scores


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.home() / "aspire_runs" / "traces_ablation"
    t = _arm_scores(root / "T")
    c = _arm_scores(root / "C")
    if not t or not c:
        print(f"missing scores (T={len(t)}, C={len(c)}) under {root}")
        return 1
    u, z = mann_whitney_u(t, c)

    def summ(label, xs):
        s = sorted(xs)
        mean = sum(s) / len(s)
        med = s[len(s) // 2] if len(s) % 2 else (s[len(s)//2 - 1] + s[len(s)//2]) / 2
        strong = sum(1 for v in s if v >= 0.80) / len(s)
        print(f"{label}: n={len(s)} mean={mean:.3f} median={med:.3f} "
              f"P(val>=0.80)={strong:.2f} scores={s}")

    summ("T (traces)", t)
    summ("C (retry)", c)
    print(f"Mann-Whitney U(T vs C)={u:.1f}  z={z:.3f}  "
          f"(z>0 => traces arm ranks higher)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_analyze_ablation.py -q -p no:anyio`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_ablation.py tests/aspire/test_analyze_ablation.py scripts/__init__.py
git commit -m "feat(scripts): pre-registered Mann-Whitney analysis for the ablation"
```

---

### Task 9: Full-suite regression gate + push

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS — all tests (prior 184 + the ~8 new ones).

- [ ] **Step 2: Confirm CLI help shows both new flags**

Run: `python3 -m aspire.run --help | grep -E "ablate-traces|--t "`
Expected: both flags listed.

- [ ] **Step 3: Push**

```bash
git push aspire_demo aspire_original_sim
```

---

## Self-review notes (spec coverage)

- Two arms differing only by trace access → Tasks 2/4/5/6 (scalar context, scalar replay, blind prompt, CLI selection); single-variable guarantee enforced in the launcher (Task 7: both arms `--t 0`, only C adds `--ablate-traces`).
- Evosearch disabled → Task 3 (`t=0` guard) + Task 6 (`--t`).
- Empty library per repeat, isolated dirs, pristine baseline, `s_val 100-119` → Task 7 launcher (mirrors `lift_repeats.sh`).
- Config logged per run → Task 1 (rides `to_dict()`), asserted in Task 6 CLI test.
- Pre-registered variance-aware analysis (Mann-Whitney U + effect sizes + P(val>=0.80)) → Task 8.
- N=8/arm pilot with staged escalation → operational (launcher `N` env var); not a code requirement.
- Symmetric extraction / winner bundles (no confound) → guaranteed by leaving those coordinator paths untouched (Task 3 changes only actor-facing writes + evosearch guard + replay flag).
- Engine-internal traces unchanged → no task touches `capx_execute.py` or the engine.
```
