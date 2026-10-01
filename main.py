"""Killer Sudoku — CLI entry point.

Usage:
    python main.py                          Generate a new puzzle (hard tier: level 3)
    python main.py --level 4                Needs contradiction checks (levels: 1 direct,
                                            2 candidate elimination, 3 advanced killer logic, 4 contradiction)
    python main.py --contradictions 5       Harder: stuck 5+ times, each broken by a first-order contradiction sweep
    python main.py --uncaged 2              Leave 2 cells in no cage
    python main.py --big-cages 2            At least 2 cages of 7-9 cells
    python main.py --workers 4              Grids tried in parallel
    python main.py --count 10               A set of 10 puzzles
    python main.py --assassin               Shaped like the Assassin series (no givens, cages of 2-5)
    python main.py --min-advanced 30        At least 30 advanced steps in the explained solve
    python main.py --min-advanced 10 --max-advanced 18   Between 10 and 18
    python main.py --list                   List saved puzzles
    python main.py --difficulty             Show difficulty of all puzzles

Classic random-layout generator (--classic):
    python main.py --classic --min-size 2 --max-size 5    Cage sizes between 2 and 5 (default)
    python main.py --classic --min-size 3 --max-size 7    Bigger cages
    python main.py --classic --big-cage 9                 Force one cage of exactly N cells
    python main.py --classic --sparse 5                   Leave ~5 cells uncaged
    python main.py --classic --boards 20 --tries 300      Search harder (more boards/layouts)
"""

import argparse
import json
import os
import sys
import io
import time
from multiprocessing import Pool
from random import choice, randint

from killer import (
    solve_killer_sudoku, solve_and_explain, estimate_difficulty,
    create_board, populate_board, LEVEL_NAMES,
)
from killer.generator import generate_sparse_cages, level_attempt, COLOR_PALETTE
from killer.solver import advanced_steps

# Grids tried in parallel. Measured on a 15 W laptop chip (2 performance +
# 8 efficiency cores): 3 workers made puzzles ~3x faster than 6 or 10, which
# land on slow cores and pull the clock down.
DEFAULT_WORKERS = min(3, os.cpu_count() or 1)

PUZZLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzles")


# =============================================================================
# Puzzle I/O
# =============================================================================

def save_puzzle(cages, solution, filename=None):
    os.makedirs(PUZZLES_DIR, exist_ok=True)
    if filename is None:
        # Next number after the highest, so gaps from deleted puzzles never overwrite one
        numbers = [int(f[7:-5]) for f in os.listdir(PUZZLES_DIR)
                   if f.startswith("puzzle_") and f.endswith(".json") and f[7:-5].isdigit()]
        filename = f"puzzle_{max(numbers, default=0) + 1:03d}.json"
    path = os.path.join(PUZZLES_DIR, filename)
    with open(path, "w") as f:
        f.write('{\n"cages": [\n')
        cage_lines = [f'  [{s}, {json.dumps(cls)}, {color}]' for s, cls, color in cages]
        f.write(",\n".join(cage_lines))
        f.write('\n],\n"solution": [\n')
        row_lines = [f'  {json.dumps(row)}' for row in solution]
        f.write(",\n".join(row_lines))
        f.write('\n]\n}')
    print(f"Saved to {path}")
    return path


def load_puzzle(filename):
    path = os.path.join(PUZZLES_DIR, filename)
    with open(path) as f:
        data = json.load(f)
    cages = [(s, [tuple(c) for c in cls], color) for s, cls, color in data["cages"]]
    return cages, data["solution"]


def list_puzzles():
    if not os.path.isdir(PUZZLES_DIR):
        print("No puzzles saved yet.")
        return []
    files = sorted(f for f in os.listdir(PUZZLES_DIR) if f.endswith(".json"))
    for f in files:
        cages, _ = load_puzzle(f)
        sizes = sorted([len(c[1]) for c in cages])
        print(f"  {f}: {len(cages)} cages, sizes {min(sizes)}-{max(sizes)}")
    return files


# =============================================================================
# Terminal display
# =============================================================================

def print_board(board):
    for i in range(9):
        if i % 3 == 0 and i != 0:
            print("------+-------+------")
        row = ""
        for j in range(9):
            if j % 3 == 0 and j != 0:
                row += "| "
            row += f"{board[i][j]} "
        print(row)
    print()


def print_board_colored(board, cages):
    color_map = {}
    for cage in cages:
        for cl in cage[1]:
            color_map[(cl[0], cl[1])] = cage[2]
    for i in range(9):
        for j in range(9):
            color = color_map.get((i, j))
            if color is not None:
                print(f"\033[1;97;{color}m{board[i][j]}\033[0m", end="")
                print(f"\033[1;97;{color}m \033[0m", end="")
            else:
                print(board[i][j], end=" ")
        print()
    print()


# =============================================================================
# Custom cage generation with size controls
# =============================================================================

def generate_custom_cages(board, min_size=2, max_size=5, big_cage=None):
    """Generate cages with configurable size range and optional one big cage.

    Args:
        board: completed 9x9 solution
        min_size: minimum cage size (default 2)
        max_size: maximum cage size (default 5)
        big_cage: if set, force one cage of exactly this size (e.g. 9)
    """
    cages = []
    used = set()

    def adjacent(cell):
        r, c = cell
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 9 and 0 <= nc < 9:
                yield nr, nc

    # Build the one big cage first if requested
    if big_cage and big_cage > max_size:
        for _ in range(100):
            start = (randint(0, 8), randint(0, 8))
            cage_cells = {start}
            cage_vals = {board[start[0]][start[1]]}
            while len(cage_cells) < big_cage:
                frontier = [c for base in cage_cells for c in adjacent(base)
                            if c not in cage_cells and board[c[0]][c[1]] not in cage_vals]
                if not frontier:
                    break
                nxt = choice(frontier)
                cage_cells.add(nxt)
                cage_vals.add(board[nxt[0]][nxt[1]])
            if len(cage_cells) == big_cage:
                cage_sum = sum(board[r][c] for r, c in cage_cells)
                cages.append((cage_sum, list(cage_cells), COLOR_PALETTE[0]))
                for c in cage_cells:
                    used.add(c)
                break

    # Build size distribution from min_size to max_size
    # Weight toward smaller sizes (more constrained = easier to solve)
    size_pool = []
    for s in range(min_size, max_size + 1):
        weight = max(1, max_size + 1 - s)  # smaller = more weight
        size_pool.extend([s] * weight)

    available = {(r, c) for r in range(9) for c in range(9)} - used

    while available:
        color = COLOR_PALETTE[len(cages) % len(COLOR_PALETTE)]
        target = min(choice(size_pool), len(available))
        best = None

        for _ in range(200):
            start = choice(list(available))
            cage_cells = {start}
            cage_vals = {board[start[0]][start[1]]}
            while len(cage_cells) < target:
                frontier = [c for base in cage_cells for c in adjacent(base)
                            if c not in cage_cells and c not in used
                            and board[c[0]][c[1]] not in cage_vals]
                if not frontier:
                    break
                nxt = choice(frontier)
                cage_cells.add(nxt)
                cage_vals.add(board[nxt[0]][nxt[1]])
            if len(cage_cells) == target:
                best = cage_cells
                break

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
            continue

        for c in best:
            used.add(c)
            available.discard(c)
        cages.append((sum(board[r][c] for r, c in best), list(best), color))

    # Merge singletons
    merged = True
    while merged:
        merged = False
        for i, (_, cls, _c) in enumerate(cages):
            if len(cls) != 1:
                continue
            cl = cls[0]
            val = board[cl[0]][cl[1]]
            for nb in adjacent(cl):
                for j, (osum, ocls, ocol) in enumerate(cages):
                    if i == j:
                        continue
                    if nb in [tuple(x) for x in ocls]:
                        if val not in {board[r][c] for r, c in ocls}:
                            cages[j] = (osum + val, ocls + [cl], ocol)
                            cages.pop(i)
                            merged = True
                            break
                if merged:
                    break
            if merged:
                break
    return cages


def generate_at_level(min_level, workers, contradictions=0, uncaged=0, big_cages=0, count=1,
                      assassin=False, min_advanced=None, max_advanced=None):
    """Generate `count` puzzles needing technique level `min_level`..4, trying
    several grids in parallel and keeping the first ones that work.

    `contradictions` > 0 asks for a harder level-4 puzzle needing at least that
    many first-order contradiction sweeps; those have fewer, bigger cages.
    `uncaged` leaves that many cells in no cage; `big_cages` asks for at least
    that many cages of 7-9 cells. `assassin` shapes them like the Assassin
    series: every cell caged, no one-cell cages (one at most when merging
    gets stuck), cages mostly of 2-5 cells with an occasional 6.
    `min_advanced` asks for that many advanced steps in the explained solve
    (default 20 for Assassin-shape level 3, whose median is 31), `max_advanced`
    at most that many.
    """
    if min_advanced is None:
        min_advanced = 20 if assassin and not contradictions and min_level == 3 else 0
    if contradictions:
        min_level, cages = 4, (20, 27)
        target = f"level 4, stuck {contradictions}+ times (first-order contradiction sweeps)"
    else:
        cages = (24, 27)
        target = f"level {min_level} ({LEVEL_NAMES[min_level]})"
    if uncaged:
        target += f", {uncaged} uncaged cell{'s' if uncaged != 1 else ''}"
    if big_cages:
        target += f", {big_cages}+ cage{'s' if big_cages != 1 else ''} of 7-9 cells"
    if assassin:
        target += ", Assassin shape"
    if min_advanced and max_advanced is not None:
        target += f", {min_advanced}-{max_advanced} advanced steps"
    elif min_advanced:
        target += f", {min_advanced}+ advanced steps"
    elif max_advanced is not None:
        target += f", at most {max_advanced} advanced steps"
    print(f"Generating: {target}, {workers} grids in parallel")
    # Exactly the asked level: solvable there, not one below (level 4 when
    # asking for contradiction sweeps)
    job = dict(min_level=min_level, max_level=4 if contradictions else min_level, cages=cages,
               min_contradictions=contradictions, min_advanced=min_advanced, max_advanced=max_advanced,
               uncaged=uncaged, big_cages=big_cages)
    if assassin:
        # Measured on the 180 Assassins: 25-27 cages (fewer when they need
        # contradiction sweeps), longest cage 5, a 6-cell one in 1 of 6
        job.update(cages=(22, 28) if contradictions else (24, 29), long_cages=(0, 1), long_size=(6, 6),
                   max_singles=0, rescue_singles=1, rescue_uncage=False)
    start = time.time()
    made = 0
    with Pool(workers, maxtasksperchild=10) as pool:
        for result in pool.imap_unordered(level_attempt, [job] * 500 * count):
            if not result:
                continue
            cages, solution = result
            made += 1
            sizes = sorted(len(c[1]) for c in cages)
            print(f"[{made}/{count}] {time.time() - start:.1f}s: {len(cages)} cages, sizes {sizes},"
                  f" {advanced_steps(cages)} advanced steps")
            if count == 1:
                print_board_colored(solution, cages)
            save_puzzle(cages, solution)
            print(estimate_difficulty(cages)["summary"])
            if made == count:
                break
    if made < count:
        print(f"Could not generate {count - made} of the {count} puzzles at this level.")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Killer Sudoku generator and solver")
    sub = parser.add_subparsers(dest="command")

    # List puzzles
    sub.add_parser("list", help="List saved puzzles")

    # Show difficulty
    sub.add_parser("difficulty", help="Show difficulty of all puzzles")

    # Generate (default)
    gen = sub.add_parser("generate", help="Generate a new puzzle")
    gen.add_argument("--min-size", type=int, default=2, help="Minimum cage size (default: 2)")
    gen.add_argument("--max-size", type=int, default=5, help="Maximum cage size (default: 5)")
    gen.add_argument("--big-cage", type=int, default=None, help="Force one cage of exactly N cells")
    gen.add_argument("--sparse", type=int, default=0, help="Leave ~N cells uncaged")
    gen.add_argument("--boards", type=int, default=10, help="Max boards to try (default: 10)")
    gen.add_argument("--tries", type=int, default=200, help="Cage layouts per board (default: 200)")
    gen.add_argument("--level", type=int, default=3, choices=range(1, 5),
                     help="Technique level the puzzle needs (default: 3, like the app's hard tier)")
    gen.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                     help=f"Grids tried in parallel (default: {DEFAULT_WORKERS})")
    gen.add_argument("--contradictions", type=int, default=0,
                     help="Harder level 4: gets stuck N+ times, each needing a first-order contradiction sweep")
    gen.add_argument("--uncaged", type=int, default=0, help="Leave N cells in no cage")
    gen.add_argument("--big-cages", type=int, default=0, help="At least N cages of 7-9 cells")
    gen.add_argument("--count", type=int, default=1, help="Generate a set of N puzzles")
    gen.add_argument("--max-advanced", type=int, default=None,
                     help="At most N advanced steps in the explained solve")
    gen.add_argument("--min-advanced", type=int, default=None,
                     help="At least N advanced steps in the explained solve (default 20 with --assassin at level 3)")
    gen.add_argument("--assassin", action="store_true",
                     help="Shape like the Assassin series: no one-cell cages, cages of 2-5 (rarely 6)")
    gen.add_argument("--classic", action="store_true",
                     help="Old random-layout generator; honours the size/sparse options above")

    # Also support --list and --difficulty as flags on root
    parser.add_argument("--list", action="store_true", help="List saved puzzles")
    parser.add_argument("--difficulty", action="store_true", help="Show difficulty of all puzzles")

    # Generation flags on root too (for convenience)
    parser.add_argument("--min-size", type=int, default=2)
    parser.add_argument("--max-size", type=int, default=5)
    parser.add_argument("--big-cage", type=int, default=None)
    parser.add_argument("--sparse", type=int, default=0)
    parser.add_argument("--boards", type=int, default=10)
    parser.add_argument("--tries", type=int, default=200)
    parser.add_argument("--level", type=int, default=3, choices=range(1, 5))
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--contradictions", type=int, default=0)
    parser.add_argument("--uncaged", type=int, default=0)
    parser.add_argument("--big-cages", type=int, default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--assassin", action="store_true")
    parser.add_argument("--min-advanced", type=int, default=None)
    parser.add_argument("--max-advanced", type=int, default=None)
    parser.add_argument("--classic", action="store_true")

    args = parser.parse_args()

    # Handle commands
    if args.command == "list" or args.list:
        list_puzzles()
        return

    if args.command == "difficulty" or args.difficulty:
        if not os.path.isdir(PUZZLES_DIR):
            print("No puzzles.")
            return
        for f in sorted(os.listdir(PUZZLES_DIR)):
            if not f.endswith(".json"):
                continue
            cages, _ = load_puzzle(f)
            d = estimate_difficulty(cages)
            level = f"level {d['level']} ({LEVEL_NAMES[d['level']]})" if d["level"] else "stuck at level 4"
            print(f"{f}: {d['label']} ({'*' * d['rating']}) {level}")
        return

    # Generation
    if not args.classic:
        generate_at_level(args.level, args.workers, args.contradictions, args.uncaged, args.big_cages,
                          args.count, args.assassin, args.min_advanced, args.max_advanced)
        return

    min_sz, max_sz = args.min_size, args.max_size
    big = args.big_cage
    sparse = args.sparse
    max_boards, max_tries = args.boards, args.tries

    print(f"Generating: cage sizes {min_sz}-{max_sz}"
          + (f", one {big}-cell cage" if big else "")
          + (f", ~{sparse} uncaged cells" if sparse else "")
          + f" (max {max_boards} boards x {max_tries} layouts)")

    start = time.time()
    for board_num in range(max_boards):
        board = create_board()
        populate_board(board)
        print(f"Board {board_num + 1}... ", end="", flush=True)

        for cage_try in range(max_tries):
            cages = generate_custom_cages(board, min_size=min_sz, max_size=max_sz, big_cage=big)
            covered = sum(len(c[1]) for c in cages)
            if covered != 81:
                continue
            if any(len(c[1]) < 2 for c in cages) and not big:
                continue

            # Try solving
            test = create_board()
            old = sys.stdout
            sys.stdout = io.StringIO()
            _, solved = solve_killer_sudoku(test, cages)
            sys.stdout = old

            if solved:
                # Apply sparse if requested
                if sparse > 0:
                    cages = generate_sparse_cages(board, uncaged_target=sparse, base_cages=cages)
                    # Re-verify
                    test2 = create_board()
                    old = sys.stdout
                    sys.stdout = io.StringIO()
                    _, still_solved = solve_killer_sudoku(test2, cages)
                    sys.stdout = old
                    if not still_solved:
                        continue

                sizes = sorted([len(c[1]) for c in cages])
                covered_final = sum(len(c[1]) for c in cages)
                uncaged = 81 - covered_final
                elapsed = time.time() - start

                print(f"solved in {elapsed:.1f}s! (layout {cage_try + 1})")
                print(f"  {len(cages)} cages, sizes: {sizes}")
                if uncaged > 0:
                    print(f"  {uncaged} uncaged cells")

                print("\nSolved board:")
                print_board_colored(test if not sparse else test2, cages)

                save_puzzle(cages, [row[:] for row in board])

                # Difficulty
                print(estimate_difficulty(cages)["summary"])

                # Steps summary
                _, steps = solve_and_explain(cages)
                print(f"\n--- {len(steps)} steps ---")
                for i, step in enumerate(steps, 1):
                    print(f"  {i:3d}. {step['text']}")
                return

        print(f"no luck ({time.time() - start:.1f}s)")
    print("Could not generate a solvable puzzle with these constraints.")


if __name__ == "__main__":
    main()
