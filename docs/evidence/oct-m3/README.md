# ASPIRE Algorithm Implementation and Skill Artifact Index

Prepared on 2026-11-14. Implementation baseline: `a8c608fb10317a43d240047c726edbcb62a4d1ff`; the original default branch was `aspire_original_sim`.
This update packages technical artifacts only, with no new model calls or simulation experiments.

| Feature | Implementation | Technical documents and artifacts |
|---|---|---|
| Coordinator-to-actor scheduling | [coordinator](../../../aspire/coordinator.py), [actors](../../../aspire/actors.py) | [Example execution records](../../../runs/2026-07-16-m3-aspire-pilot/), [test output](verification/2026-11-14-tests.txt) |
| Trace structures and execution outcomes | [schemas](../../../aspire/schemas.py), [engines](../../../aspire/engines.py) | [Structured result](../../../runs/2026-07-16-m3-aspire-pilot/two_arm_lift/report.json) |
| Skill storage, retrieval and reuse | [skill_library](../../../aspire/skill_library.py), [evosearch](../../../aspire/evosearch.py) | [Curriculum skill index](skills/curriculum/index.md), [action-budget skill index](skills/m3x/index.md) |
| Simulation study boundaries | [Analysis script](../../../scripts/reanalyze_val.py) | [Validation reanalysis record](../../../runs/VAL-REANALYSIS.md) |

The two skill indexes are byte-identical to those in the existing 2026-08-25 evidence pack. Linked skill bodies have been recovered from the original EPYC skill libraries with directory relationships preserved, so the indexes no longer point to missing files. Source directories are `aspire_runs/curriculum/accumulated_library` and `aspire_runs/m3x/skill_library`; these paths support provenance, while reviewers can read the artifacts directly in this repository.

The [test output](verification/2026-11-14-tests.txt) records checks of the listed 59 no-hardware tests on 2026-11-14. It is not a new simulation result and does not establish completion of all tasks on physical B601 hardware.

ASPIRE skill-accumulation experiments and HarnessVLA frozen-policy/harness comparisons are separate studies. The historical `15/40` versus `23/40` figures belong to HarnessVLA simulation records, not ASPIRE results in this repository. Existing experiment records retain their incomplete validation scope.

[manifest.csv](manifest.csv) records artifact hashes and provenance.

[implementation-commits.csv](implementation-commits.csv) maps each feature to its implementation files, the historical commits that last changed them, code links at the full baseline, and artifact paths. Historical implementation commits remain separate from evidence-packaging commits so documentation work is not presented as new implementation.
