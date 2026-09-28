"""
Killer Sudoku solving strategies.

Each strategy function takes (board, cages) and returns True if it placed a value.
When placing, it prints a structured explanation:
  Line 1: "Set cell (r,c) to N via STRATEGY_NAME"
  Lines 2+: indented reasoning (parsed by solve_and_explain for the visualizer)

Strategy tiers (easiest to hardest):
  Tier 1 - Easy:   cage_deduction, rule_of_45, naked_singles
  Tier 2 - Medium: consistent_numbers, cage_candidates, hidden_singles, limited_possible_sums
  Tier 3 - Hard:   rule_of_k, clock_arithmetic, cage_complements, rule_of_necessity
  Tier 4 - Expert: candidate_elimination (naked subsets + pointing + box-line + cage filtering)
"""

from itertools import combinations, product
from killer.helpers import cell, cells, fmt_combos, house_name, cage_desc, get_house_cells
from killer.sudoku import (
    get_possible_values, get_cage_candidates, get_possible_combinations,
    digit_combos, can_assign_combo, build_candidates,
    ALL_DIGITS, MASK_SUM, to_mask, mask_to_set, cage_support,
)


# =============================================================================
# Tier 1 — Easy strategies
# =============================================================================

def apply_cage_deduction(board, cages):
    """Last cell in cage.

    When all cells in a cage are filled except one, the remaining cell's value
    is simply: cage_sum - sum_of_filled_cells.

    Example: Cage sum=15 with cells [A1, A2, A3]. If A1=3 and A2=5,
    then A3 = 15 - 3 - 5 = 7.
    """
    for cage_sum, cage_cells, _ in cages:
        filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if len(empty) != 1:
            continue
        filled_sum = sum(board[r][c] for r, c in filled)
        val = cage_sum - filled_sum
        r, c = empty[0]
        if val in get_possible_values(board, r, c):
            desc = cage_desc(cage_sum, cage_cells, board)
            board[r][c] = val
            print(f"Set cell ({r},{c}) to {val} via cage deduction")
            print(f"  {desc}")
            print(f"  Last cell in cage: {cage_sum} - {filled_sum} = {val}")
            return True
    return False


def apply_rule_of_45(board, cages):
    """Every row, column, and 3x3 box sums to exactly 45.

    If all cages within a house (row/col/box) are fully contained in it
    except for one uncovered cell, that cell = 45 - sum_of_cage_sums.

    Example: Row 1 has cages summing to 38 that are fully inside it.
    The one uncovered cell must be 45 - 38 = 7.
    """
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            house_cells = get_house_cells(house_type, i)
            # Find cages where ALL cells are inside this house
            house_cages = [(s, cls) for s, cls, _ in cages if all(c in house_cells for c in cls)]
            cage_total = sum(s for s, _ in house_cages)
            covered = {c for _, cls in house_cages for c in cls}
            remaining = [c for c in house_cells if c not in covered]
            if len(remaining) != 1:
                continue
            r, c = remaining[0]
            val = 45 - cage_total
            if board[r][c] == 0 and 1 <= val <= 9:
                board[r][c] = val
                cage_list = ", ".join(f"sum={s}" for s, _ in house_cages)
                print(f"Set cell ({r},{c}) to {val} via Rule of 45 ({house_name(house_type, i)})")
                print(f"  {house_name(house_type, i)}: cages inside sum to {cage_total} ({cage_list})")
                print(f"  One uncovered cell: {cell(r, c)} = 45 - {cage_total} = {val}")
                return True
    return False


def apply_naked_singles(board, cages):
    """Only one candidate left.

    If a cell has exactly one possible digit after considering its row, column,
    box, AND cage constraints, that digit must go there.

    This is the simplest deduction: all 8 other digits are already placed or
    blocked somewhere in the cell's row, column, box, or cage.
    """
    for r in range(9):
        for c in range(9):
            if board[r][c] != 0:
                continue
            poss = get_possible_values(board, r, c) & get_cage_candidates(board, r, c, cages)
            if len(poss) == 1:
                num = next(iter(poss))
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via naked single")
                print(f"  {cell(r, c)} has only one candidate: {num}")
                print(f"  All other digits are blocked by row, column, box, or cage constraints")
                return True
    return False


# =============================================================================
# Tier 2 — Medium strategies
# =============================================================================

def apply_consistent_numbers(board, cages):
    """Digit appears in ALL valid combos and only one cell can hold it.

    For a cage's remaining empty cells, enumerate all possible digit combinations
    that sum correctly. If a digit appears in EVERY valid combo, it MUST be in
    this cage. If only one empty cell can hold that digit (by Sudoku rules),
    place it there.

    Example: Cage sum=16, 2 empty cells. Valid combos: {7,9}. Both 7 and 9
    must be in this cage. If 7 is blocked in one cell by its row, that cell
    must be 9 and the other must be 7.
    """
    for cage_sum, cage_cells, _ in cages:
        filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        filled_nums = set(board[r][c] for r, c in filled)
        remaining_sum = cage_sum - sum(board[r][c] for r, c in filled)
        possibles = get_possible_combinations(remaining_sum, len(empty), used_numbers=filled_nums)
        if not possibles:
            continue
        # Digits that appear in ALL combos — they MUST be in this cage
        common = set.intersection(*possibles)
        for num in common:
            valid_cells = [cl for cl in empty if num in get_possible_values(board, cl[0], cl[1])]
            if len(valid_cells) == 1:
                r, c = valid_cells[0]
                desc = cage_desc(cage_sum, cage_cells, board)
                combos = fmt_combos(possibles)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via consistent numbers in cage")
                print(f"  {desc}")
                print(f"  Combos: {combos}")
                print(f"  {num} is in ALL combos; only {cell(r, c)} can hold it (row/col/box block other cells)")
                return True
    return False


def apply_cage_candidates(board, cages):
    """Filter candidates by cage combos + Sudoku, place if only one remains.

    For each empty cell in a cage, compute which digits could appear in ANY
    valid combo AND pass Sudoku constraints. If a cell has only one such digit,
    place it. Also checks if a digit that must be in the cage can only fit in
    one cell (hidden single within cage).
    """
    for cage_sum, cage_cells, _ in cages:
        filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        filled_nums = set(board[r][c] for r, c in filled)
        remaining_sum = cage_sum - sum(board[r][c] for r, c in filled)
        possibles = get_possible_combinations(remaining_sum, len(empty), used_numbers=filled_nums)
        if not possibles:
            continue
        # For each cell: which digits appear in any combo AND pass Sudoku?
        per_cell = {}
        for r, c in empty:
            sudoku = get_possible_values(board, r, c)
            per_cell[(r, c)] = {num for combo in possibles for num in combo if num in sudoku}
        # Naked single within cage: cell has only one possible digit
        for (r, c), poss in per_cell.items():
            if len(poss) == 1:
                num = next(iter(poss))
                desc = cage_desc(cage_sum, cage_cells, board)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via cage candidates")
                print(f"  {desc}")
                print(f"  After cage combo + Sudoku filtering, {cell(r, c)} can only be {num}")
                return True
        # Hidden single within cage: digit must be in cage, only one cell can hold it
        must_have = set.intersection(*possibles)
        for num in must_have:
            holders = [cl for cl, poss in per_cell.items() if num in poss]
            if len(holders) == 1:
                r, c = holders[0]
                desc = cage_desc(cage_sum, cage_cells, board)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via cage elimination")
                print(f"  {desc}")
                print(f"  {num} must be in this cage (in all combos) and only {cell(r, c)} can hold it")
                return True
    return False


def apply_hidden_single_house(board, cages):
    """A digit can only go in one cell within a row, column, or box.

    Scans each house for digits 1-9. If a digit's only valid position in that
    house is a single cell (considering both Sudoku and cage constraints),
    place it there.

    Example: In row 3, the digit 5 can only go in cell E3 because all other
    cells in row 3 either already have a value, or 5 is blocked by their
    column/box/cage.
    """
    # Precompute all candidates once (avoid recalculating per house)
    all_cands = {}
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                all_cands[(r, c)] = get_possible_values(board, r, c) & get_cage_candidates(board, r, c, cages)
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            hcells = get_house_cells(house_type, i)
            for num in range(1, 10):
                positions = [cl for cl in hcells if cl in all_cands and num in all_cands[cl]]
                if len(positions) == 1:
                    r, c = positions[0]
                    board[r][c] = num
                    hn = house_name(house_type, i)
                    # Explain why other cells can't hold this digit
                    blocked = [cl for cl in hcells if cl != (r, c) and board[cl[0]][cl[1]] == 0]
                    reasons = []
                    for br, bc in blocked:
                        if num not in get_possible_values(board, br, bc):
                            reasons.append(f"{cell(br, bc)}: blocked by row/col/box")
                        elif num not in get_cage_candidates(board, br, bc, cages):
                            reasons.append(f"{cell(br, bc)}: blocked by cage constraint")
                    print(f"Set cell ({r},{c}) to {num} via hidden single in {hn}")
                    print(f"  In {hn}, {num} can only go in {cell(r, c)}")
                    if reasons:
                        print(f"  Why: {'; '.join(reasons)}")
                    return True
    return False


def apply_limited_possible_sums(board, cages):
    """Filter combos by assignment feasibility, then place.

    Goes beyond basic combo filtering: for each combo, checks whether its
    digits can actually be assigned to the empty cells considering each cell's
    Sudoku candidates (using bipartite matching). This eliminates combos that
    look valid on paper but can't work given the current board state.

    Example: Cage sum=10, 2 cells. Combos {1,9},{2,8},{3,7},{4,6}. But if
    cell A can only hold {1,2,3} and cell B can only hold {1,2,3}, then only
    {1,9} and {2,8} are invalid (9 and 8 can't go in either cell), leaving
    only {3,7} -- wait, 7 can't go either. So maybe no combos work, revealing
    an error, or maybe only one works, narrowing candidates.
    """
    for cage_sum, cage_cells, _ in cages:
        filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        filled_nums = set(board[r][c] for r, c in filled)
        remaining_sum = cage_sum - sum(board[r][c] for r, c in filled)
        cell_cands = {cl: get_possible_values(board, cl[0], cl[1]) for cl in empty}
        # Only keep combos that can actually be assigned to cells
        combos = [combo for combo in digit_combos(len(empty), remaining_sum, filled_nums)
                  if can_assign_combo(combo, empty, cell_cands)]
        if not combos:
            continue
        # Digit in all combos, only one cell can hold it
        common = set(combos[0])
        for combo in combos[1:]:
            common &= set(combo)
        for num in common:
            holders = [cl for cl in empty if num in cell_cands[cl]]
            if len(holders) == 1:
                r, c = holders[0]
                desc = cage_desc(cage_sum, cage_cells, board)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via limited possible sums")
                print(f"  {desc}")
                print(f"  Valid combos: {fmt_combos(combos)}")
                print(f"  {num} is in all combos and only {cell(r, c)} can hold it")
                return True
        # Cell that can only be one digit across all combos
        for cl in empty:
            poss = {num for combo in combos for num in combo if num in cell_cands[cl]}
            if len(poss) == 1:
                num = next(iter(poss))
                desc = cage_desc(cage_sum, cage_cells, board)
                board[cl[0]][cl[1]] = num
                print(f"Set cell ({cl[0]},{cl[1]}) to {num} via cage hidden single")
                print(f"  {desc}")
                print(f"  Valid combos: {fmt_combos(combos)}")
                print(f"  Across all combos, {cell(*cl)} can only be {num}")
                return True
    return False


# =============================================================================
# Tier 3 — Hard strategies
# =============================================================================

def apply_rule_of_necessity(board, cages):
    """Digit must be in cage (in all combos) and only one cell can hold it.

    Similar to consistent_numbers but with a different iteration order over
    cages, which can catch cases the other misses due to early-exit behavior.
    """
    for cage_sum, cage_cells, _ in cages:
        filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        filled_nums = set(board[r][c] for r, c in filled)
        remaining_sum = cage_sum - sum(board[r][c] for r, c in filled)
        possibles = get_possible_combinations(remaining_sum, len(empty), used_numbers=filled_nums)
        if not possibles:
            continue
        common = set.intersection(*possibles)
        for num in common:
            valid_cells = [cl for cl in empty if num in get_possible_values(board, cl[0], cl[1])]
            if len(valid_cells) == 1:
                r, c = valid_cells[0]
                desc = cage_desc(cage_sum, cage_cells, board)
                combos = fmt_combos(possibles)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via Rule of Necessity")
                print(f"  {desc}")
                print(f"  Combos: {combos}")
                print(f"  {num} must be in this cage and only {cell(r, c)} can hold it")
                return True
    return False


def apply_clock_arithmetic(board, cages):
    """Outie/innie deduction from partial cage overlap.

    If every cage touching a house (row/col/box) is fully inside it EXCEPT
    one cage that sticks out by exactly one cell (the "outie"), then:
      outie_value = sum_of_all_touching_cages - 45

    This works because the house must sum to 45, and all fully-inside cages
    contribute their exact sum. The one cage that sticks out contributes its
    sum minus the outie cell. So: total - outie = 45, thus outie = total - 45.

    Example: Box 1 has cages summing to 52, with one cage having a cell outside
    the box. That outside cell = 52 - 45 = 7.
    """
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            house_cells = get_house_cells(house_type, i)
            touching = [cage for cage in cages if any(c in house_cells for c in cage[1])]
            partial = [cage for cage in touching if not all(c in house_cells for c in cage[1])]
            if len(partial) != 1:
                continue
            total = sum(cage[0] for cage in touching)
            outies = [c for c in partial[0][1] if c not in house_cells]
            if len(outies) != 1:
                continue
            val = total - 45
            r, c = outies[0]
            if 1 <= val <= 9 and board[r][c] == 0 and val in get_possible_values(board, r, c):
                board[r][c] = val
                print(f"Set cell ({r},{c}) to {val} via Clock Arithmetic ({house_name(house_type, i)})")
                print(f"  {house_name(house_type, i)}: all touching cages sum to {total}")
                print(f"  Only one cage sticks out, its outie {cell(r, c)} = {total} - 45 = {val}")
                return True
    return False


def apply_cage_complements(board, cages):
    """Complement reasoning for large cages (6+ cells).

    A cage with N cells must contain N of the 9 digits. The "complement" is
    the set of (9-N) digits NOT in the cage. Since the cage sum + complement
    sum = 45, we can enumerate valid complements and find digits that appear
    in ALL complement combos — those digits are NEVER in the cage.

    Example: 7-cell cage with sum=40. Complement is 2 cells summing to 5.
    Complement combos: {1,4}, {2,3}. Digits 1,2,3,4 might not be in cage,
    but only digits in ALL complements are excluded. Here: none (1 is not in
    {2,3}, etc). But if complement were always {1,4}: then 1 and 4 are excluded.
    """
    for cage_sum, cage_cells, _ in cages:
        if len(cage_cells) < 6:
            continue
        comp_sum = 45 - cage_sum
        comp_size = 9 - len(cage_cells)
        if comp_size <= 0 or comp_size >= 9:
            continue
        comp_combos = [set(c) for c in digit_combos(comp_size, comp_sum)]
        if not comp_combos:
            continue
        # Digits in ALL complement combos = digits NEVER in the cage
        excluded = set.intersection(*comp_combos)
        if not excluded:
            continue
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        per_cell = {(r, c): get_possible_values(board, r, c) - excluded for r, c in empty}
        # Naked single after exclusion
        for (r, c), cands in per_cell.items():
            if len(cands) == 1:
                num = next(iter(cands))
                desc = cage_desc(cage_sum, cage_cells, board)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via cage complement elimination")
                print(f"  {desc}")
                print(f"  Complement reasoning: digits {sorted(excluded)} can't be in this cage")
                print(f"  After excluding them, {cell(r, c)} has only {num} left")
                return True
        # Hidden single: only digits outside every complement are sure to be in the cage
        must = set(range(1, 10)) - set().union(*comp_combos)
        placed = {board[r][c] for r, c in cage_cells if board[r][c]}
        for num in sorted(must - placed):
            holders = [cl for cl, poss in per_cell.items() if num in poss]
            if len(holders) == 1:
                r, c = holders[0]
                desc = cage_desc(cage_sum, cage_cells, board)
                board[r][c] = num
                print(f"Set cell ({r},{c}) to {num} via cage complement hidden single")
                print(f"  {desc}")
                print(f"  {num} is in no complement {fmt_combos(comp_combos)}, so it must be in the cage;"
                      f" only {cell(r, c)} can hold it")
                return True
    return False


def apply_rule_of_k(board, cages):
    """Naked subsets (pairs/triples/quads) within a house.

    If N cells in a row/column/box collectively have exactly N candidate digits
    between them, those N digits are "locked" into those N cells. No other cell
    in the house can contain any of those digits.

    Example: In row 5, cells B5 and C5 both have candidates {3,7}. This is a
    naked pair — 3 and 7 are locked into B5 and C5. If cell F5 had {3,7,9},
    we can remove 3 and 7, leaving only 9.

    Works for pairs (2 cells, 2 digits), triples (3,3), and quads (4,4).
    """
    size_names = {2: "pair", 3: "triple", 4: "quad"}
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            house_cells = get_house_cells(house_type, i)
            empties = [cl for cl in house_cells if board[cl[0]][cl[1]] == 0]
            if len(empties) < 2:
                continue
            cands = {cl: get_possible_values(board, cl[0], cl[1]) & get_cage_candidates(board, cl[0], cl[1], cages)
                     for cl in empties}
            for size in range(2, min(5, len(empties) + 1)):
                # Every cell of a naked k-subset has at most k candidates.
                small = [cl for cl in empties if len(cands[cl]) <= size]
                for subset in combinations(small, size):
                    union = set().union(*(cands[cl] for cl in subset))
                    if len(union) != size:
                        continue  # Not a naked subset
                    # Found naked subset — check if it resolves another cell
                    for cl in empties:
                        if cl in subset or board[cl[0]][cl[1]] != 0:
                            continue
                        remaining = cands[cl] - union
                        if len(remaining) == 1 and remaining != cands[cl]:
                            num = next(iter(remaining))
                            name = size_names.get(size, f"{size}-set")
                            board[cl[0]][cl[1]] = num
                            print(f"Set cell ({cl[0]},{cl[1]}) to {num} via Rule of K")
                            print(f"  {house_name(house_type, i)}: [{cells(subset)}] form a naked {name} = {sorted(union)}")
                            print(f"  Those {size} digits are locked into those {size} cells")
                            print(f"  Removing {sorted(union)} from {cell(*cl)} leaves only {num}")
                            return True
    return False


# =============================================================================
# Tier 4 — Expert: Advanced candidate elimination
#
# These operate on a full 9x9 candidate grid and use multiple elimination
# techniques iteratively until a placement can be made.
# =============================================================================

def eliminate_naked_subsets(candidates, log=None, single_step=False):
    """Naked pairs/triples/quads elimination on the candidate grid.

    Same logic as apply_rule_of_k but operates on the candidate grid directly
    (removing candidates rather than placing values), allowing multiple
    eliminations to chain together.
    """
    changed = False
    size_names = {2: "Naked Pair", 3: "Naked Triple", 4: "Naked Quad"}
    for hn, hcells in _house_list():
        empty = [(r, c) for r, c in hcells if candidates[r][c]]
        masks = {(r, c): to_mask(candidates[r][c]) for r, c in empty}
        for size in range(2, min(5, len(empty))):
            # Every cell of a naked k-subset has at most k candidates.
            small = [x for x in empty if masks[x].bit_count() <= size]
            for subset in combinations(small, size):
                union = 0
                for x in subset:
                    union |= masks[x]
                if union.bit_count() != size:
                    continue
                affected = []
                for r, c in empty:
                    if masks[(r, c)] & union and (r, c) not in subset:
                        removed = mask_to_set(masks[(r, c)] & union)
                        candidates[r][c] -= removed
                        masks[(r, c)] &= ~union
                        affected.append((cell(r, c), sorted(removed)))
                if affected:
                    changed = True
                if affected and log is not None:
                    name = size_names.get(size, f"Naked {size}-set")
                    removals = ", ".join(f"{sorted(d)} from {c}" for c, d in affected)
                    log.append(f"{name} in {hn}: [{cells(subset)}] = {sorted(mask_to_set(union))} -> removed {removals}")
                    if single_step:
                        return True
    return changed


def eliminate_pointing(candidates, log=None, single_step=False):
    """Pointing pairs/triples.

    If a digit within a box can only appear in cells that share the same row
    (or column), then that digit can be eliminated from the rest of that row
    (or column) outside the box.

    Example: In box 1, digit 5 can only go in A1 or B1 (both in row 1).
    Therefore 5 can't be anywhere else in row 1 -> remove 5 from C1..I1.
    """
    changed = False
    for i in range(9):
        br, bc = (i // 3) * 3, (i % 3) * 3
        box_cells = set((br + r, bc + c) for r in range(3) for c in range(3))
        for num in range(1, 10):
            positions = [(r, c) for r, c in box_cells if num in candidates[r][c]]
            if len(positions) < 2:
                continue
            rows = set(r for r, c in positions)
            cols = set(c for r, c in positions)
            # All positions in same row -> eliminate from rest of that row
            if len(rows) == 1:
                row = next(iter(rows))
                affected = []
                for c in range(9):
                    if (row, c) not in box_cells and num in candidates[row][c]:
                        candidates[row][c].discard(num)
                        affected.append(cell(row, c))
                if affected:
                    changed = True
                if affected and log is not None:
                    log.append(f"Pointing: {num} in box {i+1} only in row {row+1} -> removed {num} from {', '.join(affected)}")
                    if single_step:
                        return True
            # All positions in same column -> eliminate from rest of that column
            if len(cols) == 1:
                col = next(iter(cols))
                affected = []
                for r in range(9):
                    if (r, col) not in box_cells and num in candidates[r][col]:
                        candidates[r][col].discard(num)
                        affected.append(cell(r, col))
                if affected:
                    changed = True
                if affected and log is not None:
                    log.append(f"Pointing: {num} in box {i+1} only in col {col+1} -> removed {num} from {', '.join(affected)}")
                    if single_step:
                        return True
    return changed


def eliminate_box_line(candidates, log=None, single_step=False):
    """Box-line reduction (inverse of pointing).

    If a digit within a row (or column) can only appear in cells that share
    the same box, then that digit can be eliminated from the rest of that box.

    Example: In row 2, digit 8 can only go in D2 or E2 (both in box 2).
    Therefore 8 can't be anywhere else in box 2 -> remove 8 from D1, E1, F1, etc.
    """
    changed = False
    for house_type in ["row", "col"]:
        for i in range(9):
            hcells = get_house_cells(house_type, i)
            for num in range(1, 10):
                positions = [(r, c) for r, c in hcells if num in candidates[r][c]]
                if len(positions) < 2:
                    continue
                boxes = set((r // 3, c // 3) for r, c in positions)
                if len(boxes) == 1:
                    brow, bcol = next(iter(boxes))
                    box_cells = [(brow * 3 + r, bcol * 3 + c) for r in range(3) for c in range(3)]
                    pos_set = set(positions)
                    affected = []
                    for r, c in box_cells:
                        if (r, c) not in pos_set and num in candidates[r][c]:
                            candidates[r][c].discard(num)
                            affected.append(cell(r, c))
                    if affected:
                        changed = True
                    if affected and log is not None:
                        hn = house_name(house_type, i)
                        log.append(f"Box-line: {num} in {hn} only in box {brow*3+bcol//3+1} -> removed {num} from {', '.join(affected)}")
                        if single_step:
                            return True
    return changed


def _cage_must_have_digits(board, cage_sum, cage_cells, candidates):
    """Return the set of digits that MUST appear in this cage (in all valid combos)."""
    empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
    if not empty:
        return set()
    filled = [board[r][c] for r, c in cage_cells if board[r][c] != 0]
    result = cage_support([to_mask(candidates[r][c]) for r, c in empty], cage_sum - sum(filled), to_mask(filled))
    if not result:
        return set()
    must = ALL_DIGITS
    for m in result[1]:
        must &= m
    return mask_to_set(must)


def eliminate_cage_claiming(candidates, board, cages, log=None, single_step=False):
    """Cage claiming: if a digit MUST be in a cage (all combos have it), remove it
    from non-cage cells in every house the cage is fully inside.

    Example: Cage sum=17 with 2 cells in box 1, only combo {8,9}.
    Both 8 and 9 must be in this cage. Remove 8 and 9 from all other
    cells in box 1 (and from the row/column if the cage is fully inside one).

    This is broader than cage-pointing (which requires confinement to one row/col)
    — it works whenever the entire cage sits inside a single house.
    """
    changed = False
    for cage_sum, cage_cells, _ in cages:
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        cage_set = set(map(tuple, cage_cells))
        must_have = _cage_must_have_digits(board, cage_sum, cage_cells, candidates)
        if not must_have:
            continue
        # Check which houses this cage is fully inside
        for house_type in ["row", "col", "box"]:
            for hi in range(9):
                hcells = set(get_house_cells(house_type, hi))
                if not cage_set <= hcells:
                    continue  # cage not fully inside this house
                # Cage is fully in this house — must-have digits are claimed
                for num in must_have:
                    affected = []
                    for (r, c) in hcells:
                        if (r, c) not in cage_set and candidates[r][c] and num in candidates[r][c]:
                            candidates[r][c].discard(num)
                            affected.append(cell(r, c))
                    if affected:
                        changed = True
                    if affected and log is not None:
                        hn = house_name(house_type, hi)
                        cage_str = cells(cage_cells)
                        log.append(f"Cage claiming: {num} must be in cage sum={cage_sum} [{cage_str}]"
                                   f" (in all combos) -> removed {num} from {', '.join(affected)} in {hn}")
                        if single_step:
                            return True
    return changed


def eliminate_cage_pointing(candidates, board, cages, log=None, single_step=False):
    """Cage-pointing: if a digit that MUST be in a cage can only go in cells
    sharing the same row or column, eliminate it from the rest of that row/column.

    Key constraint: only applies to digits in ALL valid combos for the cage.
    A digit that appears in some combos but not all might not be in the cage,
    so confining it to one row/col proves nothing.

    Example: A 9-cell cage (sum=45) must have all digits 1-9. If digit 6 can
    only go in cells that are all in row 3, then 6 can't be elsewhere in row 3.
    """
    changed = False
    for cage_sum, cage_cells, _ in cages:
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if len(empty) < 2:
            continue
        cage_set = set(map(tuple, cage_cells))
        # Only check digits guaranteed to be in this cage
        must_have = _cage_must_have_digits(board, cage_sum, cage_cells, candidates)
        for num in must_have:
            positions = [(r, c) for r, c in empty if num in candidates[r][c]]
            if len(positions) < 2:
                continue
            rows = set(r for r, c in positions)
            cols = set(c for r, c in positions)
            if len(rows) == 1:
                row = next(iter(rows))
                affected = []
                for c in range(9):
                    if (row, c) not in cage_set and num in candidates[row][c]:
                        candidates[row][c].discard(num)
                        affected.append(cell(row, c))
                if affected:
                    changed = True
                if affected and log is not None:
                    cage_str = cells(cage_cells)
                    log.append(f"Cage-pointing: {num} must be in cage sum={cage_sum} [{cage_str}], only in row {row+1} -> removed {num} from {', '.join(affected)}")
                    if single_step:
                        return True
            if len(cols) == 1:
                col = next(iter(cols))
                affected = []
                for r in range(9):
                    if (r, col) not in cage_set and num in candidates[r][col]:
                        candidates[r][col].discard(num)
                        affected.append(cell(r, col))
                if affected:
                    changed = True
                if affected and log is not None:
                    cage_str = cells(cage_cells)
                    log.append(f"Cage-pointing: {num} must be in cage sum={cage_sum} [{cage_str}], only in col {col+1} -> removed {num} from {', '.join(affected)}")
                    if single_step:
                        return True
    return changed


def eliminate_cage_box_reduction(candidates, board, cages, log=None, single_step=False):
    """Cage-box reduction: if a digit that MUST be in a cage can only go in
    cells within one box, eliminate it from the rest of that box (outside cage).

    Key constraint: only applies to digits in ALL valid combos for the cage.

    Example: An L-shaped cage spans boxes 1 and 2, sum guarantees digit 4 must
    be present. If 4 can only go in cage cells within box 1, then 4 can't be
    elsewhere in box 1.
    """
    changed = False
    for cage_sum, cage_cells, _ in cages:
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if len(empty) < 2:
            continue
        cage_set = set(map(tuple, cage_cells))
        must_have = _cage_must_have_digits(board, cage_sum, cage_cells, candidates)
        for num in must_have:
            positions = [(r, c) for r, c in empty if num in candidates[r][c]]
            if len(positions) < 2:
                continue
            boxes = set((r // 3, c // 3) for r, c in positions)
            if len(boxes) == 1:
                br, bc = next(iter(boxes))
                box_cells = [(br * 3 + r, bc * 3 + c) for r in range(3) for c in range(3)]
                affected = []
                for r, c in box_cells:
                    if (r, c) not in cage_set and num in candidates[r][c]:
                        candidates[r][c].discard(num)
                        affected.append(cell(r, c))
                if affected:
                    changed = True
                if affected and log is not None:
                    cage_str = cells(cage_cells)
                    log.append(f"Cage-box: {num} must be in cage sum={cage_sum} [{cage_str}], only in box {br*3+bc//3+1} -> removed {num} from {', '.join(affected)}")
                    if single_step:
                        return True
    return changed


def eliminate_x_wing(candidates, log=None, single_step=False):
    """X-Wing: if a digit appears in exactly 2 columns in 2 different rows
    (same 2 columns), eliminate it from those columns in all other rows.
    Also checks columns-in-rows (transposed).

    Example: digit 3 in row 2 can only be in cols 4,7. In row 6, also only
    cols 4,7. Then 3 must be at (2,4)+(6,7) or (2,7)+(6,4). Either way,
    cols 4 and 7 are "claimed" by rows 2,6 -> remove 3 from cols 4,7 in
    all other rows.
    """
    changed = False
    for num in range(1, 10):
        # Row-based X-Wing: find rows where num appears in exactly 2 columns
        for base_type, cross_type in [("row", "col"), ("col", "row")]:
            lines = {}  # line_index -> [positions in cross direction]
            for i in range(9):
                if base_type == "row":
                    positions = [c for c in range(9) if candidates[i][c] and num in candidates[i][c]]
                else:
                    positions = [r for r in range(9) if candidates[r][i] and num in candidates[r][i]]
                if len(positions) == 2:
                    lines[i] = tuple(positions)
            # Find pairs of lines with same 2 cross-positions
            for (i1, pos1), (i2, pos2) in combinations(lines.items(), 2):
                if pos1 != pos2:
                    continue
                p1, p2 = pos1
                affected = []
                for i in range(9):
                    if i == i1 or i == i2:
                        continue
                    if base_type == "row":
                        for c in [p1, p2]:
                            if candidates[i][c] and num in candidates[i][c]:
                                candidates[i][c].discard(num)
                                affected.append(cell(i, c))
                    else:
                        for r in [p1, p2]:
                            if candidates[r][i] and num in candidates[r][i]:
                                candidates[r][i].discard(num)
                                affected.append(cell(r, i))
                if affected:
                    changed = True
                if affected and log is not None:
                    if base_type == "row":
                        log.append(f"X-Wing: {num} in rows {i1+1},{i2+1} x cols {p1+1},{p2+1}"
                                   f" -> removed {num} from {', '.join(affected)}")
                    else:
                        log.append(f"X-Wing: {num} in cols {i1+1},{i2+1} x rows {p1+1},{p2+1}"
                                   f" -> removed {num} from {', '.join(affected)}")
                    if single_step:
                        return True
    return changed


def eliminate_hidden_subsets(candidates, log=None, single_step=False):
    """Hidden pairs/triples: if N digits can only go in N cells within a house,
    those cells can't contain any OTHER digits.

    This is the inverse of naked subsets:
    - Naked: "these N cells share N candidates" -> remove from other cells
    - Hidden: "these N digits share N cells" -> remove other candidates from those cells

    Example: In row 5, digits 6 and 9 can only go in A5 or E5.
    So A5 and E5 must be {6,9} -> remove everything else from A5 and E5.
    """
    changed = False
    size_names = {2: "Hidden Pair", 3: "Hidden Triple", 4: "Hidden Quad"}
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            hcells = get_house_cells(house_type, i)
            empties = [(r, c) for r, c in hcells if candidates[r][c]]
            if len(empties) < 3:
                continue
            # For each digit, find which empty cells can hold it
            digit_positions = {}
            for num in range(1, 10):
                positions = [(r, c) for r, c in empties if num in candidates[r][c]]
                if 2 <= len(positions) <= 4:
                    digit_positions[num] = positions
            # Try subsets of digits
            for size in range(2, min(5, len(empties))):
                for digit_subset in combinations(digit_positions.keys(), size):
                    # Cells that can hold ANY of these digits
                    union_cells = set()
                    for d in digit_subset:
                        union_cells.update(digit_positions[d])
                    if len(union_cells) != size:
                        continue
                    # Hidden subset found! Remove all OTHER candidates from these cells
                    digit_set = set(digit_subset)
                    affected = []
                    for r, c in union_cells:
                        extras = candidates[r][c] - digit_set
                        if extras:
                            candidates[r][c] &= digit_set
                            affected.append((cell(r, c), sorted(extras)))
                    if affected:
                        changed = True
                    if affected and log is not None:
                        name = size_names.get(size, f"Hidden {size}-set")
                        hn = house_name(house_type, i)
                        digit_str = ",".join(str(d) for d in sorted(digit_subset))
                        cell_str = cells(sorted(union_cells))
                        removals = ", ".join(f"{sorted(ex)} from {cn}" for cn, ex in affected)
                        log.append(f"{name} in {hn}: {{{digit_str}}} only in [{cell_str}]"
                                   f" -> removed {removals}")
                        if single_step:
                            return True
    return changed


def eliminate_generalized_outies(candidates, board, cages, log=None, single_step=False):
    """Generalized innies/outies for 2-cell outies.

    Extension of Clock Arithmetic: if all cages touching a house sum to T,
    and one cage sticks out by exactly 2 cells, those 2 outie cells must
    sum to T - 45. This constrains which digit pairs are valid, eliminating
    candidates that don't appear in any feasible pair.

    Example: Row 1 cages sum to 52, one cage has 2 cells outside row 1.
    Those 2 cells sum to 52 - 45 = 7. Valid pairs: {1,6},{2,5},{3,4}.
    Any candidate not in {1,2,3,4,5,6} can be removed from those cells.
    """
    changed = False
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            hcells = set(get_house_cells(house_type, i))
            touching = [cage for cage in cages if any(tuple(c) in hcells for c in cage[1])]
            partial = [cage for cage in touching if not all(tuple(c) in hcells for c in cage[1])]
            if len(partial) != 1:
                continue
            total = sum(cage[0] for cage in touching)
            outies = [(r, c) for r, c in partial[0][1] if (r, c) not in hcells]
            if len(outies) != 2:
                continue
            outie_sum = total - 45
            if outie_sum < 3 or outie_sum > 17:
                continue
            (r1, c1), (r2, c2) = outies
            if board[r1][c1] != 0 or board[r2][c2] != 0:
                continue
            # Find valid digit pairs that sum to outie_sum
            cands1 = candidates[r1][c1]
            cands2 = candidates[r2][c2]
            if not cands1 or not cands2:
                continue
            # Both cells must have different digits (they're in the same cage)
            valid_pairs = []
            for a in range(1, 10):
                b = outie_sum - a
                if b <= 0 or b >= 10 or a == b:
                    continue
                if a > b:
                    continue  # avoid duplicates
                if (a in cands1 and b in cands2) or (b in cands1 and a in cands2):
                    valid_pairs.append((a, b))
            if not valid_pairs:
                continue
            # Which digits appear in any valid pair?
            allowed = set()
            for a, b in valid_pairs:
                allowed.add(a)
                allowed.add(b)
            # Remove candidates not in any valid pair
            removed1 = cands1 - allowed
            removed2 = cands2 - allowed
            if not removed1 and not removed2:
                continue
            if removed1:
                candidates[r1][c1] -= removed1
            if removed2:
                candidates[r2][c2] -= removed2
            changed = True
            if log is not None:
                hn = house_name(house_type, i)
                pairs_str = " ".join(f"{{{a},{b}}}" for a, b in valid_pairs)
                parts = []
                if removed1:
                    parts.append(f"{sorted(removed1)} from {cell(r1, c1)}")
                if removed2:
                    parts.append(f"{sorted(removed2)} from {cell(r2, c2)}")
                log.append(f"Outie pair in {hn}: {cell(r1,c1)}+{cell(r2,c2)}={outie_sum}"
                           f" (pairs: {pairs_str}) -> removed {', '.join(parts)}")
                if single_step:
                    return True
    return changed


def eliminate_xy_wing(candidates, log=None, single_step=False):
    """XY-Wing: three cells with 2 candidates each in a pivot-wing pattern.

    Setup: Pivot has {A, B}. Wing1 has {A, C}. Wing2 has {B, C}.
    - Pivot sees Wing1 (shares row/col/box)
    - Pivot sees Wing2 (shares row/col/box)
    - Wing1 and Wing2 don't need to see each other

    Logic: Pivot is A or B.
    - If Pivot=A -> Wing1 can't be A -> Wing1=C
    - If Pivot=B -> Wing2 can't be B -> Wing2=C
    Either way, C appears in Wing1 or Wing2 (or both).

    Any cell that sees BOTH Wing1 AND Wing2 can't be C.

    Example: Pivot A1={3,7}, Wing1 A5={3,9}, Wing2 D1={7,9}.
    C=9 must be in A5 or D1. Cell D5 sees both -> remove 9 from D5.
    """
    changed = False
    def sees(r1, c1, r2, c2):
        """Do two cells share a row, column, or box?"""
        if r1 == r2 or c1 == c2:
            return True
        return (r1 // 3 == r2 // 3) and (c1 // 3 == c2 // 3)

    # Find all cells with exactly 2 candidates
    bi_cells = []
    for r in range(9):
        for c in range(9):
            if len(candidates[r][c]) == 2:
                bi_cells.append((r, c, frozenset(candidates[r][c])))

    for pi, (pr, pc, p_cands) in enumerate(bi_cells):
        if len(p_cands) != 2:
            continue
        a, b = sorted(p_cands)
        # Find Wing1: sees pivot, shares exactly one digit with pivot, has 2 candidates
        for wi, (w1r, w1c, w1_cands) in enumerate(bi_cells):
            if wi == pi:
                continue
            if not sees(pr, pc, w1r, w1c):
                continue
            shared1 = p_cands & w1_cands
            if len(shared1) != 1:
                continue
            a_shared = next(iter(shared1))  # digit shared with pivot
            c_digit_options = w1_cands - shared1  # the "C" digit from wing1
            if len(c_digit_options) != 1:
                continue
            c_digit = next(iter(c_digit_options))
            # The other pivot digit
            b_shared = next(iter(p_cands - shared1))
            # Find Wing2: sees pivot, has {b_shared, c_digit}
            for wj, (w2r, w2c, w2_cands) in enumerate(bi_cells):
                if wj == pi or wj == wi:
                    continue
                if not sees(pr, pc, w2r, w2c):
                    continue
                if w2_cands != {b_shared, c_digit}:
                    continue
                # XY-Wing found! Eliminate c_digit from cells that see both wings
                affected = []
                for r in range(9):
                    for c in range(9):
                        if (r, c) in ((pr, pc), (w1r, w1c), (w2r, w2c)):
                            continue
                        if not candidates[r][c] or c_digit not in candidates[r][c]:
                            continue
                        if sees(r, c, w1r, w1c) and sees(r, c, w2r, w2c):
                            candidates[r][c].discard(c_digit)
                            affected.append(cell(r, c))
                if affected:
                    changed = True
                if affected and log is not None:
                    log.append(
                        f"XY-Wing: pivot {cell(pr,pc)}={{{a},{b}}}, "
                        f"wing1 {cell(w1r,w1c)}={{{a_shared},{c_digit}}}, "
                        f"wing2 {cell(w2r,w2c)}={{{b_shared},{c_digit}}} "
                        f"-> removed {c_digit} from {', '.join(affected)}"
                    )
                    if single_step:
                        return True
    return changed


def eliminate_cage_interaction(candidates, board, cages, log=None, single_step=False):
    """Cross-cage combo elimination within a house.

    If two cages share a house (row/col/box), and choosing a specific combo
    for cage A would leave zero valid combos for cage B (because the digits
    are all claimed), then that combo is impossible for cage A.

    Example: In box 1, cage A has combos {1,4} {2,3}, cage B has {1,5} {2,4}.
    If B picks {2,4}, cage A can't use {1,4} (4 taken) or {2,3} (2 taken) → dead.
    So B can't be {2,4} → B must be {1,5}.
    """
    changed = False
    for house_type in ["row", "col", "box"]:
        for hi in range(9):
            hcells = set(get_house_cells(house_type, hi))
            # Find cages fully inside this house with unfilled cells
            house_cages = []
            for ci, (cs, cls, _) in enumerate(cages):
                if not all(tuple(c) in hcells for c in cls):
                    continue
                empty = [(r, c) for r, c in cls if board[r][c] == 0]
                if not empty:
                    continue
                filled_nums = set(board[r][c] for r, c in cls if board[r][c] != 0)
                rem_sum = cs - sum(board[r][c] for r, c in cls if board[r][c] != 0)
                cell_cands = {cl: candidates[cl[0]][cl[1]] for cl in empty}
                combos = [combo for combo in digit_combos(len(empty), rem_sum, filled_nums)
                          if can_assign_combo(combo, empty, cell_cands)]
                if combos:
                    house_cages.append((ci, cs, cls, empty, filled_nums, combos))

            if len(house_cages) < 2:
                continue

            # For each pair of cages, check if any combo in cage A
            # invalidates all combos in cage B
            for ai, (ci_a, cs_a, cls_a, empty_a, filled_a, combos_a) in enumerate(house_cages):
                new_combos_a = []
                for combo_a in combos_a:
                    digits_a = set(combo_a)
                    # Check: does this combo leave at least one valid combo for every other cage?
                    valid = True
                    for bi, (ci_b, cs_b, cls_b, empty_b, filled_b, combos_b) in enumerate(house_cages):
                        if ai == bi:
                            continue
                        # Cage B can't use any digit from combo_a (same house = unique digits)
                        surviving = [cb for cb in combos_b if not (set(cb) & digits_a)]
                        if not surviving:
                            valid = False
                            break
                    if valid:
                        new_combos_a.append(combo_a)

                if len(new_combos_a) < len(combos_a):
                    # Some combos eliminated — update candidates
                    removed_combos = [c for c in combos_a if c not in new_combos_a]
                    valid_digits = {num for combo in new_combos_a for num in combo}
                    affected = []
                    for r, c in empty_a:
                        gone = candidates[r][c] - valid_digits
                        if gone:
                            candidates[r][c] -= gone
                            affected.append((cell(r, c), sorted(gone)))
                            changed = True
                    if affected:
                        changed = True
                    if affected and log is not None:
                        hn = house_name(house_type, hi)
                        removed_str = " ".join("{" + ",".join(str(x) for x in sorted(c)) + "}" for c in removed_combos)
                        kept_str = " ".join("{" + ",".join(str(x) for x in sorted(c)) + "}" for c in new_combos_a)
                        rem_detail = ", ".join(f"{sorted(g)} from {cn}" for cn, g in affected)
                        log.append(f"Cage interaction in {hn}: cage sum={cs_a} can't be {removed_str}"
                                   f" (would block other cages) -> kept {kept_str}, removed {rem_detail}")
                        if single_step:
                            return True
    return changed


def _region_list():
    """Weighted house combinations with a known digit total: (name, total, {cell: coefficient}).

    Plain unions of houses total 45 per house. Adding an overlapping line and
    box counts their 3 shared cells twice (total 90); subtracting them leaves
    the two leftovers with opposite signs (total 0).
    """
    regions = []
    for a in range(9):
        for b in range(a, 8 if a == 0 else 9):
            span = f"{a + 1}" if a == b else f"{a + 1}-{b + 1}"
            regions.append((f"rows {span}", 45 * (b - a + 1),
                            {(r, c): 1 for r in range(a, b + 1) for c in range(9)}))
            regions.append((f"columns {span}", 45 * (b - a + 1),
                            {(r, c): 1 for r in range(9) for c in range(a, b + 1)}))
    box = [set(get_house_cells("box", i)) for i in range(9)]
    for i in range(9):
        regions.append((f"box {i + 1}", 45, {x: 1 for x in box[i]}))
    for i in range(9):
        for j in (i + 1, i + 3):
            if j < 9 and (j == i + 3 or i // 3 == j // 3):
                regions.append((f"boxes {i + 1}+{j + 1}", 90, {x: 1 for x in box[i] | box[j]}))
    for i in (0, 1, 3, 4):
        cells_ = box[i] | box[i + 1] | box[i + 3] | box[i + 4]
        regions.append((f"boxes {i + 1},{i + 2},{i + 4},{i + 5}", 180, {x: 1 for x in cells_}))
    for kind in ("row", "col"):
        for li in range(9):
            line = set(get_house_cells(kind, li))
            name = f"{house_name(kind, li)}"
            for bi in range(9):
                if not line & box[bi]:
                    continue
                regions.append((f"{name} + box {bi + 1}", 90,
                                {x: (x in line) + (x in box[bi]) for x in line | box[bi]}))
                regions.append((f"{name} - box {bi + 1}", 0,
                                {x: (x in line) - (x in box[bi]) for x in line ^ box[bi]}))
    return regions


_REGIONS = _region_list()
_SUM_CONSTRAINTS = {}
_SUPPORT_CACHE = {}
# Last refined candidate grid, as (cages key) -> (flat board it was proven on, grid).
_REFINED = {}


def _cages_key(cages):
    return tuple((s, tuple(sorted(map(tuple, cls)))) for s, cls, _ in cages)


def _expr(terms):
    """'A1+2*B2-C3' for [(cell, coefficient), ...]."""
    out = ""
    for x, k in sorted(terms, key=lambda t: (-t[1], t[0])):
        name = cell(*x) if abs(k) == 1 else f"{abs(k)}*{cell(*x)}"
        out += ("+" if k > 0 else "-") + name
    return out[1:] if out.startswith("+") else out


def _sum_constraints(cages, max_cells=5, max_large=8):
    """Linear constraints sum(coefficient * value) == target from the rule of 45.

    Returns (small, large): small ones (<= max_cells terms) are solved exactly
    by enumeration, large ones (up to max_large terms) get virtual cages,
    bounds and parity. Each is (terms, target, why), terms [(cell, coef), ...].

    A cage whose cells all carry one coefficient c is the constant c * sum. A
    straddling cage picks a base b among its cells' coefficients (0 outside
    the region): it contributes b * sum and its cells keep coef - b, which
    gives innies (b = 0), outies (b = 1) and every mix of the two.
    """
    if _SUM_CONSTRAINTS.get("cages") is cages:
        return _SUM_CONSTRAINTS["result"]
    key = _cages_key(cages)
    if _SUM_CONSTRAINTS.get("key") == key:
        _SUM_CONSTRAINTS["cages"] = cages
        return _SUM_CONSTRAINTS["result"]
    # Only the current puzzle is kept, so generating many layouts can't grow this.
    _SUM_CONSTRAINTS.clear()
    _SUPPORT_CACHE.clear()
    caged = {tuple(x) for _, cls, _ in cages for x in cls}
    seen, small, large = set(), [], []
    for name, total, coef in _REGIONS:
        target0 = total
        options = []
        for s, cls, _ in cages:
            cls = [tuple(x) for x in cls]
            ks = [coef.get(x, 0) for x in cls]
            if not any(ks):
                continue
            if len(set(ks)) == 1:
                target0 -= ks[0] * s
                continue
            options.append([(b * s, [(x, k - b) for x, k in zip(cls, ks) if k != b])
                            for b in sorted(set(ks) | {0})])
        n_choices = 1
        for o in options:
            n_choices *= len(o)
        if n_choices > 729:
            continue
        loose = [(x, k) for x, k in coef.items() if x not in caged]
        for choice in product(*options):
            terms = loose + [t for _, ts in choice for t in ts]
            if not terms or len(terms) > max_large:
                continue
            target = target0 - sum(c for c, _ in choice)
            sig = (frozenset(terms), target)
            if sig in seen:
                continue
            seen.add(sig)
            entry = (terms, target, f"{name}: {_expr(terms)} = {target}")
            (small if len(terms) <= max_cells else large).append(entry)
    _SUM_CONSTRAINTS.update(key=key, cages=cages, result=(small, large))
    return small, large


def _must_differ(a, b, cage_of):
    return (a[0] == b[0] or a[1] == b[1] or (a[0] // 3 == b[0] // 3 and a[1] // 3 == b[1] // 3)
            or cage_of.get(a, a) == cage_of.get(b, b))


_DIGIT_OF_BIT = {1 << d: d for d in range(1, 10)}


def _supported_values(terms, target, domains, cage_of):
    """Per-cell values that appear in at least one assignment meeting the sum."""
    order = sorted(range(len(terms)), key=lambda k: len(domains[terms[k][0]]))
    cells_o = [terms[k][0] for k in order]
    coefs = [terms[k][1] for k in order]
    doms = [to_mask(domains[x]) for x in cells_o]
    n = len(order)
    # Bounds of what the remaining suffix can still contribute.
    lo = [0] * (n + 1)
    hi = [0] * (n + 1)
    for k in range(n - 1, -1, -1):
        vals = [coefs[k] * d for d in range(1, 10) if doms[k] >> d & 1]
        lo[k] = lo[k + 1] + min(vals)
        hi[k] = hi[k + 1] + max(vals)
    # The digits ruled out for each later cell are packed 10 bits per cell,
    # nearest cell lowest; choosing a digit at k copies its bit into the slot
    # of every later cell it clashes with (one multiply, no carries).
    spread = [sum(1 << 10 * (j - k - 1) for j in range(k + 1, n)
                  if _must_differ(cells_o[k], cells_o[j], cage_of)) for k in range(n)]
    memo = {}

    def sub(k, acc, forbid):
        """Support masks for cells k.. given the sum so far and the packed
        digits earlier choices rule out; None if infeasible."""
        key = (k, acc, forbid)
        if key in memo:
            return memo[key]
        res = None
        if k == n:
            res = () if acc == target else None
        elif lo[k] <= target - acc <= hi[k]:
            free = doms[k] & ~forbid & 1023
            carried = forbid >> 10
            coef, spr = coefs[k], spread[k]
            while free:
                low = free & -free
                free ^= low
                rest = sub(k + 1, acc + coef * _DIGIT_OF_BIT[low], carried | low * spr)
                if rest is None:
                    continue
                if res is None:
                    res = [low, *rest]
                else:
                    res[0] |= low
                    for i, m in enumerate(rest):
                        res[i + 1] |= m
            if res is not None:
                res = tuple(res)
        memo[key] = res
        return res

    res = sub(0, 0, 0)
    return {cells_o[i]: (mask_to_set(res[i]) if res else set()) for i in range(n)}


def _bounds_and_parity(terms, target, domains):
    """Per-cell values allowed by min/max sums and parity (distinctness ignored)."""
    vals = {x: [k * d for d in domains[x]] for x, k in terms}
    lo = sum(min(v) for v in vals.values())
    hi = sum(max(v) for v in vals.values())
    allowed = {}
    for x, k in terms:
        rest_lo, rest_hi = lo - min(vals[x]), hi - max(vals[x])
        allowed[x] = {d for d in domains[x] if rest_lo <= target - k * d <= rest_hi}
    # Only odd coefficients affect parity; if all but one such cell have a
    # fixed parity, the last one's parity is forced.
    odd = [x for x, k in terms if k % 2]
    unknown = [x for x in odd if len({d % 2 for d in allowed[x]}) > 1]
    if len(unknown) == 1 and all(allowed[x] for x in odd):
        known = sum(next(iter(allowed[x])) % 2 for x in odd if x != unknown[0])
        need = (target - known) % 2
        allowed[unknown[0]] = {d for d in allowed[unknown[0]] if d % 2 == need}
    return allowed


def _prune_by_sum(terms, target, why, candidates, board, cage_of, exact=True):
    """Remove candidates no assignment meeting the sum can use; returns removals.

    `exact` enumerates assignments (small constraints); otherwise it uses
    bounds and parity. `why` names the constraint and keys the result cache.
    """
    domains = {}
    for (r, c), _ in terms:
        domains[(r, c)] = {board[r][c]} if board[r][c] else candidates[r][c]
    if any(not d for d in domains.values()) or all(board[r][c] for (r, c), _ in terms):
        return []
    if exact:
        cache_key = (why, tuple(to_mask(domains[x]) for x, _ in terms))
        support = _SUPPORT_CACHE.get(cache_key)
        if support is None:
            support = _SUPPORT_CACHE[cache_key] = _supported_values(terms, target, domains, cage_of)
    else:
        support = _bounds_and_parity(terms, target, domains)
    if any(not support[x] for x, _ in terms):
        return []  # no assignment fits: leave it for the contradiction checks
    affected = []
    for (r, c), _ in terms:
        if board[r][c]:
            continue
        gone = candidates[r][c] - support[(r, c)]
        if gone:
            candidates[r][c] -= gone
            affected.append((cell(r, c), sorted(gone)))
    return affected


def eliminate_innies_outies(candidates, board, cages, log=None, single_step=False):
    """Rule of 45 over one or several houses, plain or weighted.

    The cages wholly inside a region fix the total of its remaining cells
    (innies); the cages poking out of it fix the total of the cells outside
    (outies); mixing the two gives innie-minus-outie differences. Weighted
    regions (row + box counts the overlap twice, row - box cancels it) give
    more such totals. Any candidate that fits no assignment meeting a total is
    removed. Cells may share a digit only if they neither see each other nor
    share a cage.

    Example: rows 1-2 total 90; the cages inside sum to 79, leaving innies
    C2+G2 = 11. If C2 is {1,2} and G2 is {3,9}, the pairs are 2+9 only.
    """
    changed = False
    cage_of = {tuple(x): k for k, (_, cls, _) in enumerate(cages) for x in cls}
    for terms, target, why in _sum_constraints(cages)[0]:
        affected = _prune_by_sum(terms, target, why, candidates, board, cage_of)
        if affected:
            changed = True
            if log is not None:
                removals = ", ".join(f"{sorted(g)} from {cn}" for cn, g in affected)
                log.append(f"Innies/outies: {why} -> removed {removals}")
                if single_step:
                    return True
    return changed


def _virtual_cages(candidates, board, cages):
    """Cell groups whose total the grid has already proven: (cells, total, why).

    All-positive innie groups from the rule of 45, and naked subsets in a
    house (k cells sharing k candidates hold exactly those digits).
    """
    out = [(frozenset(x for x, _ in terms), target, why)
           for terms, target, why in _sum_constraints(cages)[0]
           if len(terms) >= 2 and all(k == 1 for _, k in terms)]
    for house_type in ("row", "col", "box"):
        for i in range(9):
            empty = [(r, c) for r, c in get_house_cells(house_type, i) if board[r][c] == 0]
            for size in range(2, min(5, len(empty))):
                small = [x for x in empty if len(candidates[x[0]][x[1]]) <= size]
                for group in combinations(small, size):
                    digits = set().union(*(candidates[r][c] for r, c in group))
                    if len(digits) == size:
                        out.append((frozenset(group), sum(digits),
                                    f"naked set {cells(group)} = {sorted(digits)}"))
    return out


def eliminate_large_sums(candidates, board, cages, log=None, single_step=False):
    """Rule-of-45 totals too big to enumerate (6-8 cells).

    Groups whose total is already proven (virtual cages: innie groups, naked
    subsets) are swapped for that constant wherever they sit inside a large
    total with one coefficient; placed digits become constants too. That often
    shrinks it to an enumerable size, which is how one region's innies feed
    the next region's outies. Whatever stays large still gets min/max bounds
    per cell and a parity check.

    Example: rows 1-3 leave 7 innies = 31; a naked pair {4,8} among them is
    12, so the other 5 cells sum to 19 and can be enumerated.
    """
    changed = False
    cage_of = {tuple(x): k for k, (_, cls, _) in enumerate(cages) for x in cls}
    virtual = sorted(_virtual_cages(candidates, board, cages), key=lambda v: -len(v[0]))
    for terms, target, why in _sum_constraints(cages)[1]:
        cur = dict(terms)
        used = []
        for vcells, vsum, vwhy in virtual:
            ks = {cur.get(x) for x in vcells}
            if len(ks) != 1 or None in ks:
                continue
            q = ks.pop()
            for x in vcells:
                del cur[x]
            target -= q * vsum
            used.append(vwhy)
        for (r, c) in list(cur):
            if board[r][c]:
                target -= cur.pop((r, c)) * board[r][c]
        if not cur:
            continue
        reduced = sorted(cur.items())
        affected = _prune_by_sum(reduced, target, f"{_expr(reduced)} = {target}", candidates, board, cage_of,
                                 exact=len(reduced) <= 5)
        if affected:
            changed = True
            if log is not None:
                via = f" using {'; '.join(used)}" if used else ""
                removals = ", ".join(f"{sorted(g)} from {cn}" for cn, g in affected)
                log.append(f"Large sum: {why}{via} -> {_expr(reduced)} = {target} -> removed {removals}")
                if single_step:
                    return True
    return changed


_PEERS = [
    [rr * 9 + cc for rr in range(9) for cc in range(9)
     if (rr, cc) != (r, c) and (rr == r or cc == c or (rr // 3 == r // 3 and cc // 3 == c // 3))]
    for r in range(9) for c in range(9)
]
_HOUSES = [[r * 9 + c for r, c in get_house_cells(t, i)] for t in ("row", "col", "box") for i in range(9)]
# Each box/line overlap as (overlap, rest of the line, rest of the box).
_LOCKS = []
for _b in range(9):
    _box = [r * 9 + c for r, c in get_house_cells("box", _b)]
    for _line in _HOUSES[:18]:
        _overlap = [i for i in _line if i in _box]
        if _overlap:
            _LOCKS.append((_overlap, [i for i in _line if i not in _overlap], [i for i in _box if i not in _overlap]))


def _propagate(board, cand, cages):
    """Apply singles, cage combos and box/line locks until nothing changes.

    `board` and `cand` are flat 81-long lists (digits, candidate masks) that
    are changed in place; `cages` is a list of (sum, cell indices). Returns
    False on a contradiction.
    """
    while True:
        progress = False
        for i in range(81):
            if board[i] == 0:
                m = cand[i]
                if m == 0:
                    return False
                if m & (m - 1) == 0:
                    d = m.bit_length() - 1
                    board[i] = d
                    cand[i] = 0
                    for p in _PEERS[i]:
                        if board[p] == d:
                            return False
                        if cand[p] & m:
                            cand[p] &= ~m
                            if cand[p] == 0:
                                return False
                    progress = True
        for house in _HOUSES:
            placed = once = twice = 0
            for i in house:
                if board[i]:
                    placed |= 1 << board[i]
                else:
                    twice |= once & cand[i]
                    once |= cand[i]
            if ALL_DIGITS & ~(placed | once):
                return False
            lone = once & ~twice
            while lone:
                low = lone & -lone
                lone ^= low
                for i in house:
                    if cand[i] & low and cand[i] != low:
                        cand[i] = low
                        progress = True
        for total, idx in cages:
            filled = [board[i] for i in idx if board[i]]
            fmask = 0
            for d in filled:
                fmask |= 1 << d
            if len(filled) != fmask.bit_count():
                return False
            empty = [i for i in idx if board[i] == 0]
            remaining = total - sum(filled)
            if not empty:
                if remaining:
                    return False
                continue
            result = cage_support([cand[i] for i in empty], remaining, fmask)
            if result is None:
                return False
            for i, sup in zip(empty, result[0]):
                if cand[i] & ~sup:
                    cand[i] &= sup
                    progress = True
        if progress:
            continue
        # Box/line locks are the costly pass; only reached once the rest stall.
        for overlap, line_rest, box_rest in _LOCKS:
            inside = line_m = box_m = 0
            for i in overlap:
                inside |= cand[i]
            for i in line_rest:
                line_m |= cand[i]
            for i in box_rest:
                box_m |= cand[i]
            pointing = inside & ~box_m
            claiming = inside & ~line_m
            for i in line_rest:
                if cand[i] & pointing:
                    cand[i] &= ~pointing
                    progress = True
            for i in box_rest:
                if cand[i] & claiming:
                    cand[i] &= ~claiming
                    progress = True
        if not progress:
            return True


def eliminate_by_contradiction(candidates, board, cages, log=None, single_step=False):
    """Contradiction (forcing): if assuming a candidate leads, through singles,
    cage combinations, pointing and box-line, to an impossible grid, that
    candidate is false.

    Tries cells with the fewest candidates first. Stops once a cell is down to
    one candidate (or at the first elimination with single_step, so the
    explainer shows one at a time).

    Example: E5 is {3,8}. Placing 3 forces C5=7, which leaves cage sum=12
    [C4, C5] needing a 5 that row 4 already has -> E5 can't be 3.
    """
    changed = False
    flat_board = [board[r][c] for r in range(9) for c in range(9)]
    flat_cand = [0 if board[r][c] else to_mask(candidates[r][c]) for r in range(9) for c in range(9)]
    flat_cages = [(s, [r * 9 + c for r, c in cls]) for s, cls, _ in cages]
    order = sorted((m.bit_count(), i) for i, m in enumerate(flat_cand) if m & (m - 1))
    for _, i in order:
        r, c = divmod(i, 9)
        for v in range(1, 10):
            bit = 1 << v
            if not flat_cand[i] & bit or flat_cand[i] == bit:
                continue
            trial = flat_cand[:]
            trial[i] = bit
            if _propagate(flat_board[:], trial, flat_cages):
                continue
            # Still valid after later removals: the grid only ever narrows.
            flat_cand[i] &= ~bit
            candidates[r][c].discard(v)
            changed = True
            if log is not None:
                log.append(f"Contradiction: assuming {cell(r, c)}={v} leads to an impossible grid"
                           f" -> removed {v} from {cell(r, c)}")
            if single_step or flat_cand[i] & (flat_cand[i] - 1) == 0:
                return True
    return changed


# =============================================================================
# Advanced killer techniques (pure logic, level 3)
# =============================================================================

_PEER_SET = {(r, c): {(rr, cc) for rr in range(9) for cc in range(9) if (rr, cc) != (r, c)
                     and (rr == r or cc == c or (rr // 3 == r // 3 and cc // 3 == c // 3))}
             for r in range(9) for c in range(9)}


def _sees(a, b):
    return a[0] == b[0] or a[1] == b[1] or (a[0] // 3 == b[0] // 3 and a[1] // 3 == b[1] // 3)


def _cage_state(board, cage, candidates, keep=None):
    """(empty cells, valid digit-set masks, per-cell support masks) of a cage, or None.

    `keep` limits the digit sets to those masks (a frozenset).
    """
    cage_sum, cage_cells, _ = cage
    empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
    if not empty:
        return None
    filled = [board[r][c] for r, c in cage_cells if board[r][c]]
    res = cage_support([to_mask(candidates[r][c]) for r, c in empty],
                       cage_sum - sum(filled), to_mask(filled), keep)
    return (empty, res[1], res[0]) if res else None


def _restrict_cage(board, cage, candidates, keep):
    """Narrow a cage's cells to assignments whose digit set is in `keep`; returns removals."""
    state = _cage_state(board, cage, candidates, frozenset(keep))
    if state is None:
        return []  # nothing would fit: leave it for the contradiction checks
    removed = []
    for (r, c), sup in zip(state[0], state[2]):
        gone = candidates[r][c] - mask_to_set(sup)
        if gone:
            candidates[r][c] -= gone
            removed.append((cell(r, c), sorted(gone)))
    return removed


_NAMED_HOUSES = [(house_name(t, i), get_house_cells(t, i)) for t in ("row", "col", "box") for i in range(9)]


def _house_list():
    return _NAMED_HOUSES


def _log_removals(log, text, affected):
    removals = ", ".join(f"{sorted(g)} from {cn}" for cn, g in affected)
    log.append(f"{text} -> removed {removals}")


def eliminate_hidden_killer_subsets(candidates, board, cages, log=None, single_step=False):
    """Hidden killer subsets, with mandatory inclusion as the one-digit case.

    In a house, if k digits can only go into k "entities" (single cells, or the
    part of one cage inside the house) and no entity can hold two of them,
    each entity holds exactly one: a cell keeps only those digits, and a cage
    keeps only combos with one of them, placed inside the house (so they leave
    its cells outside it).

    Example (k = 1, mandatory inclusion): every spot for 1 in box 2 lies in
    cage 15/3, so that cage must be {1,5,9} or {1,6,8}.
    Example (k = 2): in row 5, 1 and 2 only fit in cages 5/2 and 9/2; 9/2
    can't hold both, so it must be {1,8} or {2,7}.
    """
    changed = False
    cage_of = {tuple(x): i for i, (_, cls, _) in enumerate(cages) for x in cls}
    for hname, hcells in _house_list():
        placed = {board[r][c] for r, c in hcells if board[r][c]}
        empty = [(r, c) for r, c in hcells if board[r][c] == 0]
        groups = {}
        for x in empty:
            groups.setdefault(cage_of.get(x, x), []).append(x)
        glist = list(groups)
        cage_groups = sum(1 << gi for gi, g in enumerate(glist) if isinstance(g, int))
        states = {}
        holders = None
        digits = [d for d in range(1, 10) if d not in placed]
        for k in (1, 2, 3):
            for subset in combinations(digits, k):
                if holders is None:  # digit -> groups (bitmask) that can still take it; refreshed after a change
                    holders = [0] * 10
                    for gi, g in enumerate(glist):
                        m = 0
                        for r, c in groups[g]:
                            m |= to_mask(candidates[r][c])
                        for d in range(1, 10):
                            if m >> d & 1:
                                holders[d] |= 1 << gi
                ent_bits = 0
                for d in subset:
                    ent_bits |= holders[d]
                if ent_bits.bit_count() != k or not ent_bits & cage_groups:
                    continue  # plain hidden singles/subsets are handled elsewhere
                sset, smask = set(subset), to_mask(subset)
                ents = [glist[gi] for gi in range(len(glist)) if ent_bits >> gi & 1]
                ok = True
                for g in ents:
                    if isinstance(g, int):
                        if g not in states:
                            states[g] = _cage_state(board, cages[g], candidates)
                        if states[g] is None or any((f & smask).bit_count() > 1 for f in states[g][1]):
                            ok = False
                            break
                if not ok:
                    continue
                affected = []
                for g in ents:
                    if isinstance(g, int):
                        keep = {f for f in states[g][1] if f & smask}
                        if len(keep) < len(states[g][1]):
                            affected += _restrict_cage(board, cages[g], candidates, keep)
                        for r, c in cages[g][1]:
                            if board[r][c] == 0 and (r, c) not in groups[g] and candidates[r][c] & sset:
                                affected.append((cell(r, c), sorted(candidates[r][c] & sset)))
                                candidates[r][c] -= sset
                    else:
                        r, c = g
                        if candidates[r][c] - sset:
                            affected.append((cell(r, c), sorted(candidates[r][c] - sset)))
                            candidates[r][c] &= sset
                if affected:
                    changed = True
                    states.clear()
                    holders = None
                    if log is not None:
                        where = ", ".join(f"cage sum={cages[g][0]}" if isinstance(g, int) else cell(*g)
                                          for g in ents)
                        _log_removals(log, f"Hidden killer subset in {hname}: {sorted(subset)} only in [{where}],"
                                           f" one each", affected)
                        if single_step:
                            return True
    return changed


def eliminate_naked_killer_subsets(candidates, board, cages, log=None, single_step=False):
    """Naked killer subsets: cages act like cells in a naked subset.

    In a house, k entities that each must hold one of k digits (a cell whose
    candidates are all among them, or a cage wholly inside the house whose
    every combo uses at least one) lock those digits: each entity holds exactly
    one, and no other cell of the house can have them.

    Example: in column 6, cage 6/2 is {1,5} or {2,4} so it holds a 1 or a 2;
    with cell F3 = {1,2}, 1 and 2 are locked there and leave the column.
    """
    changed = False
    cage_bits = [_bits(tuple(x) for x in cls) for _, cls, _ in cages]
    states = None
    for (hname, hcells), hbits in zip(_house_list(), _HOUSE_BITS):
        if states is None:  # (re)computed only after a change
            states = [_cage_state(board, cage, candidates) for cage in cages]
        inside = [(ci, set(states[ci][0]), tuple(states[ci][1])) for ci in range(len(cages))
                  if states[ci] and not cage_bits[ci] & ~hbits]
        if not inside:
            continue
        placed = {board[r][c] for r, c in hcells if board[r][c]}
        empty = [(r, c) for r, c in hcells if board[r][c] == 0]
        cmask = {x: to_mask(candidates[x[0]][x[1]]) for x in empty}
        digits = [d for d in range(1, 10) if d not in placed]
        for k in range(2, min(5, len(digits))):
            for subset in combinations(digits, k):
                smask = 0
                for d in subset:
                    smask |= 1 << d
                cage_ents = [(ci, ccells, finals) for ci, ccells, finals in inside
                             if all(map(smask.__and__, finals))]
                if not cage_ents:
                    continue
                in_cages = set().union(*(cc for _, cc, _ in cage_ents))
                cell_ents = [x for x in empty if not cmask[x] & ~smask and x not in in_cages]
                if len(cage_ents) + len(cell_ents) != k:
                    continue
                sset = set(subset)
                affected = []
                for ci, _, finals in cage_ents:
                    keep = {f for f in finals if (f & smask).bit_count() == 1}
                    if len(keep) < len(finals):
                        affected += _restrict_cage(board, cages[ci], candidates, keep)
                for r, c in empty:
                    if (r, c) not in in_cages and (r, c) not in cell_ents and candidates[r][c] & sset:
                        affected.append((cell(r, c), sorted(candidates[r][c] & sset)))
                        candidates[r][c] -= sset
                if affected:
                    changed = True
                    states = None
                    cmask = {x: to_mask(candidates[x[0]][x[1]]) for x in empty}
                    if log is not None:
                        where = ", ".join([f"cage sum={cages[ci][0]}" for ci, _, _ in cage_ents]
                                          + [cell(*x) for x in cell_ents])
                        _log_removals(log, f"Naked killer subset in {hname}: {sorted(subset)} locked in [{where}]",
                                      affected)
                        if single_step:
                            return True
                    break
    return changed


def eliminate_common_peers(candidates, board, cages, log=None, single_step=False):
    """Common peer elimination, including locked cages.

    If a group of cells must contain digit d, any other cell that sees every
    spot where d can go in the group (same row, column, box or cage) can't be
    d. Groups: each house; each cage whose every combo uses d; and locked
    cages - when d is confined to two cages in a house and every combo of both
    that uses d also uses e, one of the two cages holds e.

    Example: cage 13/3 must hold a 4, which can only go in A1 or B2; A2 sees
    A1 (same column) and B2 (same row), so A2 can't be 4.
    """
    changed = False
    cage_of = {tuple(x): i for i, (_, cls, _) in enumerate(cages) for x in cls}

    seen_by = {}  # cell -> every cell it sees through a row, column, box or cage
    for r in range(9):
        for c in range(9):
            mates = {tuple(x) for x in cages[cage_of[(r, c)]][1]} if (r, c) in cage_of else set()
            seen_by[(r, c)] = {x for x in _PEER_SET[(r, c)]} | mates

    states = {i: _cage_state(board, cage, candidates) for i, cage in enumerate(cages)}
    groups = []  # (digit, cells that may hold it, description)
    for hname, hcells in _house_list():
        placed = {board[r][c] for r, c in hcells if board[r][c]}
        for d in range(1, 10):
            if d in placed:
                continue
            spots = [x for x in hcells if board[x[0]][x[1]] == 0 and d in candidates[x[0]][x[1]]]
            groups.append((d, spots, f"{d} must be in {hname}"))
            # Locked cages: d confined to two cages of this house
            owners = {cage_of.get(x) for x in spots}
            if len(owners) == 2 and None not in owners:
                a, b = sorted(owners)
                if states[a] and states[b]:
                    bit = 1 << d
                    for e in range(1, 10):
                        ebit = 1 << e
                        if e == d:
                            continue
                        if all(f & ebit for f in states[a][1] if f & bit) and \
                                all(f & ebit for f in states[b][1] if f & bit):
                            espots = [x for g in (a, b) for x in states[g][0] if e in candidates[x[0]][x[1]]]
                            groups.append((e, espots, f"{d} in {hname} is in cage sum={cages[a][0]} or"
                                                      f" sum={cages[b][0]}, and each combo with {d} has {e}"))
    for ci, state in states.items():
        if state is None:
            continue
        must = ALL_DIGITS
        for f in state[1]:
            must &= f
        for d in mask_to_set(must):
            spots = [x for x in state[0] if d in candidates[x[0]][x[1]]]
            groups.append((d, spots, f"{d} must be in cage sum={cages[ci][0]}"))
    for d, spots, why in groups:
        if not spots:
            continue
        # A cell that sees every spot sees the first one, so only its peers qualify
        affected = []
        for r, c in seen_by[spots[0]]:
            if board[r][c] or d not in candidates[r][c] or (r, c) in spots:
                continue
            if all(s in seen_by[(r, c)] for s in spots):
                candidates[r][c].discard(d)
                affected.append((cell(r, c), [d]))
        if affected:
            changed = True
            if log is not None:
                _log_removals(log, f"Common peers: {why}, only in [{cells(spots)}]", affected)
                if single_step:
                    return True
    return changed


def eliminate_conflicting_combos(candidates, board, cages, log=None, single_step=False):
    """Conflicting combinations across houses.

    A combo of cage A is impossible if its digits would leave no option for a
    cell or cage that sees every cell of A: a cell whose candidates are all in
    the combo, or a cage whose cells all see all of A and whose every combo
    shares a digit with it.

    Example: cell G5 = {2,8} sees every cell of cage 10/2 [G1, G2], so that
    cage can't be {2,8}.
    """
    changed = False
    states = [_cage_state(board, cage, candidates) for cage in cages]
    for ai, state in enumerate(states):
        if state is None:
            continue
        a_cells = state[0]
        watchers = [(r, c) for r in range(9) for c in range(9)
                    if board[r][c] == 0 and (r, c) not in a_cells
                    and (r, c) not in {tuple(x) for x in cages[ai][1]}
                    and all(_sees((r, c), x) for x in a_cells)]
        watching_cages = [bi for bi, b in enumerate(states)
                          if b and bi != ai and all(all(_sees(y, x) for x in a_cells) for y in b[0])]
        if not watchers and not watching_cages:
            continue
        dead = set()
        for f in state[1]:
            digits = mask_to_set(f)
            if any(candidates[r][c] <= digits for r, c in watchers):
                dead.add(f)
            elif any(all(g & f for g in states[bi][1]) for bi in watching_cages):
                dead.add(f)
        if not dead or dead == set(state[1]):
            continue
        affected = _restrict_cage(board, cages[ai], candidates, set(state[1]) - dead)
        if affected:
            changed = True
            states[ai] = _cage_state(board, cages[ai], candidates)
            if log is not None:
                gone = " ".join("{" + ",".join(map(str, sorted(mask_to_set(f)))) + "}" for f in sorted(dead))
                _log_removals(log, f"Conflicting combos: cage sum={cages[ai][0]} [{cells(cages[ai][1])}] can't be"
                                   f" {gone} (would empty a cell or cage that sees it all)", affected)
                if single_step:
                    return True
    return changed


def eliminate_leftovers(candidates, board, cages, log=None, single_step=False):
    """Law of leftovers: a line and a box it crosses hold the same digits
    outside their overlap, so a digit missing from one leftover part can't be
    in the other.

    Example: row 1 and box 1 share A1-C1; D1-I1 hold the same digits as
    A2-C3. If no cell in A2-C3 can be 7, none of D1-I1 is 7.
    """
    changed = False
    for kind in ("row", "col"):
        for li in range(9):
            line = get_house_cells(kind, li)
            for bi in range(9):
                box = get_house_cells("box", bi)
                if not set(line) & set(box):
                    continue
                side_a = [x for x in line if x not in box]
                side_b = [x for x in box if x not in line]

                def possible(side):
                    out = set()
                    for r, c in side:
                        out |= {board[r][c]} if board[r][c] else candidates[r][c]
                    return out
                pa, pb = possible(side_a), possible(side_b)
                affected = []
                for side, other in ((side_a, pb), (side_b, pa)):
                    for r, c in side:
                        if board[r][c] == 0 and candidates[r][c] - other:
                            affected.append((cell(r, c), sorted(candidates[r][c] - other)))
                            candidates[r][c] &= other
                if affected:
                    changed = True
                    if log is not None:
                        _log_removals(log, f"Leftovers: {house_name(kind, li)} and box {bi + 1} hold the same"
                                           f" digits outside their overlap", affected)
                        if single_step:
                            return True
    return changed


def _part_options(board, cage, candidates, part):
    """Digit masks the cells in `part` (some of a cage's empty cells) can hold
    together in a valid assignment of the whole cage."""
    cage_sum, cage_cells, _ = cage
    empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
    filled = [board[r][c] for r, c in cage_cells if board[r][c]]
    fmask = to_mask(filled)
    remaining = cage_sum - sum(filled)
    rest = [x for x in empty if x not in part]
    layers = {0}
    for r, c in part:
        cm = to_mask(candidates[r][c]) & ~fmask
        nxt = set()
        for used in layers:
            free = cm & ~used
            while free:
                low = free & -free
                nxt.add(used | low)
                free ^= low
        layers = nxt
    options = set()
    for m in layers:
        if not rest:
            if MASK_SUM[m] == remaining:
                options.add(m)
        elif cage_support([to_mask(candidates[r][c]) for r, c in rest], remaining - MASK_SUM[m], fmask | m):
            options.add(m)
    return options


def eliminate_house_combos(candidates, board, cages, log=None, single_step=False):
    """Whole-house combination analysis ("combo blocks").

    In a row, column or box, each cage touching it offers the digit sets its
    cells there could hold (checked against the whole cage), and each uncaged
    cell offers its candidates. Together they must fill exactly the house's
    missing digits, with no digit twice. Options that fit no such fill are
    dropped, and cells lose digits no surviving option gives them.

    Example: box 5 holds cages 10/2 ({1,9} {2,8} {3,7} {4,6}) and 11/2 inside,
    plus parts of two others; if every fill of the box that uses {4,6} for
    10/2 leaves 11/2 without a pair, 10/2 can't be {4,6}.
    """
    changed = False
    cage_of = {tuple(x): i for i, (_, cls, _) in enumerate(cages) for x in cls}
    for hname, hcells in _house_list():
        placed = to_mask([board[r][c] for r, c in hcells if board[r][c]])
        target = ALL_DIGITS & ~placed
        empty = [(r, c) for r, c in hcells if board[r][c] == 0]
        if not empty:
            continue
        parts = {}
        for x in empty:
            parts.setdefault(cage_of.get(x, x), []).append(x)
        segments = []  # (key, cells, options)
        for key, cells_ in parts.items():
            if isinstance(key, int):
                opts = {m for m in _part_options(board, cages[key], candidates, cells_) if not m & ~target}
            else:
                opts = {1 << d for d in candidates[key[0]][key[1]] if target >> d & 1}
            if not opts:
                break
            segments.append((key, cells_, opts))
        else:
            segments.sort(key=lambda s: len(s[2]))
            layers = [{0}]
            for _, _, opts in segments:
                layers.append({u | m for u in layers[-1] for m in opts if not u & m})
            if target not in layers[-1]:
                continue  # no fill at all: leave it for the contradiction checks
            good = {target}
            allowed = [set() for _ in segments]
            for k in range(len(segments) - 1, -1, -1):
                prev_good = set()
                for u in layers[k]:
                    for m in segments[k][2]:
                        if not u & m and u | m in good:
                            allowed[k].add(m)
                            prev_good.add(u)
                good = prev_good
            affected = []
            for (key, cells_, opts), keep in zip(segments, allowed):
                if keep == opts:
                    continue
                union = 0
                for m in keep:
                    union |= m
                digits = mask_to_set(union)
                for r, c in cells_:
                    gone = candidates[r][c] - digits
                    if gone:
                        candidates[r][c] -= gone
                        affected.append((cell(r, c), sorted(gone)))
            if affected:
                changed = True
                if log is not None:
                    _log_removals(log, f"House combos in {hname}: cages and cells must fill its missing digits once each",
                                  affected)
                    if single_step:
                        return True
    return changed


_HOUSE_BITS = [sum(1 << (r * 9 + c) for r, c in get_house_cells(t, i)) for t in ("row", "col", "box") for i in range(9)]


def _bits(cells_):
    return sum(1 << (r * 9 + c) for r, c in cells_)


# Cell index -> the three houses (indices into _HOUSE_BITS) holding it
_CELL_HOUSES = [[h for h, hb in enumerate(_HOUSE_BITS) if hb >> i & 1] for i in range(81)]


def _covers(spots, n):
    """Every set of n houses covering all of `spots` (a cell bitmask).

    The lowest uncovered cell lies in just three houses and one of them must
    be a cover, so branching on those reaches every cover set in at most 3^n
    paths instead of trying all combinations of the houses touched.
    """
    found = set()

    def grow(left, chosen):
        if not left:
            if len(chosen) == n:
                found.add(tuple(sorted(chosen)))
            return
        if len(chosen) == n:
            return
        low = (left & -left).bit_length() - 1
        for h in _CELL_HOUSES[low]:
            if h not in chosen:
                grow(left & ~_HOUSE_BITS[h], chosen + [h])

    grow(spots, [])
    return sorted(found)  # same order as trying combinations of houses


def _cells_of(bits):
    out = []
    while bits:
        low = bits & -bits
        i = low.bit_length() - 1
        out.append((i // 9, i % 9))
        bits ^= low
    return out


def eliminate_killer_fish(candidates, board, cages, log=None, single_step=False):
    """Fish (X-Wing, Swordfish, Franken) with cages as units.

    For a digit d, a "base" is a unit holding d exactly once: a house, or a
    cage whose every combo uses d. If N disjoint bases (N = 2 or 3) have all
    their spots for d inside N covering houses, those N copies of d fill the
    covers, so no other cell of the covers can be d.

    Example: cage 16/2 = {7,9} spans rows 2-3 of column 1, and 9 in row 7 fits
    only in columns 1 and 5; the cage and row 7 lie within columns 1 and 5, so
    no other cell of those columns is 9.
    """
    changed = False
    houses = _house_list()
    states = [_cage_state(board, cage, candidates) for cage in cages]
    for d in range(1, 10):
        cand_bits = sum(1 << (r * 9 + c) for r in range(9) for c in range(9)
                        if board[r][c] == 0 and d in candidates[r][c])
        units = []
        for (hname, hcells), hb in zip(houses, _HOUSE_BITS):
            if any(board[r][c] == d for r, c in hcells):
                continue
            spots = hb & cand_bits
            if spots.bit_count() >= 2:
                units.append((hname, spots))
        for ci, state in enumerate(states):
            if state and all(f >> d & 1 for f in state[1]):
                spots = _bits(state[0]) & cand_bits
                if spots.bit_count() >= 2:
                    units.append((f"cage sum={cages[ci][0]}", spots))
        for n in (2, 3):
            for bases in combinations(units, n):
                spots = 0
                ok = True
                for _, s in bases:
                    if spots & s:
                        ok = False
                        break
                    spots |= s
                if not ok:
                    continue
                for covers in _covers(spots, n):
                    cover_bits = 0
                    for h in covers:
                        cover_bits |= _HOUSE_BITS[h]
                    targets = cover_bits & cand_bits & ~spots
                    if not targets:
                        continue
                    affected = []
                    for r, c in _cells_of(targets):
                        candidates[r][c].discard(d)
                        affected.append((cell(r, c), [d]))
                    cand_bits &= ~targets
                    changed = True
                    if log is not None:
                        _log_removals(log, f"Killer fish on {d}: {', '.join(b for b, _ in bases)} lie within"
                                           f" {', '.join(houses[h][0] for h in sorted(covers))}", affected)
                        if single_step:
                            return True
    return changed


def eliminate_als_xz(candidates, board, cages, log=None, single_step=False):
    """ALS-XZ with houses and cages as almost locked sets.

    An almost locked set (ALS) is N cells that must all differ - within a
    house, or a whole cage - holding N+1 candidates. For two disjoint ALSs A
    and B sharing a digit X where every X in A sees every X in B, X can sit in
    at most one of them, so the other is locked; then any other shared digit Z
    lies in A or B, and a cell seeing every Z in both can't be Z.

    Example: B2 = {4,7} is one cell with two candidates; D2 and E2 hold
    {4,5,7} between them. Every 4 in either sees the other's 4s (row 2), so
    one of the two sets is locked, and the 7 is in B2 or in D2/E2: any cell
    of row 2 outside them loses 7.
    """
    changed = False
    cage_of = {tuple(x): i for i, (_, cls, _) in enumerate(cages) for x in cls}
    seen = {}
    for r in range(9):
        for c in range(9):
            mates = [tuple(x) for x in cages[cage_of[(r, c)]][1]] if (r, c) in cage_of else []
            seen[(r, c)] = _bits(_PEER_SET[(r, c)]) | _bits(x for x in mates if x != (r, c))
    als = {}
    for _, hcells in _house_list():
        empty = [(r, c) for r, c in hcells if board[r][c] == 0]
        for size in (1, 2, 3):
            for group in combinations(empty, size):
                m = to_mask(set().union(*(candidates[r][c] for r, c in group)))
                if m.bit_count() == size + 1:
                    als[_bits(group)] = m
    for cage in cages:
        empty = [tuple(x) for x in cage[1] if board[x[0]][x[1]] == 0]
        if 2 <= len(empty) <= 5:
            m = to_mask(set().union(*(candidates[r][c] for r, c in empty)))
            if m.bit_count() == len(empty) + 1:
                als[_bits(empty)] = m
    items = list(als.items())

    def digit_cells(bits, d):
        return _bits(x for x in _cells_of(bits) if d in candidates[x[0]][x[1]])

    for i, (a_bits, a_mask) in enumerate(items):
        for b_bits, b_mask in items[i + 1:]:
            common = a_mask & b_mask
            if a_bits & b_bits or common.bit_count() < 2:
                continue
            for x in mask_to_set(common):
                xa, xb = digit_cells(a_bits, x), digit_cells(b_bits, x)
                if not all(seen[p] & xb == xb for p in _cells_of(xa)):
                    continue
                for z in mask_to_set(common):
                    if z == x:
                        continue
                    z_cells = _cells_of(digit_cells(a_bits, z) | digit_cells(b_bits, z))
                    if not z_cells:
                        continue
                    watchers = ~(a_bits | b_bits) & ((1 << 81) - 1)
                    for p in z_cells:
                        watchers &= seen[p]
                    affected = []
                    for r, c in _cells_of(watchers):
                        if board[r][c] == 0 and z in candidates[r][c]:
                            candidates[r][c].discard(z)
                            affected.append((cell(r, c), [z]))
                    if affected:
                        changed = True
                        if log is not None:
                            _log_removals(log, f"ALS-XZ: [{cells(_cells_of(a_bits))}] and [{cells(_cells_of(b_bits))}]"
                                               f" linked by {x}, both can hold {z}", affected)
                            if single_step:
                                return True
    return changed


def _distinct_virtual_cages(candidates, board, cages):
    """Derived cages whose digits must all differ: groups of 2-4 cells with a
    proven total (innie groups, naked sets) that all see each other or share
    a cage, and aren't simply a real cage. (cells, total, why) each."""
    cage_of = {tuple(x): i for i, (_, cls, _) in enumerate(cages) for x in cls}
    real = {frozenset(tuple(x) for x in cls) for _, cls, _ in cages}
    out, found = [], set()
    for vcells, total, why in _virtual_cages(candidates, board, cages):
        if not 2 <= len(vcells) <= 4 or vcells in real or vcells in found:
            continue
        if all(b in _PEER_SET[a] or cage_of.get(a, a) == cage_of.get(b, b)
               for a, b in combinations(vcells, 2)):
            found.add(vcells)
            out.append((vcells, total, why))
    return out


def eliminate_cage_pairs(candidates, board, cages, log=None, single_step=False):
    """Combination clashes between two cages, derived cages included.

    Real cages and derived cages (2-4 mutually different cells with a proven
    total, e.g. two innies of a row) are paired when a cell of one sees all
    of the other. Combo f of A and combo g of B can't both hold if such a
    cell could only take digits of f that g also needs (or, when every cell
    sees every other, if f and g share a digit). Combos with no compatible
    partner go, and a digit every compatible pair uses must sit in A or B,
    so a cell seeing all its spots in both loses it. Digits a derived cage
    always holds first get the common-peer treatment on their own.

    Example (Assassin 44V1.5): the innies of row 9 give A9 + E9 = 6, so
    {1,5} or {2,4}; the 6-cage in box 8 is {1,5} or {2,4} too, and E9 sees
    all of it, so the two take different pairs: together they hold exactly
    {1,2,4,5}, and a cell seeing all four cells loses those digits.
    """
    changed = False
    cage_of = {tuple(x): i for i, (_, cls, _) in enumerate(cages) for x in cls}
    seen_by = {}
    for r in range(9):
        for c in range(9):
            mates = {tuple(x) for x in cages[cage_of[(r, c)]][1]} if (r, c) in cage_of else set()
            seen_by[(r, c)] = _PEER_SET[(r, c)] | (mates - {(r, c)})
    units = [(f"cage sum={s}", (s, [tuple(x) for x in cls], 0)) for s, cls, _ in cages]
    units += [(f"derived {cells(sorted(vc))} = {total}", (total, sorted(vc), 0))
              for vc, total, _ in _distinct_virtual_cages(candidates, board, cages)]
    states = [_cage_state(board, unit, candidates) for _, unit in units]
    for i in range(len(cages), len(units)):
        # A derived cage's must-have digits, like a real cage's in common peers
        if not states[i]:
            continue
        must = ALL_DIGITS
        for f in states[i][1]:
            must &= f
        affected = []
        for d in mask_to_set(must):
            spots = [x for x in states[i][0] if d in candidates[x[0]][x[1]]]
            for r, c in seen_by[spots[0]]:
                if board[r][c] == 0 and d in candidates[r][c] and (r, c) not in spots                         and all(s in seen_by[(r, c)] for s in spots):
                    candidates[r][c].discard(d)
                    affected.append((cell(r, c), [d]))
        if affected:
            changed = True
            if log is not None:
                _log_removals(log, f"Common peers: digits {sorted(mask_to_set(must))} must be in {units[i][0]}", affected)
                if single_step:
                    return True
    states = [_cage_state(board, unit, candidates) for _, unit in units]
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            a, b = states[i], states[j]
            if not a or not b or set(a[0]) & set(b[0]):
                continue
            a_watch = [x for x in a[0] if all(y in seen_by[x] for y in b[0])]
            b_watch = [y for y in b[0] if all(x in seen_by[y] for x in a[0])]
            if not a_watch and not b_watch:
                continue
            a_masks = [to_mask(candidates[r][c]) for r, c in a_watch]
            b_masks = [to_mask(candidates[r][c]) for r, c in b_watch]
            apart = len(a_watch) == len(a[0])

            def clash(f, g):
                return (apart and f & g) or any(not m & f & ~g for m in a_masks) \
                    or any(not m & g & ~f for m in b_masks)

            pairs = [(f, g) for f in a[1] for g in b[1] if not clash(f, g)]
            if not pairs:
                continue  # nothing fits: leave it for the contradiction checks
            keep_a, keep_b = {f for f, _ in pairs}, {g for _, g in pairs}
            affected = []
            if len(keep_a) < len(a[1]):
                affected += _restrict_cage(board, units[i][1], candidates, keep_a)
            if len(keep_b) < len(b[1]):
                affected += _restrict_cage(board, units[j][1], candidates, keep_b)
            must = ALL_DIGITS
            for f, g in pairs:
                must &= f | g
            for d in mask_to_set(must):
                spots = [x for x in a[0] + b[0] if d in candidates[x[0]][x[1]]]
                if not spots:
                    continue
                for r, c in seen_by[spots[0]]:
                    if board[r][c] == 0 and d in candidates[r][c] and (r, c) not in spots \
                            and all(s in seen_by[(r, c)] for s in spots):
                        candidates[r][c].discard(d)
                        affected.append((cell(r, c), [d]))
            if affected:
                changed = True
                states[i] = _cage_state(board, units[i][1], candidates)
                states[j] = _cage_state(board, units[j][1], candidates)
                if log is not None:
                    _log_removals(log, f"Cage pair: {units[i][0]} and {units[j][0]} can't take clashing"
                                       f" combos; together they hold {sorted(mask_to_set(must))}", affected)
                    if single_step:
                        return True
    return changed


def filter_cage_combos(candidates, board, cages):
    """Re-filter candidate grid by cage combos.

    For each cage, recompute which combos are valid given the current candidate
    grid (not just Sudoku rules). Remove any candidate that doesn't appear in
    at least one valid combo for its cage.

    This catches cases where earlier eliminations (naked subsets, pointing, etc.)
    invalidated some combos, which in turn eliminates more candidates.
    """
    changed = False
    for cage_sum, cage_cells, _ in cages:
        empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
        if not empty:
            continue
        filled = [board[r][c] for r, c in cage_cells if board[r][c] != 0]
        result = cage_support([to_mask(candidates[r][c]) for r, c in empty], cage_sum - sum(filled), to_mask(filled))
        if not result:
            continue
        in_some = 0
        for m in result[1]:
            in_some |= m
        in_some = mask_to_set(in_some)
        for r, c in empty:
            allowed = candidates[r][c] & in_some
            if candidates[r][c] != allowed and allowed:
                candidates[r][c] = allowed
                changed = True
    return changed


def _find_single(board, candidates):
    """First naked single, else first hidden single: (r, c, num, house) or None.

    `house` is None for a naked single, (house_type, i) for a hidden one.
    """
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0 and len(candidates[r][c]) == 1:
                return r, c, next(iter(candidates[r][c])), None
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            hcells = get_house_cells(house_type, i)
            for num in range(1, 10):
                positions = [(r, c) for r, c in hcells if board[r][c] == 0 and num in candidates[r][c]]
                if len(positions) == 1:
                    r, c = positions[0]
                    return r, c, num, (house_type, i)
    return None


def apply_candidate_elimination(board, cages, innies=True, contradiction=True, stats=None):
    """Expert-level strategy: iterative candidate elimination.

    1. Build a full candidate grid (Sudoku + deep cage combo filtering)
    2. Repeatedly apply: naked subsets, pointing, box-line, cage re-filtering
    3. After each round, check if any cell is resolved (1 candidate) or if
       a hidden single appeared in any house
    4. Place the first resolved cell found

    This is the most powerful strategy and can solve positions that no single
    simpler strategy can crack, by chaining multiple elimination techniques.
    `innies` switches the advanced killer techniques (rule of 45 over several
    houses, killer subsets, common peers, conflicting combos, leftovers, house
    combos, cage pairs, killer fish, ALS-XZ) and
    `contradiction` the first-order contradiction checks; that is how the
    solver measures which level a puzzle needs. A `stats` dict
    collects "contradictions": how many times everything else was stuck and a
    first-order contradiction sweep had to break the deadlock.
    """
    key = (_cages_key(cages), innies, contradiction)
    candidates = build_candidates(board, cages)
    prior = _REFINED.get(key)
    # Eliminations proven on an earlier board still hold once more cells are filled.
    if prior and all(v == 0 or v == board[i // 9][i % 9] for i, v in enumerate(prior[0])):
        for r in range(9):
            for c in range(9):
                if board[r][c] == 0 and prior[1][r][c]:
                    candidates[r][c] &= prior[1][r][c]
    initial = {(r, c): set(candidates[r][c]) for r in range(9) for c in range(9) if candidates[r][c]}
    elim_log = []
    for _ in range(1000):
        changed = False
        if eliminate_naked_subsets(candidates, elim_log):
            changed = True
        if eliminate_pointing(candidates, elim_log):
            changed = True
        if eliminate_box_line(candidates, elim_log):
            changed = True
        if eliminate_cage_claiming(candidates, board, cages, elim_log):
            changed = True
        if eliminate_cage_pointing(candidates, board, cages, elim_log):
            changed = True
        if eliminate_cage_box_reduction(candidates, board, cages, elim_log):
            changed = True
        if eliminate_x_wing(candidates, elim_log):
            changed = True
        if eliminate_hidden_subsets(candidates, elim_log):
            changed = True
        if eliminate_xy_wing(candidates, elim_log):
            changed = True
        if eliminate_generalized_outies(candidates, board, cages, elim_log):
            changed = True
        if eliminate_cage_interaction(candidates, board, cages, elim_log):
            changed = True
        if innies:
            for technique in (eliminate_innies_outies, eliminate_hidden_killer_subsets,
                              eliminate_naked_killer_subsets, eliminate_common_peers,
                              eliminate_conflicting_combos, eliminate_leftovers, eliminate_house_combos):
                if technique(candidates, board, cages, elim_log):
                    changed = True
        if filter_cage_combos(candidates, board, cages):
            changed = True
            elim_log.append("Cage combo re-filtering")
        # The costly techniques only run once everything cheaper has stalled.
        if innies and not changed and not _find_single(board, candidates):
            changed = (eliminate_large_sums(candidates, board, cages, elim_log)
                       or eliminate_cage_pairs(candidates, board, cages, elim_log)
                       or eliminate_killer_fish(candidates, board, cages, elim_log)
                       or eliminate_als_xz(candidates, board, cages, elim_log))
        if contradiction and not changed and not _find_single(board, candidates):
            changed = eliminate_by_contradiction(candidates, board, cages, elim_log)
            if changed and stats is not None:
                stats["contradictions"] = stats.get("contradictions", 0) + 1
        if not changed or _find_single(board, candidates):
            break

    _REFINED.clear()
    _REFINED[key] = ([board[r][c] for r in range(9) for c in range(9)],
                     [[set(x) for x in row] for row in candidates])

    def _explain(r, c, num, extra=""):
        before = sorted(initial.get((r, c), set()))
        lines = [f"{cell(r, c)} started with {before}"]
        relevant = [e for e in elim_log if cell(r, c) in e or "combo" in e.lower()]
        if relevant:
            lines.append("Key eliminations:")
            for e in relevant[:6]:
                lines.append(f"  - {e}")
        lines.append(f"Result: {cell(r, c)} -> {extra}{num}")
        return "\n".join(lines)

    single = _find_single(board, candidates)
    if not single:
        return False
    r, c, num, house = single
    board[r][c] = num
    if house is None:
        print(f"Set cell ({r},{c}) to {num} via candidate elimination")
        print(f"  " + _explain(r, c, num).replace("\n", "\n  "))
    else:
        house_type, i = house
        hn = house_name(house_type, i)
        print(f"Set cell ({r},{c}) to {num} via candidate elimination (hidden single in {hn})")
        print(f"  " + _explain(r, c, num, extra=f"only place for {num} in {hn} -> ").replace("\n", "\n  "))
    return True
