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

## Output contract (MANDATORY)
After writing candidates, write `report.json`:
{"outcome": "success", "diagnosis": "<why these K strategies>", "code_path":
 "<relative path of the candidate you consider strongest>", "proposed_skills": []}
