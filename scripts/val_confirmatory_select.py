#!/usr/bin/env python3
"""Pure selection for the val-confirmatory campaign: keep tasks in the frozen
overfit band (cold solves the debug seed but not held-out validation)."""
import argparse, json, sys
from pathlib import Path


def select(candidates, dbg_min=0.6, val_max=0.2, need=2):
    audit, selected = [], []
    for c in candidates:
        keep = c["cold_dbg_rate"] >= dbg_min and c["cold_val_rate"] <= val_max
        if keep:
            selected.append(c["task"])
            reason = f"overfit band (dbg {c['cold_dbg_rate']:.2f}>={dbg_min}, val {c['cold_val_rate']:.2f}<={val_max})"
        elif c["cold_dbg_rate"] < dbg_min:
            reason = f"floor (dbg {c['cold_dbg_rate']:.2f}<{dbg_min})"
        else:
            reason = f"ceiling (val {c['cold_val_rate']:.2f}>{val_max})"
        audit.append({**c, "keep": keep, "reason": reason})
    return {"selected": selected, "audit": audit, "sufficient": len(selected) >= need}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, help="path to candidates JSON list")
    ap.add_argument("--out", required=True, help="path to write selection result JSON")
    args = ap.parse_args()
    cands = json.loads(Path(args.candidates).read_text())
    res = select(cands)
    Path(args.out).write_text(json.dumps(res, indent=1))
    for a in res["audit"]:
        print(f"  {a['task']:<10} {'KEEP' if a['keep'] else 'drop':<4}  {a['reason']}")
    print(f"selected {res['selected']} (sufficient={res['sufficient']})")


if __name__ == "__main__":
    main()
