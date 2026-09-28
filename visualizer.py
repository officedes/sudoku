"""
Killer Sudoku Visual Solver & Player

Modes:
  python visualizer.py puzzle_001              Step-through solver
  python visualizer.py puzzle_001 --play       Interactive play mode
  python visualizer.py puzzle_001 --print      Text walkthrough

Solver controls:
  SPACE/RIGHT next | LEFT back | A auto | +/- speed | R reset | Q quit

Play controls:
  Click cell to select | 1-9 place digit | 0/DEL clear | H hint
  P toggle pencil mode | C check errors | R reset | Q quit
"""

import pygame
import os
import sys
import textwrap

# --- Load puzzle data ---

PUZZLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzles")

from killer import (
    get_possible_values, get_cage_candidates, solve_and_explain as _solve_and_explain,
    COL_LETTERS as _COL, can_assign_combo, digit_combos,
)
from main import load_puzzle, PUZZLES_DIR


def _compute_candidates(board, cages):
    """Compute candidates for all empty cells from current board state."""
    result = {}
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                sudoku = get_possible_values(board, r, c)
                cage = get_cage_candidates(board, r, c, cages)
                result[f"{_COL[c]}{r+1}"] = sorted(sudoku & cage)
    return result


def _cage_combos(board, cage_sum, cells, candidates=None, excluded=None, excluded_combos=None):
    """Get currently valid combinations for a cage, filtered by pencil marks, digit exclusions, and combo exclusions."""
    filled = [(r, c) for r, c in cells if board[r][c] != 0]
    empty = [(r, c) for r, c in cells if board[r][c] == 0]
    if not empty:
        return []
    filled_nums = set(board[r][c] for r, c in filled)
    remaining_sum = cage_sum - sum(board[r][c] for r, c in filled)
    remaining_size = len(empty)
    excluded = excluded or set()
    excluded_combos = excluded_combos or set()
    result = []
    for combo in digit_combos(remaining_size, remaining_sum, filled_nums):
        # Skip combos containing excluded digits
        if excluded and set(combo) & excluded:
            continue
        # Skip manually excluded combos
        if frozenset(combo) in excluded_combos:
            continue
        # If we have pencil marks, check the combo can be spread over the cells;
        # a cell the player hasn't pencilled yet could still hold anything
        if candidates:
            cell_cands = {}
            for r, c in empty:
                key = f"{_COL[c]}{r+1}"
                cell_cands[(r, c)] = set(candidates[key]) if key in candidates else set(range(1, 10))
            if not can_assign_combo(list(combo), empty, cell_cands):
                continue
        result.append(sorted(combo))
    return result


def load_and_solve(filename):
    """Load a puzzle and compute solution steps at runtime."""
    cages, solution = load_puzzle(filename)
    print(f"Solving {filename}...")
    _, steps = _solve_and_explain(cages)
    print(f"  {len(steps)} steps ready.")
    return cages, solution, steps


# --- Color palette for cages ---

CAGE_COLORS = [
    (255, 179, 186),  # light pink
    (186, 225, 255),  # light blue
    (186, 255, 201),  # light green
    (255, 255, 186),  # light yellow
    (225, 186, 255),  # light purple
    (255, 218, 185),  # peach
    (185, 255, 255),  # light cyan
    (255, 200, 221),  # rose
    (200, 255, 200),  # mint
    (220, 220, 255),  # lavender
    (255, 235, 205),  # blanched almond
    (205, 255, 235),  # aquamarine
    (240, 200, 200),  # dusty rose
    (200, 240, 200),  # pale green
    (200, 200, 240),  # pale blue
    (240, 240, 200),  # pale yellow
    (240, 200, 240),  # pale magenta
    (200, 240, 240),  # pale cyan
    (230, 210, 190),  # tan
    (190, 230, 210),  # seafoam
    (210, 190, 230),  # wisteria
    (230, 230, 190),  # khaki
    (230, 190, 210),  # mauve
    (190, 210, 230),  # steel blue
    (220, 200, 180),  # sand
    (180, 220, 200),  # sage
    (200, 180, 220),  # lilac
    (220, 220, 180),  # cream
    (220, 180, 200),  # blush
    (180, 200, 220),  # powder blue
    (210, 210, 190),  # stone
    (190, 210, 210),  # ice
    (210, 190, 210),  # thistle
    (215, 205, 195),  # warm grey
    (195, 215, 205),  # cool grey
]

HIGHLIGHT_COLOR = (255, 255, 100)  # bright yellow for just-placed cell
GRID_BG = (255, 255, 255)
GRID_LINE = (0, 0, 0)
GRID_LINE_THIN = (180, 180, 180)
TEXT_COLOR = (30, 30, 30)
TEXT_FADED = (160, 160, 160)
EXPLANATION_BG = (245, 245, 250)
STEP_HIGHLIGHT = (70, 130, 70)


def build_cage_color_map(cages):
    """Assign a color to each cage and build cell->color + cell->cage_index maps."""
    cell_color = {}
    cell_cage = {}
    for i, (cage_sum, cells, _) in enumerate(cages):
        color = CAGE_COLORS[i % len(CAGE_COLORS)]
        for cell in cells:
            cell_color[tuple(cell)] = color
            cell_cage[tuple(cell)] = i
    return cell_color, cell_cage


def build_cage_borders(cages):
    """For each cell, determine which edges are cage boundaries (not shared with same cage)."""
    cell_cage = {}
    for i, (_, cells, _) in enumerate(cages):
        for cell in cells:
            cell_cage[tuple(cell)] = i

    borders = {}
    for r in range(9):
        for c in range(9):
            cage_id = cell_cage.get((r, c))
            b = {
                "top": r == 0 or cell_cage.get((r - 1, c)) != cage_id,
                "bottom": r == 8 or cell_cage.get((r + 1, c)) != cage_id,
                "left": c == 0 or cell_cage.get((r, c - 1)) != cage_id,
                "right": c == 8 or cell_cage.get((r, c + 1)) != cage_id,
            }
            borders[(r, c)] = b
    return borders


def get_cage_label_cell(cells):
    """Get the top-left cell of a cage (for placing the sum label)."""
    return min(cells, key=lambda c: (c[0], c[1]))


def print_steps(cages, solution, steps):
    """Print the full solution walkthrough to stdout."""
    sizes = sorted([len(c[1]) for c in cages])
    print("KILLER SUDOKU PUZZLE")
    print("=" * 60)
    print(f"\nCages ({len(cages)} total, sizes {min(sizes)}-{max(sizes)}):\n")
    for i, (cage_sum, cells, _) in enumerate(cages, 1):
        cell_str = ", ".join(f"{_COL[c]}{r+1}" for r, c in cells)
        print(f"  Cage {i:2d}: sum={cage_sum:2d}  cells=[{cell_str}]")
    print(f"\n{'=' * 60}")
    print("SOLUTION:\n")
    for i, row in enumerate(solution):
        if i % 3 == 0 and i != 0:
            print("  ------+-------+------")
        line = ""
        for j, val in enumerate(row):
            if j % 3 == 0 and j != 0:
                line += " | "
            line += f" {val}"
        print(line)
    placements = sum(1 for s in steps if s.get("type") == "placement")
    eliminations = sum(1 for s in steps if s.get("type") == "elimination")
    print(f"\n{'=' * 60}")
    print(f"SOLUTION STEPS ({len(steps)} total: {placements} placements, {eliminations} eliminations):\n")
    for i, step in enumerate(steps, 1):
        stype = step.get("type", "placement")
        tag = {"info": "INFO", "elimination": "ELIM", "placement": "PLACE"}.get(stype, "STEP")
        print(f"Step {i}. [{tag}] {step['text']}")
        if step.get("explanation"):
            for eline in step["explanation"].split("\n"):
                print(f"    {eline}")
        print()


def play_mode(cages, solution):
    """Interactive mode — human solves the puzzle."""
    import time as _time

    pygame.init()
    # Portrait layout modelled on the phone app: top bar, combination bar,
    # grid, message line, tool row, then the Digits / Candidates keypad.
    CELL_SIZE = 60
    GRID_SIZE = CELL_SIZE * 9
    GRID_OFFSET_X = 20
    TOP_H = 44
    COMBO_Y = TOP_H + 4
    COMBO_H = 62
    GRID_OFFSET_Y = COMBO_Y + COMBO_H + 6
    MSG_Y = GRID_OFFSET_Y + GRID_SIZE + 8
    TOOLS_Y = MSG_Y + 26
    PAD_Y = TOOLS_Y + 44
    PAD_KEY_H = 46
    WINDOW_W = GRID_OFFSET_X * 2 + GRID_SIZE
    WINDOW_H = PAD_Y + 3 * (PAD_KEY_H + 6) + 30

    T = {
        "bg": (38, 40, 46), "cell": (47, 49, 55), "uncaged": (40, 42, 48),
        "house": (44, 62, 88), "selected": (62, 92, 140), "selected_edge": (120, 160, 225),
        "multi": (56, 82, 124), "error_bg": (110, 45, 50), "blocked": (60, 64, 76), "hl": (240, 168, 60),
        "grid": (62, 66, 76), "box": (96, 142, 222), "cage": (206, 208, 214),
        "label": (236, 238, 242), "digit": (226, 232, 246), "digit_bad": (245, 105, 105),
        "pencil": (158, 164, 182), "pencil_bad": (235, 90, 90), "pencil_must": (110, 215, 140),
        "text": (214, 218, 228), "muted": (130, 136, 152),
        "chip": (52, 60, 76), "chip_edge": (110, 132, 176), "chip_off": (60, 62, 70),
        "btn": (52, 56, 66), "btn_hover": (66, 72, 86), "btn_active": (70, 110, 90),
        "key": (40, 48, 64), "key_edge": (64, 78, 104), "key_hover": (54, 66, 88),
        "tip": (30, 32, 38), "tip_edge": (96, 102, 120),
    }

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Killer Sudoku — Play Mode")

    font_num = pygame.font.SysFont("segoeui", 30, bold=True)
    font_pencil = pygame.font.SysFont("segoeui", 12)
    font_pencil_bold = pygame.font.SysFont("segoeui", 12, bold=True)
    font_cage_sum = pygame.font.SysFont("segoeui", 12, bold=True)
    font_timer = pygame.font.SysFont("segoeui", 26)
    font_top = pygame.font.SysFont("segoeui", 14, bold=True)
    font_info = pygame.font.SysFont("segoeui", 15)
    font_combo_head = pygame.font.SysFont("segoeui", 24, bold=True)
    font_chip = pygame.font.SysFont("segoeui", 17)
    font_tooltip = pygame.font.SysFont("segoeui", 14)
    font_tooltip_bold = pygame.font.SysFont("segoeui", 14, bold=True)
    font_btn = pygame.font.SysFont("segoeui", 13, bold=True)
    font_key = pygame.font.SysFont("segoeui", 28, bold=True)
    font_key_sup = pygame.font.SysFont("segoeui", 12, bold=True)
    font_key_cand = pygame.font.SysFont("segoeui", 17)
    font_pad_label = pygame.font.SysFont("segoeui", 13, bold=True)

    _, cell_cage_map = build_cage_color_map(cages)

    # Button rects (rebuilt each frame)
    button_rects = {}  # name -> pygame.Rect

    # Game state
    board = [[0] * 9 for _ in range(9)]  # player's board
    pencil = [[set() for _ in range(9)] for _ in range(9)]  # pencil marks
    selected = set()  # set of (row, col)
    pencil_mode = False
    show_errors = False
    hints_used = 0
    start_time = _time.time()
    history = []  # for undo: list of (action, r, c, old_val, old_pencil)
    cage_excluded = {}  # cage_index -> set of excluded digits
    cage_excluded_combos = {}  # cage_index -> set of excluded combos (as frozensets)
    user_cages = []  # list of {"id", "cells": sorted list, "sum": int or None, "color", "distinct": bool}
    next_mark_id = 0
    selected_mark = None  # index into user_cages, or None
    marking_sum = None  # when not None, we're typing a sum for a new mark
    marking_input = ""  # string being typed for sum
    highlight_digit = None  # 1-9 to highlight all cells containing this digit
    message = "Click a cell, type 1-9 or use the keypad. P = pencil, right-click = select cage."
    pad_force = None  # "place" / "pencil" for a digit coming from the keypad
    hint_panel = None  # {"cell", "title", "lines"}: the last hint's explanation, until the next click or key
    msg_color = (60, 60, 80)

    # Precompute which cells are in cages (for coloring uncaged cells differently)
    caged_cells = set()
    for _, cls, _ in cages:
        for cl in cls:
            caged_cells.add(tuple(cl))

    # Clickable combo chips and keypad keys (rebuilt each frame)
    combo_click_rects = []  # list of (pygame.Rect, cage_idx, combo_tuple)
    pad_rects = []  # list of (pygame.Rect, digit, "place" or "pencil")

    clock = pygame.time.Clock()
    running = True

    def _sees(a, b):
        return a[0] == b[0] or a[1] == b[1] or (a[0] // 3 == b[0] // 3 and a[1] // 3 == b[1] // 3)

    def mark_key(uc):
        """Key for a player's mark in the per-cage exclusion dicts (puzzle cages use their index)."""
        return ("mark", uc["id"])

    def summed_areas():
        """Every area with a known sum as (key, sum, cells, distinct): the puzzle's
        cages plus the player's marks that have a sum. A mark's digits are only
        distinct when all its cells see each other."""
        areas = [(ci, cs, ccls, True) for ci, (cs, ccls, _) in enumerate(cages)]
        areas += [(mark_key(uc), uc["sum"], uc["cells"], uc["distinct"])
                  for uc in user_cages if uc["sum"] is not None]
        return areas

    def areas_at(cell):
        return [a for a in summed_areas() if cell in a[2]]

    def do_auto_pencil():
        """Fill pencil marks for the selected cages, or the selected mark, from their valid combos.

        A mark overlays the puzzle's cages, so it only narrows pencil marks a
        cell already has rather than replacing them.
        """
        if selected_mark is not None:
            uc = user_cages[selected_mark]
            if uc["sum"] is None or not uc["distinct"]:
                return 0, 0
            targets = [(mark_key(uc), uc["sum"], uc["cells"])]
        else:
            idxs = sorted({cell_cage_map[cl] for cl in selected if cl in cell_cage_map})
            targets = [(ci, cages[ci][0], cages[ci][1]) for ci in idxs]
        filled_count = 0
        batch = []
        for key, cs, ccls in targets:
            combos = _cage_combos(board, cs, ccls, excluded=cage_excluded.get(key, set()),
                                  excluded_combos=cage_excluded_combos.get(key, set()))
            if not combos:
                continue
            allowed = {num for combo in combos for num in combo}
            for (cr, cc) in ccls:
                if board[cr][cc] != 0:
                    continue
                new_p = allowed & get_possible_values(board, cr, cc)
                if isinstance(key, tuple) and pencil[cr][cc]:
                    new_p &= pencil[cr][cc]
                if new_p != pencil[cr][cc]:
                    batch.append(("pencil_auto", cr, cc, board[cr][cc], set(pencil[cr][cc])))
                    pencil[cr][cc] = new_p
                    filled_count += 1
        if batch:
            history.append(("batch", batch))
        return filled_count, len(targets)

    def do_hint():
        """Place the next logical cell from the player's position and explain it.

        Starts from the player's correct digits (wrong ones are ignored), so the
        explanation matches the grid on screen.
        """
        nonlocal hints_used, hint_panel
        start = [[board[r][c] if board[r][c] == solution[r][c] else 0 for c in range(9)] for r in range(9)]
        _, steps = _solve_and_explain(cages, board=start, stop_after=1)
        idx = next((i for i, s in enumerate(steps) if s["type"] == "placement"), None)
        if idx is None:
            return None
        step = steps[idx]
        r, c = step["cell"]
        val = step["value"]
        batch = [("place", r, c, board[r][c], set(pencil[r][c]))]
        board[r][c] = val
        pencil[r][c] = set()
        _remove_pencil_peers(r, c, val, batch)
        history.append(("batch", batch))
        hints_used += 1
        # Conclusion first, then only the eliminations that fed it: ones that
        # removed candidates from this cell, or removed its digit from a cell
        # sharing a row, column or box with it (what naked/hidden singles rest on)
        lines = [ln for ln in step.get("explanation", "").splitlines() if ln.strip()]
        key_elims, others, prev = [], 0, None
        for s in steps[:idx]:
            now = s.get("candidates")
            if s["type"] == "elimination" and prev is not None and now is not None:
                removed = {(k, d) for k, ds in prev.items() for d in ds if d not in now.get(k, ds)}
                if any(k == cell_name or (d == val and _sees((r, c), (int(k[1:]) - 1, _COL.index(k[0]))))
                       for k, d in removed for cell_name in [f"{_COL[c]}{r+1}"]):
                    key_elims.append(f"  {s['text']}")
                else:
                    others += 1
            if now is not None:
                prev = now
        if key_elims:
            lines += ["Because of:"] + key_elims
        if others:
            lines.append(f"({others} other elimination{'s' if others != 1 else ''} along the way weren't needed here)")
        hint_panel = {"cell": (r, c), "title": step["text"], "lines": lines}
        return f"Hint: {step['text']}"

    def _undo_entry(entry):
        if entry[0] == "combo_excl":
            _, ci, combo_t, was_excluded, pencil_changes = entry
            if ci not in cage_excluded_combos:
                cage_excluded_combos[ci] = set()
            if was_excluded:
                cage_excluded_combos[ci].add(combo_t)
            else:
                cage_excluded_combos[ci].discard(combo_t)
            for (r, c, old_p) in pencil_changes:
                pencil[r][c] = set(old_p)
        else:
            action, r, c, old_val, old_p = entry
            board[r][c] = old_val
            pencil[r][c] = set(old_p)

    def do_undo():
        """Undo last action (single or batched)."""
        if not history:
            return None
        entry = history.pop()
        if entry[0] == "batch":
            _, entries = entry
            for e in reversed(entries):
                _undo_entry(e)
            return f"Undo ({len(entries)} ops)"
        _undo_entry(entry)
        if entry[0] == "combo_excl":
            return f"Undo: combo {sorted(entry[2])}"
        return f"Undo: {_COL[entry[2]]}{entry[1]+1}"

    def _remove_pencil_peers(rr, cc, val, batch):
        """Remove `val` from pencil marks in the row/col/box/cage of (rr, cc)."""
        for i in range(9):
            if pencil[rr][i] and val in pencil[rr][i]:
                batch.append(("auto_remove", rr, i, board[rr][i], set(pencil[rr][i])))
                pencil[rr][i].discard(val)
            if pencil[i][cc] and val in pencil[i][cc]:
                batch.append(("auto_remove", i, cc, board[i][cc], set(pencil[i][cc])))
                pencil[i][cc].discard(val)
        br, bc = (rr // 3) * 3, (cc // 3) * 3
        for bi in range(3):
            for bj in range(3):
                ar, ac = br + bi, bc + bj
                if pencil[ar][ac] and val in pencil[ar][ac]:
                    batch.append(("auto_remove", ar, ac, board[ar][ac], set(pencil[ar][ac])))
                    pencil[ar][ac].discard(val)
        for _key, _sum, acells, distinct in areas_at((rr, cc)):
            if not distinct:
                continue
            for cr, cc2 in acells:
                if (cr, cc2) != (rr, cc) and pencil[cr][cc2] and val in pencil[cr][cc2]:
                    batch.append(("auto_remove", cr, cc2, board[cr][cc2], set(pencil[cr][cc2])))
                    pencil[cr][cc2].discard(val)

    def do_reset():
        """Reset everything."""
        nonlocal start_time, hints_used, show_errors, highlight_digit
        for r in range(9):
            for c in range(9):
                board[r][c] = 0
                pencil[r][c] = set()
        history.clear()
        cage_excluded.clear()
        cage_excluded_combos.clear()
        selected.clear()
        start_time = _time.time()
        hints_used = 0
        show_errors = False
        highlight_digit = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif hint_panel and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                hint_panel = None  # the click or key only closes the hint

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                gr = (my - GRID_OFFSET_Y) // CELL_SIZE
                gc = (mx - GRID_OFFSET_X) // CELL_SIZE
                in_grid = (0 <= gr < 9 and 0 <= gc < 9
                           and GRID_OFFSET_X <= mx < GRID_OFFSET_X + GRID_SIZE
                           and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE)

                if in_grid:
                    shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                    if event.button == 3:  # right click: select cage or user mark
                        deleted_mark = False
                        for mi, uc in enumerate(user_cages):
                            if (gr, gc) in uc["cells"]:
                                selected = set(uc["cells"])
                                selected_mark = mi
                                s = f"sum={uc['sum']}" if uc.get("sum") else "no sum"
                                message = f"User mark ({s}, {len(selected)} cells) — click Del Mark to remove"
                                msg_color = (0, 80, 160)
                                deleted_mark = True
                                break
                        if not deleted_mark:
                            selected_mark = None
                            ci = cell_cage_map.get((gr, gc))
                            if ci is not None:
                                cage_cells_list = cages[ci][1]
                                cage_set = {(r, c) for r, c in cage_cells_list}
                                if shift:
                                    selected |= cage_set
                                else:
                                    selected = cage_set
                                message = f"Cage sum={cages[ci][0]} ({len(selected)} cells)"
                                msg_color = (60, 60, 80)
                    elif shift:
                        # Shift+click: add/remove cell from selection
                        if (gr, gc) in selected:
                            selected.discard((gr, gc))
                        else:
                            selected.add((gr, gc))
                    elif (gr, gc) in selected and len(selected) == 1 and selected_mark is None:
                        # Click already-selected cell: toggle pencil mode
                        pencil_mode = not pencil_mode
                        message = f"{'Pencil' if pencil_mode else 'Place'} mode"
                        msg_color = (0, 120, 0) if pencil_mode else (60, 60, 80)
                    else:
                        selected = {(gr, gc)}
                        selected_mark = None
                        # Clicking a placed digit highlights all cells with that digit
                        if board[gr][gc] != 0:
                            highlight_digit = board[gr][gc]

                else:
                    hit_something = False
                    # Keypad: hand the digit to the key handler, forcing place or pencil;
                    # with nothing selected the key handler toggles the digit highlight,
                    # which also finds digits that only exist as pencil marks
                    for rect, num, how in pad_rects:
                        if rect.collidepoint(mx, my):
                            hit_something = True
                            pad_force = how if selected else None
                            pygame.event.post(pygame.event.Event(
                                pygame.KEYDOWN, key=pygame.K_0 + num, mod=0, unicode=str(num), scancode=0))
                            break
                    # Check combo chip clicks
                    for rect, ci, combo_t in combo_click_rects:
                        if rect.collidepoint(mx, my):
                            hit_something = True
                            if ci not in cage_excluded_combos:
                                cage_excluded_combos[ci] = set()
                            was_excluded = combo_t in cage_excluded_combos[ci]
                            if was_excluded:
                                cage_excluded_combos[ci].discard(combo_t)
                                message = f"Un-excluded {sorted(combo_t)}"
                            else:
                                cage_excluded_combos[ci].add(combo_t)
                                message = f"Excluded {sorted(combo_t)}"
                            # Update pencil marks: remove digits no longer in any valid combo
                            _, cs, ccls, _ = next(a for a in summed_areas() if a[0] == ci)
                            excl = cage_excluded.get(ci, set())
                            remaining = _cage_combos(board, cs, ccls, excluded=excl, excluded_combos=cage_excluded_combos.get(ci, set()))
                            still_valid = {num for combo in remaining for num in combo}
                            removed_count = 0
                            pencil_changes = []
                            for (cr, cc) in ccls:
                                if board[cr][cc] != 0:
                                    continue
                                gone = pencil[cr][cc] - still_valid
                                if gone:
                                    pencil_changes.append((cr, cc, set(pencil[cr][cc])))
                                    pencil[cr][cc] -= gone
                                    removed_count += len(gone)
                            history.append(("combo_excl", ci, combo_t, was_excluded, pencil_changes))
                            if removed_count:
                                message += f" (removed {removed_count} pencil marks)"
                            msg_color = (180, 80, 0)
                            break
                    else:
                        # Check button clicks
                        for btn_name, btn_rect in button_rects.items():
                            if btn_rect.collidepoint(mx, my):
                                hit_something = True
                                if btn_name == "Pencil":
                                    pencil_mode = not pencil_mode
                                    message = f"{'Pencil' if pencil_mode else 'Place'} mode"
                                    msg_color = (0, 120, 0) if pencil_mode else (60, 60, 80)
                                elif btn_name == "Undo":
                                    result = do_undo()
                                    message = result or "Nothing to undo"
                                    msg_color = (60, 60, 80)
                                elif btn_name == "Hint":
                                    result = do_hint()
                                    message = result or "No hints available"
                                    msg_color = (0, 80, 160) if result else (120, 120, 120)
                                elif btn_name == "Check":
                                    show_errors = not show_errors
                                    if show_errors:
                                        errs = sum(1 for r in range(9) for c in range(9)
                                                   if board[r][c] != 0 and board[r][c] != solution[r][c])
                                        message = f"{errs} errors" if errs else "No errors!"
                                        msg_color = (180, 0, 0) if errs else (0, 130, 0)
                                    else:
                                        message = "Errors hidden"
                                        msg_color = (60, 60, 80)
                                elif btn_name == "Fill":
                                    if selected:
                                        cnt, ncages = do_auto_pencil()
                                        message = f"Filled {cnt} cells in {ncages} cage(s)"
                                        msg_color = (0, 100, 0)
                                    else:
                                        message = "Right-click a cage first"
                                        msg_color = (120, 80, 0)
                                elif btn_name == "Fill All":
                                    selected = {(r, c) for r in range(9) for c in range(9) if board[r][c] == 0}
                                    cnt, ncages = do_auto_pencil()
                                    selected = set()
                                    message = f"Filled all: {cnt} cells in {ncages} cages"
                                    msg_color = (0, 100, 0)
                                elif btn_name == "Mark":
                                    if not selected or len(selected) < 2:
                                        message = "Select 2+ cells first, then click Mark"
                                        msg_color = (120, 80, 0)
                                    else:
                                        marking_sum = True
                                        marking_input = ""
                                        message = "Type sum for marked cage (Enter=confirm, Esc=cancel, empty=no sum)"
                                        msg_color = (0, 80, 160)
                                elif btn_name == "Del Mark":
                                    if selected_mark is not None and selected_mark < len(user_cages):
                                        gone = mark_key(user_cages.pop(selected_mark))
                                        cage_excluded.pop(gone, None)
                                        cage_excluded_combos.pop(gone, None)
                                        selected_mark = None
                                        selected = set()
                                        message = "Mark deleted"
                                        msg_color = (60, 60, 80)
                                elif btn_name == "Reset":
                                    do_reset()
                                    message = "Board reset!"
                                    msg_color = (60, 60, 80)
                                break
                    # Click in empty sidebar/background area clears selection
                    if not hit_something and event.button == 1:
                        selected = set()
                        selected_mark = None

            elif event.type == pygame.MOUSEMOTION and pygame.mouse.get_pressed()[0]:
                mx, my = event.pos
                gr = (my - GRID_OFFSET_Y) // CELL_SIZE
                gc = (mx - GRID_OFFSET_X) // CELL_SIZE
                if (0 <= gr < 9 and 0 <= gc < 9
                        and GRID_OFFSET_X <= mx < GRID_OFFSET_X + GRID_SIZE
                        and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE):
                    selected.add((gr, gc))

            elif event.type == pygame.KEYDOWN:
                if marking_sum is not None:
                    # Sum input mode for marking a cage
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        cage_sum_val = int(marking_input) if marking_input.isdigit() else None
                        mark_color = [
                            (255, 160, 160), (160, 200, 255), (160, 255, 160),
                            (255, 220, 140), (200, 160, 255), (140, 240, 240),
                        ][len(user_cages) % 6]
                        mark_cells = sorted(selected)
                        new_mark = {"id": next_mark_id, "cells": mark_cells, "sum": cage_sum_val, "color": mark_color,
                                    "distinct": all(_sees(a, b) for a in mark_cells for b in mark_cells)}
                        next_mark_id += 1
                        user_cages.append(new_mark)
                        marking_sum = None
                        marking_input = ""
                        # Auto-remove pencil marks that can't appear in any valid combo
                        # (combos assume distinct digits, so only when all cells see each other)
                        removed_count = 0
                        if cage_sum_val is not None and new_mark["distinct"]:
                            empty_m = [(r, c) for r, c in mark_cells if board[r][c] == 0]
                            if empty_m:
                                filled_m = [(r, c) for r, c in mark_cells if board[r][c] != 0]
                                filled_nums = set(board[r][c] for r, c in filled_m)
                                rem_sum = cage_sum_val - sum(board[r][c] for r, c in filled_m)
                                combos = digit_combos(len(empty_m), rem_sum, filled_nums)
                                if combos:
                                    valid_digits = {num for combo in combos for num in combo}
                                    for (r, c) in empty_m:
                                        gone = pencil[r][c] - valid_digits
                                        if gone:
                                            history.append(("pencil_auto", r, c, board[r][c], set(pencil[r][c])))
                                            pencil[r][c] -= gone
                                            removed_count += len(gone)
                        s = f"sum={cage_sum_val}" if cage_sum_val else "no sum"
                        extra = f", removed {removed_count} pencil marks" if removed_count else ""
                        if not new_mark["distinct"]:
                            extra += ", digits may repeat"
                        message = f"Marked {len(selected)} cells ({s}{extra})"
                        msg_color = (0, 80, 160)
                    elif event.key == pygame.K_ESCAPE:
                        marking_sum = None
                        marking_input = ""
                        message = "Marking cancelled"
                        msg_color = (60, 60, 80)
                    elif event.key == pygame.K_BACKSPACE:
                        marking_input = marking_input[:-1]
                        message = f"Sum: {marking_input or '(empty = no sum)'} [Enter=confirm]"
                        msg_color = (0, 80, 160)
                    elif event.unicode.isdigit():
                        marking_input += event.unicode
                        message = f"Sum: {marking_input} [Enter=confirm]"
                        msg_color = (0, 80, 160)
                    continue
                if event.key == pygame.K_ESCAPE:
                    # Clear selection/highlight (never quits — use window close to exit)
                    selected = set()
                    selected_mark = None
                    highlight_digit = None
                    message = "Cleared"
                    msg_color = (60, 60, 80)
                elif event.key == pygame.K_p:
                    pencil_mode = not pencil_mode
                    message = f"{'Pencil' if pencil_mode else 'Place'} mode"
                    msg_color = (0, 120, 0) if pencil_mode else (60, 60, 80)
                elif event.key == pygame.K_z and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    result = do_undo()
                    message = result or "Nothing to undo"
                    msg_color = (60, 60, 80)
                elif not selected and event.key in (pygame.K_DELETE, pygame.K_BACKSPACE, pygame.K_0, pygame.K_KP_0):
                    if highlight_digit is not None:
                        highlight_digit = None
                        message = "Highlight cleared"
                        msg_color = (60, 60, 80)
                elif selected and event.key in (pygame.K_DELETE, pygame.K_BACKSPACE, pygame.K_0, pygame.K_KP_0):
                    batch = []
                    for (r, c) in list(selected):
                        if board[r][c] != 0:
                            batch.append(("clear", r, c, board[r][c], set(pencil[r][c])))
                            board[r][c] = 0
                        elif pencil[r][c]:
                            batch.append(("clear_pencil", r, c, 0, set(pencil[r][c])))
                            pencil[r][c] = set()
                    if batch:
                        history.append(("batch", batch))
                    message = "Cleared"
                    msg_color = (60, 60, 80)
                elif pygame.K_1 <= event.key <= pygame.K_9 or pygame.K_KP_1 <= event.key <= pygame.K_KP_9:
                    num = (event.key - pygame.K_0) if event.key <= pygame.K_9 else (event.key - pygame.K_KP_0)
                    if not selected:
                        # No cells selected: toggle digit highlight
                        highlight_digit = None if highlight_digit == num else num
                        if highlight_digit:
                            cnt = sum(1 for rr in range(9) for cc in range(9)
                                      if board[rr][cc] == num or (board[rr][cc] == 0 and num in pencil[rr][cc]))
                            message = f"Highlighting {num} ({cnt} cells)"
                            msg_color = (0, 100, 180)
                        else:
                            message = "Highlight cleared"
                            msg_color = (60, 60, 80)
                        continue
                    use_pencil = (pad_force == "pencil" or len(selected) > 1
                                  or (pad_force != "place" and pencil_mode))
                    pad_force = None
                    if use_pencil:
                        # Pencil mode: if any cell is missing the digit, add to all; else remove from all
                        empty_sel = [(r, c) for (r, c) in selected if board[r][c] == 0]
                        all_have = all(num in pencil[r][c] for r, c in empty_sel) if empty_sel else False
                        batch = []
                        for (r, c) in empty_sel:
                            batch.append(("pencil", r, c, board[r][c], set(pencil[r][c])))
                            if all_have:
                                pencil[r][c].discard(num)
                            else:
                                pencil[r][c].add(num)
                        if batch:
                            history.append(("batch", batch))
                        action = "Removed" if all_have else "Added"
                        message = f"{action} pencil {num} in {len(empty_sel)} cell(s)"
                        msg_color = (0, 120, 0)
                    else:
                        # Place mode, single cell: place digit
                        r, c = next(iter(selected))
                        batch = []
                        batch.append(("place", r, c, board[r][c], set(pencil[r][c])))
                        board[r][c] = num
                        pencil[r][c] = set()
                        # Auto-remove from row/col/box
                        for i in range(9):
                            if pencil[r][i] and num in pencil[r][i]:
                                batch.append(("auto_remove", r, i, board[r][i], set(pencil[r][i])))
                                pencil[r][i].discard(num)
                            if pencil[i][c] and num in pencil[i][c]:
                                batch.append(("auto_remove", i, c, board[i][c], set(pencil[i][c])))
                                pencil[i][c].discard(num)
                        br, bc = (r // 3) * 3, (c // 3) * 3
                        for bi in range(3):
                            for bj in range(3):
                                rr, cc = br + bi, bc + bj
                                if pencil[rr][cc] and num in pencil[rr][cc]:
                                    batch.append(("auto_remove", rr, cc, board[rr][cc], set(pencil[rr][cc])))
                                    pencil[rr][cc].discard(num)
                        # Auto-remove from the same cage or mark (digits can't repeat there)
                        for _key, _sum, acells, distinct in areas_at((r, c)):
                            if not distinct:
                                continue
                            for cr, cc in acells:
                                if (cr, cc) != (r, c) and pencil[cr][cc] and num in pencil[cr][cc]:
                                    batch.append(("auto_remove", cr, cc, board[cr][cc], set(pencil[cr][cc])))
                                    pencil[cr][cc].discard(num)
                        # Auto-fill last remaining cell in cage/mark/row/col/box
                        auto_placed = []
                        keep_checking = True
                        while keep_checking:
                            keep_checking = False
                            # Last cell in a cage or a mark with a sum
                            for _key, asum, acells, _distinct in areas_at((r, c)):
                                cage_empty = [(cr, cc) for cr, cc in acells if board[cr][cc] == 0]
                                if len(cage_empty) == 1:
                                    lr, lc = cage_empty[0]
                                    val = asum - sum(board[cr][cc] for cr, cc in acells if board[cr][cc] != 0)
                                    if 1 <= val <= 9:
                                        batch.append(("auto_place", lr, lc, board[lr][lc], set(pencil[lr][lc])))
                                        board[lr][lc] = val
                                        pencil[lr][lc] = set()
                                        _remove_pencil_peers(lr, lc, val, batch)
                                        auto_placed.append(f"{_COL[lc]}{lr+1}={val}")
                                        keep_checking = True
                            # Last cell in row/col/box
                            for house in [
                                [(r, j) for j in range(9)],    # row
                                [(i, c) for i in range(9)],    # col
                                [(r//3*3+i, c//3*3+j) for i in range(3) for j in range(3)],  # box
                            ]:
                                empty_h = [(hr, hc) for hr, hc in house if board[hr][hc] == 0]
                                if len(empty_h) == 1:
                                    lr, lc = empty_h[0]
                                    placed_digits = {board[hr][hc] for hr, hc in house if board[hr][hc] != 0}
                                    missing = set(range(1, 10)) - placed_digits
                                    if len(missing) == 1:
                                        val = next(iter(missing))
                                        batch.append(("auto_place", lr, lc, board[lr][lc], set(pencil[lr][lc])))
                                        board[lr][lc] = val
                                        pencil[lr][lc] = set()
                                        _remove_pencil_peers(lr, lc, val, batch)
                                        auto_placed.append(f"{_COL[lc]}{lr+1}={val}")
                                        keep_checking = True
                        if batch:
                            history.append(("batch", batch))
                        # Check correctness
                        if board[r][c] != solution[r][c]:
                            message = f"Wrong! {_COL[c]}{r+1} is not {num}"
                            msg_color = (200, 0, 0)
                            show_errors = True
                        else:
                            extra = f" (auto: {', '.join(auto_placed)})" if auto_placed else ""
                            message = f"{_COL[c]}{r+1} = {num}{extra}"
                            msg_color = (0, 130, 0)
                        # Check win
                        if all(board[rr][cc] != 0 for rr in range(9) for cc in range(9)):
                            errs = sum(1 for rr in range(9) for cc in range(9) if board[rr][cc] != solution[rr][cc])
                            if errs == 0:
                                elapsed = _time.time() - start_time
                                mins, secs = int(elapsed // 60), int(elapsed % 60)
                                message = f"SOLVED! {mins}m{secs:02d}s, {hints_used} hints"
                                msg_color = (0, 160, 0)

        # Multi-select forces pencil mode, but don't override back to false
        if len(selected) > 1:
            pencil_mode = True

        # --- Draw ---
        combo_click_rects = []  # rebuilt each frame
        pad_rects = []
        screen.fill(T["bg"])
        mouse = pygame.mouse.get_pos()

        # Compute invalid (red) and must-have (green) pencil digits per cell.
        # Red:   digits not in ANY active cage combo (including pencil-filtered ones)
        # Green: digits in EVERY active cage combo (certain digits for the cage)
        invalid_pencils = {}  # (r, c) -> set of red digits
        must_pencils = {}     # (r, c) -> set of green digits
        for _ci, _cs, _ccls, _distinct in summed_areas():
            if not _distinct:
                continue
            _excl = cage_excluded.get(_ci, set())
            _excl_combos = cage_excluded_combos.get(_ci, set())
            _pencil_cands = None
            if any(pencil[_r][_c] for _r, _c in _ccls if board[_r][_c] == 0):
                _pencil_cands = {}
                for (_r, _c) in _ccls:
                    if board[_r][_c] == 0 and pencil[_r][_c]:
                        _pencil_cands[f"{_COL[_c]}{_r+1}"] = list(pencil[_r][_c])
            _combos = _cage_combos(board, _cs, _ccls,
                                   candidates=_pencil_cands,
                                   excluded=_excl, excluded_combos=_excl_combos)
            _valid = {n for combo in _combos for n in combo}
            _must = set.intersection(*(set(c) for c in _combos)) if _combos else set()
            for (_cr, _cc) in _ccls:
                if board[_cr][_cc] == 0 and pencil[_cr][_cc]:
                    _bad = pencil[_cr][_cc] - _valid
                    if _bad:
                        invalid_pencils[(_cr, _cc)] = _bad
                    _good = pencil[_cr][_cc] & _must
                    if _good:
                        must_pencils[(_cr, _cc)] = _good

        def cell_xy(r, c):
            return GRID_OFFSET_X + c * CELL_SIZE, GRID_OFFSET_Y + r * CELL_SIZE

        def dashed(p1, p2, color, width=1, dash=5, gap=4):
            """Dashed axis-aligned line, phased on absolute position so dashes line up."""
            (x1, y1), (x2, y2) = p1, p2
            horizontal = y1 == y2
            a, b = sorted((x1, x2) if horizontal else (y1, y2))
            s = a - a % (dash + gap)
            while s < b:
                lo, hi = max(s, a), min(s + dash, b)
                if lo < hi:
                    if horizontal:
                        pygame.draw.line(screen, color, (lo, y1), (hi, y1), width)
                    else:
                        pygame.draw.line(screen, color, (x1, lo), (x1, hi), width)
                s += dash + gap

        def outline(cells, color, inset, width=1):
            """Dashed outline inset inside a region; the inset lines meet at inner corners."""
            cs = set(map(tuple, cells))
            S = CELL_SIZE

            def inn(r, c):
                return (r, c) in cs

            for (r, c) in cs:
                x, y = cell_xy(r, c)
                if not inn(r - 1, c):
                    x1 = x + inset if not inn(r, c - 1) else (x - inset if inn(r - 1, c - 1) else x)
                    x2 = x + S - inset if not inn(r, c + 1) else (x + S + inset if inn(r - 1, c + 1) else x + S)
                    dashed((x1, y + inset), (x2, y + inset), color, width)
                if not inn(r + 1, c):
                    x1 = x + inset if not inn(r, c - 1) else (x - inset if inn(r + 1, c - 1) else x)
                    x2 = x + S - inset if not inn(r, c + 1) else (x + S + inset if inn(r + 1, c + 1) else x + S)
                    dashed((x1, y + S - inset), (x2, y + S - inset), color, width)
                if not inn(r, c - 1):
                    y1 = y + inset if not inn(r - 1, c) else (y - inset if inn(r - 1, c - 1) else y)
                    y2 = y + S - inset if not inn(r + 1, c) else (y + S + inset if inn(r + 1, c - 1) else y + S)
                    dashed((x + inset, y1), (x + inset, y2), color, width)
                if not inn(r, c + 1):
                    y1 = y + inset if not inn(r - 1, c) else (y - inset if inn(r - 1, c + 1) else y)
                    y2 = y + S - inset if not inn(r + 1, c) else (y + S + inset if inn(r + 1, c + 1) else y + S)
                    dashed((x + S - inset, y1), (x + S - inset, y2), color, width)

        def soft(color):
            """Status colours were picked for a light theme; lift them for the dark one."""
            return tuple(min(255, int(v * 0.5 + 128)) for v in color)

        # Row/column/box of a single selected cell, like the app
        hl_house_cells = set()
        if len(selected) == 1:
            sr, sc = next(iter(selected))
            hl_house_cells = ({(sr, i) for i in range(9)} | {(i, sc) for i in range(9)}
                              | {(sr // 3 * 3 + i, sc // 3 * 3 + j) for i in range(3) for j in range(3)})

        # Digit highlight, like the app: placed copies and pencil copies get
        # orange boxes, and the houses already holding the digit are shaded
        hl = highlight_digit if len(selected) <= 1 else None
        blocked = set()
        if hl:
            for r in range(9):
                for c in range(9):
                    if board[r][c] == hl:
                        blocked |= ({(r, i) for i in range(9)} | {(i, c) for i in range(9)}
                                    | {(r // 3 * 3 + i, c // 3 * 3 + j) for i in range(3) for j in range(3)})

        # Cell backgrounds (kept per cell so sum labels can knock out the dashed line)
        cell_bg = {}
        for r in range(9):
            for c in range(9):
                x, y = cell_xy(r, c)
                if show_errors and board[r][c] != 0 and board[r][c] != solution[r][c]:
                    bg = T["error_bg"]
                elif len(selected) > 1 and (r, c) in selected:
                    bg = T["multi"]
                elif (r, c) in hl_house_cells:
                    bg = T["house"]
                elif (r, c) in blocked:
                    bg = T["blocked"]
                elif (r, c) not in caged_cells:
                    bg = T["uncaged"]
                else:
                    bg = T["cell"]
                cell_bg[(r, c)] = bg
                pygame.draw.rect(screen, bg, (x, y, CELL_SIZE, CELL_SIZE))
        if len(selected) == 1:
            sr, sc = next(iter(selected))
            x, y = cell_xy(sr, sc)
            pygame.draw.rect(screen, T["selected"], (x + 1, y + 1, CELL_SIZE - 2, CELL_SIZE - 2), border_radius=7)
            pygame.draw.rect(screen, T["selected_edge"], (x + 1, y + 1, CELL_SIZE - 2, CELL_SIZE - 2), 2, border_radius=7)
            cell_bg[(sr, sc)] = T["selected"]

        # Grid lines, then the blue 3x3 box lines on top
        for i in range(10):
            p = i * CELL_SIZE
            pygame.draw.line(screen, T["grid"], (GRID_OFFSET_X + p, GRID_OFFSET_Y),
                             (GRID_OFFSET_X + p, GRID_OFFSET_Y + GRID_SIZE), 1)
            pygame.draw.line(screen, T["grid"], (GRID_OFFSET_X, GRID_OFFSET_Y + p),
                             (GRID_OFFSET_X + GRID_SIZE, GRID_OFFSET_Y + p), 1)
        for i in (3, 6):
            p = i * CELL_SIZE
            pygame.draw.line(screen, T["box"], (GRID_OFFSET_X + p, GRID_OFFSET_Y),
                             (GRID_OFFSET_X + p, GRID_OFFSET_Y + GRID_SIZE), 2)
            pygame.draw.line(screen, T["box"], (GRID_OFFSET_X, GRID_OFFSET_Y + p),
                             (GRID_OFFSET_X + GRID_SIZE, GRID_OFFSET_Y + p), 2)
        pygame.draw.rect(screen, T["grid"], (GRID_OFFSET_X, GRID_OFFSET_Y, GRID_SIZE + 1, GRID_SIZE + 1), 2,
                         border_radius=6)

        # Cage outlines (dashed, inset) and the player's marks inside them
        for _, cage_cells_list, _ in cages:
            outline(cage_cells_list, T["cage"], 5)
        for uc in user_cages:
            outline(uc["cells"], uc["color"], 10, 2)

        # Cage sum labels, cutting through the dashed line like the app
        for cage_sum, cage_cells_list, _ in cages:
            r, c = get_cage_label_cell(cage_cells_list)
            x, y = cell_xy(r, c)
            txt = font_cage_sum.render(str(cage_sum), True, T["label"])
            pygame.draw.rect(screen, cell_bg[(r, c)], (x + 2, y + 1, txt.get_width() + 3, txt.get_height() - 2))
            screen.blit(txt, (x + 3, y))
        for uc in user_cages:
            if uc.get("sum") is not None:
                r, c = min(uc["cells"])
                x, y = cell_xy(r, c)
                stxt = font_cage_sum.render(str(uc["sum"]), True, uc["color"])
                screen.blit(stxt, (x + CELL_SIZE - stxt.get_width() - 4, y + 1))

        # Digits and pencil marks
        for r in range(9):
            for c in range(9):
                x, y = cell_xy(r, c)
                val = board[r][c]
                if val != 0:
                    bad = show_errors and val != solution[r][c]
                    txt = font_num.render(str(val), True, T["digit_bad"] if bad else T["digit"])
                    screen.blit(txt, (x + (CELL_SIZE - txt.get_width()) // 2,
                                      y + (CELL_SIZE - txt.get_height()) // 2 + 2))
                    if val == hl:
                        pygame.draw.rect(screen, T["hl"], (x + 12, y + 8, CELL_SIZE - 24, CELL_SIZE - 14), 2,
                                         border_radius=8)
                elif pencil[r][c]:
                    # Candidate grid sits below the cage-sum label
                    sub = (CELL_SIZE - 16) / 3
                    for n in pencil[r][c]:
                        if n in invalid_pencils.get((r, c), set()):
                            ptxt = font_pencil.render(str(n), True, T["pencil_bad"])
                        elif n in must_pencils.get((r, c), set()):
                            ptxt = font_pencil_bold.render(str(n), True, T["pencil_must"])
                        else:
                            ptxt = font_pencil.render(str(n), True, T["pencil"])
                        cx = x + 8 + ((n - 1) % 3 + 0.5) * sub
                        cy = y + 13 + ((n - 1) // 3 + 0.5) * sub
                        if n == hl:
                            pygame.draw.rect(screen, T["hl"], (cx - sub / 2 + 1, cy - sub / 2 + 1, sub - 2, sub - 2),
                                             1, border_radius=3)
                        screen.blit(ptxt, (cx - ptxt.get_width() / 2, cy - ptxt.get_height() / 2))

        # --- Top bar: mode, timer, progress ---
        elapsed = _time.time() - start_time
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        timer = font_timer.render(f"{mins:02d}:{secs:02d}", True, T["text"])
        screen.blit(timer, ((WINDOW_W - timer.get_width()) // 2, (TOP_H - timer.get_height()) // 2 + 2))
        mode_t = font_top.render("PENCIL" if pencil_mode else "PLACE", True,
                                 T["pencil_must"] if pencil_mode else T["muted"])
        screen.blit(mode_t, (GRID_OFFSET_X, (TOP_H - mode_t.get_height()) // 2 + 2))
        filled = sum(1 for r in range(9) for c in range(9) if board[r][c] != 0)
        prog = font_top.render(f"{filled}/81   Hints {hints_used}", True, T["muted"])
        screen.blit(prog, (WINDOW_W - GRID_OFFSET_X - prog.get_width(), (TOP_H - prog.get_height()) // 2 + 2))

        # --- Combination bar: "sum = [chips]" for the selected cage or mark ---
        if selected_mark is not None and selected_mark < len(user_cages):
            uc = user_cages[selected_mark]
            sel_areas = [(mark_key(uc), uc["sum"], uc["cells"], uc["distinct"])]
        else:
            sel_areas = [(ci, cages[ci][0], cages[ci][1], True)
                         for ci in sorted({cell_cage_map[cl] for cl in selected if cl in cell_cage_map})]
        bar_x, bar_y = GRID_OFFSET_X, COMBO_Y
        if len(sel_areas) == 1 and sel_areas[0][1] is not None and sel_areas[0][3]:
            ci, cs, ccls, _ = sel_areas[0]
            filled_c = [(r, c) for r, c in ccls if board[r][c] != 0]
            remaining = cs - sum(board[r][c] for r, c in filled_c)
            head = font_combo_head.render(f"{remaining} =" if filled_c else f"{cs} =", True, T["text"])
            screen.blit(head, (bar_x, bar_y + 2))
            pencil_cands = None
            if any(pencil[r][c] for r, c in ccls if board[r][c] == 0):
                pencil_cands = {f"{_COL[c]}{r+1}": list(pencil[r][c])
                                for r, c in ccls if board[r][c] == 0 and pencil[r][c]}
            excl = cage_excluded.get(ci, set())
            excl_combo_set = cage_excluded_combos.get(ci, set())
            all_combos = _cage_combos(board, cs, ccls)
            pencil_ok_fs = {frozenset(c) for c in _cage_combos(board, cs, ccls, candidates=pencil_cands)}
            cx, cy = bar_x + head.get_width() + 10, bar_y
            shown = 0
            for combo in all_combos:
                label = "".join(str(d) for d in combo)
                w = font_chip.size(label)[0] + 20
                if cx + w > WINDOW_W - GRID_OFFSET_X:
                    cx, cy = bar_x + head.get_width() + 10, cy + 31
                if cy > bar_y + 31:
                    more = font_info.render(f"+{len(all_combos) - shown} more", True, T["muted"])
                    screen.blit(more, (WINDOW_W - GRID_OFFSET_X - more.get_width(), bar_y + 36))
                    break
                combo_fs = frozenset(combo)
                is_digit_excl = bool(excl and set(combo) & excl)
                is_off = is_digit_excl or combo_fs in excl_combo_set or combo_fs not in pencil_ok_fs
                chip = pygame.Rect(cx, cy, w, 27)
                hover = chip.collidepoint(mouse)
                pygame.draw.rect(screen, T["chip_off"] if is_off else (T["key_hover"] if hover else T["chip"]),
                                 chip, border_radius=7)
                pygame.draw.rect(screen, T["grid"] if is_off else T["chip_edge"], chip, 1, border_radius=7)
                t = font_chip.render(label, True, T["muted"] if is_off else T["text"])
                screen.blit(t, (cx + 10, cy + (27 - t.get_height()) // 2))
                if is_off:
                    pygame.draw.line(screen, T["pencil_bad"], (cx + 7, cy + 14), (cx + w - 7, cy + 14), 1)
                if not is_digit_excl:
                    combo_click_rects.append((chip, ci, combo_fs))
                cx += w + 6
                shown += 1
            if not all_combos:
                t = font_info.render("No valid combinations!", True, T["digit_bad"])
                screen.blit(t, (cx, bar_y + 6))
        else:
            if not sel_areas:
                lines = ["Select a cell to see its cage's combinations",
                         "Click a combination to rule it out"]
            elif len(sel_areas) > 1:
                total = sum(a[1] or 0 for a in sel_areas)
                lines = [f"{len(sel_areas)} cages selected, total {total}"]
            elif sel_areas[0][1] is None:
                lines = ["Your mark has no sum", "Re-mark it with one to get combinations"]
            else:
                lines = [f"Your mark: sum {sel_areas[0][1]}",
                         "Its cells don't all see each other, so digits can repeat"]
            for i, line in enumerate(lines):
                t = (font_top if i == 0 else font_info).render(line, True, T["text"] if i == 0 else T["muted"])
                screen.blit(t, (bar_x, bar_y + 6 + i * 22))

        # --- Message line ---
        msg = font_info.render(message, True, soft(msg_color))
        screen.blit(msg, (GRID_OFFSET_X, MSG_Y))

        # --- Tool row ---
        button_rects = {}
        btn_list = ["Undo", "Pencil", "Hint", "Check", "Fill", "Fill All", "Mark"]
        if selected_mark is not None:
            btn_list.append("Del Mark")
        btn_list.append("Reset")
        widths = [font_btn.size(b)[0] + 18 for b in btn_list]
        gap = (GRID_SIZE - sum(widths)) / max(1, len(btn_list) - 1)
        btn_x = GRID_OFFSET_X
        for bname, bw in zip(btn_list, widths):
            rect = pygame.Rect(int(btn_x), TOOLS_Y, bw, 30)
            button_rects[bname] = rect
            active = (bname == "Pencil" and pencil_mode) or (bname == "Check" and show_errors)
            bg = T["btn_active"] if active else T["btn_hover"] if rect.collidepoint(mouse) else T["btn"]
            pygame.draw.rect(screen, bg, rect, border_radius=8)
            t = font_btn.render(bname, True, T["text"])
            screen.blit(t, (rect.x + (bw - t.get_width()) // 2, rect.y + (30 - t.get_height()) // 2))
            btn_x += bw + gap

        # --- Keypad: Digits (place) and Candidates (pencil), like the app ---
        placed = {d: sum(1 for r in range(9) for c in range(9) if board[r][c] == d) for d in range(1, 10)}
        block_w = (GRID_SIZE - 16) // 2
        key_w = (block_w - 12) // 3
        for block, how, label in ((0, "place", "Digits"), (1, "pencil", "Candidates")):
            bx = GRID_OFFSET_X + block * (block_w + 16)
            for n in range(1, 10):
                kx = bx + ((n - 1) % 3) * (key_w + 6)
                ky = PAD_Y + ((n - 1) // 3) * (PAD_KEY_H + 6)
                rect = pygame.Rect(kx, ky, key_w, PAD_KEY_H)
                pad_rects.append((rect, n, how))
                done = placed[n] >= 9
                pygame.draw.rect(screen, T["key_hover"] if rect.collidepoint(mouse) else T["key"], rect,
                                 border_radius=9)
                pygame.draw.rect(screen, T["key_edge"], rect, 1, border_radius=9)
                if how == "place":
                    t = font_key.render(str(n), True, T["muted"] if done else T["digit"])
                    tx = kx + (key_w - t.get_width()) // 2 - 4
                    screen.blit(t, (tx, ky + (PAD_KEY_H - t.get_height()) // 2))
                    sup = font_key_sup.render(str(9 - placed[n]), True, T["muted"] if done else T["text"])
                    screen.blit(sup, (tx + t.get_width() + 1, ky + 7))
                else:
                    t = font_key_cand.render(str(n), True, T["text"])
                    px = kx + 8 + ((n - 1) % 3) * (key_w - 16 - t.get_width()) / 2
                    py = ky + 4 + ((n - 1) // 3) * (PAD_KEY_H - 8 - t.get_height()) / 2
                    screen.blit(t, (px, py))
            t = font_pad_label.render(label, True, T["muted"])
            screen.blit(t, (bx + (block_w - t.get_width()) // 2, PAD_Y + 3 * (PAD_KEY_H + 6) + 2))

        # --- Hint explanation panel over the bottom area ---
        if hint_panel:
            hr, hc = hint_panel["cell"]
            x, y = cell_xy(hr, hc)
            pygame.draw.rect(screen, T["hl"], (x + 2, y + 2, CELL_SIZE - 4, CELL_SIZE - 4), 3, border_radius=8)
            panel = pygame.Rect(GRID_OFFSET_X - 8, MSG_Y - 4, GRID_SIZE + 16, WINDOW_H - MSG_Y - 4)
            pygame.draw.rect(screen, T["tip"], panel, border_radius=10)
            pygame.draw.rect(screen, T["hl"], panel, 1, border_radius=10)
            title = font_top.render(f"Hint: {hint_panel['title']}", True, T["hl"])
            screen.blit(title, (panel.x + 12, panel.y + 8))
            wrapped = []
            for line in hint_panel["lines"]:
                indent = len(line) - len(line.lstrip())
                words, cur = line.split(), " " * indent
                for w in words:
                    if font_tooltip.size(cur + w)[0] > panel.w - 28 and cur.strip():
                        wrapped.append(cur.rstrip())
                        cur = " " * (indent + 2)
                    cur += w + " "
                wrapped.append(cur.rstrip())
            room = (panel.h - 58) // 19
            if len(wrapped) > room:
                wrapped = wrapped[:room - 1] + [f"... (+{len(wrapped) - room + 1} more lines)"]
            for j, line in enumerate(wrapped):
                t = font_tooltip.render(line, True, T["text"])
                screen.blit(t, (panel.x + 12, panel.y + 32 + j * 19))
            foot = font_tooltip.render("Click or press any key to close", True, T["muted"])
            screen.blit(foot, (panel.right - foot.get_width() - 12, panel.bottom - 24))

        # --- Tooltip on hover ---
        mx, my = mouse
        gr = (my - GRID_OFFSET_Y) // CELL_SIZE
        gc = (mx - GRID_OFFSET_X) // CELL_SIZE
        if 0 <= gr < 9 and 0 <= gc < 9 and GRID_OFFSET_X <= mx < GRID_OFFSET_X + GRID_SIZE \
                and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE:
            tip_lines, bold_rows = [], set()
            for ci, cs, ccls, distinct in areas_at((gr, gc)):
                if tip_lines:
                    tip_lines.append("")
                bold_rows.add(len(tip_lines))
                kind = "Your mark" if isinstance(ci, tuple) else "Cage"
                tip_lines.append(f"{kind}: sum = {cs}, {len(ccls)} cells")
                filled_c = [(r, c) for r, c in ccls if board[r][c] != 0]
                empty_c = [(r, c) for r, c in ccls if board[r][c] == 0]
                if filled_c:
                    filled_str = " + ".join(f"{board[r][c]}" for r, c in filled_c)
                    tip_lines.append(f"Filled: {filled_str} = {sum(board[r][c] for r, c in filled_c)}")
                if empty_c:
                    remaining = cs - sum(board[r][c] for r, c in filled_c)
                    tip_lines.append(f"Need: {remaining} in {len(empty_c)} cell{'s' if len(empty_c)>1 else ''}")
                    if not distinct:
                        tip_lines.append("(digits may repeat)")
                        continue
                    combos = _cage_combos(board, cs, ccls, excluded=cage_excluded.get(ci, set()),
                                          excluded_combos=cage_excluded_combos.get(ci, set()))
                    if combos:
                        combo_strs = ["{" + ",".join(str(x) for x in c) + "}" for c in combos]
                        line = "Combos: "
                        for cstr in combo_strs:
                            if len(line) + len(cstr) > 45:
                                tip_lines.append(line)
                                line = "        " + cstr + " "
                            else:
                                line += cstr + " "
                        tip_lines.append(line)
                        tip_lines.append(f"({len(combos)} possible)")
            if tip_lines:
                tip_w = max(font_tooltip.size(l)[0] for l in tip_lines) + 16
                tip_h = len(tip_lines) * 20 + 8
                tip_x = min(mx + 15, WINDOW_W - tip_w - 5)
                tip_y = min(my + 15, WINDOW_H - tip_h - 5)
                if tip_x + tip_w > WINDOW_W - 5:
                    tip_x = mx - tip_w - 10
                if tip_y + tip_h > WINDOW_H - 5:
                    tip_y = my - tip_h - 10
                tip_x = max(5, tip_x)
                tip_y = max(5, tip_y)
                tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
                pygame.draw.rect(screen, T["tip"], tip_rect, border_radius=6)
                pygame.draw.rect(screen, T["tip_edge"], tip_rect, 1, border_radius=6)
                for j, line in enumerate(tip_lines):
                    f = font_tooltip_bold if j in bold_rows else font_tooltip
                    txt = f.render(line, True, T["text"])
                    screen.blit(txt, (tip_x + 8, tip_y + 4 + j * 20))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def main():
    # Pick puzzle file
    filename = "example.json"
    print_mode = "--print" in sys.argv
    play = "--play" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        filename = args[0]
        if not filename.endswith(".json"):
            filename += ".json"

    if not os.path.exists(os.path.join(PUZZLES_DIR, filename)):
        print(f"Puzzle not found: {filename}")
        print(f"Available puzzles in {PUZZLES_DIR}:")
        for f in sorted(os.listdir(PUZZLES_DIR)):
            if f.endswith(".json"):
                print(f"  {f}")
        return

    if play:
        cages, solution = load_puzzle(filename)
        play_mode(cages, solution)
        return

    cages, solution, steps = load_and_solve(filename)
    if not steps:
        print("No solution steps found.")
        return

    if print_mode:
        print_steps(cages, solution, steps)
        return

    # --- Pygame setup ---
    pygame.init()

    CELL_SIZE = 64
    GRID_OFFSET_X = 30
    GRID_OFFSET_Y = 30
    GRID_SIZE = CELL_SIZE * 9
    LEGEND_WIDTH = 280
    EXPLANATION_HEIGHT = 220
    WINDOW_W = GRID_OFFSET_X * 2 + GRID_SIZE + LEGEND_WIDTH
    WINDOW_H = GRID_OFFSET_Y * 2 + GRID_SIZE + EXPLANATION_HEIGHT

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(f"Killer Sudoku — {filename}")

    font_num = pygame.font.SysFont("consolas", 28, bold=True)
    font_small = pygame.font.SysFont("consolas", 12)
    font_cage_sum = pygame.font.SysFont("consolas", 11, bold=True)
    font_explain = pygame.font.SysFont("segoeui", 15)
    font_explain_bold = pygame.font.SysFont("segoeui", 15, bold=True)
    font_step_counter = pygame.font.SysFont("segoeui", 18, bold=True)
    font_legend_title = pygame.font.SysFont("segoeui", 16, bold=True)
    font_legend = pygame.font.SysFont("segoeui", 13)
    font_controls = pygame.font.SysFont("segoeui", 12)
    font_pencil = pygame.font.SysFont("consolas", 11)
    font_tooltip = pygame.font.SysFont("segoeui", 14)
    font_tooltip_bold = pygame.font.SysFont("segoeui", 14, bold=True)

    cell_color_map, cell_cage_map = build_cage_color_map(cages)
    cage_borders = build_cage_borders(cages)

    # State
    current_step = -1  # -1 = empty board
    board = [[0] * 9 for _ in range(9)]
    highlight_cell = None
    auto_play = False
    auto_delay = 800  # ms between steps
    last_auto_time = 0
    explain_scroll = 0  # scroll offset for explanation panel (in lines)
    live_candidates = _compute_candidates(board, cages)
    prev_live_candidates = dict(live_candidates)
    candidates_dirty = True  # recompute when board changes

    clock = pygame.time.Clock()
    running = True

    while running:
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key in (pygame.K_SPACE, pygame.K_RIGHT):
                    if current_step < len(steps) - 1:
                        current_step += 1
                        s = steps[current_step]
                        if s.get("type") == "placement" and "cell" in s:
                            r, c = s["cell"]
                            board[r][c] = s["value"]
                            highlight_cell = (r, c)
                            candidates_dirty = True
                        else:
                            highlight_cell = None  # elimination step, no cell placed
                        explain_scroll = 0
                        last_auto_time = now
                elif event.key == pygame.K_LEFT:
                    if current_step >= 0:
                        s = steps[current_step]
                        if s.get("type") == "placement" and "cell" in s:
                            r, c = s["cell"]
                            board[r][c] = 0
                            candidates_dirty = True
                        current_step -= 1
                        highlight_cell = None
                        explain_scroll = 0
                        if current_step >= 0 and steps[current_step].get("type") == "placement":
                            highlight_cell = tuple(steps[current_step]["cell"])
                elif event.key == pygame.K_r:
                    current_step = -1
                    board = [[0] * 9 for _ in range(9)]
                    highlight_cell = None
                    explain_scroll = 0
                    candidates_dirty = True
                elif event.key == pygame.K_DOWN:
                    explain_scroll += 2
                elif event.key == pygame.K_UP:
                    explain_scroll = max(0, explain_scroll - 2)
                elif event.key == pygame.K_a:
                    auto_play = not auto_play
                    last_auto_time = now
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    auto_delay = max(100, auto_delay - 100)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    auto_delay = min(3000, auto_delay + 100)
            elif event.type == pygame.MOUSEWHEEL:
                explain_scroll = max(0, explain_scroll - event.y * 2)

        # Auto-play
        if auto_play and current_step < len(steps) - 1 and now - last_auto_time >= auto_delay:
            current_step += 1
            s = steps[current_step]
            if s.get("type") == "placement" and "cell" in s:
                r, c = s["cell"]
                board[r][c] = s["value"]
                highlight_cell = (r, c)
                candidates_dirty = True
            else:
                highlight_cell = None
            last_auto_time = now
            if current_step >= len(steps) - 1:
                auto_play = False

        # Recompute candidates when board changes
        if candidates_dirty:
            prev_live_candidates = dict(live_candidates)
            live_candidates = _compute_candidates(board, cages)
            candidates_dirty = False

        # --- Draw ---
        screen.fill((250, 250, 252))

        # Draw cells
        for r in range(9):
            for c in range(9):
                x = GRID_OFFSET_X + c * CELL_SIZE
                y = GRID_OFFSET_Y + r * CELL_SIZE
                rect = pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)

                # Cell background
                if highlight_cell == (r, c):
                    pygame.draw.rect(screen, HIGHLIGHT_COLOR, rect)
                else:
                    color = cell_color_map.get((r, c), GRID_BG)
                    pygame.draw.rect(screen, color, rect)

                # Cage borders (thick dashed)
                borders = cage_borders.get((r, c), {})
                bw = 2
                if borders.get("top"):
                    pygame.draw.line(screen, (50, 50, 50), (x, y), (x + CELL_SIZE, y), bw)
                if borders.get("bottom"):
                    pygame.draw.line(screen, (50, 50, 50), (x, y + CELL_SIZE), (x + CELL_SIZE, y + CELL_SIZE), bw)
                if borders.get("left"):
                    pygame.draw.line(screen, (50, 50, 50), (x, y), (x, y + CELL_SIZE), bw)
                if borders.get("right"):
                    pygame.draw.line(screen, (50, 50, 50), (x + CELL_SIZE, y), (x + CELL_SIZE, y + CELL_SIZE), bw)

                # Number or pencil marks
                val = board[r][c]
                if val != 0:
                    txt = font_num.render(str(val), True, TEXT_COLOR)
                    tx = x + (CELL_SIZE - txt.get_width()) // 2
                    ty = y + (CELL_SIZE - txt.get_height()) // 2
                    screen.blit(txt, (tx, ty))
                elif current_step >= 0:
                    # Draw pencil marks — use step's candidates for elimination steps,
                    # live-computed for placement steps
                    key = f"{_COL[c]}{r+1}"
                    s = steps[current_step]
                    step_cands = s.get("candidates", {})
                    cand_source = step_cands if step_cands else live_candidates
                    # Get previous step's candidates to detect removals
                    prev_cands = {}
                    if current_step > 0:
                        ps = steps[current_step - 1]
                        ps_cands = ps.get("candidates", {})
                        prev_cands = ps_cands if ps_cands else prev_live_candidates
                    cur_nums = set(cand_source.get(key, []))
                    prev_nums = set(prev_cands.get(key, []))
                    removed_nums = prev_nums - cur_nums
                    # Draw current candidates + removed ones with red bg
                    all_to_draw = cur_nums | removed_nums
                    for n in sorted(all_to_draw):
                        pr = (n - 1) // 3
                        pc = (n - 1) % 3
                        px = x + 14 + pc * 14
                        py = y + 14 + pr * 14
                        if n in removed_nums:
                            # Red background for removed candidate
                            red_rect = pygame.Rect(px - 1, py, 12, 14)
                            pygame.draw.rect(screen, (255, 100, 100), red_rect, border_radius=2)
                            ptxt = font_pencil.render(str(n), True, (180, 30, 30))
                        else:
                            ptxt = font_pencil.render(str(n), True, (120, 120, 150))
                        screen.blit(ptxt, (px, py))

        # Draw cage sum labels (top-left corner of each cage)
        for i, (cage_sum, cells, _) in enumerate(cages):
            label_cell = get_cage_label_cell(cells)
            r, c = label_cell
            x = GRID_OFFSET_X + c * CELL_SIZE + 3
            y = GRID_OFFSET_Y + r * CELL_SIZE + 1
            txt = font_cage_sum.render(str(cage_sum), True, (100, 30, 30))
            screen.blit(txt, (x, y))

        # Draw 3x3 box borders as subtle dashed lines
        dash_color = (140, 140, 160)
        dash_len = 6
        gap_len = 4
        for i in range(1, 3):  # only inner lines, not outer edge
            bx = GRID_OFFSET_X + i * 3 * CELL_SIZE
            by = GRID_OFFSET_Y + i * 3 * CELL_SIZE
            # Vertical dashed line
            y = GRID_OFFSET_Y
            while y < GRID_OFFSET_Y + GRID_SIZE:
                end_y = min(y + dash_len, GRID_OFFSET_Y + GRID_SIZE)
                pygame.draw.line(screen, dash_color, (bx, y), (bx, end_y), 2)
                y += dash_len + gap_len
            # Horizontal dashed line
            x = GRID_OFFSET_X
            while x < GRID_OFFSET_X + GRID_SIZE:
                end_x = min(x + dash_len, GRID_OFFSET_X + GRID_SIZE)
                pygame.draw.line(screen, dash_color, (x, by), (end_x, by), 2)
                x += dash_len + gap_len
        # Outer grid border (solid, thin)
        outer = pygame.Rect(GRID_OFFSET_X, GRID_OFFSET_Y, GRID_SIZE, GRID_SIZE)
        pygame.draw.rect(screen, (80, 80, 80), outer, 2)

        # --- Legend (right side) ---
        legend_x = GRID_OFFSET_X + GRID_SIZE + 15
        legend_y = GRID_OFFSET_Y

        title = font_legend_title.render("CAGES", True, TEXT_COLOR)
        screen.blit(title, (legend_x, legend_y))
        legend_y += 24

        # Show cages in a scrollable-ish compact list
        max_legend_items = 28
        for i, (cage_sum, cells, _) in enumerate(cages):
            if i >= max_legend_items:
                more = font_legend.render(f"... +{len(cages) - max_legend_items} more", True, TEXT_FADED)
                screen.blit(more, (legend_x, legend_y))
                break
            color = CAGE_COLORS[i % len(CAGE_COLORS)]
            swatch = pygame.Rect(legend_x, legend_y + 1, 14, 14)
            pygame.draw.rect(screen, color, swatch)
            pygame.draw.rect(screen, (100, 100, 100), swatch, 1)
            cell_str = ",".join(f"{_COL[c]}{r+1}" for r, c in cells)
            label = font_legend.render(f" {cage_sum:2d}  {cell_str}", True, TEXT_COLOR)
            screen.blit(label, (legend_x + 18, legend_y))
            legend_y += 17

        # --- Explanation panel (bottom) ---
        panel_y = GRID_OFFSET_Y + GRID_SIZE + 10
        panel_rect = pygame.Rect(GRID_OFFSET_X, panel_y, WINDOW_W - GRID_OFFSET_X * 2, EXPLANATION_HEIGHT - 15)
        pygame.draw.rect(screen, EXPLANATION_BG, panel_rect, border_radius=6)
        pygame.draw.rect(screen, (200, 200, 210), panel_rect, 1, border_radius=6)

        if current_step >= 0:
            s = steps[current_step]
            stype = s.get("type", "placement")
            # Step counter
            label_map = {"info": "Info", "elimination": "Elimination", "placement": "Placement"}
            color_map = {"info": (50, 80, 160), "elimination": (180, 100, 30), "placement": STEP_HIGHLIGHT}
            step_label = label_map.get(stype, "Step")
            counter_color = color_map.get(stype, STEP_HIGHLIGHT)
            counter_txt = font_step_counter.render(
                f"Step {current_step + 1}/{len(steps)}  [{step_label}]", True, counter_color
            )
            screen.blit(counter_txt, (GRID_OFFSET_X + 10, panel_y + 6))

            # Step summary
            if stype == "info":
                place_txt = font_explain_bold.render(s.get("text", ""), True, (50, 80, 160))
            elif stype == "elimination":
                place_txt = font_explain_bold.render(s.get("text", ""), True, (150, 80, 20))
            else:
                rc = s.get("cell", (0, 0))
                place_txt = font_explain_bold.render(
                    f"{_COL[rc[1]]}{rc[0]+1} = {s['value']}    Strategy: {s.get('strategy', '')}", True, TEXT_COLOR
                )
            screen.blit(place_txt, (GRID_OFFSET_X + 10, panel_y + 30))

            # Explanation text (wrapped, scrollable)
            explanation = s.get("explanation", "")
            if explanation:
                wrapped = []
                for line in explanation.split("\n"):
                    wrapped.extend(textwrap.wrap(line, width=100) or [""])
                # Clamp scroll
                max_visible = (EXPLANATION_HEIGHT - 75) // 17
                max_scroll = max(0, len(wrapped) - max_visible)
                explain_scroll = min(explain_scroll, max_scroll)
                # Clip to panel area
                clip_rect = pygame.Rect(GRID_OFFSET_X, panel_y + 50, panel_rect.width, EXPLANATION_HEIGHT - 70)
                screen.set_clip(clip_rect)
                ey = panel_y + 52
                for wl in wrapped[explain_scroll:explain_scroll + max_visible + 1]:
                    etxt = font_explain.render(wl, True, (60, 60, 80))
                    screen.blit(etxt, (GRID_OFFSET_X + 10, ey))
                    ey += 17
                screen.set_clip(None)
                # Scroll indicator
                if len(wrapped) > max_visible:
                    indicator = font_controls.render(
                        f"[scroll: {explain_scroll+1}-{min(explain_scroll+max_visible, len(wrapped))}/{len(wrapped)}  UP/DOWN or mousewheel]",
                        True, TEXT_FADED,
                    )
                    screen.blit(indicator, (GRID_OFFSET_X + panel_rect.width - 330, panel_y + 6))
        else:
            intro = font_step_counter.render("Press SPACE to start solving", True, TEXT_FADED)
            screen.blit(intro, (GRID_OFFSET_X + 10, panel_y + 10))

        # Controls hint
        auto_str = f"Auto: {'ON' if auto_play else 'OFF'} ({auto_delay}ms)"
        controls = font_controls.render(
            f"SPACE/-> next  <- back  UP/DN scroll  A auto  +/- speed  R reset  Q quit  |  {auto_str}",
            True, TEXT_FADED,
        )
        screen.blit(controls, (GRID_OFFSET_X, WINDOW_H - 18))

        # --- Cage tooltip on hover ---
        mx, my = pygame.mouse.get_pos()
        grid_r = (my - GRID_OFFSET_Y) // CELL_SIZE
        grid_c = (mx - GRID_OFFSET_X) // CELL_SIZE
        if 0 <= grid_r < 9 and 0 <= grid_c < 9 and GRID_OFFSET_X <= mx < GRID_OFFSET_X + GRID_SIZE and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE:
            cage_idx = cell_cage_map.get((grid_r, grid_c))
            if cage_idx is not None:
                cage_sum, cage_cells, _ = cages[cage_idx]
                # Use current pencil marks to filter combos
                tip_cands = None
                if current_step >= 0:
                    s = steps[current_step]
                    tip_cands = s.get("candidates") or live_candidates
                combos = _cage_combos(board, cage_sum, cage_cells, candidates=tip_cands)
                filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
                empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
                filled_str = ", ".join(f"{board[r][c]}" for r, c in filled) if filled else "none"

                # Build tooltip lines
                tip_lines = [
                    f"Cage: sum = {cage_sum}, {len(cage_cells)} cells",
                    f"Cells: {', '.join(f'R{r+1}C{c+1}' for r, c in cage_cells)}",
                ]
                if filled:
                    filled_str = " + ".join(f"{board[r][c]}" for r, c in filled)
                    tip_lines.append(f"Filled: {filled_str} = {sum(board[r][c] for r, c in filled)}")
                if empty:
                    remaining = cage_sum - sum(board[r][c] for r, c in filled)
                    tip_lines.append(f"Need: {remaining} in {len(empty)} cell{'s' if len(empty)>1 else ''}")
                    if combos:
                        # Show combos compactly, multiple per line
                        combo_strs = ["{" + ",".join(str(x) for x in c) + "}" for c in combos]
                        line = "Combos: "
                        combo_lines = []
                        for cs in combo_strs:
                            if len(line) + len(cs) > 50:
                                combo_lines.append(line)
                                line = "        " + cs + " "
                            else:
                                line += cs + " "
                        combo_lines.append(line)
                        tip_lines.extend(combo_lines)
                        tip_lines.append(f"({len(combos)} possible)")
                    else:
                        tip_lines.append("No valid combos!")
                else:
                    tip_lines.append("(complete)")

                # Render tooltip — position so it never goes off-screen
                tip_w = max(font_tooltip.size(l)[0] for l in tip_lines) + 16
                tip_h = len(tip_lines) * 20 + 8
                # Try right/below mouse, then flip if needed
                tip_x = mx + 15
                tip_y = my + 15
                if tip_x + tip_w > WINDOW_W - 5:
                    tip_x = mx - tip_w - 10
                if tip_y + tip_h > WINDOW_H - 5:
                    tip_y = my - tip_h - 10
                tip_x = max(5, tip_x)
                tip_y = max(5, tip_y)
                tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
                pygame.draw.rect(screen, (255, 255, 240), tip_rect, border_radius=4)
                pygame.draw.rect(screen, (150, 150, 130), tip_rect, 1, border_radius=4)
                for j, line in enumerate(tip_lines):
                    f = font_tooltip_bold if j == 0 else font_tooltip
                    txt = f.render(line, True, (40, 40, 40))
                    screen.blit(txt, (tip_x + 8, tip_y + 4 + j * 20))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
