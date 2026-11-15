# Technical Recommendations and Follow-up Work for Skill Accumulation

Sources: [validation analysis](../../../runs/VAL-REANALYSIS.md), [preregistration](../../../runs/2026-07-26-val-confirmatory/PREREGISTRATION.md), [recovered-cell audit](../nov-m4/confirmatory/audit.json).

- Distinguish debug-seed solving from held-out generalization; interpret effects after fixing preregistered metrics and task selection.
- Retrieval can cause negative transfer. Skill counts do not replace per-task result analysis. Keep ASPIRE and frozen-policy HarnessVLA evidence and denominators separate.
- The original confirmatory experiment remains incomplete: historically 50/60, with 48 JSON summaries, 2 error texts and 10 missing cells retained. Dropping error files or shrinking the denominator cannot turn this into a final positive conclusion.
- Record process and port ownership for concurrent environment services. Confirm that summaries match actual run status before analysis. The selected dry-run software check depends on Linux /proc.

Follow-up work: continue missing cells only after the responsible owner decides; retain error cells and preregistered handling rules; pin cap-x, model identifiers and runtime environment for reproduction; place large campaign inputs and outputs in retrievable storage. This packaging update did not start models or rerun tasks.
