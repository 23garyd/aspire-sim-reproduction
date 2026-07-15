# ASPIRE Reproduction on Original Simulation — Design

**Date:** 2026-07-14
**Branch:** `aspire_original_sim`
**Status:** Approved by user

## Goal

Reproduce the ASPIRE paper (arXiv 2607.00272, NVIDIA GEAR) using its original simulation
stack. ASPIRE's own code is unreleased ("coming soon"), but its execution substrate —
**CaP-X** (github.com/capgym/cap-x, MIT) — is released, including **CaP-Agent0**, the
paper's main baseline, and all three benchmark integrations. We therefore run stock CaP-X
and **re-implement the ASPIRE layer on top**, from the paper's method section and
Appendix E prompts/file conventions.

**Success bar: trend reproduction.** ASPIRE-layer beats our own measured CaP-Agent0
baseline on the same tasks with the paper's qualitative pattern (e.g. large bimanual-handover
gain, robustness under perturbations). Exact percentages are not required — different LLM
version and budget make exact matches unrealistic. Model IDs are logged per run.

**Scope decisions (user-approved):**
- Full ASPIRE loop (traces → debugging → skill library → evolutionary search).
- Benchmarks staged: Robosuite → LIBERO-Pro → BEHAVIOR-1K (stretch).
- Actors are **headless Claude Code** (`claude -p`), tiered: Opus for diagnosis/repair/skill
  synthesis, Sonnet for evosearch candidate proposals, Haiku never writes code.
- Approach A: standalone orchestrator over **unmodified** CaP-X (rejected: forking
  CaP-Agent0 — blurs the baseline; porting the A2 `robot_engine` — wrong altitude, CaP-X
  already is the execution engine).

## Ground truth from paper + site

- Agent in paper: Claude Code + Opus 4.6, 1M context. Framework: CaP-X on MuJoCo
  Playground; Gymnasium envs; agent composes perception/control primitives in Python.
- Benchmarks: LIBERO-Pro (object/goal/spatial perturbations), Robosuite 1.5 (contact-rich,
  bimanual handover 20%→92%), BEHAVIOR-1K via OmniGibson (navigate-and-pick-up
  soda-can / radio). Transfer study: library from LIBERO-90 → held-out LIBERO-Pro Long.
- Paper file conventions (Appendix E): `code.py` (baseline strategy), per-seed `fix.py`,
  generalizable `fix_code.py` (no seed-specific branches), and for evosearch:
  `<EVOSEARCH_OUTPUT_DIR>/<suite>/<task>/<run_id>/` containing `task_analysis.md`
  (rewritten each round: eliminated vs blocked strategy branches), `iter_XX/candidate_A/code.py`,
  `iter_summary.json`; final `evosearch_best_code.py` + `findings.md` at the task level.
  Stage 1 = debugging seeds `S_dbg`; Stage 2 = validation seeds `S_val` used **exactly once**.
  Evosearch Step 0b: always print the runtime task language — it is ground truth over the
  task name. Step 2: scene snapshot on one debug seed before writing candidates.
- Paper coordinator dispatch model: one task = one subagent = one compute device;
  dispatch → idle → on completion notification, redispatch freed device; never re-dispatch
  a done task (done = Stage 2 complete on disk).
- **K, T, θ are NOT published** (appendix marks them experiment-specific and omits them).
  We make them config parameters with `[RECONSTRUCTED]` defaults (K=3, T=5, θ=1.0 on
  debugging seeds) and record actual values per run.
- Forbidden-API wall: no `env.handle.env.sim` access; never read sim asset files
  (`.bddl`, `.xml`, `.urdf`); diagnose from observations and traces only.
- Algorithm 1 (evolutionary search): population K, rounds T, history H, propose repairs
  conditioned on Top3(H) + skill library + failure traces; execute on S_dbg; early-stop at
  threshold θ; final one-shot validation on S_val; extract validated patterns.
- Hardware target: `simhost` (ssh USER@simhost) — RTX 5090 32GB, 64 cores, 251GB RAM,
  514GB free. Sufficient for all three benchmarks incl. OmniGibson.

## Architecture

```
Mac (this repo)                      simhost (RTX 5090)
├─ aspire/          ← new package    ├─ ~/cap-x/            (unmodified clone, uv env)
│  coordinator, harness, schemas     ├─ ~/aspire_runs/      (all experiment state)
├─ prompts/         ← paper App. E   │   └─ <SUITE>/<TASK>/ (file-convention state)
├─ tests/           ← TDD, no GPU    └─ headless `claude -p` actor invocations
└─ docs/specs, plans                     (spawned by our harness, cwd = task dir)
```

CaP-X is lab equipment: never modified; released CaP-Agent0 stays pristine as the baseline.

## Components

### `aspire/engine_adapter.py`
Only code touching CaP-X. Launches env from task YAML; `Execute(P, S) -> (score,
trace_bundle)` per Algorithm 1; normalizes CaP-X per-primitive feedback into our
`TraceRecord` schema (carried over conceptually from the A2 work). Enforces the
forbidden-API wall by exposing only whitelisted primitives to actor code. Duck-typed;
tests use `FakeEngine` with scripted outcomes.

### `aspire/actor.py`
Wraps one headless Claude Code run: builds actor working dir (task spec, current program,
trace bundle, coordinator-injected skills), invokes `claude -p` with prompt file + model
tier, enforces turn/token budget, parses the structured actor report. Actors never see the
shared library directly.

### `aspire/coordinator.py`
Owns the run. Implements the paper's dispatch model (one task = one actor = one device;
dispatch → idle → redispatch on completion; never re-dispatch a done task) — on simhost's
single GPU this degenerates to sequential or small-N parallel envs, which is fine. Audits
actor findings mechanically (API-policy compliance, no seed-specific branches); invokes an
Opus judge only for the paper's coordinator-guided skill-admission decision. Enforces
single-use S_val — any re-run of validation marks the run **tainted**.

### `aspire/skill_library/`
One markdown file per skill, paper format: failure signature, when-to-apply, repair
strategy, optional code sketch, provenance (task, seeds validated on). `index.md` for
retrieval. Retrieval = category + keyword match first; embeddings only if insufficient.

### `aspire/evosearch.py`
Algorithm 1 as literal code (K, T, H, Top3, θ, one-shot S_val). Disk state after every
step (paper's file conventions double as checkpoint format) → crashed runs resume without
re-spending tokens.

### `prompts/`
Appendix E prompts transcribed verbatim where the PDF text is clean, marked
`[RECONSTRUCTED]` where gaps were filled. Diffable against the future official release.

## Data flow — one task lifecycle

```
task YAML ──► Stage 0: baseline code.py on S_dbg
                 │ pass ──► Stage 2
                 ▼ fail
             Stage 1: trace-guided debugging (actor loop)
                 diagnose TraceRecords → per-seed fix.py →
                 generalizable fix_code.py (no seed branches)
                 │ still failing after N rounds
                 ▼
             Evosearch (Algorithm 1): K candidates × T rounds on S_dbg
                 ──► evosearch_best_code.py
                 ▼
             Stage 2: S_val — exactly once
                 ▼
             Actor report → coordinator audit → skill admission → library
```

## Milestones

- **M0 — Rig up.** CaP-X + uv on simhost; GPU smoke test; one scripted (non-LLM) episode
  through the adapter; TraceRecords verified against real CaP-X output.
- **M1 — Baseline.** Released CaP-Agent0 on ~5 Robosuite tasks incl. bimanual handover.
  Establishes OUR baseline numbers; never compare against numbers we didn't reproduce.
- **M2 — ASPIRE debug loop.** Stages 0–2 without evosearch. First skills admitted.
- **M3 — Evosearch + trend claim.** Full Algorithm 1 where M2 plateaued (handover is the
  headline). ASPIRE vs our M1 baseline = the reproduction result.
- **M4 — LIBERO-Pro.** Second venv (robosuite 1.4 conflict is documented by CaP-X);
  perturbation suites; LIBERO-90 → held-out Long transfer study.
- **M5 (stretch) — BEHAVIOR-1K.** OmniGibson; the two paper tasks. Only after M3; ~20-min
  episodes make it the most expensive place to learn a lesson.

## Testing

- TDD (Red-Green-Refactor) on all non-LLM components: coordinator state machine, report
  parser, admission rules, evosearch loop — driven by `FakeEngine`/`FakeActor` scripted
  outcomes (verifies Top3 selection, early stop, single-use S_val, resume-from-disk).
- Trace normalization tested against golden CaP-X outputs captured in M0.
- LLM-dependent behavior: replay tests — recorded actor transcripts through parser/auditor.
- Per-milestone on-GPU canary: one cheap task before any batch run.

## Risks

| Risk | Mitigation |
|------|-----------|
| Appendix prompts partially garbled in PDF extraction | Transcribe clean parts verbatim; mark `[RECONSTRUCTED]`; accept as known deviation |
| Token burn (evosearch = K×T×seeds agent runs) | Tiered models; disk-checkpoint resume; per-task budget caps; M1/M2 before any search |
| Model drift (paper: Opus 4.6; ours: current Opus) | Trend bar absorbs it; model IDs logged per run |
| Released CaP-Agent0 underperforms its paper on our rig | M1 finding, not blocker — ASPIRE compares against our measured baseline |
| LIBERO-Pro venv conflict (robosuite 1.4 vs 1.5) | CaP-X documents the dual-venv setup; M4 isolated from M1–M3 |

## Relationship to prior work in this repo

The `robot_engine/` A2 stack (branch `aspire_a2_sim`) stays untouched. What carries over:
the `TraceRecord` schema concept, the TDD discipline, and the Mac-develop → simhost-run
workflow. No A2 code is imported by the `aspire/` package.
