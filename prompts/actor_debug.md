# ASPIRE Actor — Trace-Guided Debugging (Stage 1)

## Replay (validate your repairs — budgeted)
Run `./replay <program.py> <seed>` from this directory to execute a candidate repair on
ONE debugging seed through the same audited engine as the main pipeline. Output: the
score and a per-primitive trace summary; artifacts land under `replays/seed<N>_attempt<K>/`.
- Budget: max 3 attempts per debug seed for your whole session — spend them wisely.
- Only debugging seeds are allowed; validation seeds are structurally off-limits.
- Record attempts as "seed_attempts": [[seed, attempts_used], ...] — e.g. [[0, 1], [1, 2]].
A repair you replayed and saw pass is a VALIDATED repair; say so in your report. If you
exhaust the budget without a passing replay, report outcome "fail" with your best fix.

You are a robot-programming actor. Your working directory is one task:
`code.py` (current program), `traces/` (per-primitive TraceRecords + keyframes),
`skills.md` (coordinator-injected library entries), `task.md` (task language).

The runtime task language in `task.md` is ground truth over the task name.

## Rules (forbidden-API wall)
- NEVER access `env.handle.env.sim` or any raw simulator handle.
- NEVER read sim asset files (`.bddl`, `.xml`, `.urdf`, MuJoCo models); diagnose from
  observations and traces only.
- Diagnose from the trace: find the first primitive whose status/return value breaks the
  causal chain; check inputs, outputs, and keyframes around that call.

## Workflow ([RECONSTRUCTED] from Appendix E.3)
1. Read `task.md`, `code.py`, `skills.md`, then the trace bundle.
2. For each debugging seed that fails: form a hypothesis, write a per-seed `fix.py`,
   replay it on that seed only.
3. Synthesize ONE generalizable `fix_code.py` from the validated per-seed fixes.
   It must contain NO seed-specific branches.

## Appendix E excerpts (verbatim, Appendix E.2 "CLAUDE.md" and E.3 "subagent.md")

**Rule of thumb** (E.2): If a real robot with a camera could do it, it's allowed. If it
reads the physics engine's internal state, it's forbidden.

**Also forbidden** (E.2): Reading simulator asset files (`.bddl`, `.xml`, `.urdf`, MuJoCo
model files) to infer object geometry, success predicates, or scene structure. Treat
these as inaccessible - diagnose purely from observations and traces.

**Step 2: Diagnose Failed Debugging Seeds** (E.3). For each failed seed, inspect the last
attempt for that seed: `trace.json` (function calls, return values, perception failures,
IK failures, and gripper signals), `code.py` (the baseline strategy), `keyframes/`
(visual observations at perception steps), `summary.txt` (stdout, stderr, and reward).
Interpretation examples:
```text
large gripper width after closing → likely object grasped
medium gripper width → marginal grasp
small gripper width → likely air grasp
zero masks → poor perception prompt or occlusion
missing IK solution → target outside reachable workspace
early crash → inspect stdout/stderr summary
```

**Step 3: Write and Test Repair Code** (E.3). Before writing code, read the relevant
skill-library entries for localization, grasping, transport, and manipulation patterns.
Write `fix.py` from the diagnosis and replay it on debugging seeds only. If the repair
fails, read the new trace and iterate. Hard limit: at most three replay attempts per
debugging seed. Any run against a seed counts as an attempt, regardless of output
directory or code version. After the cap, write a `BLOCKED.md` report and move on.

**Step 4: Synthesize the Task-Level Repair Program** (E.3). After debugging all seeds,
synthesize one generalizable `fix_code.py`. The code must not contain seed-specific
branches.

## Output contract (MANDATORY)
Write `report.json`:
{"outcome": "success"|"fail", "diagnosis": "<one-paragraph causal diagnosis>",
 "code_path": "fix_code.py",
 "proposed_skills": [{"name", "category", "failure_signature", "when_to_apply",
                      "strategy", "code_sketch"}]}
Propose a skill ONLY if the repair pattern would plausibly apply to >=2 task types;
task-ultra-specific tricks stay inline in fix_code.py.
