"""Core Sudoku logic: candidates, cage combinations, board checks."""

from itertools import combinations
from killer.helpers import cell


_DIGIT_SET = set(range(1, 10))  # a set, so the difference below is a fresh mutable set


def get_possible_values(board, row, col):
    """Candidates for a cell based on Sudoku row/column/box constraints."""
    if board[row][col] != 0:
        return set()
    br, bc = (row // 3) * 3, (col // 3) * 3
    used = set(board[row])
    used.update([board[i][col] for i in range(9)], board[br][bc:bc + 3], board[br + 1][bc:bc + 3],
                board[br + 2][bc:bc + 3])
    return _DIGIT_SET - used


def is_solved(board):
    return all(board[r][c] != 0 for r in range(9) for c in range(9))


def check_cages(board, cages):
    return all(sum(board[r][c] for r, c in cls) == s for s, cls, _ in cages)


# --- Digit bitmasks: digit d is bit d, so a candidate set is an int ---

ALL_DIGITS = 0b1111111110
MASK_SUM = [sum(d for d in range(1, 10) if m >> d & 1) for m in range(1024)]


def to_mask(digits):
    m = 0
    for d in digits:
        m |= 1 << d
    return m


def mask_to_set(m):
    return {d for d in range(1, 10) if m >> d & 1}


_SUPPORT_MEMO = {}


def cage_support(cell_masks, total, excluded=0, keep=None):
    """Distinct digits for the given cells summing to `total`, avoiding `excluded`.

    Returns (support, finals): support[i] is the mask of digits cell i takes in
    at least one valid assignment, finals the digit-set masks of the valid
    assignments (only those in `keep`, a frozenset, when given). None if there
    is no valid assignment. Callers must not mutate
    the result: it is memoised, since propagation re-asks about unchanged cages.
    """
    key = (tuple(cell_masks), total, excluded, keep)
    if key in _SUPPORT_MEMO:
        return _SUPPORT_MEMO[key]
    if len(_SUPPORT_MEMO) > 200_000:
        _SUPPORT_MEMO.clear()
    result = _SUPPORT_MEMO[key] = _cage_support(cell_masks, total, excluded, keep)
    return result


def _cage_support(cell_masks, total, excluded, keep=None):
    """Walk the cells keeping every reachable used-digits mask (at most 126
    per step), then walk back from the masks that hit the sum."""
    allowed = ALL_DIGITS & ~excluded
    masks = [m & allowed for m in cell_masks]
    layers = [{0}]
    for cm in masks:
        nxt = set()
        for used in layers[-1]:
            free = cm & ~used
            while free:
                low = free & -free
                nxt.add(used | low)
                free ^= low
        layers.append(nxt)
    finals = {m for m in layers[-1] if MASK_SUM[m] == total and (keep is None or m in keep)}
    if not finals:
        return None
    good = finals
    support = [0] * len(masks)
    for k in range(len(masks) - 1, -1, -1):
        prev_good = set()
        for used in layers[k]:
            free = masks[k] & ~used
            while free:
                low = free & -free
                if used | low in good:
                    support[k] |= low
                    prev_good.add(used)
                free ^= low
        good = prev_good
    return support, finals


# --- Cage combinations ---

_COMBOS = {}
for _size in range(10):
    for _combo in combinations(range(1, 10), _size):
        _COMBOS.setdefault((_size, sum(_combo)), []).append(_combo)


def digit_combos(size, total, excluded=frozenset()):
    """Tuples of `size` distinct digits 1-9 summing to `total`, avoiding `excluded`."""
    return [combo for combo in _COMBOS.get((size, total), ()) if excluded.isdisjoint(combo)]


def get_possible_combinations(cage_sum, size, used_numbers=None):
    """All sets of `size` unique digits (1-9) that sum to `cage_sum`, excluding `used_numbers`."""
    return [set(combo) for combo in digit_combos(size, cage_sum, used_numbers or frozenset())]


def get_cage_candidates(board, row, col, cages):
    """Candidates for a cell filtered by its cage's possible combos."""
    for cage_sum, cells, _ in cages:
        if (row, col) not in cells:
            continue
        filled = [(r, c) for r, c in cells if board[r][c] != 0]
        empty = [(r, c) for r, c in cells if board[r][c] == 0]
        if not empty:
            return set()
        filled_nums = set(board[r][c] for r, c in filled)
        remaining_sum = cage_sum - sum(board[r][c] for r, c in filled)
        possibles = get_possible_combinations(remaining_sum, len(empty), used_numbers=filled_nums)
        if not possibles:
            return set()
        sudoku_cands = get_possible_values(board, row, col)
        return {num for combo in possibles for num in combo if num in sudoku_cands}
    return set(range(1, 10))


def can_assign_combo(combo, empty_cells, cell_candidates):
    """Can the digits in `combo` be assigned 1-to-1 to `empty_cells` respecting candidates?"""
    combo_list = list(combo)
    n = len(empty_cells)
    used = [False] * n

    def match(idx):
        if idx == len(combo_list):
            return True
        num = combo_list[idx]
        for i in range(n):
            if not used[i] and num in cell_candidates[empty_cells[i]]:
                used[i] = True
                if match(idx + 1):
                    return True
                used[i] = False
        return False
    return match(0)


# --- Candidate grid builders ---

def build_candidates(board, cages):
    """Build a 9x9 grid of candidate sets using Sudoku + deep cage combo filtering.

    A digit survives in a cell only if the cage's remaining sum can be made
    with it there and distinct candidates in the other empty cells.
    """
    rows, cols, boxes = [0] * 9, [0] * 9, [0] * 9
    for r in range(9):
        for c in range(9):
            if board[r][c]:
                bit = 1 << board[r][c]
                rows[r] |= bit
                cols[c] |= bit
                boxes[r // 3 * 3 + c // 3] |= bit
    masks = [[0 if board[r][c] else ALL_DIGITS & ~(rows[r] | cols[c] | boxes[r // 3 * 3 + c // 3])
              for c in range(9)] for r in range(9)]
    for cage_sum, cells, _ in cages:
        empty = [(r, c) for r, c in cells if board[r][c] == 0]
        if not empty:
            continue
        filled = [board[r][c] for r, c in cells if board[r][c] != 0]
        result = cage_support([masks[r][c] for r, c in empty], cage_sum - sum(filled), to_mask(filled))
        if result:
            for (r, c), sup in zip(empty, result[0]):
                masks[r][c] &= sup
    return [[mask_to_set(masks[r][c]) for c in range(9)] for r in range(9)]


def candidates_to_dict(candidates):
    """Convert 9x9 candidate grid to {A1: [1,2,...]} dict."""
    return {cell(r, c): sorted(candidates[r][c])
            for r in range(9) for c in range(9) if candidates[r][c]}


def snapshot_candidates(board, cages):
    """Quick candidate snapshot (basic Sudoku + cage filtering, no deep combo check)."""
    result = {}
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                s = get_possible_values(board, r, c) & get_cage_candidates(board, r, c, cages)
                result[cell(r, c)] = sorted(s)
    return result
