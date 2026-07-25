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
    source_xy: str = ""          # "x,y" when tagged by the tiling runner; "" = location-agnostic

    @classmethod
    def from_proposed(cls, p: ProposedSkill, provenance: str) -> "Skill":
        return cls(provenance=provenance, **p.to_dict())


def render_skill(s: Skill) -> str:
    parts = [f"# {s.name}", f"category: {s.category}"]
    if s.source_xy:
        parts.append(f"source_xy: {s.source_xy}")
    for key in _SECTIONS:
        parts += [f"## {_TITLES[key]}", getattr(s, key)]
    return "\n\n".join(parts) + "\n"


def parse_skill(text: str) -> Skill:
    name = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    category = re.search(r"^category: (.+)$", text, re.M).group(1).strip()
    m_xy = re.search(r"^source_xy: (.+)$", text, re.M)
    source_xy = m_xy.group(1).strip() if m_xy else ""
    # Locate each known section header positionally: search for each header only
    # after the previous one, so an in-field "## ..." line can't be mistaken for
    # the next header unless it exactly matches one of the remaining known titles.
    positions = []
    cursor = 0
    for key in _SECTIONS:
        m = re.compile(rf"^## {re.escape(_TITLES[key])}$", re.M).search(text, cursor)
        positions.append((key, m))
        if m:
            cursor = m.end()
    fields = {}
    for i, (key, m) in enumerate(positions):
        if m is None:
            fields[key] = ""
            continue
        nxt = next((p.start() for _, p in positions[i + 1:] if p), len(text))
        fields[key] = text[m.end():nxt].strip()
    return Skill(name=name, category=category, source_xy=source_xy, **fields)


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

    def load_all(self) -> list:
        return [parse_skill(p.read_text())
                for p in sorted(self.root.glob("*/*.md"))]

    def retrieve(self, categories=None, keywords=None) -> list:
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
