"""Board and cage generation for Killer Sudoku puzzles.

This module handles:
1. Creating a random valid Sudoku solution (populate_board)
2. Partitioning the board into adjacent cages (generate_cages)
3. Growing puzzles to a target technique level (generate_to_level)

Cage generation strategy:
- Randomly grow connected groups of cells (2-5 cells each)
- Each cage must have unique digit values (no repeats within a cage)
- If a target size can't be reached, try smaller sizes
- Any leftover single-cell cages are merged into adjacent cages
- ANSI color codes are assigned for terminal display
"""

from random import choice, choices, randint

# ANSI background color codes for terminal display of cages
COLOR_PALETTE = [41, 42, 43, 44, 45, 46, 101, 102, 103, 104, 105, 106]


def create_board():
    """Create an empty 9x9 board (all zeros)."""
    return [[0] * 9 for _ in range(9)]


def is_valid(board, num, pos):
    """Check if placing `num` at `pos` violates Sudoku rules (row/col/box)."""
    r, c = pos
    # Check row and column
    if any(board[r][j] == num and j != c for j in range(9)):
        return False
    if any(board[i][c] == num and i != r for i in range(9)):
        return False
    # Check 3x3 box
    br, bc = (r // 3) * 3, (c // 3) * 3
    for i in range(br, br + 3):
        for j in range(bc, bc + 3):
            if board[i][j] == num and (i, j) != pos:
                return False
    return True


def populate_board(board, row=0, col=0):
    """Fill the board with a random valid Sudoku solution using backtracking.

    Tries digits 1-9 in random order at each cell. Backtracks if no valid
    digit fits. Guarantees a complete valid solution.
    """
    if row == 9:
        return True  # All rows filled successfully
    if col == 9:
        return populate_board(board, row + 1, 0)  # Next row
    if board[row][col] != 0:
        return populate_board(board, row, col + 1)  # Skip pre-filled

    nums = list(range(1, 10))
    while nums:
        num = choice(nums)  # Random order for variety
        nums.remove(num)
        if is_valid(board, num, (row, col)):
            board[row][col] = num
            if populate_board(board, row, col + 1):
                return True
            board[row][col] = 0  # Backtrack
    return False


def generate_cages(board):
    """Generate non-overlapping adjacent cages covering all 81 cells.

    Algorithm:
    1. Pick a random target cage size (weighted: mostly 2-3, some 4-5)
    2. Start from a random available cell, grow by adding adjacent cells
       whose digit values don't duplicate within the cage
    3. If the target size can't be reached after 200 attempts, try smaller sizes
    4. After all cells are covered, merge any remaining size-1 cages into
       adjacent cages (to avoid trivially solved single-cell cages)

    Returns list of (cage_sum, cell_list, color_code) tuples.
    """
    cages = []
    used = set()

    def adjacent(cell_pos):
        """Yield orthogonally adjacent cells within the 9x9 grid."""
        r, c = cell_pos
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 9 and 0 <= nc < 9:
                yield nr, nc

    available = {(r, c) for r in range(9) for c in range(9)}

    while available:
        color = COLOR_PALETTE[len(cages) % len(COLOR_PALETTE)]
        # Weighted random size: mostly 2-3 cells, sometimes 4-5
        target = min(choice([2, 2, 3, 3, 3, 4, 5]), len(available))
        best = None

        # Try to build a cage of the target size
        for _ in range(200):
            start = choice(list(available))
            cage_cells = {start}
            cage_vals = {board[start[0]][start[1]]}

            # Grow the cage by adding adjacent cells with unique values
            while len(cage_cells) < target:
                frontier = [c for base in cage_cells for c in adjacent(base)
                            if c not in cage_cells and c not in used
                            and board[c[0]][c[1]] not in cage_vals]
                if not frontier:
                    break  # Can't grow further
                nxt = choice(frontier)
                cage_cells.add(nxt)
                cage_vals.add(board[nxt[0]][nxt[1]])

            if len(cage_cells) == target:
                best = cage_cells
                break

        # Fallback: try progressively smaller cage sizes
        if best is None:
            for smaller in range(target - 1, 0, -1):
                for _ in range(100):
                    start = choice(list(available))
                    cage_cells = {start}
                    cage_vals = {board[start[0]][start[1]]}
                    while len(cage_cells) < smaller:
                        frontier = [c for base in cage_cells for c in adjacent(base)
                                    if c not in cage_cells and c not in used
                                    and board[c[0]][c[1]] not in cage_vals]
                        if not frontier:
                            break
                        nxt = choice(frontier)
                        cage_cells.add(nxt)
                        cage_vals.add(board[nxt[0]][nxt[1]])
                    if len(cage_cells) == smaller:
                        best = cage_cells
                        break
                if best:
                    break

        if best is None:
            continue  # Extremely rare: skip this iteration

        for cl in best:
            used.add(cl)
            available.discard(cl)
        cages.append((sum(board[r][c] for r, c in best), list(best), color))

    # --- Merge single-cell cages into adjacent cages ---
    # Single-cell cages are trivially solvable (the sum IS the answer),
    # so we merge them into a neighbor to make the puzzle more interesting.
    merged = True
    while merged:
        merged = False
        for i, (_, cls, _c) in enumerate(cages):
            if len(cls) != 1:
                continue
            cl = cls[0]
            val = board[cl[0]][cl[1]]
            for neighbor in adjacent(cl):
                for j, (os, ocls, ocol) in enumerate(cages):
                    if i == j:
                        continue
                    if neighbor in [(r, c) for r, c in ocls]:
                        # Only merge if the digit doesn't duplicate in the neighbor cage
                        if val not in {board[r][c] for r, c in ocls}:
                            cages[j] = (os + val, ocls + [cl], ocol)
                            cages.pop(i)
                            merged = True
                            break
                if merged:
                    break
            if merged:
                break
    return cages


# =============================================================================
# Backtracking solver (used only during generation to verify solvability)
# =============================================================================

def generate_sparse_cages(board, uncaged_target=8, base_cages=None):
    """Remove cells from cages while keeping the puzzle strategy-solvable.

    Args:
        board: completed 9x9 solution
        uncaged_target: aim to leave this many cells uncaged
        base_cages: existing cage layout to start from (if None, generates new ones)

    Strategy:
    1. Start from a full cage layout (provided or generated)
    2. Progressively remove edge cells from cages
    3. After each removal, verify strategies can still solve the puzzle
    4. If not, undo and try a different cell
    5. Stop when enough cells are uncaged
    """
    from killer.solver import solve_killer_sudoku
    import io, sys

    cages = list(base_cages) if base_cages else generate_cages(board)
    if not cages:
        return cages

    uncaged = 0
    failures = 0

    for _ in range(uncaged_target * 10):
        if uncaged >= uncaged_target:
            break
        if failures > uncaged_target * 3:
            break  # Too many failed attempts, stop trying

        # Pick a random cage with more than 2 cells and try shrinking it
        shrinkable = [(i, s, cls, col) for i, (s, cls, col) in enumerate(cages) if len(cls) > 2]
        if not shrinkable:
            break

        idx, s, cls, col = choice(shrinkable)

        # Pick an edge cell (has a neighbor outside the cage)
        cage_set = set(map(tuple, cls))
        edge_cells = []
        for r, c in cls:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < 9 and 0 <= nc < 9 and (nr, nc) not in cage_set:
                    edge_cells.append((r, c))
                    break
        if not edge_cells:
            failures += 1
            continue

        remove_cell = choice(edge_cells)
        new_cells = [c for c in cls if tuple(c) != tuple(remove_cell)]

        # Check remaining cells are still connected (BFS)
        if len(new_cells) > 1:
            visited = {tuple(new_cells[0])}
            queue = [tuple(new_cells[0])]
            new_set = set(map(tuple, new_cells))
            while queue:
                cr, cc = queue.pop()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cr + dr, cc + dc
                    if (nr, nc) in new_set and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))
            if len(visited) != len(new_cells):
                failures += 1
                continue

        # Build test cages with the cell removed
        new_sum = sum(board[r][c] for r, c in new_cells)
        test_cages = list(cages)
        test_cages[idx] = (new_sum, new_cells, col)

        # Check: can strategies still solve it?
        test_board = create_board()
        old = sys.stdout
        sys.stdout = io.StringIO()
        _, solved = solve_killer_sudoku(test_board, test_cages, verbose=False)
        sys.stdout = old

        if solved:
            cages[idx] = (new_sum, new_cells, col)
            uncaged += 1
            failures = 0
        else:
            failures += 1

    return cages


def _mergeable(board, groups, max_size):
    """Pairs of adjacent groups whose union stays within max_size with no repeated digit."""
    owner = {x: i for i, g in enumerate(groups) for x in g}
    pairs = set()
    for i, g in enumerate(groups):
        for r, c in g:
            for nb in ((r + 1, c), (r, c + 1)):
                j = owner.get(nb)
                if j is None or j == i:
                    continue
                a, b = min(i, j), max(i, j)
                if len(groups[a]) + len(groups[b]) > max_size:
                    continue
                if {board[x][y] for x, y in groups[a]} & {board[x][y] for x, y in groups[b]}:
                    continue
                pairs.add((a, b))
    return sorted(pairs)


def _to_cages(board, groups):
    """Cage tuples with neighbouring cages given different palette colours."""
    owner = {x: i for i, g in enumerate(groups) for x in g}
    colours = {}
    for i, g in enumerate(groups):
        near = {colours.get(owner.get((r + dr, c + dc))) for r, c in g
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))}
        colours[i] = next(col for col in COLOR_PALETTE if col not in near)
    return [(sum(board[r][c] for r, c in g), [list(x) for x in g], colours[i]) for i, g in enumerate(groups)]


def _connected(cells):
    cells = set(cells)
    if not cells:
        return True
    seen, stack = set(), [next(iter(cells))]
    while stack:
        r, c = stack.pop()
        if (r, c) in seen:
            continue
        seen.add((r, c))
        stack += [x for x in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)) if x in cells]
    return seen == cells


def _uncage_options(groups, rejected):
    """(group index, cell) pairs that could leave their cage: one-cell cages
    first, else edge cells of 3+ cell cages that stay connected without them."""
    singles = [(i, g[0]) for i, g in enumerate(groups) if len(g) == 1 and g[0] not in rejected]
    if singles:
        return singles
    return [(i, x) for i, g in enumerate(groups) if len(g) >= 3
            for x in g if x not in rejected and _connected([y for y in g if y != x])]


def _plant_big(board, count, sizes=(7, 9), tries=500):
    """`count` disjoint connected regions of 7-9 cells, each with distinct
    digits (a cage can't repeat one), grown by random walks; fewer if some
    won't fit. Random merging almost never builds these, as a 9-cell region
    must hold every digit once."""
    taken, regions = set(), []
    for _ in range(count):
        for _ in range(tries):
            size = randint(*sizes)
            start = choice([(r, c) for r in range(9) for c in range(9) if (r, c) not in taken])
            region, digits = [start], {board[start[0]][start[1]]}
            while len(region) < size:
                frontier = [x for r, c in region for x in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1))
                            if 0 <= x[0] < 9 and 0 <= x[1] < 9 and x not in taken and x not in region
                            and board[x[0]][x[1]] not in digits]
                if not frontier:
                    break
                nxt = choice(frontier)
                region.append(nxt)
                digits.add(board[nxt[0]][nxt[1]])
            if len(region) == size:
                regions.append(region)
                taken |= set(region)
                break
    return regions


def generate_to_level(min_level, max_level=4, cages=(24, 27), long_cages=(1, 4),
                      long_size=(6, 8), max_singles=1, min_contradictions=0,
                      uncaged=0, big_cages=0, attempts=800):
    """Grow a puzzle whose hardest needed technique lies in [min_level, max_level]
    (see solver.LEVEL_NAMES), shaped like published hard killers: a count in
    `cages`, one to a few long snakes of `long_size` cells (each puzzle picks
    its own longest), everything else at most 5 cells, and at most
    `max_singles` one-cell cages.

    Starts from 81 one-cell cages (the solution itself), then merges
    neighbouring cages one at a time, keeping a merge only while the puzzle
    stays solvable at `max_level` (sound logic also proves the solution
    unique). Stops at the first layout inside the shape that `min_level - 1`
    can't solve, so the puzzle sits just over the difficulty threshold.

    With `min_contradictions`, it keeps merging past that point until solving
    gets stuck at least that many times, each broken by a first-order
    contradiction sweep (never a deeper assumption), which makes harder
    level-4 puzzles.

    `uncaged` leaves that many cells in no cage: once the layout is nearly
    done, one-cell cages (or edge cells of bigger cages) are dropped while the
    puzzle stays solvable without them - an uncaged cell gives nothing away.
    `big_cages` plants at least that many cages of 7-9 cells before merging.

    Returns (cages, solution), or None if this grid got too few cages first.
    """
    import io
    from contextlib import redirect_stdout
    from killer.solver import solve_killer_sudoku

    def solvable(groups, lv, stats=None):
        with redirect_stdout(io.StringIO()):
            return solve_killer_sudoku(create_board(), _to_cages(board, groups), verbose=False,
                                       level=lv, stats=stats)[1]

    if big_cages:
        long_size = (7, 9)
        long_cages = (big_cages, max(big_cages, long_cages[1]))
    board = create_board()
    populate_board(board)
    groups = [[(r, c)] for r in range(9) for c in range(9)]
    if big_cages:
        # Plant the big cages first. Two 45-cages can leave a swappable pair
        # of cells even with every other cell given, so re-plant until the
        # start is solvable.
        for _ in range(20):
            planted = _plant_big(board, big_cages)
            if len(planted) < big_cages:
                continue
            in_big = {x for g in planted for x in g}
            start = planted + [[(r, c)] for r in range(9) for c in range(9) if (r, c) not in in_big]
            if solvable(start, max_level):
                groups = start
                break
        else:
            return None
    long_quota = randint(*long_cages)
    long_max = 9 if big_cages else randint(*long_size)
    free = []  # cells left out of every cage
    # Uncaged cells and big cages each use up cells that would otherwise
    # form cages, so allow that many fewer
    min_cages = cages[0] - uncaged - big_cages
    # Merging and uncaging only remove information, so a move that broke the
    # puzzle once would break it again later: never retry it.
    rejected, rejected_free = set(), set()
    for _ in range(attempts):
        if len(groups) < min_cages:
            return None
        stats = {}
        spots = _uncage_options(groups, rejected_free)             if len(free) < uncaged and len(groups) <= cages[1] + 2 else []
        if spots:
            gi, x = choice(spots)
            trial = [g for g in ([y for y in g if y != x] if i == gi else g for i, g in enumerate(groups)) if g]
            if not solvable(trial, max_level, stats):
                rejected_free.add(x)
                continue
            groups = trial
            free.append(x)
        else:
            longs = sum(len(g) >= long_size[0] for g in groups)
            options = []
            for a, b in _mergeable(board, groups, long_max):
                size = len(groups[a]) + len(groups[b])
                grows_long = max(len(groups[a]), len(groups[b])) >= long_size[0]
                if size > 5 and not grows_long and longs >= long_quota:
                    continue
                if (frozenset(groups[a]), frozenset(groups[b])) not in rejected:
                    options.append((a, b))
            if not options:
                return None
            # Favour growing the long snakes until the quota is met, then small merges.
            weights = []
            for a, b in options:
                size = len(groups[a]) + len(groups[b])
                w = size ** 3 if size > 5 or longs < long_quota else 1
                weights.append(w * (8 if min(len(groups[a]), len(groups[b])) == 1 else 1))
            a, b = choices(options, weights)[0]
            merged = [g for i, g in enumerate(groups) if i not in (a, b)] + [groups[a] + groups[b]]
            if not solvable(merged, max_level, stats):
                rejected.add((frozenset(groups[a]), frozenset(groups[b])))
                continue
            groups = merged
        in_shape = (min_cages <= len(groups) <= cages[1]
                    and len(free) >= uncaged
                    and sum(len(g) == 1 for g in groups) <= max_singles
                    and sum(len(g) >= long_size[0] for g in groups) >= long_cages[0]
                    and stats.get("contradictions", 0) >= min_contradictions)
        if in_shape and (min_level == 1 or not solvable(groups, min_level - 1)):
            return _to_cages(board, groups), [row[:] for row in board]
    return None


def level_attempt(job):
    """One generate_to_level try on a fresh grid; a picklable pool worker.

    `job` is the dict of generate_to_level arguments.
    """
    return generate_to_level(**job)
