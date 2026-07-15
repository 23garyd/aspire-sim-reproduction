# Gap-Fix Plan: review_codex.md Findings → Mechanism-Complete ASPIRE

**Date:** 2026-07-15
**Input:** `docs/review_codex.md` (third-party gap analysis vs Aspire.pdf) — findings
verified against the code; all substantive claims confirmed accurate.
**Branch:** `aspire_original_sim`
**Posture:** phase-level plan; each phase gets bite-sized TDD tasks at execution time
(same subagent-driven process as the 14-task build).

## Dependency classes and confidence WITHOUT an NVIDIA release

| Class | Findings | Depends on | Confidence |
|---|---|---|---|
| **A: CaP-X integration** | P0 run_episode stub; trace/keyframe capture | CaP-X repo (MIT, released) | **~90%** — hooks exist (CaP-Agent0 consumes structured feedback); residual risk = feedback richness may need a thin instrumentation wrapper |
| **B: published mechanism** | evosearch trace-history, program audit, ExtractValidatedPatterns, task-dir materialization, judge dedup context, App-E operational details | Algorithm 1 (printed in full) + Appendix E (conventions + much verbatim prompt text) | **~85–90%** for faithful mechanism |
| **C: genuinely unpublished** | exact K/T/θ, omitted prompt passages, admission-criteria details, trace-summary format | Only an NVIDIA release resolves | Not blocking: affects exact numbers only; success bar is trend vs our own baseline; all reconstructions marked `[RECONSTRUCTED]` and diffable later |

**Overall: ~85% confidence in a mechanism-complete end-to-end ASPIRE without NVIDIA;
~60–70% for trend reproduction (dominated by LLM-version drift, not missing code).**

Conscious-design items the review flagged that we KEEP (documented, not gaps):
validation lives in the coordinator (single-use S_val guard); multi-device dispatch
degenerates to sequential on one GPU (spec'd); K enforced as a max via truncation.

## Phases (order = review's completion order, grouped for review cycles)

### Phase G1 — Close the audit hole (P1-#4) + judge dedup context (P2)  [pure Class B, no GPU]
- Coordinator audits EVERY program before execution: baseline `code.py`, Stage-1
  `fix_code.py`, every evosearch candidate. Violation → candidate scored 0 and marked
  `AUDIT_REJECTED` (never executed), logged in iter summary; Stage-1 violation → treated
  as failed round.
- `ClaudeJudge.admit` receives top-N similar existing skills (reuse existing
  `SkillLibrary.retrieve` keyword/category search) so the dedup instruction can work.
- Effort: small. All fake-testable. **Do first — it's a correctness hole in scoring.**

**G1 review carry-forward (non-blocking):** dedup selection is alphabetical
(`retrieve(categories=...)[:5]`), not similarity-ranked — pass keywords from
`failure_signature`/`when_to_apply` or rank when the library grows past ~5 entries per
category. Revisit in G4 (admission rework touches the same code).

### Phase G2 — Materialize the task directory (P1-#2 core)  [Class B]
- New `aspire/task_context.py`: writes `traces/trace.json` (+ media file copies),
  `summary.txt`, `task.md` (runtime task language), `skills.md` (coordinator-retrieved
  relevant skills — switch from pass-all to retrieval) into the task dir after every
  execute; refreshed before each actor invocation.
- Extend `ActorReport` schema with debug-validation rate + per-seed attempts fields
  (review: "missing from report schema").
- Fake-testable end-to-end (FakeEngine already returns TraceRecords).

### Phase G3 — Trace-conditioned evosearch (P1-#3)  [Class B]
- History entries become `(path, score, trace_summary)`; `iter_summary.json` gains the
  failure-mode summary per candidate.
- `ProposeContext.history_note` populated from accumulated failure modes; orchestrator
  creates/updates `task_analysis.md` (eliminated vs blocked ledger) from actual results.
- Per-candidate trace analyzer = deterministic summarizer first (status/error extraction
  from TraceRecords); LLM summarization only if the deterministic one proves too lossy.

### Phase G4 — ExtractValidatedPatterns + admission rebinding (P1-#5)  [Class B]
- Implement Algorithm 1 line 17 as a post-validation actor call: input = history, the
  WINNING program (wherever it came from), validation result; output = proposed skills.
- Admission consumes THIS output; Stage-1 report skills only admitted if the Stage-1
  repair is the validated winner. Evosearch winners now produce skills.
- Prompt: from App E.1 transcriptions + `[RECONSTRUCTED]` bridging (Class C residue,
  marked).

### Phase G5 — run_episode() against real CaP-X (P0)  [Class A, on simhost]
- Execute existing `m0_rig_up.sh`; wire `run_episode()` to CaP-Gym per the repo docs;
  capture golden episode; add golden regression test (`tests/aspire/golden/`).
- If CaP-Gym feedback lacks per-primitive media, add a thin instrumentation wrapper
  around the primitive namespace (our code, their API).
- Exit criterion: one Robosuite task end-to-end (real env, real actor, real trace,
  real skill admitted) — review step 9.

### Phase G6 — Appendix-E operational details  [Class B, prompt+enforcement]
- Enforce in code what today is prompt-only: three-attempt cap per seed, `BLOCKED.md`
  handling, fast path from successful baseline seed, `findings.md` writer (evosearch),
  initial scene snapshot step, runtime task-language check (task.md now exists per G2).
- Progress tracker + never-redispatch-done for the sequential coordinator (the
  single-GPU degenerate form of App E's dispatch loop; fleet version stays out of scope).

### Ordering rationale
G1–G4 are GPU-free and fully testable with fakes → they proceed on the Mac immediately
and keep every review cycle cheap. G5 is the only simhost-bound phase and was already the
plan's M0. G6 hardens operations before benchmark campaigns. Benchmarks (SOW M2's agent
baseline onward) start only after G5's exit criterion — review step 10.

## SOW alignment note
These phases ARE the SOW execution map's M2–M3 engineering content (infrastructure,
agentic integration, bounded control/telemetry): closing the review's gaps and earning
the SOW's monthly evidence are the same work, sequenced the same way.
