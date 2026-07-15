# ASPIRE — Extract Validated Patterns (Algorithm 1, line 17)

You are run ONCE per task, after held-out validation, to distill reusable repair
knowledge from the VALIDATED winning program. Your working directory contains:
`winner/trace.json` + `winner/summary.txt` (the winning program's debug-seed execution),
`winner/validation_trace.json` + `winner/validation_summary.txt` (held-out validation),
the winning program file, `task.md`, and — when evolutionary search ran —
`run_001/task_analysis.md` (per-round candidate outcomes) and `traces/` (last failure
before the winning repair).

## Rules (forbidden-API wall)
- NEVER access `env.handle.env.sim` or any raw simulator handle.
- NEVER read sim asset files (`.bddl`, `.xml`, `.urdf`, MuJoCo models); diagnose from
  observations and traces only.

## What to extract ([RECONSTRUCTED] from Appendix E.1)
Compare the winning program against the failures that preceded it (traces/, ledger).
The reusable knowledge is the failure->repair PATTERN, not the task solution:
failure signature, when-to-apply condition, repair strategy, optional minimal code
sketch. Propose a skill ONLY if it would plausibly apply to >=2 task types; no
seed-specific logic; respect the forbidden-API wall (no env.handle.env.sim, no
.bddl/.xml/.urdf reads) in any code sketch.

## Appendix E excerpt (verbatim, Appendix E.1)

Actor agents report candidate repairs using a structured findings schema: the observed
failure mode, the validated repair, transferable patterns, task-specific quirks, and the
validation success rate on debug configurations. The coordinator prompt then audits each
candidate for reusability, checks API-policy compliance, and admits only validated
repairs that are likely to transfer beyond the originating task. (E.1)

## Output contract (MANDATORY)
Write `extraction_report.json` (NOT report.json):
{"outcome": "success", "diagnosis": "<what failure class the winner overcame>",
 "code_path": "<winning program filename>",
 "proposed_skills": [{"name", "category", "failure_signature", "when_to_apply",
                      "strategy", "code_sketch"}]}
An empty proposed_skills list is a valid outcome (nothing generalizable).
