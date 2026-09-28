"""Saved puzzles: each has exactly one solution, and the logical solver
reaches it without ever placing a wrong digit.

Runs the strategies one move at a time and compares every placement with
the stored solution, so an unsound technique is caught at the move it errs.

    python tests/check_saved.py [puzzle_001 ...]
"""

import os
import sys
import time

from common import ROOT, exact_solutions, quiet

import killer.solver as S  # noqa: E402
from main import load_puzzle  # noqa: E402


def check(name):
    """None if fine, else a one-line problem description."""
    cages, sol = load_puzzle(name)
    sols = exact_solutions(cages, 2)
    if len(sols) != 1 or sols[0] != sol:
        return f"{len(sols)} solutions" if len(sols) != 1 else "stored solution is wrong"
    board = S.create_board()
    for _ in range(200):
        if S.is_solved(board):
            return None
        for fn in S.ALL_STRATEGIES:
            with quiet():
                moved = fn(board, cages)
            wrong = [(r, c) for r in range(9) for c in range(9) if board[r][c] and board[r][c] != sol[r][c]]
            if wrong:
                r, c = wrong[0]
                return f"{getattr(fn, '__name__', fn)} placed {board[r][c]} at row {r + 1} col {c + 1}, answer {sol[r][c]}"
            if moved:
                break
        else:
            filled = sum(1 for row in board for v in row if v)
            return f"stuck at {filled}/81"
    return None if S.is_solved(board) else "ran out of moves"


def main():
    names = [n if n.endswith(".json") else n + ".json" for n in sys.argv[1:]] or \
        sorted(f for f in os.listdir(os.path.join(ROOT, "puzzles")) if f.endswith(".json"))
    failures = 0
    for name in names:
        t = time.time()
        problem = check(name)
        failures += problem is not None
        print(f"{name:18s} {time.time() - t:5.1f}s  {problem or 'ok'}", flush=True)
    print(f"\nsaved puzzles: {len(names) - failures}/{len(names)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
