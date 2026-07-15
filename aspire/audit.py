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
