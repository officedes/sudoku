"""Shared helpers for the test scripts: paths, the text-grid parser for the
hard puzzle set, solution checks and an exact solution counter."""

import contextlib
import io
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
HARD_DIR = os.path.join(TESTS, "hard_puzzles")
OUTPUT_DIR = os.path.join(TESTS, "output")
sys.path.insert(0, ROOT)

from killer.helpers import get_house_cells  # noqa: E402
from killer.strategies import _propagate  # noqa: E402
from killer.sudoku import build_candidates, to_mask  # noqa: E402


def quiet():
    """Silence the strategies' explanation printing."""
    return contextlib.redirect_stdout(io.StringIO())


def parse_grid(text):
    """Cages from a text-drawn killer grid (the purge-and-merge format).

    Cells are 4 characters wide; '|' or '║' between cells and '---' / '==='
    below them are cage walls, and each cage's sum is written in one of its
    cells (not always the top-left one, so numbers are matched by position).
    """
    lines = [line.ljust(37) for line in text.splitlines() if line.startswith(("+", "|"))][:19]
    if len(lines) != 19:
        raise ValueError(f"expected 19 grid lines, got {len(lines)}")
    parent = {(r, c): (r, c) for r in range(9) for c in range(9)}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sums = {}
    for r in range(9):
        row = lines[2 * r + 1]
        for m in re.finditer(r"\d+", row):
            sums[(r, (m.start() - 1) // 4)] = int(m.group())
        for c in range(9):
            if c < 8 and row[4 * c + 4] not in "|║":
                parent[find((r, c))] = find((r, c + 1))
            if r < 8 and lines[2 * r + 2][4 * c + 1:4 * c + 4].strip() == "":
                parent[find((r, c))] = find((r + 1, c))
    groups = defaultdict(list)
    for x in parent:
        groups[find(x)].append(x)
    cages = []
    for cells in groups.values():
        labels = [sums[x] for x in cells if x in sums]
        if len(labels) != 1:
            raise ValueError(f"cage {sorted(cells)} has sum labels {labels}")
        cages.append((labels[0], sorted(cells), 41))
    if sum(s for s, _, _ in cages) != 405:
        raise ValueError("cage sums don't total 405")
    return cages


def load_hard(name):
    """(cages, reported difficulty) of one file in tests/hard_puzzles."""
    text = open(os.path.join(HARD_DIR, name), encoding="utf-8").read()
    difficulty = next((line.split(":", 1)[1].strip() for line in text.splitlines()
                       if line.startswith("#reported difficulty")), "?")
    return parse_grid(text), difficulty


def hard_names():
    return sorted(n for n in os.listdir(HARD_DIR) if n.endswith(".txt"))


def is_valid_solution(board, cages):
    """Every house holds 1-9 once and every cage sums right with distinct digits."""
    houses_ok = all(sorted(board[r][c] for r, c in get_house_cells(t, i)) == list(range(1, 10))
                    for t in ("row", "col", "box") for i in range(9))
    return houses_ok and all(sum(board[r][c] for r, c in cls) == s
                             and len({board[r][c] for r, c in cls}) == len(cls) for s, cls, _ in cages)


def exact_solutions(cages, limit=2):
    """Up to `limit` full solutions by search (a test oracle, not solver logic)."""
    grid = build_candidates([[0] * 9 for _ in range(9)], cages)
    cand = [to_mask(grid[r][c]) for r in range(9) for c in range(9)]
    flat_cages = [(s, [r * 9 + c for r, c in cls]) for s, cls, _ in cages]
    found = []

    def search(board, masks):
        if len(found) >= limit or not _propagate(board, masks, flat_cages):
            return
        open_cells = [(masks[i].bit_count(), i) for i in range(81) if board[i] == 0]
        if not open_cells:
            found.append([board[r * 9:r * 9 + 9] for r in range(9)])
            return
        _, i = min(open_cells)
        m = masks[i]
        while m:
            low = m & -m
            m ^= low
            trial = masks[:]
            trial[i] = low
            search(board[:], trial)

    search([0] * 81, cand)
    return found
