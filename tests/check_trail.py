"""The step-by-step explanations follow a logical trail.

Replays solve_and_explain for each saved puzzle and checks, step by step:
the true digit is never removed, a removed candidate never comes back, a
placed digit was still a candidate, a placement credited to elimination is
visible as a naked or hidden single, and each elimination step removes
something - and nothing beyond the cells its text names.

    python tests/check_trail.py [puzzle_001 ...]
"""

import os
import re
import sys
from collections import defaultdict

from common import ROOT, quiet

import killer.solver as S  # noqa: E402
from killer.helpers import cell, get_house_cells, parse_cell  # noqa: E402
from main import load_puzzle  # noqa: E402


def _hidden_single(cands, key, v):
    r, c = parse_cell(key)
    for house_type, i in (("row", r), ("col", c), ("box", r // 3 * 3 + c // 3)):
        if [cell(*x) for x in get_house_cells(house_type, i) if v in cands.get(cell(*x), [])] == [key]:
            return True
    return False


def check(cages, sol):
    """(number of steps, {issue kind: [examples]})."""
    with quiet():
        _, steps = S.solve_and_explain(cages)
    issues = defaultdict(list)
    prev = None
    for k, step in enumerate(steps):
        cur = step.get("candidates")
        if cur is None:
            continue
        tag = f"#{k} {step['text'][:80]}"
        for key, vals in cur.items():
            r, c = parse_cell(key)
            if sol[r][c] not in vals:
                issues["true digit removed"].append(f"{tag}: {key} {vals}, answer {sol[r][c]}")
        if prev is not None:
            if step["type"] == "placement":
                (r, c), v = step["cell"], step["value"]
                key = cell(r, c)
                if v != sol[r][c]:
                    issues["wrong placement"].append(tag)
                if v not in prev.get(key, []):
                    issues["placed digit wasn't a candidate"].append(f"{tag}: {key} was {prev.get(key)}")
                if ("candidate elimination" in step["text"] or "hidden single" in step["text"]) \
                        and prev.get(key) != [v] and not _hidden_single(prev, key, v):
                    issues["placement not visible as a single"].append(f"{tag}: {key} was {prev.get(key)}")
            for key, vals in cur.items():
                if key in prev and set(vals) - set(prev[key]):
                    issues["candidate came back"].append(f"{tag}: {key} {prev[key]} -> {vals}")
            if step["type"] == "elimination":
                diff = {key for key in prev if key in cur and set(prev[key]) - set(cur[key])}
                if not diff:
                    issues["elimination changed nothing"].append(tag)
                named = set(re.findall(r"\b([A-I][1-9])\b", step["text"].split("->")[-1])) \
                    if "->" in step["text"] else None
                if named and diff - named:
                    issues["removed more than the text says"].append(f"{tag}: also {sorted(diff - named)}")
        prev = cur
    return len(steps), issues


def main():
    names = [n if n.endswith(".json") else n + ".json" for n in sys.argv[1:]] or \
        sorted(f for f in os.listdir(os.path.join(ROOT, "puzzles")) if f.endswith(".json"))
    total = defaultdict(int)
    for name in names:
        n, issues = check(*load_puzzle(name))
        print(f"{name:18s} {n:4d} steps  {dict((k, len(v)) for k, v in issues.items()) or 'clean'}", flush=True)
        for kind, examples in issues.items():
            total[kind] += len(examples)
            for ex in examples[:2]:
                print(f"    {kind}: {ex}")
    print(f"\ntrail issues: {dict(total) or 'none'}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
