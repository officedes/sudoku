"""The 150 hard puzzles in tests/hard_puzzles (dailykillersudoku 10/10,
krazydad "insane", the Gizmodo "hardest", three easier controls).

Each must be solved to a valid grid by logic alone. Also reports how many
needed first-order contradiction sweeps, the number to watch when adding
techniques, and CPU time.

    python tests/check_hard.py [--workers 3] [--every N]

--every N checks every Nth puzzle for a quick run. Workers restart every 10
puzzles to keep memory low.
"""

import argparse
import multiprocessing as mp
import sys
import time
from collections import Counter

from common import hard_names, is_valid_solution, load_hard, quiet

import killer.solver as S  # noqa: E402


def solve(name):
    cages, _ = load_hard(name)
    board, stats = S.create_board(), {}
    t = time.process_time()
    with quiet():
        S.solve_killer_sudoku(board, cages, verbose=False, stats=stats)
    ok = S.is_solved(board) and is_valid_solution(board, cages)
    return name, ok, stats.get("contradictions", 0), time.process_time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--every", type=int, default=1)
    args = ap.parse_args()
    names = hard_names()[::args.every]
    with mp.Pool(args.workers, maxtasksperchild=10) as pool:
        results = pool.map(solve, names)
    bad = [n for n, ok, _, _ in results if not ok]
    sweeps = Counter(min(c, 5) for _, _, c, _ in results)
    times = [t for *_, t in results]
    print(f"hard puzzles: {len(results) - len(bad)}/{len(results)} solved to a valid grid")
    print(f"  pure logic (no contradiction sweep): {sweeps[0]}/{len(results)}, "
          f"sweeps total {sum(c for _, _, c, _ in results)}, per puzzle {dict(sorted(sweeps.items()))}")
    print(f"  cpu {sum(times):.0f}s, slowest {max(times):.1f}s")
    for name in bad:
        print(f"  FAILED: {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
