# ASPIRE Comparative Study and Confirmatory Experiment Artifacts

Prepared on 2026-11-14. This update recovers original experiment files and technical indexes; it does not call models, rerun simulations or declare the confirmatory experiment complete.

| Work | Implementation | Technical record |
|---|---|---|
| Skill accumulation and retrieval comparison | [skill_library](../../../aspire/skill_library.py), [offline reanalysis](../../../scripts/reanalyze_val.py) | [Existing validation analysis](../../../runs/VAL-REANALYSIS.md) |
| Preregistered task selection and analysis | [Selection logic](../../../scripts/val_confirmatory_select.py), [analysis program](../../../scripts/analyze_libero_tiling.py) | [Preregistration](../../../runs/2026-07-26-val-confirmatory/PREREGISTRATION.md), [original file inventory](confirmatory/source-inventory.csv), [60-cell file audit](confirmatory/cell-audit.csv) |
| Bimanual scenario candidate | [Existing bimanual trial directory](../../../runs/2026-07-16-m3-aspire-pilot/two_arm_handover/) | Its result is fail, and the repair was not successfully replayed; it is not an accepted second industrial demonstration |
| Analysis and scheduling software checks | [Related tests](../../../tests/aspire/) | [Output: 6 passed on Linux](verification/2026-11-14-tests.txt) |

## Available Files and Historical Experiment Status

The [file audit](confirmatory/audit.json) covers 60 cells: the original three selected tasks, two conditions and ten repeats per condition. There are 48 parseable JSON files, 2 error texts and 10 cells without summaries. Error texts are retained as `.json.invalid.txt`, with no fabricated JSON or replacement zero scores.

The original technical record describes the experiment as 50/60 and unfinished. The 48 valid JSON files and 2 error files are the 50 summary files recovered here. This file audit is not a new completion rate and does not replace the original statistical treatment of failures. Recomputing final significance from only the 48 valid JSON files would change the denominator; that is not done here.

`confirmatory/results.json` is an original intermediate result with only 20 rows for spatial_6. Its bytes are preserved for traceability; it is not a final three-task summary. No confirmatory statistical conclusion has been established, and the incomplete status in the original [technical study report](../../../ASPIRE-reproduction-report.pdf) still applies.

ASPIRE and HarnessVLA simulation studies are cited separately. This repository does not establish physical wireless comparisons or B601 ACT comparisons. The listed runner dry-run check depends on Linux `/proc`; it failed on macOS due to platform requirements and then passed in the existing EPYC environment. Implementation was not changed to conceal the platform difference.

[implementation-commits.csv](implementation-commits.csv) and [manifest.csv](manifest.csv) record code history and artifact hashes respectively.
