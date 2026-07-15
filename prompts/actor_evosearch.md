# ASPIRE Actor — Evolutionary Search Proposals

You propose K candidate programs for one task (K and the output directory are given in
the appended "This round" section).

## Rules
- Same forbidden-API wall as debugging: no raw sim access (`env.handle.env.sim`), never
  read `.bddl`/`.xml`/`.urdf` asset files; no seed-specific branches in any candidate.
- The "Top programs so far" list gives you FILE PATHS and scores. READ each top
  program file before proposing — your candidates must be conditioned on their actual
  code and remaining failure modes, not on the scores alone.
- Read `task_analysis.md` first: do NOT re-test eliminated strategy branches; blocked
  branches may be retried only with a genuinely new technique. [RECONSTRUCTED]
- Make the K candidates STRATEGICALLY DISTINCT (different grasp axis, approach side,
  ordering), not K small mutations of one idea.
- Write each candidate to `candidate_<LETTER>/code.py` under the given iteration dir.
- Update `task_analysis.md` with the hypotheses behind this round's candidates.

## Appendix E excerpts (verbatim, Appendix E.4)

Evolutionary search maintains a persistent task-analysis document that is carried across
rounds. It consists of (i) a per-task scene description populated once from an initial
snapshot (object shapes, goal geometry, obstacles, blocked approach directions), (ii)
running hypotheses and the candidate metadata that tests them, and (iii) a ledger of
eliminated directions (through testing) and blocked, untested directions (failed due to
a workspace constraint). UpdateAnalysis rewrites this document each round from the new
traces, keyframes, and library retrievals. This document is what lets a later round
avoid re-testing an eliminated branch while still retrying blocked branches once a new
technique (e.g. a wrist rotation) becomes available.

**Step 3: Write K Candidates** (E.4): Each candidate must test a distinct hypothesis. No
two candidates should fail at the same stage for the same reason. Each candidate should
include a docstring describing the hypothesis, how it differs from prior candidates, and
the expected failure mode if wrong.

**Step 5: Iterate** (E.4): When progress stalls, use the remaining iteration budget to
explore structurally new approaches rather than stopping early. A plateau on the current
approach family means the current family may be wrong, not that the task is unsolvable.
The debug seeds are a small, potentially unrepresentative sample. The code will be
evaluated on unseen held-out seeds; write for those, not for the debug seeds. Prefer
strategies that work for mechanistic reasons over strategies that exploit patterns
specific to debug-seed failures. Avoid hard-coded thresholds, image-region masks, or
offsets derived by fitting to observed debug-seed failures.

## Output contract (MANDATORY)
After writing candidates, write `report.json`:
{"outcome": "success", "diagnosis": "<why these K strategies>", "code_path":
 "<relative path of the candidate you consider strongest>", "proposed_skills": []}

(advisory: the orchestrator selects candidates by executing candidate_*/code.py;
report.json here is for audit trail only)
