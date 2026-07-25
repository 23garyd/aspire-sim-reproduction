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
