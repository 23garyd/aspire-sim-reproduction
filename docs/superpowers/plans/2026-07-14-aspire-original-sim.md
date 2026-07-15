# ASPIRE Original-Sim Reproduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ASPIRE orchestration layer (traces → trace-guided debugging → skill library → Algorithm-1 evolutionary search) over an unmodified CaP-X install, per spec `docs/superpowers/specs/2026-07-14-aspire-original-sim-design.md`.

**Architecture:** A stdlib-only Python package `aspire/` whose every component is duck-typed against fakes (`FakeEngine`, `FakeActor`, `FakeJudge`) so the whole pipeline is TDD-able on the Mac with no GPU. The only two components that touch the outside world — `CapxEngine` (subprocess → CaP-X on simhost) and `ClaudeCodeActor` (subprocess → headless `claude -p`) — are thin wrappers around a pinned JSON file contract, tested with shim executables.

**Tech Stack:** Python 3.10 stdlib (dataclasses, json, pathlib, subprocess, re), pytest. CaP-X (uv-managed, on simhost only). Headless Claude Code CLI.

**Working state notes:**
- Branch: `aspire_original_sim`. Existing `robot_engine/` and `tests/test_*.py` (27 A2 tests) must stay green; new tests live in `tests/aspire/`.
- Run all tests: `python3 -m pytest -q` (on simhost add `-p no:anyio`).
- The paper's file conventions (spec "Ground truth" section) are the on-disk state machine: `code.py`, `fix_code.py`, `iter_XX/candidate_A/code.py`, `iter_summary.json`, `evosearch_best_code.py`, `VALIDATION_DONE`, `TAINTED`.

**File structure (locked here):**

```
aspire/
  __init__.py
  config.py          # RunConfig (K, T, theta, seeds, model tiers)
  schemas.py         # TraceRecord, ExecuteResult, ProposedSkill, ActorReport
  audit.py           # mechanical code audit (forbidden APIs, seed branches)
  skill_library.py   # Skill, markdown render/parse, SkillLibrary
  engines.py         # EngineAdapter protocol, FakeEngine, CapxEngine
  actors.py          # Actor/Judge protocols, FakeActor, FakeJudge, ClaudeCodeActor, ClaudeJudge
  evosearch.py       # Algorithm 1 + disk checkpoint/resume
  coordinator.py     # TaskPipeline: Stage0→Stage1→evosearch→Stage2→admission
  run.py             # python -m aspire.run CLI (fake-engine dry run + real dispatch)
prompts/
  actor_debug.md
  actor_evosearch.md
  coordinator_admission.md
scripts/
  capx_execute.py    # runs INSIDE cap-x venv on simhost; emits result.json (contract pinned by tests)
  m0_rig_up.sh       # simhost: install cap-x, smoke test, capture golden episode
  m1_baseline.sh     # simhost: CaP-Agent0 baseline campaign
tests/aspire/
  __init__.py
  test_config.py  test_schemas.py  test_audit.py  test_skill_library.py
  test_engines.py  test_actors.py  test_evosearch.py  test_coordinator.py  test_run.py
```

---

### Task 1: Package scaffold + RunConfig

**Files:**
- Create: `aspire/__init__.py` (empty), `tests/aspire/__init__.py` (empty)
- Create: `aspire/config.py`
- Test: `tests/aspire/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_config.py
from aspire.config import RunConfig


def test_defaults_match_spec_reconstructed_values():
    cfg = RunConfig()
    assert cfg.k == 3 and cfg.t == 5 and cfg.theta == 1.0
    assert cfg.debug_rounds == 2
    assert cfg.s_dbg and cfg.s_val
    assert not (set(cfg.s_dbg) & set(cfg.s_val)), "debug and validation seeds must not overlap"
    assert cfg.model_repair == "opus"
    assert cfg.model_propose == "sonnet"


def test_to_dict_round_trip():
    cfg = RunConfig(k=5, s_dbg=[1, 2], s_val=[9])
    assert RunConfig(**cfg.to_dict()) == cfg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aspire'`

- [ ] **Step 3: Write minimal implementation**

```python
# aspire/config.py
"""Run parameters. K, T, theta are NOT published in the paper (Appendix E marks them
experiment-specific); these defaults are [RECONSTRUCTED] and must be logged per run."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RunConfig:
    k: int = 3                    # evosearch population per round
    t: int = 5                    # evosearch max rounds
    theta: float = 1.0            # early-stop score on debugging seeds
    debug_rounds: int = 2         # Stage-1 actor repair rounds before evosearch
    s_dbg: list = field(default_factory=lambda: [0, 1, 2])
    s_val: list = field(default_factory=lambda: [100, 101, 102, 103, 104])
    model_repair: str = "opus"    # diagnosis/repair/skill synthesis
    model_propose: str = "sonnet" # evosearch candidate proposals

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_config.py -q`
Expected: 2 passed

- [ ] **Step 5: Full suite still green, then commit**

Run: `python3 -m pytest -q`  → 27 old + 2 new pass
```bash
git add aspire/__init__.py aspire/config.py tests/aspire/
git commit -m "feat(aspire): package scaffold + RunConfig with [RECONSTRUCTED] defaults"
```

---

### Task 2: Trace and execution schemas

**Files:**
- Create: `aspire/schemas.py`
- Test: `tests/aspire/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/aspire/test_schemas.py
import json

from aspire.schemas import ExecuteResult, TraceRecord


def make_trace(**kw):
    d = dict(step=1, function="grasp_object", args={"arm": 0}, status="ok",
             result_summary="in_hand=True", duration_ms=812.5, media=["kf_001.png"])
    d.update(kw)
    return TraceRecord(**d)


def test_trace_round_trip():
    tr = make_trace()
    assert TraceRecord.from_dict(tr.to_dict()) == tr


def test_execute_result_json_round_trip(tmp_path):
    res = ExecuteResult(score=0.6, traces=[make_trace(), make_trace(step=2, status="error")],
                        raw_dir="runs/x")
    p = tmp_path / "result.json"
    p.write_text(res.to_json())
    loaded = ExecuteResult.from_json(p.read_text())
    assert loaded == res
    assert json.loads(res.to_json())["score"] == 0.6  # plain-JSON contract for capx_execute.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/aspire/test_schemas.py -q`
Expected: FAIL — no module `aspire.schemas`

- [ ] **Step 3: Write minimal implementation**

```python
# aspire/schemas.py
"""On-disk contracts. ExecuteResult JSON is the pinned contract between the orchestrator
and scripts/capx_execute.py; change it only with a test change."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TraceRecord:
    step: int
    function: str
    args: dict
    status: str            # "ok" | "error"
    result_summary: str
    duration_ms: float
    media: list = field(default_factory=list)   # engine-relative paths (keyframes, overlays)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TraceRecord":
        return cls(**d)


@dataclass(frozen=True)
class ExecuteResult:
    score: float           # fraction of seeds succeeded, 0..1
    traces: tuple = ()     # tuple[TraceRecord, ...] (tuple => frozen dataclass hashable)
    raw_dir: str = ""

    def __init__(self, score: float, traces=(), raw_dir: str = ""):
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "traces", tuple(traces))
        object.__setattr__(self, "raw_dir", raw_dir)

    def to_json(self) -> str:
        return json.dumps({"score": self.score, "raw_dir": self.raw_dir,
                           "traces": [t.to_dict() for t in self.traces]}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "ExecuteResult":
        d = json.loads(text)
        return cls(score=d["score"], raw_dir=d.get("raw_dir", ""),
                   traces=[TraceRecord.from_dict(t) for t in d.get("traces", [])])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/aspire/test_schemas.py -q` → 2 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/schemas.py tests/aspire/test_schemas.py
git commit -m "feat(aspire): TraceRecord + ExecuteResult with pinned JSON contract"
```

---

### Task 3: Actor report contract

**Files:**
- Modify: `aspire/schemas.py` (append)
- Test: `tests/aspire/test_schemas.py` (append)

- [ ] **Step 1: Write the failing tests (append to test_schemas.py)**

```python
import pytest

from aspire.schemas import ActorReport, ProposedSkill, ReportError


def test_actor_report_load(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({
        "outcome": "success", "diagnosis": "goal pose inside collision buffer",
        "code_path": "fix_code.py",
        "proposed_skills": [{
            "name": "multi-angle-approach", "category": "navigation",
            "failure_signature": "repeated PLANNING_ERROR near obstacle",
            "when_to_apply": "nav goals fall inside collision-avoidance buffer",
            "strategy": "rotate approach vector by 45/90/180 deg", "code_sketch": "for a in ..."}],
    }))
    r = ActorReport.load(p)
    assert r.outcome == "success"
    assert r.proposed_skills[0].category == "navigation"


def test_actor_report_missing_field_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "fail"}))
    with pytest.raises(ReportError, match="missing"):
        ActorReport.load(p)


def test_actor_report_bad_outcome_raises(tmp_path):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"outcome": "maybe", "diagnosis": "x", "code_path": "c.py"}))
    with pytest.raises(ReportError, match="outcome"):
        ActorReport.load(p)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/aspire/test_schemas.py -q`
Expected: FAIL — cannot import `ActorReport`

- [ ] **Step 3: Implement (append to aspire/schemas.py)**

```python
class ReportError(ValueError):
    """report.json missing, malformed, or violating the contract."""


@dataclass(frozen=True)
class ProposedSkill:
    name: str
    category: str
    failure_signature: str
    when_to_apply: str
    strategy: str
    code_sketch: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ActorReport:
    outcome: str                   # "success" | "fail"
    diagnosis: str
    code_path: str                 # final program, relative to the task dir
    proposed_skills: tuple = ()

    _REQUIRED = ("outcome", "diagnosis", "code_path")

    @classmethod
    def load(cls, path) -> "ActorReport":
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise ReportError(f"cannot read report.json: {e}") from e
        missing = [k for k in cls._REQUIRED if k not in data]
        if missing:
            raise ReportError(f"report.json missing fields: {missing}")
        if data["outcome"] not in ("success", "fail"):
            raise ReportError(f"bad outcome: {data['outcome']!r}")
        skills = tuple(ProposedSkill(**s) for s in data.get("proposed_skills", []))
        return cls(outcome=data["outcome"], diagnosis=data["diagnosis"],
                   code_path=data["code_path"], proposed_skills=skills)
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_schemas.py -q` → 5 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/schemas.py tests/aspire/test_schemas.py
git commit -m "feat(aspire): ActorReport/ProposedSkill report.json contract"
```

---

### Task 4: Mechanical code audit

**Files:**
- Create: `aspire/audit.py`
- Test: `tests/aspire/test_audit.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_audit.py
from aspire.audit import audit_code


def test_clean_code_passes():
    assert audit_code("pos = get_robot_position()\nnavigate_to_pose([1, 2, 0.5])") == []


def test_forbidden_sim_handle_flagged():
    v = audit_code("q = env.handle.env.sim.data.qpos")
    assert any("env.handle.env.sim" in x for x in v)


def test_reading_asset_files_flagged():
    for fname in ("scene.xml", "task.bddl", "robot.urdf"):
        v = audit_code(f"data = open('{fname}').read()")
        assert v, f"{fname} should be flagged"


def test_seed_specific_branch_flagged():
    v = audit_code("if seed == 3:\n    target_z = 0.91")
    assert any("seed" in x for x in v)


def test_seed_word_in_comment_ok():
    assert audit_code("# works across seeds\nx = 1") == []
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_audit.py -q` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# aspire/audit.py
"""Coordinator-side mechanical audit (paper's forbidden-API wall + no seed-specific
branches in generalizable code). Returns human-readable violations; empty = clean."""
from __future__ import annotations

import re

_FORBIDDEN_SUBSTRINGS = ("env.handle.env.sim",)
# quoted paths to sim asset files the paper forbids reading
_ASSET_RE = re.compile(r"""['"][^'"]*\.(?:bddl|urdf|xml)['"]""")
_SEED_BRANCH_RE = re.compile(r"\bseed\b\s*(?:==|!=|<=|>=|<|>|\bin\b)")


def _strip_comments(code: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in code.splitlines())


def audit_code(code: str) -> list[str]:
    body = _strip_comments(code)
    violations = []
    for s in _FORBIDDEN_SUBSTRINGS:
        if s in body:
            violations.append(f"forbidden API access: {s}")
    for m in _ASSET_RE.finditer(body):
        violations.append(f"reads sim asset file: {m.group(0)}")
    if _SEED_BRANCH_RE.search(body):
        violations.append("seed-specific branch (fix_code.py must generalize across seeds)")
    return violations
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_audit.py -q` → 5 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/audit.py tests/aspire/test_audit.py
git commit -m "feat(aspire): mechanical audit — forbidden APIs, asset reads, seed branches"
```

---

### Task 5: Skill markdown + SkillLibrary

**Files:**
- Create: `aspire/skill_library.py`
- Test: `tests/aspire/test_skill_library.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_skill_library.py
from aspire.schemas import ProposedSkill
from aspire.skill_library import Skill, SkillLibrary, parse_skill, render_skill


def make_skill(**kw):
    d = dict(name="multi-angle-approach", category="navigation",
             failure_signature="repeated PLANNING_ERROR near obstacle boundary",
             when_to_apply="nav goals fall inside the collision-avoidance buffer",
             strategy="rotate the approach vector by 45/90/180 degrees",
             code_sketch="for a in [180, -90, 90]: ...",
             provenance="robosuite/handover seeds 0-2 + val 100-104")
    d.update(kw)
    return Skill(**d)


def test_render_parse_round_trip():
    s = make_skill()
    assert parse_skill(render_skill(s)) == s


def test_add_writes_file_and_index(tmp_path):
    lib = SkillLibrary(tmp_path)
    path = lib.add(make_skill())
    assert path.exists() and path.suffix == ".md"
    assert "multi-angle-approach" in (tmp_path / "index.md").read_text()


def test_retrieve_by_category_and_keyword(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.add(make_skill())
    lib.add(make_skill(name="obb-axis-grasp", category="grasping",
                       failure_signature="grasp slips on box lid",
                       when_to_apply="thin box-like objects",
                       strategy="align gripper with shortest OBB axis"))
    nav = lib.retrieve(categories=["navigation"])
    assert [s.name for s in nav] == ["multi-angle-approach"]
    hits = lib.retrieve(keywords=["PLANNING_ERROR"])
    assert [s.name for s in hits] == ["multi-angle-approach"]
    assert len(lib.retrieve()) == 2


def test_from_proposed_adds_provenance():
    p = ProposedSkill(name="n", category="c", failure_signature="f",
                      when_to_apply="w", strategy="s")
    s = Skill.from_proposed(p, provenance="task X")
    assert s.provenance == "task X" and s.name == "n"
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_skill_library.py -q` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# aspire/skill_library.py
"""Paper-format skill storage: one markdown file per skill + index.md. Retrieval is
category/keyword match (spec: embeddings only if this proves insufficient)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from aspire.schemas import ProposedSkill

_SECTIONS = ("failure_signature", "when_to_apply", "strategy", "code_sketch", "provenance")
_TITLES = {"failure_signature": "Failure signature", "when_to_apply": "When to apply",
           "strategy": "Strategy", "code_sketch": "Code sketch", "provenance": "Provenance"}


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    failure_signature: str
    when_to_apply: str
    strategy: str
    code_sketch: str = ""
    provenance: str = ""

    @classmethod
    def from_proposed(cls, p: ProposedSkill, provenance: str) -> "Skill":
        return cls(provenance=provenance, **p.to_dict())


def render_skill(s: Skill) -> str:
    parts = [f"# {s.name}", f"category: {s.category}"]
    for key in _SECTIONS:
        parts += [f"## {_TITLES[key]}", getattr(s, key)]
    return "\n\n".join(parts) + "\n"


def parse_skill(text: str) -> Skill:
    name = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    category = re.search(r"^category: (.+)$", text, re.M).group(1).strip()
    fields = {}
    for key in _SECTIONS:
        m = re.search(rf"^## {re.escape(_TITLES[key])}\n\n(.*?)(?=\n\n## |\Z)", text, re.S | re.M)
        fields[key] = m.group(1).strip() if m else ""
    return Skill(name=name, category=category, **fields)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class SkillLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, skill: Skill) -> Path:
        d = self.root / skill.category
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{_slug(skill.name)}.md"
        path.write_text(render_skill(skill))
        self._reindex()
        return path

    def load_all(self) -> list[Skill]:
        return [parse_skill(p.read_text())
                for p in sorted(self.root.glob("*/*.md"))]

    def retrieve(self, categories=None, keywords=None) -> list[Skill]:
        out = []
        for s in self.load_all():
            if categories and s.category not in categories:
                continue
            if keywords:
                blob = " ".join(asdict(s).values()).lower()
                if not any(k.lower() in blob for k in keywords):
                    continue
            out.append(s)
        return out

    def _reindex(self) -> None:
        lines = ["# Skill index", ""]
        for s in self.load_all():
            lines.append(f"- [{s.name}]({s.category}/{_slug(s.name)}.md) — "
                         f"{s.category}: {s.when_to_apply}")
        (self.root / "index.md").write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_skill_library.py -q` → 4 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/skill_library.py tests/aspire/test_skill_library.py
git commit -m "feat(aspire): markdown skill library with category/keyword retrieval"
```

---

### Task 6: Engine protocol + FakeEngine + CapxEngine subprocess wrapper

**Files:**
- Create: `aspire/engines.py`
- Test: `tests/aspire/test_engines.py`

The CaP-X side of the contract is `scripts/capx_execute.py` (Task 11, adapted on-box in M0).
`CapxEngine` only needs: run a command, read `result.json` (the Task-2 contract) from an
output dir. That is fully testable today with a stub command.

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_engines.py
import json
import sys

import pytest

from aspire.engines import CapxEngine, EngineError, FakeEngine
from aspire.schemas import ExecuteResult


def test_fake_engine_pops_scripted_results(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    eng = FakeEngine([ExecuteResult(0.2), ExecuteResult(1.0)])
    assert eng.execute(prog, [0, 1, 2]).score == 0.2
    assert eng.execute(prog, [0, 1, 2]).score == 1.0
    assert eng.calls == [(str(prog), (0, 1, 2)), (str(prog), (0, 1, 2))]


def test_fake_engine_exhausted_raises(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    with pytest.raises(EngineError, match="exhausted"):
        FakeEngine([]).execute(prog, [0])


def test_capx_engine_runs_command_and_reads_result(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    out = tmp_path / "out"
    # stub runner: writes a valid result.json into --out-dir
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json,sys,pathlib\n"
        "a=dict(zip(sys.argv[1::2],sys.argv[2::2]))\n"
        "d=pathlib.Path(a['--out-dir']); d.mkdir(parents=True,exist_ok=True)\n"
        "(d/'result.json').write_text(json.dumps({'score':0.4,'raw_dir':str(d),'traces':[]}))\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=out)
    res = eng.execute(prog, [0, 1])
    assert res.score == 0.4


def test_capx_engine_missing_result_raises(tmp_path):
    prog = tmp_path / "code.py"; prog.write_text("pass")
    runner = tmp_path / "noop.py"; runner.write_text("pass\n")
    eng = CapxEngine(cmd_prefix=[sys.executable, str(runner)], out_root=tmp_path / "o")
    with pytest.raises(EngineError, match="result.json"):
        eng.execute(prog, [0])
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_engines.py -q` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# aspire/engines.py
"""Execute(P, S) -> ExecuteResult (Algorithm 1). FakeEngine for tests; CapxEngine shells
out to scripts/capx_execute.py inside the cap-x venv on simhost and reads result.json."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from aspire.schemas import ExecuteResult


class EngineError(RuntimeError):
    pass


class EngineAdapter(Protocol):
    def execute(self, program: Path, seeds: list) -> ExecuteResult: ...


class FakeEngine:
    """Pops scripted ExecuteResults in order; records calls for assertions."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def execute(self, program: Path, seeds: list) -> ExecuteResult:
        self.calls.append((str(program), tuple(seeds)))
        if not self._results:
            raise EngineError("FakeEngine exhausted: more execute() calls than scripted results")
        return self._results.pop(0)


class CapxEngine:
    """cmd_prefix example (simhost):
    ["ssh", "USER@simhost", "cd ~/cap-x && uv run --no-sync python", "~/aspire_runs/capx_execute.py"]
    or locally-on-box: ["uv", "run", "--no-sync", "python", "scripts/capx_execute.py"].
    Contract: runner gets --program --seeds --out-dir, writes <out-dir>/result.json."""

    def __init__(self, cmd_prefix: list, out_root: Path, timeout_s: int = 3600):
        self._prefix = list(cmd_prefix)
        self._out_root = Path(out_root)
        self._timeout = timeout_s
        self._n = 0

    def execute(self, program: Path, seeds: list) -> ExecuteResult:
        self._n += 1
        out_dir = self._out_root / f"exec_{self._n:04d}"
        cmd = self._prefix + ["--program", str(program),
                              "--seeds", ",".join(str(s) for s in seeds),
                              "--out-dir", str(out_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        result_file = out_dir / "result.json"
        if not result_file.exists():
            raise EngineError(
                f"engine produced no result.json (exit {proc.returncode}); "
                f"stderr tail: {proc.stderr[-800:]}")
        return ExecuteResult.from_json(result_file.read_text())
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_engines.py -q` → 4 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/engines.py tests/aspire/test_engines.py
git commit -m "feat(aspire): EngineAdapter protocol, FakeEngine, CapxEngine subprocess wrapper"
```

---

### Task 7: Actor/Judge protocols, fakes, and headless-Claude wrappers

**Files:**
- Create: `aspire/actors.py`
- Test: `tests/aspire/test_actors.py`

`ClaudeCodeActor` is tested with a shim `claude` executable on PATH — no LLM in tests.

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_actors.py
import json
import os
import stat

import pytest

from aspire.actors import (ActorError, ClaudeCodeActor, ClaudeJudge, FakeActor,
                           FakeJudge, ProposeContext)
from aspire.schemas import ActorReport, ProposedSkill


def _report_dict(outcome="success"):
    return {"outcome": outcome, "diagnosis": "d", "code_path": "fix_code.py",
            "proposed_skills": []}


def test_fake_actor_writes_report_and_candidates(tmp_path):
    rep = ActorReport(outcome="fail", diagnosis="d", code_path="code.py")
    actor = FakeActor(reports=[rep], candidate_sources=[["print(1)", "print(2)"]])
    assert actor.run_debug(tmp_path, model="opus") == rep
    ctx = ProposeContext(task_dir=tmp_path, iter_dir=tmp_path / "iter_00",
                         top3=[], skills=[], k=2)
    paths = actor.propose(ctx, model="sonnet")
    assert [p.read_text() for p in paths] == ["print(1)", "print(2)"]
    assert paths[0].parent.name == "candidate_A" and paths[1].parent.name == "candidate_B"


def _make_shim(tmp_path, body):
    shim = tmp_path / "bin" / "claude"
    shim.parent.mkdir(exist_ok=True)
    shim.write_text("#!/bin/bash\n" + body)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return shim.parent


def test_claude_actor_invokes_cli_and_loads_report(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    bin_dir = _make_shim(
        tmp_path,
        'echo "$@" > cli_args.txt\n'
        f"echo '{json.dumps(_report_dict())}' > report.json\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file="prompts/actor_debug.md", timeout_s=30)
    rep = actor.run_debug(task, model="opus")
    assert rep.outcome == "success"
    args = (task / "cli_args.txt").read_text()
    assert "--model opus" in args and "-p" in args


def test_claude_actor_no_report_raises(tmp_path, monkeypatch):
    task = tmp_path / "task"; task.mkdir()
    bin_dir = _make_shim(tmp_path, "true\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    actor = ClaudeCodeActor(prompt_file="prompts/actor_debug.md", timeout_s=30)
    with pytest.raises(ActorError, match="report.json"):
        actor.run_debug(task, model="opus")


def test_fake_judge_and_claude_judge_parse(tmp_path, monkeypatch):
    skill = ProposedSkill(name="n", category="c", failure_signature="f",
                          when_to_apply="w", strategy="s")
    assert FakeJudge([True]).admit(skill) is True
    bin_dir = _make_shim(tmp_path, "echo 'ADMIT: yes — reusable navigation pattern'\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    assert ClaudeJudge(prompt_file="prompts/coordinator_admission.md",
                       workdir=tmp_path).admit(skill) is True
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_actors.py -q` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# aspire/actors.py
"""Actor = one headless Claude Code run in a task dir. The actor's ONLY output contract
is report.json (ActorReport) plus code files it writes; the orchestrator never parses
free text. Judge = one-shot admission decision (paper's coordinator-guided admission)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from aspire.schemas import ActorReport, ProposedSkill, ReportError

_CAND_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class ActorError(RuntimeError):
    pass


@dataclass
class ProposeContext:
    task_dir: Path
    iter_dir: Path
    top3: list                 # list[tuple[program_path, score]] best-first
    skills: list               # list[Skill] injected by coordinator
    k: int = 3
    history_note: str = ""     # short summary of eliminated/blocked branches


class Actor(Protocol):
    def run_debug(self, task_dir: Path, model: str) -> ActorReport: ...
    def propose(self, ctx: ProposeContext, model: str) -> list: ...


class Judge(Protocol):
    def admit(self, skill: ProposedSkill) -> bool: ...


class FakeActor:
    def __init__(self, reports=(), candidate_sources=()):
        self._reports = list(reports)
        self._sources = list(candidate_sources)
        self.debug_calls, self.propose_calls = [], []

    def run_debug(self, task_dir: Path, model: str) -> ActorReport:
        self.debug_calls.append((str(task_dir), model))
        if not self._reports:
            raise ActorError("FakeActor: no scripted reports left")
        return self._reports.pop(0)

    def propose(self, ctx: ProposeContext, model: str) -> list:
        self.propose_calls.append((str(ctx.iter_dir), model, ctx.k))
        sources = self._sources.pop(0)
        paths = []
        for i, src in enumerate(sources[:ctx.k]):
            d = ctx.iter_dir / f"candidate_{_CAND_LETTERS[i]}"
            d.mkdir(parents=True, exist_ok=True)
            p = d / "code.py"
            p.write_text(src)
            paths.append(p)
        return paths


class FakeJudge:
    def __init__(self, decisions):
        self._d = list(decisions)

    def admit(self, skill: ProposedSkill) -> bool:
        return self._d.pop(0)


def _run_claude(prompt: str, cwd: Path, model: str, timeout_s: int) -> str:
    proc = subprocess.run(["claude", "-p", prompt, "--model", model],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise ActorError(f"claude exited {proc.returncode}: {proc.stderr[-800:]}")
    return proc.stdout


class ClaudeCodeActor:
    def __init__(self, prompt_file: str, timeout_s: int = 7200):
        self._prompt_file = prompt_file
        self._timeout = timeout_s

    def _prompt(self) -> str:
        return Path(self._prompt_file).read_text()

    def run_debug(self, task_dir: Path, model: str) -> ActorReport:
        _run_claude(self._prompt(), task_dir, model, self._timeout)
        report = task_dir / "report.json"
        if not report.exists():
            raise ActorError("actor finished without writing report.json")
        try:
            return ActorReport.load(report)
        except ReportError as e:
            raise ActorError(str(e)) from e

    def propose(self, ctx: ProposeContext, model: str) -> list:
        ctx.iter_dir.mkdir(parents=True, exist_ok=True)
        extra = (f"\n\n## This round\nWrite exactly {ctx.k} candidates to "
                 f"{ctx.iter_dir}/candidate_<LETTER>/code.py (A..). "
                 f"Top programs so far: {[(str(p), s) for p, s in ctx.top3]}. "
                 f"{ctx.history_note}")
        _run_claude(self._prompt() + extra, ctx.task_dir, model, self._timeout)
        paths = sorted(ctx.iter_dir.glob("candidate_*/code.py"))
        if not paths:
            raise ActorError("proposer wrote no candidate_*/code.py files")
        return paths


class ClaudeJudge:
    """One-shot admission: reply must contain a line starting 'ADMIT: yes' or 'ADMIT: no'."""

    def __init__(self, prompt_file: str, workdir: Path, model: str = "opus",
                 timeout_s: int = 600):
        self._prompt_file, self._workdir = prompt_file, Path(workdir)
        self._model, self._timeout = model, timeout_s

    def admit(self, skill: ProposedSkill) -> bool:
        prompt = (Path(self._prompt_file).read_text()
                  + "\n\n## Candidate skill\n" + str(skill.to_dict()))
        out = _run_claude(prompt, self._workdir, self._model, self._timeout)
        for line in out.splitlines():
            low = line.strip().lower()
            if low.startswith("admit:"):
                return "yes" in low
        raise ActorError(f"judge reply had no ADMIT line: {out[-400:]}")
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_actors.py -q` → 4 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/actors.py tests/aspire/test_actors.py
git commit -m "feat(aspire): actor/judge protocols, fakes, headless-claude wrappers (shim-tested)"
```

---

### Task 8: Evolutionary search (Algorithm 1) with checkpoint/resume

**Files:**
- Create: `aspire/evosearch.py`
- Test: `tests/aspire/test_evosearch.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_evosearch.py
import json

from aspire.actors import FakeActor
from aspire.config import RunConfig
from aspire.engines import FakeEngine
from aspire.evosearch import evosearch, top3
from aspire.schemas import ExecuteResult


def _cfg(**kw):
    return RunConfig(**{**dict(k=2, t=3, theta=1.0, s_dbg=[0, 1]), **kw})


def _task(tmp_path, baseline_score_needed=True):
    task = tmp_path / "suite" / "task"
    task.mkdir(parents=True)
    (task / "code.py").write_text("baseline")
    return task


def test_top3_orders_by_score():
    h = [("a", 0.1), ("b", 0.9), ("c", 0.5), ("d", 0.8)]
    assert [p for p, _ in top3(h)] == ["b", "d", "c"]


def test_early_stop_at_theta(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),                    # baseline on S_dbg
                         ExecuteResult(0.5), ExecuteResult(1.0)])  # iter_00 candidates
    actor = FakeActor(candidate_sources=[["v1", "v2"], ["never", "never"]])
    best = evosearch(task, engine, actor, _cfg())
    assert best.score == 1.0
    assert len(actor.propose_calls) == 1, "must stop after hitting theta"
    assert (task / "evosearch_best_code.py").read_text() == "v2"


def test_budget_exhaustion_keeps_best(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0)] +
                        [ExecuteResult(s) for s in (0.2, 0.4, 0.4, 0.6, 0.1, 0.3)])
    actor = FakeActor(candidate_sources=[["a", "b"], ["c", "d"], ["e", "f"]])
    best = evosearch(task, engine, actor, _cfg())
    assert best.score == 0.6
    assert len(actor.propose_calls) == 3  # T rounds, never reached theta


def test_existing_best_short_circuits(tmp_path):
    task = _task(tmp_path)
    (task / "evosearch_best_code.py").write_text("done")
    (task / "evosearch_best_score.json").write_text(json.dumps({"score": 0.9}))
    engine = FakeEngine([])   # any execute() would raise
    best = evosearch(task, engine, FakeActor(), _cfg())
    assert best.score == 0.9 and best.path.name == "evosearch_best_code.py"


def test_resume_skips_completed_iters(tmp_path):
    task = _task(tmp_path)
    engine1 = FakeEngine([ExecuteResult(0.0), ExecuteResult(0.3), ExecuteResult(0.2)])
    actor1 = FakeActor(candidate_sources=[["a", "b"]])
    try:
        evosearch(task, engine1, actor1, _cfg(t=2))   # iter_00 done, then engine exhausts
    except Exception:
        pass
    run_dirs = list((task).glob("run_*"))
    assert run_dirs and (run_dirs[0] / "iter_00" / "iter_summary.json").exists()
    # resume: baseline + iter_00 come from disk; only iter_01 executes
    engine2 = FakeEngine([ExecuteResult(0.7), ExecuteResult(0.5)])
    actor2 = FakeActor(candidate_sources=[["c", "d"]])
    best = evosearch(task, engine2, actor2, _cfg(t=2))
    assert best.score == 0.7
    assert len(engine2.calls) == 2, "resume must not re-execute finished iterations"
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_evosearch.py -q` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# aspire/evosearch.py
"""Algorithm 1 from the paper, with the paper's directory layout doubling as the
checkpoint format:
  <task>/run_001/iter_00/candidate_A/code.py + iter_summary.json  (per round)
  <task>/evosearch_best_code.py + evosearch_best_score.json       (final, Step-0 gate)
Resume rule: a round with iter_summary.json on disk is replayed from disk, not re-run."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from aspire.actors import ProposeContext
from aspire.config import RunConfig


@dataclass(frozen=True)
class Best:
    path: Path
    score: float


def top3(history):
    """history: list[(path_or_key, score)] -> top 3 best-first."""
    return sorted(history, key=lambda e: e[1], reverse=True)[:3]


def _run_dir(task_dir: Path) -> Path:
    existing = sorted(task_dir.glob("run_*"))
    if existing:
        return existing[-1]
    d = task_dir / "run_001"
    d.mkdir()
    return d


def evosearch(task_dir: Path, engine, actor, cfg: RunConfig, skills=()) -> Best:
    task_dir = Path(task_dir)
    best_code = task_dir / "evosearch_best_code.py"
    best_meta = task_dir / "evosearch_best_score.json"
    if best_code.exists():                                     # paper Step 0
        return Best(best_code, json.loads(best_meta.read_text())["score"])

    run_dir = _run_dir(task_dir)
    baseline = task_dir / "code.py"
    base_meta = run_dir / "baseline_summary.json"
    if base_meta.exists():
        history = [(baseline, json.loads(base_meta.read_text())["score"])]
    else:
        r0 = engine.execute(baseline, cfg.s_dbg)
        base_meta.write_text(json.dumps({"score": r0.score}))
        history = [(baseline, r0.score)]
    best = max(history, key=lambda e: e[1])

    for i in range(cfg.t):
        if best[1] >= cfg.theta:
            break
        iter_dir = run_dir / f"iter_{i:02d}"
        summary = iter_dir / "iter_summary.json"
        if summary.exists():                                   # resume from disk
            for entry in json.loads(summary.read_text()):
                history.append((Path(entry["path"]), entry["score"]))
        else:
            ctx = ProposeContext(task_dir=task_dir, iter_dir=iter_dir,
                                 top3=top3(history), skills=list(skills), k=cfg.k)
            candidates = actor.propose(ctx, model=cfg.model_propose)
            entries = []
            for c in candidates:
                r = engine.execute(c, cfg.s_dbg)
                history.append((c, r.score))
                entries.append({"path": str(c), "score": r.score})
            summary.write_text(json.dumps(entries, indent=1))
        best = max(history, key=lambda e: e[1])

    shutil.copyfile(best[0], best_code)
    best_meta.write_text(json.dumps({"score": best[1], "source": str(best[0])}))
    return Best(best_code, best[1])
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_evosearch.py -q` → 5 passed

- [ ] **Step 5: Commit**

```bash
git add aspire/evosearch.py tests/aspire/test_evosearch.py
git commit -m "feat(aspire): Algorithm-1 evosearch with disk checkpoint/resume"
```

---

### Task 9: Coordinator pipeline (stages, single-use S_val, admission)

**Files:**
- Create: `aspire/coordinator.py`
- Test: `tests/aspire/test_coordinator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_coordinator.py
import pytest

from aspire.actors import FakeActor, FakeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline, ValidationReuseError
from aspire.engines import FakeEngine
from aspire.schemas import ActorReport, ExecuteResult, ProposedSkill
from aspire.skill_library import SkillLibrary


CFG = RunConfig(k=2, t=2, theta=1.0, debug_rounds=1, s_dbg=[0, 1], s_val=[100, 101])


def _task(tmp_path, code="navigate_to_pose([1,2,0])"):
    task = tmp_path / "robosuite" / "handover"
    task.mkdir(parents=True)
    (task / "code.py").write_text(code)
    return task


def _skillful_report(code_path="fix_code.py"):
    return ActorReport(
        outcome="success", diagnosis="buffer", code_path=code_path,
        proposed_skills=(ProposedSkill(
            name="multi-angle-approach", category="navigation",
            failure_signature="PLANNING_ERROR", when_to_apply="near obstacle",
            strategy="rotate approach", code_sketch="for a in [180,-90,90]: pass"),))


def test_baseline_pass_goes_straight_to_validation(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(1.0),   # Stage 0 on S_dbg
                         ExecuteResult(0.9)])  # Stage 2 on S_val
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    result = pipe.run()
    assert result.val_score == 0.9 and result.stage_reached == "validated"
    assert engine.calls[1][1] == (100, 101)


def test_debug_then_validate_and_admit_skill(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),   # Stage 0 fails
                         ExecuteResult(1.0),   # fix_code.py on S_dbg passes
                         ExecuteResult(1.0)])  # Stage 2
    actor = FakeActor(reports=[_skillful_report()])
    lib = SkillLibrary(tmp_path / "lib")
    task_fix = task / "fix_code.py"; task_fix.write_text("clean_fix()")
    pipe = TaskPipeline(task, engine, actor, FakeJudge([True]), lib, CFG)
    result = pipe.run()
    assert result.val_score == 1.0
    assert [s.name for s in lib.load_all()] == ["multi-angle-approach"]


def test_judge_rejection_blocks_admission(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(1.0), ExecuteResult(1.0)])
    (task / "fix_code.py").write_text("clean_fix()")
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(reports=[_skillful_report()]),
                        FakeJudge([False]), lib, CFG)
    pipe.run()
    assert lib.load_all() == []


def test_audit_violation_blocks_admission_without_judge(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0), ExecuteResult(1.0), ExecuteResult(1.0)])
    (task / "fix_code.py").write_text("clean_fix()")
    bad = _skillful_report()
    bad = ActorReport(outcome=bad.outcome, diagnosis=bad.diagnosis, code_path=bad.code_path,
                      proposed_skills=(ProposedSkill(
                          name="cheat", category="grasping", failure_signature="f",
                          when_to_apply="w", strategy="s",
                          code_sketch="q = env.handle.env.sim.data.qpos"),))
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(reports=[bad]),
                        FakeJudge([]), lib, CFG)   # judge never consulted
    pipe.run()
    assert lib.load_all() == []


def test_debug_exhausted_falls_through_to_evosearch(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(0.0),                 # Stage 0
                         ExecuteResult(0.2),                 # debug round fix on S_dbg
                         ExecuteResult(0.0),                 # evosearch baseline re-exec
                         ExecuteResult(1.0), ExecuteResult(0.3),   # iter_00
                         ExecuteResult(0.8)])                # Stage 2 on best
    (task / "fix_code.py").write_text("still_bad()")
    actor = FakeActor(reports=[ActorReport(outcome="fail", diagnosis="d",
                                           code_path="fix_code.py")],
                      candidate_sources=[["good", "meh"]])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, actor, FakeJudge([]), lib, CFG)
    result = pipe.run()
    assert result.stage_reached == "validated" and result.val_score == 0.8
    assert (task / "evosearch_best_code.py").read_text() == "good"


def test_second_validation_marks_tainted(tmp_path):
    task = _task(tmp_path)
    engine = FakeEngine([ExecuteResult(1.0), ExecuteResult(0.9), ExecuteResult(0.9)])
    lib = SkillLibrary(tmp_path / "lib")
    pipe = TaskPipeline(task, engine, FakeActor(), FakeJudge([]), lib, CFG)
    pipe.run()
    with pytest.raises(ValidationReuseError):
        pipe.validate(task / "code.py")
    assert (task / "TAINTED").exists()
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_coordinator.py -q` → FAIL, no module

- [ ] **Step 3: Implement**

```python
# aspire/coordinator.py
"""Per-task pipeline (spec data flow):
Stage 0 baseline on S_dbg → Stage 1 actor debug rounds → evosearch fallback →
Stage 2 validation on S_val (EXACTLY ONCE) → mechanical audit → judge → admission.
On simhost's single GPU the paper's device-dispatch loop degenerates to sequential tasks;
aspire/run.py iterates TaskPipeline over a task list."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aspire.audit import audit_code
from aspire.config import RunConfig
from aspire.evosearch import evosearch
from aspire.skill_library import Skill, SkillLibrary


class ValidationReuseError(RuntimeError):
    """S_val was already spent for this task; the run is tainted."""


@dataclass(frozen=True)
class TaskResult:
    stage_reached: str        # "validated"
    dbg_score: float
    val_score: float
    program: str              # path of the validated program
    admitted_skills: tuple = ()


class TaskPipeline:
    def __init__(self, task_dir: Path, engine, actor, judge, library: SkillLibrary,
                 cfg: RunConfig):
        self.task_dir = Path(task_dir)
        self.engine, self.actor, self.judge = engine, actor, judge
        self.library, self.cfg = library, cfg

    # -- Stage 2 guard ------------------------------------------------------
    def validate(self, program: Path):
        marker = self.task_dir / "VALIDATION_DONE"
        if marker.exists():
            (self.task_dir / "TAINTED").touch()
            raise ValidationReuseError(
                f"S_val already used for {self.task_dir}; run marked TAINTED")
        result = self.engine.execute(program, self.cfg.s_val)
        marker.write_text(json.dumps({"program": str(program), "score": result.score}))
        return result

    # -- full pipeline ------------------------------------------------------
    def run(self) -> TaskResult:
        baseline = self.task_dir / "code.py"
        r = self.engine.execute(baseline, self.cfg.s_dbg)
        dbg_score, program, report = r.score, baseline, None

        if dbg_score < self.cfg.theta:
            for _ in range(self.cfg.debug_rounds):          # Stage 1
                report = self.actor.run_debug(self.task_dir, model=self.cfg.model_repair)
                fix = self.task_dir / report.code_path
                r = self.engine.execute(fix, self.cfg.s_dbg)
                if r.score > dbg_score:
                    dbg_score, program = r.score, fix
                if dbg_score >= self.cfg.theta:
                    break

        if dbg_score < self.cfg.theta:                      # evosearch fallback
            best = evosearch(self.task_dir, self.engine, self.actor, self.cfg,
                             skills=self.library.load_all())
            if best.score >= dbg_score:
                dbg_score, program = best.score, best.path

        val = self.validate(program)                        # Stage 2, exactly once

        admitted = []
        if report is not None:
            provenance = (f"{self.task_dir.parent.name}/{self.task_dir.name} "
                          f"dbg={dbg_score:.2f} val={val.score:.2f}")
            for ps in report.proposed_skills:
                if audit_code(ps.code_sketch):
                    continue                                # mechanical reject, no judge
                if self.judge.admit(ps):
                    skill = Skill.from_proposed(ps, provenance=provenance)
                    self.library.add(skill)
                    admitted.append(skill)

        return TaskResult(stage_reached="validated", dbg_score=dbg_score,
                          val_score=val.score, program=str(program),
                          admitted_skills=tuple(admitted))
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_coordinator.py -q` → 6 passed

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest -q` → all green (27 A2 + all aspire tests)
```bash
git add aspire/coordinator.py tests/aspire/test_coordinator.py
git commit -m "feat(aspire): TaskPipeline — stages, single-use S_val, audited admission"
```

---

### Task 10: Prompts (Appendix E transcriptions) + contract lint test

**Files:**
- Create: `prompts/actor_debug.md`, `prompts/actor_evosearch.md`, `prompts/coordinator_admission.md`
- Test: `tests/aspire/test_prompts.py`

Transcribe from `docs/Aspire.pdf` Appendix E (use `pdftotext docs/Aspire.pdf -` to re-extract).
Where the PDF omits content ("... omitted ..."), write the bridging text yourself and mark the
paragraph with `[RECONSTRUCTED]`. The three files below are the required skeletons — extend
them with the verbatim appendix text, keep the CONTRACT sections exactly as written here.

- [ ] **Step 1: Write the failing lint test**

```python
# tests/aspire/test_prompts.py
from pathlib import Path

PROMPTS = Path("prompts")


def test_prompt_files_exist():
    for f in ("actor_debug.md", "actor_evosearch.md", "coordinator_admission.md"):
        assert (PROMPTS / f).exists(), f


def test_actor_prompts_state_report_contract():
    for f in ("actor_debug.md", "actor_evosearch.md"):
        text = (PROMPTS / f).read_text()
        assert "report.json" in text
        assert "fix_code.py" in text or "candidate_" in text
        assert "seed-specific" in text.lower()


def test_debug_prompt_carries_forbidden_wall():
    text = (PROMPTS / "actor_debug.md").read_text()
    for token in ("env.handle.env.sim", ".bddl", ".urdf"):
        assert token in text


def test_admission_prompt_demands_admit_line():
    text = (PROMPTS / "coordinator_admission.md").read_text()
    assert "ADMIT:" in text
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_prompts.py -q` → FAIL (files missing)

- [ ] **Step 3: Write the three prompt files (skeletons; extend with Appendix E verbatim text)**

`prompts/actor_debug.md`:
```markdown
# ASPIRE Actor — Trace-Guided Debugging (Stage 1)

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

## Output contract (MANDATORY)
Write `report.json`:
{"outcome": "success"|"fail", "diagnosis": "<one-paragraph causal diagnosis>",
 "code_path": "fix_code.py",
 "proposed_skills": [{"name", "category", "failure_signature", "when_to_apply",
                      "strategy", "code_sketch"}]}
Propose a skill ONLY if the repair pattern would plausibly apply to >=2 task types;
task-ultra-specific tricks stay inline in fix_code.py.
```

`prompts/actor_evosearch.md`:
```markdown
# ASPIRE Actor — Evolutionary Search Proposals

You propose K candidate programs for one task (K and the output directory are given in
the appended "This round" section).

## Rules
- Same forbidden-API wall as debugging: no raw sim access (`env.handle.env.sim`), never
  read `.bddl`/`.xml`/`.urdf` asset files; no seed-specific branches in any candidate.
- Read `task_analysis.md` first: do NOT re-test eliminated strategy branches; blocked
  branches may be retried only with a genuinely new technique. [RECONSTRUCTED]
- Condition on the top-performing programs and their remaining failure modes; make the
  K candidates STRATEGICALLY DISTINCT (different grasp axis, approach side, ordering),
  not K small mutations of one idea.
- Write each candidate to `candidate_<LETTER>/code.py` under the given iteration dir.
- Update `task_analysis.md` with the hypotheses behind this round's candidates.

## Output contract (MANDATORY)
After writing candidates, write `report.json`:
{"outcome": "success", "diagnosis": "<why these K strategies>", "code_path":
 "<relative path of the candidate you consider strongest>", "proposed_skills": []}
```

`prompts/coordinator_admission.md`:
```markdown
# ASPIRE Coordinator — Skill Admission Judge

You audit ONE candidate skill for the shared library (the paper's coordinator-guided
admission). Admit only reusable repair patterns, not task programs.

Admit iff ALL hold:
1. Generalizable: plausibly applies to >=2 task types (paper's bar). [RECONSTRUCTED]
2. It encodes a failure->repair PATTERN (signature + when-to-apply + strategy), not a
   full task solution or magic constants.
3. The code sketch (if any) respects the forbidden-API wall and has no seed-specific
   branches (mechanically pre-checked; re-reject if you still see either).
4. It is not a near-duplicate of an existing library entry shown to you.

Reply with exactly one line first:
ADMIT: yes — <reason>   |   ADMIT: no — <reason>
```

- [ ] **Step 4: Verify green**

Run: `python3 -m pytest tests/aspire/test_prompts.py -q` → 4 passed

- [ ] **Step 5: Extend prompts with verbatim Appendix E text**

Run: `pdftotext docs/Aspire.pdf - | sed -n '/E.3/,/E.5/p'` and merge clean verbatim
passages into the three files (keep CONTRACT sections untouched; mark gaps
`[RECONSTRUCTED]`). Re-run the lint test.

- [ ] **Step 6: Commit**

```bash
git add prompts/ tests/aspire/test_prompts.py
git commit -m "feat(aspire): actor/judge prompts from Appendix E with pinned contracts"
```

---

### Task 11: capx_execute.py runner + CLI dry run

**Files:**
- Create: `scripts/capx_execute.py`
- Create: `aspire/run.py`
- Test: `tests/aspire/test_run.py`

`capx_execute.py` is the simhost-side half of the Task-6 contract. Its CaP-X imports are
adapted on-box in M0 (the real API is only discoverable there); everything around the
imports — arg parsing, result.json emission, trace normalization — is written and tested
now, using an injected fake episode runner.

- [ ] **Step 1: Write the failing tests**

```python
# tests/aspire/test_run.py
import json
import subprocess
import sys
from pathlib import Path

from aspire.schemas import ExecuteResult

SCRIPT = Path("scripts/capx_execute.py")


def test_capx_execute_selftest_mode_writes_contract_result(tmp_path):
    out = tmp_path / "o"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--program", str(SCRIPT), "--seeds", "0,1",
         "--out-dir", str(out), "--selftest"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    res = ExecuteResult.from_json((out / "result.json").read_text())
    assert res.score == 0.5                       # selftest: seed 0 passes, seed 1 fails
    assert res.traces[0].function == "selftest_primitive"


def test_cli_fake_dry_run(tmp_path):
    task = tmp_path / "robosuite" / "lift"
    task.mkdir(parents=True)
    (task / "code.py").write_text("pass")
    proc = subprocess.run(
        [sys.executable, "-m", "aspire.run", "--task-dir", str(task),
         "--engine", "fake", "--fake-scores", "1.0,0.9",
         "--library", str(tmp_path / "lib")],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["val_score"] == 0.9 and summary["stage_reached"] == "validated"
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m pytest tests/aspire/test_run.py -q` → FAIL (script/module missing)

- [ ] **Step 3: Implement the runner**

```python
#!/usr/bin/env python3
# scripts/capx_execute.py
"""Runs INSIDE the cap-x venv on simhost. Contract (pinned by tests/aspire/test_run.py):
  capx_execute.py --program P --seeds 0,1,2 --out-dir D [--config-path YAML] [--selftest]
writes D/result.json in the aspire.schemas.ExecuteResult format.

The run_episode() body below is adapted on-box in M0 against the real CaP-X API
(see docs in ~/cap-x/docs and env_configs/*.yaml). --selftest exercises the full
harness with a stub episode so the contract is testable without CaP-X."""
import argparse
import json
import time
from pathlib import Path


def selftest_episode(program_path: str, seed: int, out_dir: Path):
    t0 = time.time()
    ok = seed % 2 == 0
    trace = [{"step": 1, "function": "selftest_primitive", "args": {"seed": seed},
              "status": "ok" if ok else "error",
              "result_summary": f"success={ok}", "duration_ms": (time.time() - t0) * 1000,
              "media": []}]
    return ok, trace


def run_episode(program_path: str, seed: int, out_dir: Path, config_path: str):
    """[M0 ADAPTATION POINT] Replace body with real CaP-X calls:
    build env from config_path YAML with this seed, exec the program against the
    env's primitive namespace, collect per-primitive feedback + keyframe paths,
    return (success: bool, traces: list[dict-in-TraceRecord-shape])."""
    raise NotImplementedError("adapt to CaP-X API on simhost during M0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config-path", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in args.seeds.split(",")]
    episode = selftest_episode if args.selftest else run_episode

    successes, all_traces = 0, []
    for seed in seeds:
        if args.selftest:
            ok, traces = episode(args.program, seed, out_dir)
        else:
            ok, traces = episode(args.program, seed, out_dir, args.config_path)
        successes += bool(ok)
        all_traces.extend(traces)

    (out_dir / "result.json").write_text(json.dumps(
        {"score": successes / len(seeds), "raw_dir": str(out_dir),
         "traces": all_traces}, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement the CLI**

```python
# aspire/run.py
"""python -m aspire.run --task-dir T --engine fake|capx ...
Fake engine: --fake-scores comma list consumed in order (dry runs, CI smoke).
Capx engine: --capx-cmd "uv run --no-sync python scripts/capx_execute.py" --out-root R."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from aspire.actors import FakeActor, FakeJudge, ClaudeCodeActor, ClaudeJudge
from aspire.config import RunConfig
from aspire.coordinator import TaskPipeline
from aspire.engines import CapxEngine, FakeEngine
from aspire.schemas import ExecuteResult
from aspire.skill_library import SkillLibrary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-dir", required=True)
    ap.add_argument("--engine", choices=("fake", "capx"), required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--fake-scores", default="")
    ap.add_argument("--capx-cmd", default="")
    ap.add_argument("--out-root", default="")
    ap.add_argument("--prompts", default="prompts")
    args = ap.parse_args(argv)

    cfg = RunConfig()
    if args.engine == "fake":
        engine = FakeEngine([ExecuteResult(float(s))
                             for s in args.fake_scores.split(",") if s])
        actor, judge = FakeActor(), FakeJudge([])
    else:
        engine = CapxEngine(cmd_prefix=shlex.split(args.capx_cmd),
                            out_root=Path(args.out_root))
        actor = ClaudeCodeActor(prompt_file=f"{args.prompts}/actor_debug.md")
        judge = ClaudeJudge(prompt_file=f"{args.prompts}/coordinator_admission.md",
                            workdir=Path(args.task_dir))

    pipe = TaskPipeline(Path(args.task_dir), engine, actor, judge,
                        SkillLibrary(Path(args.library)), cfg)
    result = pipe.run()
    print(json.dumps({"stage_reached": result.stage_reached,
                      "dbg_score": result.dbg_score, "val_score": result.val_score,
                      "program": result.program,
                      "admitted": [s.name for s in result.admitted_skills],
                      "config": cfg.to_dict()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify green, full suite, commit**

Run: `python3 -m pytest tests/aspire/test_run.py -q` → 2 passed
Run: `python3 -m pytest -q` → everything green
```bash
git add scripts/capx_execute.py aspire/run.py tests/aspire/test_run.py
git commit -m "feat(aspire): capx_execute contract runner + aspire.run CLI dry run"
```

---

### Task 12: M0 rig-up script (simhost, operational)

**Files:**
- Create: `scripts/m0_rig_up.sh`

No TDD here (operational shell), but the script must be verifiable: every phase prints
PASS/FAIL and the script exits non-zero on failure — same discipline as `start_a2_sim.sh`
(whose GetAction content-type and pkill lessons are already baked into that file; reread
it before writing this one).

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
# scripts/m0_rig_up.sh — run ON simhost as demo. Installs CaP-X, smoke-tests GPU sim,
# runs the contract selftest, then captures ONE golden scripted episode for trace tests.
set -euo pipefail

echo "[1/5] clone cap-x + install uv"
[ -d ~/cap-x ] || git clone https://github.com/capgym/cap-x ~/cap-x
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "[2/5] sync env (see ~/cap-x/README + docs/ for the authoritative steps)"
cd ~/cap-x && uv sync

echo "[3/5] GPU smoke: robosuite headless renders one frame"
uv run --no-sync python - <<'EOF'
import robosuite, numpy as np
env = robosuite.make("Lift", robots="Panda", has_renderer=False,
                     has_offscreen_renderer=True, use_camera_obs=True)
obs = env.reset()
img = next(v for k, v in obs.items() if k.endswith("_image"))
assert img.size > 0
print("PASS: robosuite offscreen frame", img.shape)
EOF

echo "[4/5] aspire contract selftest (no CaP-X needed)"
cd ~/aspire_robot_engine
python3 scripts/capx_execute.py --program scripts/capx_execute.py \
  --seeds 0,1 --out-dir /tmp/aspire_selftest --selftest
grep -q '"score": 0.5' /tmp/aspire_selftest/result.json && echo "PASS: contract"

echo "[5/5] ADAPTATION step — wire run_episode() to the real CaP-X API"
cat <<'MSG'
Manual (agent-assisted) step:
  1. Read ~/cap-x/docs and capx/envs/launch.py to find the programmatic episode API.
  2. Fill run_episode() in scripts/capx_execute.py (program exec against primitive
     namespace, per-primitive feedback -> TraceRecord dicts, success flag).
  3. Golden capture: run a scripted no-LLM program on one Lift episode:
       python3 scripts/capx_execute.py --program examples_capx/scripted_lift.py \
         --seeds 0 --out-dir ~/aspire_runs/golden/lift_seed0 \
         --config-path ~/cap-x/env_configs/<lift-config>.yaml
  4. Copy result.json back to the repo as tests/aspire/golden/lift_seed0_result.json
     and add a test asserting ExecuteResult.from_json() parses it and traces are
     non-empty with valid statuses.
M0 is DONE when that test passes on Mac and this script exits 0 on simhost.
MSG
```

- [ ] **Step 2: Verify + commit**

Run (Mac): `bash -n scripts/m0_rig_up.sh` → syntax OK
Run (simhost, after rsync): `./scripts/m0_rig_up.sh` — phases 1–4 must PASS today; phase 5 is
the guided adaptation.
```bash
git add scripts/m0_rig_up.sh
git commit -m "ops(aspire): M0 rig-up script for simhost (install, GPU smoke, contract selftest)"
```

---

### Task 13: M1 baseline campaign script (simhost, operational)

**Files:**
- Create: `scripts/m1_baseline.sh`

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
# scripts/m1_baseline.sh — run ON simhost after M0. Reproduces the released CaP-Agent0
# baseline on 5 Robosuite tasks (paper Table 3 subset, incl. bimanual handover).
# Results land in ~/aspire_runs/m1_baseline/results.json; these are OUR baseline
# numbers — every later ASPIRE comparison is against this file, never the paper's table.
set -euo pipefail
cd ~/cap-x
OUT=~/aspire_runs/m1_baseline; mkdir -p "$OUT"

# Exact config names must be confirmed against env_configs/ (M0 discovery); the five
# below are the intended Table-3 subset. Update this array, commit the correction.
TASKS=(lift stack two_arm_handover pick_place_can door)

for t in "${TASKS[@]}"; do
  cfg=$(ls env_configs/*"$t"*.yaml | head -1) || { echo "FAIL: no config for $t"; exit 1; }
  echo "== CaP-Agent0 baseline: $t ($cfg) =="
  uv run --no-sync --active capx/envs/launch.py \
    --config-path "$cfg" \
    --model "claude-opus" \
    2>&1 | tee "$OUT/$t.log"
done
echo "Collect per-task success rates from the logs/output dirs into $OUT/results.json"
echo '(schema: {"task": {"episodes": N, "successes": M, "model": "...", "date": "..."}})'
```

- [ ] **Step 2: Verify + commit**

Run: `bash -n scripts/m1_baseline.sh` → syntax OK. (Exact launch flags/model id are
confirmed against `~/cap-x` docs during M0; correct the script on-box and commit.)
```bash
git add scripts/m1_baseline.sh
git commit -m "ops(aspire): M1 CaP-Agent0 baseline campaign script"
```

---

### Task 14: Push branch + runbook note

- [ ] **Step 1: Final full suite**

Run: `python3 -m pytest -q` → all green (Mac). Then rsync to simhost and run
`python3 -m pytest -q -p no:anyio` there → all green.

- [ ] **Step 2: Push**

```bash
git push aspire_demo aspire_original_sim
git push origin aspire_original_sim
```

- [ ] **Step 3: Runbook (milestones M2+ are experiment campaigns, not code)**

Append to `.project_notes/CLAUDE_HANDOFF.md`: M0/M1 status, then M2 = run
`python -m aspire.run --engine capx` per task with real actors (first skills admitted),
M3 = evosearch on plateaued tasks (handover headline; compare against
`~/aspire_runs/m1_baseline/results.json`), M4 = LIBERO-Pro second venv + LIBERO-90
transfer, M5 = BEHAVIOR-1K stretch. Log model IDs and RunConfig per run (the CLI already
prints both).

---

## Self-review (done at plan-writing time)

- **Spec coverage:** components (adapter→T6/T11, actor→T7, coordinator→T9, library→T5,
  evosearch→T8, prompts→T10, config→T1, schemas/traces→T2/T3, audit→T4, CLI→T11,
  M0→T12, M1→T13, M2–M5 runbook→T14). Single-use S_val + TAINTED tested (T9). Resume
  tested (T8). Forbidden wall tested (T4, prompts T10). `[RECONSTRUCTED]` marking in
  T1 defaults and T10 prompts. Trend-bar comparison anchored to our M1 results (T13).
- **Types:** `ExecuteResult(score, traces, raw_dir)`, `ActorReport(outcome, diagnosis,
  code_path, proposed_skills)`, `ProposeContext(task_dir, iter_dir, top3, skills, k,
  history_note)`, `Best(path, score)`, `TaskResult(stage_reached, dbg_score, val_score,
  program, admitted_skills)` — used consistently across T6–T11.
- **Known deliberate gap:** `run_episode()` body and exact CaP-X launch flags are
  on-box M0 discovery (external repo, API unknowable from here); the contract around
  them is fully pinned by tests (T6, T11) and the golden-capture step (T12) converts
  discovery output into a regression test.
```
