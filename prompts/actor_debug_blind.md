# Repair task (reward-only / trace-blind)

You are repairing a robot control program. Your program is `code.py` in this
directory. It currently fails some of the debugging seeds.

## What you can see

- `code.py` — the current program.
- `outcome.txt` — a single line `score: <float>`: the fraction of debugging seeds
  the current program passes (0.0 = all fail, 1.0 = all pass). This is your ONLY
  feedback on the program's behaviour. There are no per-step execution records or
  images available for this task.
- `skills.md` — any retrieved library skills (may be empty).
- `task.md` — the task identity.

The runtime task language in `task.md` is ground truth over the task name.

## Rules (forbidden-API wall)
- NEVER access `env.handle.env.sim` or any raw simulator handle.
- NEVER read sim asset files (`.bddl`, `.xml`, `.urdf`, MuJoCo models); diagnose from
  observations and the scalar score only.
- You cannot inspect per-primitive call records, return values, or visual
  observations for this run — treat them as inaccessible. Diagnose purely from
  `code.py` and the scalar score.

## The replay affordance (reward-only)

You may test a candidate program on a single debugging seed:

    ./replay <program_path> <seed>

It prints one line, `score: <float>`, for that seed and nothing else. You have a
bounded number of replays per seed (over-use is audited). Use them to check
whether a change helps, judging only by the returned score.
- Budget: max 3 attempts per debug seed for your whole session — spend them wisely.
- Only debugging seeds are allowed; validation seeds are structurally off-limits.
- Record attempts as "seed_attempts": [[seed, attempts_used], ...] — e.g. [[0, 1], [1, 2]].
A repair you replayed and saw pass is a VALIDATED repair; say so in your report. If you
exhaust the budget without a passing replay, report outcome "fail" with your best fix.

## Workflow

1. Read `task.md`, `code.py`, and `skills.md`. Reason about likely failure causes
   from the program text and the scalar score in `outcome.txt` alone.
2. For each debugging seed: form a hypothesis, write a per-seed `fix.py`, and
   replay it on that seed only, judging success purely by the returned score.
3. Synthesize ONE generalizable `fix_code.py` from the validated per-seed fixes.
   It must contain NO seed-specific branches — that is audited and rejected.

Do not attempt to read, reconstruct, or fabricate execution records — none exist
for this run. Base every decision on the scalar score alone.

## Output contract (MANDATORY)
Write `report.json`:
{"outcome": "success"|"fail", "diagnosis": "<one-paragraph causal diagnosis>",
 "code_path": "fix_code.py",
 "proposed_skills": [{"name", "category", "failure_signature", "when_to_apply",
                      "strategy", "code_sketch"}]}
Propose a skill ONLY if the repair pattern would plausibly apply to >=2 task types;
task-ultra-specific tricks stay inline in fix_code.py.
