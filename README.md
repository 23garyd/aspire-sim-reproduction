# aspire-robot-engine

当前实现的技术入口、附件与核验记录见 [技术证据索引](docs/evidence/oct-m3/README.md)。

Reproduction study of the **ASPIRE** architecture's *skill-accumulation* claim — does an
agent that banks reusable skills from earlier tasks measurably solve later, held-out tasks
better? The `aspire/` package (coordinator → actor → evosearch → skill library, with
trace-guided repair) is reused unchanged; this repo drives it against simulation and, on
sibling tracks, real robots.

## Tracks

| Track | What it is | Status |
|-------|------------|--------|
| **LIBERO sim reproduction** | The ASPIRE skill-accumulation study in simulation (LIBERO tasks via cap-x). *This repo's active focus.* | **Active** |
| **B601 real arm** | The same ASPIRE pipeline deployed on a physical reBot B601-RS arm (milestones M3a–M3d). Software built + CI-proven; on-bench live runs pending. | Separate repo: [`aspire-robot-B601`](https://github.com/23garyd/aspire-robot-B601) |
| **AgiBot A2 humanoid** | An earlier robot-execution layer for a 26-joint bimanual humanoid sim. Removed from this branch; code preserved on branch [`aspire_a2_sim`](../../tree/aspire_a2_sim). | **Shelved** |

## The sim reproduction — honest findings so far

The key methodological result: every campaign originally scored **debug-seed solving**
(`dbg_score`), and the accumulation signal was **masked by that metric**. Scored on
**held-out validation** (`val_score`) instead:

- The library arm **generalizes** to held-out seeds where **cold overfits** the debug seed —
  in **5 of 5 campaigns**, cold's dbg→val drop exceeds the library's (sign-test p≈0.06).
- Pooled held-out-validation success: **library 0.45 vs cold 0.22** (Fisher p≈0.006, post-hoc).
- A **pre-registered confirmatory** (val as the primary metric, mechanistic "overfit-band"
  task selection) sits right on the **p≈0.05 boundary** and is currently **parked incomplete**
  (50/60 cells) — see `runs/2026-07-26-val-confirmatory/`.

**Takeaway:** ASPIRE-style accumulation reproduces as a **held-out generalization** benefit,
not a debug-solve benefit — strong post-hoc evidence, a not-yet-closed pre-registered result.

### Campaign trail (all under `runs/`)
1. **Frontier** — warm-vs-cold on LIBERO-spatial; H0 on dbg-success, a speed effect, negative transfer.
2. **Tiling** — three arms (geometry vs dump-all retrieval vs cold); geometry retrieval avoids negative transfer.
3. **Harder (libero_10)** — first positive signal, post-hoc on held-out validation.
4. **Val re-analysis** — `scripts/reanalyze_val.py` → `runs/VAL-REANALYSIS.md` (the metric finding above; no new runs).
5. **Val-confirmatory** — the pre-registered study (parked incomplete).

## Layout

| Path | What it is |
|------|-----------|
| `aspire/` | The reused ASPIRE pipeline (coordinator, actor, evosearch, skill_library, engines, schemas). |
| `scripts/` | Campaign runners + analyzers (`analyze_libero_tiling.py`, `reanalyze_val.py`, `val_confirmatory_*`, `libero_*`). |
| `runs/` | Per-campaign specs, results, `FINDINGS.md`, and `VAL-REANALYSIS.md`. |
| `docs/superpowers/` | Design specs and implementation plans for each campaign. |
| `robot_b601/`, `scripts/b601_*` | B601 hardware track (also mirrored to the B601 repo). |
| `tests/` | Unit tests. Run anywhere — no robot/GPU/credits needed. |

## Running

```bash
# tests (the -p no:anyio flag is required)
python3 -m pytest tests/ -q -p no:anyio

# pure cross-campaign re-analysis on held-out validation (no GPU, reads existing results)
python3 scripts/reanalyze_val.py
```

LIBERO campaigns run through cap-x's **`.venv-libero`** (robosuite 1.4.0), `MUJOCO_GL=egl`;
campaign data lives outside the repo under `~/aspire_runs/`. Per-campaign specs, results and
`FINDINGS.md` are under `runs/`; design specs and plans are under `docs/superpowers/`.

## License

Licensed under the Apache License, Version 2.0 — see [`LICENSE`](LICENSE).

This repo reimplements the ASPIRE layer described in arXiv 2607.00272 (NVIDIA GEAR); the
paper itself is not redistributed here. It runs on top of [CaP-X](https://github.com/capgym/cap-x)
(MIT), which is not vendored — install it separately.
