# LIBERO Tiling-Curriculum + Retrieval-Discrimination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-arm LIBERO campaign (warm-dumpall / warm-geometry / cold) over a tiled skill library to separate the coverage hypothesis from the retrieval hypothesis, plus the contained geometry-aware retrieval it needs.

**Architecture:** Add a string `source_xy` tag to `Skill` (round-trips through the existing markdown render/parse) and a `retrieve_by_location` function to `SkillLibrary`. A `select_skills` helper in `task_context.py` dispatches to geometry retrieval when env vars are set, else the stock `relevant_skills`; the coordinator's two retrieval call sites use it. A runner tags each accumulated skill with its source bowl location and runs the three arms; a three-arm analyzer computes pairwise Fisher-exact.

**Tech Stack:** Python 3 (aspire pure modules + stdlib `math.comb`), bash runner, cap-x `.venv-libero` (robosuite 1.4.0) for LIBERO execution, pytest.

## Global Constraints

- `.venv-libero` python = `/home/demo/cap-x/.venv-libero/bin/python`; robosuite must be 1.4.x (Phase 0 asserts). Never use the main `.venv` for LIBERO.
- Only the retrieval addition touches `aspire/` (`skill_library.py`, `task_context.py`, `coordinator.py`). The stock `relevant_skills` path stays behavior-identical when env is unset, so Arms A and C reproduce prior behavior exactly.
- `source_xy` is a STRING field (`""` when untagged, `"x,y"` when tagged) — never a tuple — because `SkillLibrary.retrieve` joins `asdict(s).values()` and would break on a non-string.
- capx contract unchanged: `capx_execute.py --workdir /home/demo/cap-x --config-path <cfg>`; `aspire.run` prints one JSON summary line; solved = `dbg_score >= 1.0`; admitted skill = non-empty `admitted`.
- `MUJOCO_GL=egl`; runner idempotent via `DONE` markers; `DRY=1` prints the plan with no GPU/venv calls.
- theta = 1.0; admission_min_val = 0.5 (aspire defaults; not overridden).
- Test budget `TEST_T=2`; accumulate `ACCUM_T=5`. N=5 repeats/arm/task. Arms: `warm_dumpall`, `warm_geo`, `cold`.
- All tests run with `python3 -m pytest tests/ -q -p no:anyio` (the `-p no:anyio` flag is REQUIRED).
- Reuse `runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py`; do not re-create it.
- Verdict strings labeled **suggestive, not conclusive** at N=5/arm/task.

---

### Task 1: `source_xy` tag on Skill (render/parse round-trip)

**Files:**
- Modify: `aspire/skill_library.py` (Skill dataclass, `render_skill`, `parse_skill`)
- Test: `tests/aspire/test_libero_tiling_sourcexy.py`

**Interfaces:**
- Consumes: existing `Skill`, `render_skill`, `parse_skill`.
- Produces: `Skill(..., source_xy: str = "")`; `render_skill` emits a `source_xy: <val>` line (only when non-empty) directly after the `category:` line; `parse_skill` reads it back (absent → `""`).

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_libero_tiling_sourcexy.py
from aspire.skill_library import Skill, render_skill, parse_skill


def _skill(**kw):
    base = dict(name="rim grasp", category="grasping", failure_signature="fs",
                when_to_apply="wa", strategy="st", code_sketch="cs", provenance="spatial_2")
    base.update(kw)
    return Skill(**base)


def test_sourcexy_roundtrips_when_set():
    s = _skill(source_xy="0.123,-0.045")
    back = parse_skill(render_skill(s))
    assert back.source_xy == "0.123,-0.045"
    # all other fields survive unchanged
    assert back.name == "rim grasp" and back.category == "grasping" and back.strategy == "st"


def test_sourcexy_absent_defaults_empty():
    s = _skill()  # no source_xy
    text = render_skill(s)
    assert "source_xy:" not in text          # not emitted when empty
    assert parse_skill(text).source_xy == ""


def test_sourcexy_line_does_not_break_section_parse():
    s = _skill(source_xy="1.0,2.0", strategy="line1\nline2")
    back = parse_skill(render_skill(s))
    assert back.strategy == "line1\nline2" and back.source_xy == "1.0,2.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_sourcexy.py -q -p no:anyio`
Expected: FAIL (`Skill.__init__() got an unexpected keyword argument 'source_xy'`)

- [ ] **Step 3: Implement in `aspire/skill_library.py`**

Add the field to the dataclass (after `provenance`, keep default so `from_proposed`'s `**p.to_dict()` still works):

```python
@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    failure_signature: str
    when_to_apply: str
    strategy: str
    code_sketch: str = ""
    provenance: str = ""
    source_xy: str = ""          # "x,y" when tagged by the tiling runner; "" = location-agnostic
```

Emit it in `render_skill` right after the `category:` line, only when non-empty:

```python
def render_skill(s: Skill) -> str:
    parts = [f"# {s.name}", f"category: {s.category}"]
    if s.source_xy:
        parts.append(f"source_xy: {s.source_xy}")
    for key in _SECTIONS:
        parts += [f"## {_TITLES[key]}", getattr(s, key)]
    return "\n\n".join(parts) + "\n"
```

Read it in `parse_skill` (optional line; add after the `category` line is parsed, before the section loop):

```python
def parse_skill(text: str) -> Skill:
    name = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    category = re.search(r"^category: (.+)$", text, re.M).group(1).strip()
    m_xy = re.search(r"^source_xy: (.+)$", text, re.M)
    source_xy = m_xy.group(1).strip() if m_xy else ""
    # ... existing positional section parsing unchanged ...
    return Skill(name=name, category=category, source_xy=source_xy, **fields)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_sourcexy.py -q -p no:anyio`
Expected: PASS (3 passed)

- [ ] **Step 5: Guard the existing suite (no regression in render/parse users)**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS (prior count + 3).

- [ ] **Step 6: Commit**

```bash
git add aspire/skill_library.py tests/aspire/test_libero_tiling_sourcexy.py
git commit -m "feat(aspire): optional source_xy tag on Skill (render/parse round-trip)"
```

---

### Task 2: `retrieve_by_location` on SkillLibrary

**Files:**
- Modify: `aspire/skill_library.py` (add method to `SkillLibrary`)
- Test: `tests/aspire/test_libero_tiling_retrieve.py`

**Interfaces:**
- Consumes: `SkillLibrary.load_all`, `Skill.source_xy`.
- Produces: `SkillLibrary.retrieve_by_location(self, target_xy, k=1, include_untagged=True) -> list[Skill]` — returns the `k` location-tagged skills nearest `target_xy` (Euclidean over the parsed `source_xy`), followed by all untagged skills when `include_untagged=True`. `target_xy` is a `(float, float)` tuple.

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_libero_tiling_retrieve.py
from aspire.skill_library import Skill, SkillLibrary


def _add(lib, name, xy):
    lib.add(Skill(name=name, category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy=xy))


def test_nearest_one_by_location(tmp_path):
    lib = SkillLibrary(tmp_path)
    _add(lib, "near", "0.10,0.00")
    _add(lib, "far", "0.90,0.90")
    got = lib.retrieve_by_location((0.12, 0.01), k=1, include_untagged=False)
    assert [s.name for s in got] == ["near"]


def test_untagged_appended_when_included(tmp_path):
    lib = SkillLibrary(tmp_path)
    _add(lib, "near", "0.10,0.00")
    lib.add(Skill(name="plumbing", category="engine-quirk-motion", failure_signature="f",
                  when_to_apply="w", strategy="s"))  # no source_xy
    got = lib.retrieve_by_location((0.0, 0.0), k=1, include_untagged=True)
    names = [s.name for s in got]
    assert names[0] == "near" and "plumbing" in names


def test_untagged_excluded_when_flag_false(tmp_path):
    lib = SkillLibrary(tmp_path)
    _add(lib, "near", "0.10,0.00")
    lib.add(Skill(name="plumbing", category="engine-quirk-motion", failure_signature="f",
                  when_to_apply="w", strategy="s"))
    got = lib.retrieve_by_location((0.0, 0.0), k=1, include_untagged=False)
    assert [s.name for s in got] == ["near"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_retrieve.py -q -p no:anyio`
Expected: FAIL (`AttributeError: 'SkillLibrary' object has no attribute 'retrieve_by_location'`)

- [ ] **Step 3: Implement the method (add to `SkillLibrary`, after `retrieve`)**

```python
    def retrieve_by_location(self, target_xy, k=1, include_untagged=True) -> list:
        tx, ty = float(target_xy[0]), float(target_xy[1])
        tagged, untagged = [], []
        for s in self.load_all():
            parts = s.source_xy.split(",") if s.source_xy else []
            if len(parts) == 2:
                try:
                    sx, sy = float(parts[0]), float(parts[1])
                except ValueError:
                    untagged.append(s); continue
                tagged.append(((sx - tx) ** 2 + (sy - ty) ** 2, s))
            else:
                untagged.append(s)
        tagged.sort(key=lambda pair: pair[0])
        out = [s for _, s in tagged[:k]]
        if include_untagged:
            out += untagged
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_retrieve.py -q -p no:anyio`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add aspire/skill_library.py tests/aspire/test_libero_tiling_retrieve.py
git commit -m "feat(aspire): retrieve_by_location nearest-location skill retrieval"
```

---

### Task 3: `select_skills` env hook + coordinator wiring

**Files:**
- Modify: `aspire/task_context.py` (add `select_skills`, import `retrieve_by_location` path)
- Modify: `aspire/coordinator.py` (replace the two `relevant_skills(...)` call sites; import `select_skills`)
- Test: `tests/aspire/test_libero_tiling_selecthook.py`

**Interfaces:**
- Consumes: `relevant_skills(library, traces, cap)`, `SkillLibrary.retrieve_by_location`.
- Produces: `select_skills(library, traces, cap=10) -> list[Skill]` — when `ASPIRE_RETRIEVAL=geometry` and `ASPIRE_TARGET_XY="x,y"` are set, returns `library.retrieve_by_location((x,y), k=1)[:cap]`; otherwise returns `relevant_skills(library, traces, cap)`. Coordinator calls `select_skills(self.library, latest.traces)` in both Stage-1 and evosearch retrieval sites.

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_libero_tiling_selecthook.py
from aspire.skill_library import Skill, SkillLibrary
from aspire.task_context import select_skills


def _lib(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.add(Skill(name="near", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy="0.10,0.00"))
    lib.add(Skill(name="far", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy="0.90,0.90"))
    return lib


def test_geometry_mode_uses_location(tmp_path, monkeypatch):
    lib = _lib(tmp_path)
    monkeypatch.setenv("ASPIRE_RETRIEVAL", "geometry")
    monkeypatch.setenv("ASPIRE_TARGET_XY", "0.12,0.01")
    got = select_skills(lib, traces=[])   # traces ignored in geometry mode
    assert got[0].name == "near"


def test_default_mode_falls_back_to_relevant(tmp_path, monkeypatch):
    lib = _lib(tmp_path)
    monkeypatch.delenv("ASPIRE_RETRIEVAL", raising=False)
    # no error traces -> relevant_skills falls back to load_all (both skills)
    got = select_skills(lib, traces=[])
    assert {s.name for s in got} == {"near", "far"}


def test_geometry_mode_bad_xy_falls_back(tmp_path, monkeypatch):
    lib = _lib(tmp_path)
    monkeypatch.setenv("ASPIRE_RETRIEVAL", "geometry")
    monkeypatch.setenv("ASPIRE_TARGET_XY", "not-a-coord")
    got = select_skills(lib, traces=[])   # malformed -> stock path
    assert {s.name for s in got} == {"near", "far"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_selecthook.py -q -p no:anyio`
Expected: FAIL (`ImportError: cannot import name 'select_skills'`)

- [ ] **Step 3: Implement `select_skills` in `aspire/task_context.py`**

Add `import os` at the top if absent, and:

```python
def select_skills(library, traces, cap: int = 10) -> list:
    """Retrieval dispatcher. Geometry mode (env-gated) injects the single
    nearest-location skill; otherwise the stock keyword retrieval. Behavior is
    identical to relevant_skills when ASPIRE_RETRIEVAL is unset."""
    import os
    if os.environ.get("ASPIRE_RETRIEVAL") == "geometry":
        xy = os.environ.get("ASPIRE_TARGET_XY", "")
        parts = xy.split(",")
        if len(parts) == 2:
            try:
                tx, ty = float(parts[0]), float(parts[1])
                return library.retrieve_by_location((tx, ty), k=1)[:cap]
            except ValueError:
                pass
    return relevant_skills(library, traces, cap)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_selecthook.py -q -p no:anyio`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire the coordinator (behavior-identical when env unset)**

In `aspire/coordinator.py`, update the import that pulls `relevant_skills`:

```python
from aspire.task_context import (relevant_skills, select_skills, summarize_traces,
                                 write_execution_context, write_skills_context)
```

Replace BOTH retrieval call sites (Stage-1 debug loop and the evosearch call) — currently `relevant_skills(self.library, latest.traces)` — with:

```python
                write_skills_context(self.task_dir,
                                     select_skills(self.library, latest.traces))
```

and

```python
            best = evosearch(self.task_dir, self.engine, self.actor, self.cfg,
                             skills=select_skills(self.library, latest.traces))
```

- [ ] **Step 6: Run the full suite (coordinator behavior unchanged when env unset)**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS (all prior coordinator tests still green; +3).

- [ ] **Step 7: Commit**

```bash
git add aspire/task_context.py aspire/coordinator.py tests/aspire/test_libero_tiling_selecthook.py
git commit -m "feat(aspire): env-gated select_skills hook; coordinator uses it (stock path unchanged)"
```

---

### Task 4: Three-arm analyzer

**Files:**
- Create: `scripts/analyze_libero_tiling.py`
- Test: `tests/aspire/test_libero_tiling_analysis.py`

**Interfaces:**
- Consumes: `fisher_exact_2x2` and `attempts_to_solve` from the v2 analyzer (import), summary/exec dir layout from the runner (`test/spatial_<tid>/<arm>/<rep>/{summary.json,exec/exec_NNNN/result.json}`, arm ∈ {`warm_dumpall`,`warm_geo`,`cold`}).
- Produces: `read_arm_rows(root, heldout_tasks) -> list[dict]`, `build_tiling_report(root, heldout_tasks) -> dict` with keys `arms` (per-arm `{n,n_solved,success_rate,mean_attempts_solved_only}`), `pairwise` (`{"B_vs_C":p,"B_vs_A":p,"A_vs_C":p}`), `by_task`, `verdict`; CLI `--root --heldout` writing/echoing the report.

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_libero_tiling_analysis.py
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from analyze_libero_tiling import build_tiling_report


def _mk(root, task, arm, rep, solved, winner=2):
    d = root / "test" / f"spatial_{task}" / arm / str(rep)
    (d / "exec").mkdir(parents=True)
    for n in range(1, (winner if solved else 3) + 1):
        e = d / "exec" / f"exec_{n:04d}"; e.mkdir()
        sc = 1.0 if (solved and n == winner) else 0.0
        (e / "result.json").write_text(json.dumps({"score": sc}))
    d.joinpath("summary.json").write_text(json.dumps(
        {"dbg_score": 1.0 if solved else 0.0, "val_score": 0.0, "admitted": []}))


def test_three_arm_success_and_pairwise(tmp_path):
    # warm_geo solves all; cold solves few; warm_dumpall middling — across 3 tasks
    plan = {"warm_geo": [1,1,1,1,1], "cold": [0,0,1,0,0], "warm_dumpall": [1,0,1,0,1]}
    for task in ("3","6","8"):
        for arm, reps in plan.items():
            for i, sv in enumerate(reps, 1):
                _mk(tmp_path, task, arm, i, bool(sv))
    rep = build_tiling_report(tmp_path, ["3","6","8"])
    assert rep["arms"]["warm_geo"]["success_rate"] == 1.0
    assert rep["arms"]["cold"]["success_rate"] < 0.3
    # B_vs_C = warm_geo vs cold: strongly separated -> small p
    assert rep["pairwise"]["B_vs_C"] < 0.10
    assert "verdict" in rep


def test_excludes_non_heldout_tasks(tmp_path):
    for arm in ("warm_geo", "cold", "warm_dumpall"):
        for i in range(1, 6):
            _mk(tmp_path, "8", arm, i, True)
            _mk(tmp_path, "99", arm, i, False)   # not in heldout -> excluded
    rep = build_tiling_report(tmp_path, ["8"])
    assert rep["arms"]["warm_geo"]["n"] == 5      # only task 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_analysis.py -q -p no:anyio`
Expected: FAIL (`ModuleNotFoundError: No module named 'analyze_libero_tiling'`)

- [ ] **Step 3: Implement `scripts/analyze_libero_tiling.py`**

```python
#!/usr/bin/env python3
"""Three-arm tiling analyzer: warm_geo (B) vs warm_dumpall (A) vs cold (C).
Pairwise Fisher-exact: B_vs_C (headline reproduction), B_vs_A (retrieval effect),
A_vs_C (naive tiling). Reuses the v2 analyzer's pure helpers."""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_libero_accumulation_v2 import fisher_exact_2x2   # Fisher lives in v2
from analyze_libero_accumulation import attempts_to_solve      # attempts_to_solve lives in v1

ARMS = ("warm_geo", "warm_dumpall", "cold")


def read_arm_rows(root, heldout_tasks):
    root = Path(root)
    rows = []
    for tid in heldout_tasks:
        for arm in ARMS:
            base = root / "test" / f"spatial_{tid}" / arm
            if not base.is_dir():
                continue
            for rep_dir in sorted(base.glob("*")):
                sfile = rep_dir / "summary.json"
                if not sfile.is_file():
                    continue
                s = json.loads(sfile.read_text())
                solved = float(s.get("dbg_score", 0)) >= 1.0
                att = attempts_to_solve(rep_dir / "exec", theta=1.0)
                rows.append({"task": f"spatial_{tid}", "arm": arm,
                             "solved": solved, "attempts": att})
    return rows


def _agg(rows):
    solved = [r for r in rows if r["solved"]]
    atts = [r["attempts"] for r in solved if r["attempts"] is not None]
    return {"n": len(rows), "n_solved": len(solved),
            "success_rate": (len(solved) / len(rows)) if rows else 0.0,
            "mean_attempts_solved_only": (sum(atts) / len(atts)) if atts else None}


def _pair_p(arm_rows_x, arm_rows_y):
    a = sum(1 for r in arm_rows_x if r["solved"]); b = len(arm_rows_x) - a
    c = sum(1 for r in arm_rows_y if r["solved"]); d = len(arm_rows_y) - c
    return fisher_exact_2x2(a, b, c, d)


def build_tiling_report(root, heldout_tasks):
    rows = read_arm_rows(root, heldout_tasks)
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    arms = {arm: _agg(by_arm[arm]) for arm in ARMS}
    pairwise = {
        "B_vs_C": _pair_p(by_arm["warm_geo"], by_arm["cold"]),
        "B_vs_A": _pair_p(by_arm["warm_geo"], by_arm["warm_dumpall"]),
        "A_vs_C": _pair_p(by_arm["warm_dumpall"], by_arm["cold"]),
    }
    by_task = {}
    for tid in heldout_tasks:
        t = f"spatial_{tid}"
        by_task[t] = {arm: _agg([r for r in by_arm[arm] if r["task"] == t]) for arm in ARMS}
    verdict = _verdict(arms, pairwise)
    return {"arms": arms, "pairwise": pairwise, "by_task": by_task,
            "rows": rows, "verdict": verdict}


def _verdict(arms, pw):
    b, a, c = arms["warm_geo"], arms["warm_dumpall"], arms["cold"]
    lines = []
    if b["success_rate"] > c["success_rate"] and pw["B_vs_C"] < 0.10:
        lines.append(f"H1-COVERAGE reproduced (suggestive, N=5/arm/task): warm_geo "
                     f"{b['success_rate']:.2f} > cold {c['success_rate']:.2f}, "
                     f"Fisher p(B,C)={pw['B_vs_C']:.4f} < 0.10.")
    if b["success_rate"] > a["success_rate"] and pw["B_vs_A"] < 0.10:
        lines.append(f"H1-RETRIEVAL is the bottleneck (suggestive): warm_geo "
                     f"{b['success_rate']:.2f} > warm_dumpall {a['success_rate']:.2f}, "
                     f"Fisher p(B,A)={pw['B_vs_A']:.4f} < 0.10.")
    if not lines:
        lines.append(f"H0 (null, N=5/arm/task): no arm pair separated at p<0.10 "
                     f"(warm_geo {b['success_rate']:.2f}, warm_dumpall "
                     f"{a['success_rate']:.2f}, cold {c['success_rate']:.2f}; "
                     f"p(B,C)={pw['B_vs_C']:.4f}, p(B,A)={pw['B_vs_A']:.4f}).")
    return " ".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--heldout", required=True, help="comma-separated task ids, e.g. 3,6,8")
    args = ap.parse_args()
    heldout = args.heldout.split(",")
    rep = build_tiling_report(args.root, heldout)
    (Path(args.root) / "results.json").write_text(json.dumps(rep, indent=1))
    for arm in ARMS:
        a = rep["arms"][arm]
        print(f"  {arm}: {a['success_rate']:.2f} ({a['n_solved']}/{a['n']}), "
              f"mean_attempts={a['mean_attempts_solved_only']}")
    print("  pairwise Fisher p:", rep["pairwise"])
    print("VERDICT:", rep["verdict"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_analysis.py -q -p no:anyio`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_libero_tiling.py tests/aspire/test_libero_tiling_analysis.py
git commit -m "feat: three-arm tiling analyzer with pairwise Fisher-exact"
```

---

### Task 5: Bowl-xy probe + skill-tagging helpers

**Files:**
- Create: `scripts/capx_bowl_xy.py` (runs in `.venv-libero`; prints `x,y`)
- Create: `scripts/tag_skill_xy.py` (pure; stamps untagged skill files in a library dir)
- Test: `tests/aspire/test_libero_tiling_tagxy.py` (tests `tag_skill_xy` only; the probe needs GPU and is exercised live by the runner)

**Interfaces:**
- Consumes: `aspire.skill_library.parse_skill`, `render_skill`; capx api `get_object_pose("black_bowl")`.
- Produces: `tag_skill_xy.tag_untagged(library_dir, xy_str) -> int` (rewrites every skill file whose `source_xy` is empty, setting it to `xy_str`; returns count stamped). `capx_bowl_xy.py --config-path <cfg>` prints one line `x,y` (bowl x,y from a privileged observation).

- [ ] **Step 1: Write the failing test for `tag_untagged`**

```python
# tests/aspire/test_libero_tiling_tagxy.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from tag_skill_xy import tag_untagged
from aspire.skill_library import Skill, SkillLibrary, parse_skill


def test_stamps_only_untagged(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.add(Skill(name="fresh", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s"))                       # untagged
    lib.add(Skill(name="already", category="grasping", failure_signature="f",
                  when_to_apply="w", strategy="s", source_xy="0.5,0.5"))  # tagged
    n = tag_untagged(tmp_path, "0.1,0.2")
    assert n == 1
    by_name = {s.name: s for s in lib.load_all()}
    assert by_name["fresh"].source_xy == "0.1,0.2"
    assert by_name["already"].source_xy == "0.5,0.5"   # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_tagxy.py -q -p no:anyio`
Expected: FAIL (`ModuleNotFoundError: No module named 'tag_skill_xy'`)

- [ ] **Step 3: Implement `scripts/tag_skill_xy.py`**

```python
#!/usr/bin/env python3
"""Stamp untagged skill files in a library dir with a source_xy. Idempotent:
skills that already carry a source_xy are left untouched."""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aspire.skill_library import parse_skill, render_skill
from dataclasses import replace


def tag_untagged(library_dir, xy_str) -> int:
    n = 0
    for p in sorted(Path(library_dir).glob("*/*.md")):
        s = parse_skill(p.read_text())
        if s.source_xy:
            continue
        p.write_text(render_skill(replace(s, source_xy=xy_str)))
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", required=True)
    ap.add_argument("--xy", required=True, help='e.g. "0.10,-0.04"')
    args = ap.parse_args()
    print(tag_untagged(args.library, args.xy))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_tagxy.py -q -p no:anyio`
Expected: PASS (1 passed). NOTE: `index.md` lives at the library root (`*.md`, not `*/*.md`), so the `*/*.md` glob correctly skips it.

- [ ] **Step 5: Implement `scripts/capx_bowl_xy.py` (probe; no unit test — needs LIBERO)**

Mirror how `scripts/capx_execute.py` constructs the api from `--config-path` (read that file first to copy the exact construction), then:

```python
#!/usr/bin/env python3
"""Print 'x,y' of the black_bowl for a LIBERO task. Runs in .venv-libero.
Usage: capx_bowl_xy.py --workdir /home/demo/cap-x --config-path <cfg>"""
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--config-path", required=True)
    args = ap.parse_args()
    # Construct the FrankaLiberoApi exactly as capx_execute.py does (copy that
    # setup: chdir workdir, load config, instantiate the privileged api), then:
    api = _build_api(args.workdir, args.config_path)   # per capx_execute.py
    pose = api.get_object_pose("black_bowl", use_multiview=False)
    x, y = float(pose[0]), float(pose[1])
    print(f"{x:.5f},{y:.5f}")

if __name__ == "__main__":
    main()
```

The implementer MUST open `scripts/capx_execute.py` and reuse its exact api-construction (workdir chdir, config load, api class) for `_build_api`; do not invent a new construction path. If the pose accessor differs there, match capx_execute.

- [ ] **Step 6: Live smoke of the probe (not a unit test — requires `.venv-libero` + GPU)**

Run: `MUJOCO_GL=egl /home/demo/cap-x/.venv-libero/bin/python scripts/capx_bowl_xy.py --workdir /home/demo/cap-x --config-path /home/demo/cap-x/env_configs/libero/franka_libero_spatial_0_privileged.yaml`
Expected: one line like `-0.02100,0.13400`. If it errors, fix `_build_api` against `capx_execute.py` before proceeding. (This step is run by the human/controller, not inside pytest.)

- [ ] **Step 7: Commit**

```bash
git add scripts/tag_skill_xy.py scripts/capx_bowl_xy.py tests/aspire/test_libero_tiling_tagxy.py
git commit -m "feat: bowl-xy probe (.venv-libero) + idempotent skill-xy tagger"
```

---

### Task 6: Tiling runner + config snapshot + dry-run test

**Files:**
- Create: `scripts/libero_tiling.sh`
- Create: `runs/2026-07-24-libero-tiling/franka_libero_spatial_0_privileged.yaml` (snapshot copy of the cap-x template)
- Test: `tests/aspire/test_libero_tiling_runner_dryrun.py`

**Interfaces:**
- Consumes: `scripts/capx_execute.py`, `scripts/capx_bowl_xy.py`, `scripts/tag_skill_xy.py`, `scripts/analyze_libero_tiling.py`, `runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py`, env hooks `ASPIRE_RETRIEVAL`/`ASPIRE_TARGET_XY`.
- Produces: a committed, idempotent runner with `DRY=1` support; writes `$ROOT/selected_tasks.json` and per-arm run dirs `test/spatial_<tid>/{warm_geo,warm_dumpall,cold}/<rep>`.

- [ ] **Step 1: Snapshot the config template**

```bash
cp /home/demo/cap-x/env_configs/libero/franka_libero_spatial_0_privileged.yaml \
   runs/2026-07-24-libero-tiling/franka_libero_spatial_0_privileged.yaml
```

- [ ] **Step 2: Write the failing dry-run test**

```python
# tests/aspire/test_libero_tiling_runner_dryrun.py
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_runner_dry_run_lists_phases_arms_and_budgets():
    proc = subprocess.run(["bash", "scripts/libero_tiling.sh"],
                          capture_output=True, text=True, cwd=REPO,
                          env={"DRY": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
                               "ROOT": "/tmp/libero_tiling_dry"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for token in ("PHASE 0", "PHASE 1", "PHASE 2", "PHASE 3", "PHASE 4",
                  ".venv-libero", "--t 5", "--t 2",
                  "warm_geo", "warm_dumpall", "cold",
                  "ASPIRE_RETRIEVAL=geometry"):
        assert token in out, f"missing {token}"
    # accumulate ids and held-out ids both appear
    assert "task_id: 0" in out and "task_id: 3" in out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_runner_dryrun.py -q -p no:anyio`
Expected: FAIL (`No such file or directory: scripts/libero_tiling.sh`)

- [ ] **Step 4: Implement `scripts/libero_tiling.sh`**

Model `run_one` on `scripts/libero_accumulation_v2b_hardfrontier.sh`, adding a 5th arg for extra env (retrieval mode). Full script:

```bash
#!/bin/bash
# ASPIRE LIBERO tiling-curriculum + retrieval-discrimination campaign
# (spec: docs/superpowers/specs/2026-07-24-libero-tiling-curriculum-design.md).
# Three arms over a tiled library: warm_geo (geometry retrieval) vs warm_dumpall
# (stock retrieval) vs cold (empty). Separates COVERAGE from RETRIEVAL.
set -u
cd "$(dirname "$0")/.."
REPO="$PWD"
VENV=/home/demo/cap-x/.venv-libero/bin/python
CAPX="$REPO/scripts/capx_execute.py"
BOWLXY="$REPO/scripts/capx_bowl_xy.py"
TAGXY="$REPO/scripts/tag_skill_xy.py"
RUNS="$REPO/runs/2026-07-24-libero-tiling"
TMPL="$RUNS/franka_libero_spatial_0_privileged.yaml"
BASELINE="$REPO/runs/2026-07-22-libero-accum-frontier/baseline_grasp_lift.py"
ROOT=${ROOT:-$HOME/aspire_runs/libero_tiling}
CFGDIR="$ROOT/configs"
TILED_LIB="$ROOT/tiled_library"
XYDIR="$ROOT/bowl_xy"
DRY=${DRY:-0}
ACCUM_TASKS=(0 1 2 4 5 7 9)      # tile the location space
HELDOUT_TASKS=(3 6 8)            # fixed, pre-registered; not in ACCUM_TASKS
REPEATS=5
ACCUM_T=5
TEST_T=2

mkdir -p "$ROOT" "$CFGDIR" "$XYDIR"
gen_cfg() { local tid=$1; local out="$CFGDIR/spatial_$tid.yaml"; sed "s/task_id: 0/task_id: $tid/" "$TMPL" > "$out"; echo "$out"; }

# run_one <task_id> <library> <sub> <t> <extra_env>
run_one() {
  local tid=$1 lib=$2 sub=$3 t=$4 extra=${5:-}
  local cfg; cfg=$(gen_cfg "$tid")
  local rdir="$ROOT/$sub" task="$ROOT/$sub/task" out="$ROOT/$sub/exec"
  if [ -f "$rdir/DONE" ]; then echo "skip $sub (DONE)"; return; fi
  local capxcmd="$VENV $CAPX --workdir /home/demo/cap-x --config-path $cfg"
  if [ "$DRY" = 1 ]; then
    echo "[dry] $sub: aspire.run --library $lib --t $t  env[$extra]  ($(grep -o 'task_id: [0-9]*' "$cfg"))"; return
  fi
  mkdir -p "$task" "$out"; cp "$BASELINE" "$task/code.py"
  env $extra MUJOCO_GL=egl PATH="$HOME/.local/bin:$PATH" python3 -m aspire.run \
    --task-dir "$task" --engine capx --capx-cmd "$capxcmd" \
    --out-root "$out" --library "$lib" --s-dbg 0 --s-val 100 --t "$t" \
    2>&1 | tee "$rdir/log.txt" | tail -1 > "$rdir/summary.json"
  touch "$rdir/DONE"
}

bowl_xy() {  # bowl_xy <task_id> -> echoes "x,y" (cached)
  local tid=$1 f="$XYDIR/spatial_$tid.txt"
  if [ ! -s "$f" ]; then
    MUJOCO_GL=egl "$VENV" "$BOWLXY" --workdir /home/demo/cap-x --config-path "$(gen_cfg "$tid")" > "$f"
  fi
  cat "$f"
}

echo "=== PHASE 0: preflight + config gen ==="
if [ "$DRY" != 1 ]; then
  $VENV -c "import robosuite,sys; sys.exit(0 if robosuite.__version__.startswith('1.4') else 1)" \
    || { echo "FATAL: .venv-libero robosuite not 1.4.x. Aborting."; exit 1; }
else echo "[dry] PHASE 0 preflight: assert $VENV robosuite startswith 1.4"; fi
for tid in "${ACCUM_TASKS[@]}" "${HELDOUT_TASKS[@]}"; do gen_cfg "$tid" >/dev/null; done

echo "=== PHASE 1: tile-accumulate deeper baseline on {${ACCUM_TASKS[*]}} at --t $ACCUM_T -> $TILED_LIB ==="
mkdir -p "$TILED_LIB"
for tid in "${ACCUM_TASKS[@]}"; do
  run_one "$tid" "$TILED_LIB" "accumulate/spatial_$tid" "$ACCUM_T"
  if [ "$DRY" != 1 ]; then
    xy=$(bowl_xy "$tid"); "$VENV" "$TAGXY" --library "$TILED_LIB" --xy "$xy" >/dev/null   # stamp new skills with this task's bowl xy
  else echo "[dry] tag new skills in $TILED_LIB with bowl xy of task_id $tid"; fi
done
if [ "$DRY" != 1 ]; then
  ntag=$("$VENV" -c "from aspire.skill_library import SkillLibrary; import collections; xs=[s.source_xy for s in SkillLibrary('$TILED_LIB').load_all() if s.source_xy]; print(len(xs), len(set(xs)))")
  set -- $ntag; echo "=== tiled library: $1 tagged skills from $2 distinct locations ==="
  { [ "$1" -ge 2 ] && [ "$2" -ge 2 ]; } || { echo "GATE FAIL: need >=2 tagged skills from >=2 locations to tile. Stopping."; exit 2; }
fi

echo "=== PHASE 2: fixed held-out tasks = ${HELDOUT_TASKS[*]} ==="
printf '[%s]\n' "$(IFS=,; echo "${HELDOUT_TASKS[*]}")" > "$ROOT/selected_tasks.json"

echo "=== PHASE 3: three arms (warm_geo / warm_dumpall / cold), $REPEATS/arm, --t $TEST_T ==="
for tid in "${HELDOUT_TASKS[@]}"; do
  [ "$DRY" = 1 ] && txy="0.0,0.0" || txy=$(bowl_xy "$tid")
  for rep in $(seq 1 "$REPEATS"); do
    # Arm B: warm_geo (geometry retrieval, single nearest-location skill)
    wg="$ROOT/test/spatial_$tid/warm_geo/$rep/lib"; mkdir -p "$wg"
    [ "$DRY" = 1 ] || cp -r "$TILED_LIB/." "$wg/" 2>/dev/null
    run_one "$tid" "$wg" "test/spatial_$tid/warm_geo/$rep" "$TEST_T" "ASPIRE_RETRIEVAL=geometry ASPIRE_TARGET_XY=$txy"
    # Arm A: warm_dumpall (stock retrieval)
    wd="$ROOT/test/spatial_$tid/warm_dumpall/$rep/lib"; mkdir -p "$wd"
    [ "$DRY" = 1 ] || cp -r "$TILED_LIB/." "$wd/" 2>/dev/null
    run_one "$tid" "$wd" "test/spatial_$tid/warm_dumpall/$rep" "$TEST_T"
    # Arm C: cold (empty)
    run_one "$tid" "$ROOT/test/spatial_$tid/cold/$rep/lib" "test/spatial_$tid/cold/$rep" "$TEST_T"
  done
done

echo "=== PHASE 4: ANALYZE ==="
if [ "$DRY" != 1 ]; then
  python3 "$REPO/scripts/analyze_libero_tiling.py" --root "$ROOT" --heldout "$(IFS=,; echo "${HELDOUT_TASKS[*]}")"
else echo "[dry] analyze --root $ROOT --heldout $(IFS=,; echo "${HELDOUT_TASKS[*]}")"; fi
echo "=== TILING CAMPAIGN DONE root=$ROOT ==="
```

- [ ] **Step 5: Run the dry-run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_libero_tiling_runner_dryrun.py -q -p no:anyio`
Expected: PASS (1 passed). If a token is missing, fix the echo/command lines until all appear.

- [ ] **Step 6: Full-suite green**

Run: `python3 -m pytest tests/ -q -p no:anyio`
Expected: PASS (prior + all new tiling tests).

- [ ] **Step 7: Commit**

```bash
git add scripts/libero_tiling.sh runs/2026-07-24-libero-tiling/franka_libero_spatial_0_privileged.yaml tests/aspire/test_libero_tiling_runner_dryrun.py
git commit -m "feat: three-arm tiling campaign runner + config snapshot (DRY-tested)"
```

---

## Execution note (after all tasks built + committed)

The runner is a long GPU+credits job — execute it under the autonomous loop, NOT inside a task:

```bash
ROOT="$HOME/aspire_runs/libero_tiling" bash scripts/libero_tiling.sh \
  > runs/2026-07-24-libero-tiling/campaign.log 2>&1   # run_in_background
```

Pre-launch checks (same as prior campaigns): LLM proxy `:8110` UP, robosuite 1.4.0 in `.venv-libero`, and one live smoke of `capx_bowl_xy.py` (Task 5 Step 6) so bowl-xy probing works before Phase 1. Then drive the loop: on completion run the analyzer, apply the pre-registered verdict rule, commit `results.json` + `FINDINGS.md`, and ping only at the terminal state with the actual pairwise Fisher p values.
