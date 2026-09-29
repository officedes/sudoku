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

import json
import pygame
import os
import sys

# --- Load puzzle data ---

PUZZLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzles")

from killer import (
    get_possible_values, get_cage_candidates, solve_and_explain as _solve_and_explain,
    COL_LETTERS as _COL, can_assign_combo, digit_combos,
)
from main import load_puzzle, PUZZLES_DIR

SAVES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")


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


# --- Dark theme shared by play mode and the step-through solver (modelled on the phone app) ---

THEME = {
    "bg": (38, 40, 46), "cell": (47, 49, 55), "uncaged": (40, 42, 48),
    "house": (44, 62, 88), "selected": (62, 92, 140), "selected_edge": (120, 160, 225),
    "multi": (56, 82, 124), "error_bg": (110, 45, 50), "hl_cell": (62, 74, 94), "hl": (240, 168, 60),
    "grid": (62, 66, 76), "box": (96, 142, 222), "cage": (206, 208, 214),
    "label": (236, 238, 242), "digit": (226, 232, 246), "digit_bad": (245, 105, 105),
    "pencil": (158, 164, 182), "pencil_bad": (235, 90, 90), "pencil_must": (110, 215, 140),
    "text": (214, 218, 228), "muted": (130, 136, 152),
    "chip": (52, 60, 76), "chip_edge": (110, 132, 176), "chip_off": (60, 62, 70),
    "btn": (52, 56, 66), "btn_hover": (66, 72, 86), "btn_active": (70, 110, 90),
    "key": (40, 48, 64), "key_edge": (64, 78, 104), "key_hover": (54, 66, 88),
    "tip": (30, 32, 38), "tip_edge": (96, 102, 120), "panel": (52, 64, 88),
    "removed_bg": (120, 48, 52), "info": (120, 160, 235), "elim": (240, 168, 60), "place": (110, 215, 140),
}


def build_cell_cage_map(cages):
    """cell -> index of its cage."""
    return {tuple(cell): i for i, (_, cells, _) in enumerate(cages) for cell in cells}


def draw_dashed(screen, p1, p2, color, width=1, dash=5, gap=4):
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


def draw_outline(screen, cells, color, inset, width, gx, gy, size):
    """Dashed outline inset inside a region of cells; the inset lines meet at inner corners."""
    cs = set(map(tuple, cells))

    def inn(r, c):
        return (r, c) in cs

    for (r, c) in cs:
        x, y = gx + c * size, gy + r * size
        if not inn(r - 1, c):
            x1 = x + inset if not inn(r, c - 1) else (x - inset if inn(r - 1, c - 1) else x)
            x2 = x + size - inset if not inn(r, c + 1) else (x + size + inset if inn(r - 1, c + 1) else x + size)
            draw_dashed(screen, (x1, y + inset), (x2, y + inset), color, width)
        if not inn(r + 1, c):
            x1 = x + inset if not inn(r, c - 1) else (x - inset if inn(r + 1, c - 1) else x)
            x2 = x + size - inset if not inn(r, c + 1) else (x + size + inset if inn(r + 1, c + 1) else x + size)
            draw_dashed(screen, (x1, y + size - inset), (x2, y + size - inset), color, width)
        if not inn(r, c - 1):
            y1 = y + inset if not inn(r - 1, c) else (y - inset if inn(r - 1, c - 1) else y)
            y2 = y + size - inset if not inn(r + 1, c) else (y + size + inset if inn(r + 1, c - 1) else y + size)
            draw_dashed(screen, (x + inset, y1), (x + inset, y2), color, width)
        if not inn(r, c + 1):
            y1 = y + inset if not inn(r - 1, c) else (y - inset if inn(r - 1, c + 1) else y)
            y2 = y + size - inset if not inn(r + 1, c) else (y + size + inset if inn(r + 1, c + 1) else y + size)
            draw_dashed(screen, (x + size - inset, y1), (x + size - inset, y2), color, width)


def draw_grid_lines(screen, gx, gy, size):
    """Thin cell lines, blue 3x3 box lines and a rounded outer border."""
    total = size * 9
    for i in range(10):
        p = i * size
        pygame.draw.line(screen, THEME["grid"], (gx + p, gy), (gx + p, gy + total), 1)
        pygame.draw.line(screen, THEME["grid"], (gx, gy + p), (gx + total, gy + p), 1)
    for i in (3, 6):
        p = i * size
        pygame.draw.line(screen, THEME["box"], (gx + p, gy), (gx + p, gy + total), 2)
        pygame.draw.line(screen, THEME["box"], (gx, gy + p), (gx + total, gy + p), 2)
    pygame.draw.rect(screen, THEME["grid"], (gx, gy, total + 1, total + 1), 2, border_radius=6)


def draw_cages(screen, cages, cell_bg, font, gx, gy, size):
    """Dashed inset cage outlines, with sum labels cutting through them like the app."""
    for _, cells, _ in cages:
        draw_outline(screen, cells, THEME["cage"], 5, 1, gx, gy, size)
    for cage_sum, cells, _ in cages:
        r, c = get_cage_label_cell(cells)
        x, y = gx + c * size, gy + r * size
        txt = font.render(str(cage_sum), True, THEME["label"])
        pygame.draw.rect(screen, cell_bg[(r, c)], (x + 2, y + 1, txt.get_width() + 3, txt.get_height() - 2))
        screen.blit(txt, (x + 3, y))


def draw_tooltip(screen, lines, bold_rows, pos, fonts, window):
    """Dark tooltip box near the mouse, kept inside the window."""
    font, font_bold = fonts
    mx, my = pos
    tip_w = max(font.size(line)[0] for line in lines) + 16
    tip_h = len(lines) * 20 + 8
    tip_x = mx + 15 if mx + 15 + tip_w <= window[0] - 5 else mx - tip_w - 10
    tip_y = my + 15 if my + 15 + tip_h <= window[1] - 5 else my - tip_h - 10
    rect = pygame.Rect(max(5, tip_x), max(5, tip_y), tip_w, tip_h)
    pygame.draw.rect(screen, THEME["tip"], rect, border_radius=6)
    pygame.draw.rect(screen, THEME["tip_edge"], rect, 1, border_radius=6)
    for j, line in enumerate(lines):
        f = font_bold if j in bold_rows else font
        screen.blit(f.render(line, True, THEME["text"]), (rect.x + 8, rect.y + 4 + j * 20))


def wrap_text(lines, font, width):
    """Word-wrap lines to a pixel width, keeping each line's indent."""
    out = []
    for line in lines:
        indent = len(line) - len(line.lstrip())
        cur = " " * indent
        for w in line.split():
            if font.size(cur + w)[0] > width and cur.strip():
                out.append(cur.rstrip())
                cur = " " * (indent + 2)
            cur += w + " "
        out.append(cur.rstrip())
    return out


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


def play_mode(cages, solution, save_path=None):
    """Interactive mode — human solves the puzzle.

    With `save_path` the game is kept there - every few seconds and on close -
    and picked up again next time: digits, pencil marks, ruled-out
    combinations, marks, the clock and the hints used (not the undo history).
    Solving the puzzle deletes the save.
    """
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
    LIST_ROWS = 4  # rows of the chevron list on screen at once; the wheel scrolls the rest
    LABEL_H = 16  # column letters above the grid; row numbers sit in the left margin
    GRID_OFFSET_Y = COMBO_Y + COMBO_H + 6 + LABEL_H
    MSG_Y = GRID_OFFSET_Y + GRID_SIZE + 8
    TOOLS_Y = MSG_Y + 26
    PAD_Y = TOOLS_Y + 44
    PAD_KEY_H = 46
    WINDOW_W = GRID_OFFSET_X * 2 + GRID_SIZE
    WINDOW_H = PAD_Y + 3 * (PAD_KEY_H + 6) + 30

    T = THEME

    # Everything is drawn at the design size on `screen`; when the desktop is
    # shorter than that (1920x1200 at 125% leaves 912 px) the window shows it
    # scaled down, and mouse positions are scaled back. Headless tests (the
    # dummy driver) drive design coordinates, so they never scale.
    scale = 1.0
    if pygame.display.get_driver() != "dummy":
        desk_w, desk_h = pygame.display.get_desktop_sizes()[0]
        # Windows 11's taskbar (48) and a title bar (~32) share the desktop height
        scale = min(1.0, (desk_h - 48 - 32 - 8) / WINDOW_H)
        if scale < 1.0:
            # Centred on the whole desktop the bottom would slide under the taskbar
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{(desk_w - round(WINDOW_W * scale)) // 2},32"
    window = pygame.display.set_mode((round(WINDOW_W * scale), round(WINDOW_H * scale)))
    screen = window if scale == 1.0 else pygame.Surface((WINDOW_W, WINDOW_H))

    def to_design(pos):
        return (round(pos[0] / scale), round(pos[1] / scale)) if scale != 1.0 else pos
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

    cell_cage_map = build_cell_cage_map(cages)

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
    marks_open = False  # the list of the player's marks, opened from the combination bar
    marks_toggle_rect = marks_panel_rect = None  # drawn each frame, clicked on the next
    mark_trash_rects = []  # (pygame.Rect, mark index)
    mark_row_rects = []  # (pygame.Rect, ("cage" | "mark", index)): click a row to show just it in the bar
    marks_scroll = 0  # first list row on screen; the wheel scrolls it
    bar_pick = None  # (cage index, the selection it was picked for): a cage picked from the list
    marking_sum = None  # when not None, we're typing a sum for a new mark
    marking_input = ""  # string being typed for sum
    highlight_digit = None  # 1-9 to highlight all cells containing this digit
    message = "Click a cell, type 1-9 or use the keypad. P = pencil, right-click = select cage."
    pad_force = None  # "place" / "pencil" for a digit coming from the keypad
    hint_panel = None  # {"cells", "title", "lines"}: the last hint's explanation, until the next click or key
    hinted_steps = set()  # step texts Hint already gave, so the next hint moves on
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

    def delete_mark(mi):
        nonlocal selected_mark, selected
        gone = mark_key(user_cages.pop(mi))
        cage_excluded.pop(gone, None)
        cage_excluded_combos.pop(gone, None)
        selected_mark = None
        selected = set()

    def draw_chips(key, cs, ccls, x0, y0, x_max, rows):
        """An area's combinations as chips from (x0, y0), wrapping over `rows`
        rows; ruled-out ones are greyed and struck through, and every chip not
        hidden by a digit rule-out can be clicked to toggle it."""
        pencil_cands = None
        if any(pencil[r][c] for r, c in ccls if board[r][c] == 0):
            pencil_cands = {f"{_COL[c]}{r+1}": list(pencil[r][c])
                            for r, c in ccls if board[r][c] == 0 and pencil[r][c]}
        excl = cage_excluded.get(key, set())
        excl_combo_set = cage_excluded_combos.get(key, set())
        all_combos = _cage_combos(board, cs, ccls)
        pencil_ok_fs = {frozenset(c) for c in _cage_combos(board, cs, ccls, candidates=pencil_cands)}

        def ruled_out(combo):
            return (bool(excl and set(combo) & excl) or frozenset(combo) in excl_combo_set
                    or frozenset(combo) not in pencil_ok_fs)

        # Valid combinations first, so the ones cut off by "+N more" are struck ones
        all_combos = sorted(all_combos, key=ruled_out)
        cx, cy = x0, y0
        shown = 0
        for combo in all_combos:
            label = "".join(str(d) for d in combo)
            w = font_chip.size(label)[0] + 20
            if cx + w > x_max:
                cx, cy = x0, cy + 31
            if cy > y0 + 31 * (rows - 1):
                more = font_info.render(f"+{len(all_combos) - shown} more", True, T["muted"])
                screen.blit(more, (x_max - more.get_width(), y0 + 31 * (rows - 1) + 5))
                break
            combo_fs = frozenset(combo)
            is_digit_excl = bool(excl and set(combo) & excl)
            is_off = ruled_out(combo)
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
                combo_click_rects.append((chip, key, combo_fs))
            cx += w + 6
            shown += 1
        if not all_combos:
            t = font_info.render("No valid combinations!", True, T["digit_bad"])
            screen.blit(t, (cx, y0 + 6))

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
        """Explain the next step from the player's position, one at a time.

        Starts from the player's correct digits (wrong ones are ignored), so the
        explanation matches the grid on screen. Eliminations the pencil marks
        already show, and steps already hinted, are skipped. An elimination's
        digits leave the pencil marks that still hold them (undoable); a
        placement is only explained - the player makes it.
        """
        nonlocal hints_used, hint_panel
        start = [[board[r][c] if board[r][c] == solution[r][c] else 0 for c in range(9)] for r in range(9)]
        _, steps = _solve_and_explain(cages, board=start, stop_after=1)
        prev = None
        for s in steps:
            now = s.get("candidates")
            lines = [ln for ln in s.get("explanation", "").splitlines() if ln.strip()]
            if s["type"] == "placement":
                r, c = s["cell"]
                if s["text"] not in hinted_steps:  # asking again for the same placement is free
                    hinted_steps.add(s["text"])
                    hints_used += 1
                hint_panel = {"cells": [(r, c)], "title": s["text"],
                              "lines": lines + [f"Place {s['value']} in {_COL[c]}{r+1} yourself when you're ready."]}
                return f"Hint: {s['text']}"
            if s["type"] == "elimination" and prev is not None and now is not None:
                removed = [(int(k[1:]) - 1, _COL.index(k[0]), d)
                           for k, ds in prev.items() for d in ds if d not in now.get(k, ds)]
                # New to the player unless their pencil marks already rule it out
                new = [(r, c, d) for r, c, d in removed
                       if board[r][c] == 0 and (not pencil[r][c] or d in pencil[r][c])]
                # The explainer's re-filter of every cage at once is hinted one cage at a time
                bulk = s["text"].startswith("Cage combo filtering")
                parts = {}
                for r, c, d in new:
                    parts.setdefault(cell_cage_map.get((r, c)) if bulk else None, []).append((r, c, d))
                for key, part in parts.items():
                    if (s["text"], key) in hinted_steps:
                        continue
                    hinted_steps.add((s["text"], key))
                    batch = []
                    for r, c, d in part:
                        if d in pencil[r][c]:
                            batch.append(("pencil_auto", r, c, board[r][c], set(pencil[r][c])))
                            pencil[r][c].discard(d)
                    if batch:
                        history.append(("batch", batch))
                    hints_used += 1
                    title, shown = s["text"], sorted({(r, c) for r, c, _ in part})
                    if key is not None:
                        cs, ccls, _ = cages[key]
                        ccls = [tuple(x) for x in ccls]
                        names = [f"{_COL[c]}{r+1}" for r, c in ccls]
                        left = {n: now.get(n, []) for (r, c), n in zip(ccls, names) if start[r][c] == 0}
                        fits = ", ".join("{" + ",".join(map(str, co)) + "}"
                                         for co in _cage_combos(start, cs, ccls, candidates=left))
                        rem = cs - sum(start[r][c] for r, c in ccls)
                        title = f"Cage {cs} [{', '.join(names)}]: only {fits} still fit"
                        lines = [f"With the digits its empty cells can still take, only {fits} add up to {rem}"
                                 f"{f' (the cage {cs} minus its placed digits)' if rem != cs else ''}."]
                        for r, c, d in sorted(part):
                            n = f"{_COL[c]}{r+1}"
                            others = [x for x in left if x != n]
                            if len(others) == 1:
                                o, need = others[0], rem - d
                                why = (f"{n} = {d} would need {o} = {need}, which isn't a digit" if not 1 <= need <= 9
                                       else f"{n} = {d} would need {o} = {need} too" if need == d
                                       else f"{n} = {d} would need {o} = {need}, but {o} can't be {need}")
                            else:
                                why = (f"with {n} = {d}, the other cells can't make up the remaining {rem - d}"
                                       f" from the digits they can still take")
                            lines.append(f"{why}, so {n} loses {d}.")
                        shown = ccls
                    hint_panel = {"cells": shown, "title": title, "lines": lines}
                    return f"Hint: {title}"
            if now is not None:
                prev = now
        return None

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
        hinted_steps.clear()
        selected.clear()
        start_time = _time.time()
        hints_used = 0
        show_errors = False
        highlight_digit = None

    # Keys of the per-cage rule-outs are cage indices or ("mark", id); JSON has no tuples
    def key_out(k):
        return list(k) if isinstance(k, tuple) else k

    def key_in(k):
        return tuple(k) if isinstance(k, list) else k

    def save_progress():
        if not save_path:
            return
        if all(board[r][c] == solution[r][c] for r in range(9) for c in range(9)):
            if os.path.exists(save_path):
                os.remove(save_path)  # solved: next time starts fresh
            return
        state = {
            "board": board,
            "pencil": [[sorted(p) for p in row] for row in pencil],
            "elapsed": _time.time() - start_time,
            "hints_used": hints_used,
            "cage_excluded": [[key_out(k), sorted(v)] for k, v in cage_excluded.items()],
            "cage_excluded_combos": [[key_out(k), [sorted(co) for co in v]] for k, v in cage_excluded_combos.items()],
            "user_cages": [{**uc, "cells": [list(x) for x in uc["cells"]], "color": list(uc["color"])}
                           for uc in user_cages],
            "next_mark_id": next_mark_id,
            "hinted_steps": [list(h) if isinstance(h, tuple) else h for h in hinted_steps],
        }
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        tmp = save_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, save_path)  # never leave a half-written save behind

    if save_path and os.path.exists(save_path):
        try:
            with open(save_path, encoding="utf-8") as f:
                saved = json.load(f)
            for r in range(9):
                for c in range(9):
                    board[r][c] = saved["board"][r][c]
                    pencil[r][c] = set(saved["pencil"][r][c])
            start_time = _time.time() - saved["elapsed"]
            hints_used = saved["hints_used"]
            cage_excluded.update({key_in(k): set(v) for k, v in saved["cage_excluded"]})
            cage_excluded_combos.update({key_in(k): {frozenset(co) for co in v}
                                         for k, v in saved["cage_excluded_combos"]})
            user_cages.extend({**uc, "cells": [tuple(x) for x in uc["cells"]], "color": tuple(uc["color"])}
                              for uc in saved["user_cages"])
            next_mark_id = saved["next_mark_id"]
            hinted_steps.update(tuple(h) if isinstance(h, list) else h for h in saved["hinted_steps"])
            placed_n = sum(1 for row in board for v in row if v)
            message = f"Welcome back: {placed_n}/81 placed, {int(saved['elapsed'] // 60)} min in"
        except (OSError, ValueError, KeyError, TypeError) as e:
            message = f"Couldn't read the saved game ({e}); starting fresh"
    last_save = _time.time()

    while running:
        if _time.time() - last_save > 5:
            save_progress()
            last_save = _time.time()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif hint_panel and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                hint_panel = None  # the click or key only closes the hint

            elif event.type == pygame.MOUSEWHEEL:
                if marks_open and marks_panel_rect is not None and marks_panel_rect.collidepoint(to_design(pygame.mouse.get_pos())):
                    marks_scroll -= event.y

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                pass  # the wheel, handled as MOUSEWHEEL

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = to_design(event.pos)
                gr = (my - GRID_OFFSET_Y) // CELL_SIZE
                gc = (mx - GRID_OFFSET_X) // CELL_SIZE
                in_panel = marks_open and marks_panel_rect is not None and marks_panel_rect.collidepoint(mx, my)
                in_grid = (0 <= gr < 9 and 0 <= gc < 9 and not in_panel
                           and GRID_OFFSET_X <= mx < GRID_OFFSET_X + GRID_SIZE
                           and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE)

                if in_grid:
                    shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                    if event.button == 3:  # right click: select the puzzle's cage, even under a mark
                        selected_mark = None
                        ci = cell_cage_map.get((gr, gc))
                        if ci is not None:
                            cage_set = {(r, c) for r, c in cages[ci][1]}
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
                    elif (gr, gc) in selected and len(selected) == 1:
                        # Click already-selected cell: toggle pencil mode
                        pencil_mode = not pencil_mode
                        message = f"{'Pencil' if pencil_mode else 'Place'} mode"
                        msg_color = (0, 120, 0) if pencil_mode else (60, 60, 80)
                    else:
                        selected = {(gr, gc)}
                        # A cell in one of the player's marks shows that mark (the
                        # newest, if several) like a puzzle cage: its combinations
                        # in the bar, clickable; right-click reaches the cage
                        selected_mark = next((mi for mi in range(len(user_cages) - 1, -1, -1)
                                              if (gr, gc) in user_cages[mi]["cells"]), None)
                        if selected_mark is not None:
                            uc = user_cages[selected_mark]
                            s = f"sum={uc['sum']}" if uc.get("sum") is not None else "no sum"
                            message = f"Your mark ({s}, {len(uc['cells'])} cells) — right-click for the cage"
                            msg_color = (0, 80, 160)
                        # Clicking a placed digit highlights all cells with that digit
                        if board[gr][gc] != 0:
                            highlight_digit = board[gr][gc]

                else:
                    hit_something = in_panel  # clicks on the open marks list never clear the selection
                    if marks_toggle_rect is not None and marks_toggle_rect.collidepoint(mx, my):
                        hit_something = True
                        marks_open = not marks_open
                        marks_scroll = 0
                    for rect, mi in mark_trash_rects:
                        if rect.collidepoint(mx, my) and mi < len(user_cages):
                            delete_mark(mi)
                            if not user_cages:
                                marks_open = False
                            message = "Mark deleted"
                            msg_color = (60, 60, 80)
                            break
                    # A click on a list row outside its chips and bin shows just that
                    # cage or mark in the combination bar, and closes the list
                    if in_panel and not any(r.collidepoint(mx, my) for r, _ in mark_trash_rects) \
                            and not any(r.collidepoint(mx, my) for r, _, _ in combo_click_rects):
                        for rect, (kind, idx) in mark_row_rects:
                            if rect.collidepoint(mx, my):
                                if kind == "mark":
                                    selected_mark, bar_pick = idx, None
                                else:
                                    selected_mark, bar_pick = None, (idx, frozenset(selected))
                                marks_open = False
                                break
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
                                        delete_mark(selected_mark)
                                        if not user_cages:
                                            marks_open = False
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
                mx, my = to_design(event.pos)
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
                            (240, 72, 72), (80, 150, 255), (70, 210, 110),
                            (245, 175, 40), (175, 115, 250), (40, 200, 210),
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
        mouse = to_design(pygame.mouse.get_pos())

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
        # orange boxes, and every cell the digit is in or can still go (placed
        # or pencilled) is tinted, so the rest of the grid stays dark
        hl = highlight_digit if len(selected) <= 1 else None
        hl_cells = set()
        if hl:
            hl_cells = {(r, c) for r in range(9) for c in range(9)
                        if board[r][c] == hl or (not board[r][c] and hl in pencil[r][c])}

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
                elif (r, c) in hl_cells:
                    bg = T["hl_cell"]
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

        draw_grid_lines(screen, GRID_OFFSET_X, GRID_OFFSET_Y, CELL_SIZE)
        # Coordinates, so cell names in hints (F4 = column F, row 4) can be found;
        # the rows and columns of the selection and of the hinted cells are lit
        lit = set(selected) | set(hint_panel["cells"] if hint_panel else [])
        sel_rows, sel_cols = {r for r, _ in lit}, {c for _, c in lit}
        for i in range(9):
            t = font_cage_sum.render(_COL[i], True, T["hl"] if i in sel_cols else T["muted"])
            screen.blit(t, (GRID_OFFSET_X + i * CELL_SIZE + (CELL_SIZE - t.get_width()) // 2,
                            GRID_OFFSET_Y - LABEL_H + (LABEL_H - t.get_height()) // 2 - 1))
            t = font_cage_sum.render(str(i + 1), True, T["hl"] if i in sel_rows else T["muted"])
            screen.blit(t, ((GRID_OFFSET_X - t.get_width()) // 2,
                            GRID_OFFSET_Y + i * CELL_SIZE + (CELL_SIZE - t.get_height()) // 2))
        draw_cages(screen, cages, cell_bg, font_cage_sum, GRID_OFFSET_X, GRID_OFFSET_Y, CELL_SIZE)
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

        # The player's marks on top of the digits, like the app: a dashed box in
        # each marked cell, and the sum on a patch of the cell's colour. Only
        # the marks passing through the selection show (and are listed under the
        # chevron); hovering a row of that list shows just its mark
        visible_marks = [mi for mi, uc in enumerate(user_cages)
                         if mi == selected_mark or not selected.isdisjoint(uc["cells"])]
        # The list under the chevron: the puzzle's cages through the selection
        # (a mark can cover them), then the marks
        panel_rows = ([("cage", ci) for ci in sorted({cell_cage_map[cl] for cl in selected if cl in cell_cage_map})]
                      + [("mark", mi) for mi in visible_marks])
        marks_scroll = max(0, min(marks_scroll, len(panel_rows) - LIST_ROWS))
        list_rows = panel_rows[marks_scroll:marks_scroll + LIST_ROWS]
        hovered_row = None
        if marks_open and marks_panel_rect is not None and marks_panel_rect.collidepoint(mouse):
            row = (mouse[1] - marks_panel_rect.y - 6) // 40
            hovered_row = list_rows[row] if 0 <= row < len(list_rows) else None
        for mi, uc in enumerate(user_cages):
            if mi not in visible_marks or hovered_row not in (None, ("mark", mi)):
                continue
            for r, c in uc["cells"]:
                x, y = cell_xy(r, c)
                x1, y1, x2, y2 = x + 3, y + 3, x + CELL_SIZE - 4, y + CELL_SIZE - 4
                for a, b in (((x1, y1), (x2, y1)), ((x1, y2), (x2, y2)), ((x1, y1), (x1, y2)), ((x2, y1), (x2, y2))):
                    draw_dashed(screen, a, b, uc["color"], 2, dash=6, gap=4)
            if uc.get("sum") is not None:
                r, c = min(uc["cells"])
                x, y = cell_xy(r, c)
                stxt = font_cage_sum.render(str(uc["sum"]), True, uc["color"])
                label = pygame.Rect(x + CELL_SIZE - stxt.get_width() - 8, y + 1, stxt.get_width() + 4, stxt.get_height())
                pygame.draw.rect(screen, cell_bg[(r, c)], label)
                screen.blit(stxt, (label.x + 2, label.y))

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
        elif bar_pick is not None and bar_pick[1] == frozenset(selected):
            ci = bar_pick[0]
            sel_areas = [(ci, cages[ci][0], cages[ci][1], True)]
        else:
            sel_areas = [(ci, cages[ci][0], cages[ci][1], True)
                         for ci in sorted({cell_cage_map[cl] for cl in selected if cl in cell_cage_map})]
        bar_x, bar_y = GRID_OFFSET_X, COMBO_Y
        # The marks list opens from a chevron at the start of the bar, like the app
        marks_toggle_rect = None
        if visible_marks:
            marks_toggle_rect = pygame.Rect(bar_x, bar_y, 34, 30)
            hover = marks_toggle_rect.collidepoint(mouse)
            pygame.draw.rect(screen, T["key_hover"] if hover or marks_open else T["key"], marks_toggle_rect,
                             border_radius=7)
            mx0, my0 = marks_toggle_rect.center
            tip = -5 if marks_open else 5  # points up when open
            pygame.draw.lines(screen, T["text"], False, [(mx0 - 8, my0 - tip), (mx0, my0 + tip), (mx0 + 8, my0 - tip)], 3)
            bar_x += 42
        if len(sel_areas) == 1 and sel_areas[0][1] is not None and sel_areas[0][3]:
            ci, cs, ccls, _ = sel_areas[0]
            filled_c = [(r, c) for r, c in ccls if board[r][c] != 0]
            remaining = cs - sum(board[r][c] for r, c in filled_c)
            head = font_combo_head.render(f"{remaining} =" if filled_c else f"{cs} =", True, T["text"])
            screen.blit(head, (bar_x, bar_y + 2))
            draw_chips(ci, cs, ccls, bar_x + head.get_width() + 10, bar_y, WINDOW_W - GRID_OFFSET_X, 2)
        else:
            if not sel_areas:
                lines = ["Select a cell to see its cage's combinations",
                         "Click a combination to rule it out"]
            elif len(sel_areas) > 1:
                # A fully selected cage counts its sum. A partly selected one
                # counts its sum minus the cells left out when all of those are
                # known (placed, or a single pencil mark); otherwise just the
                # digits placed in the selection, and its empty cells stay open
                def known(r, c):
                    if board[r][c]:
                        return board[r][c]
                    return next(iter(pencil[r][c])) if len(pencil[r][c]) == 1 else None

                total, open_cells = 0, 0
                for _, cs, ccls, _ in sel_areas:
                    cells_a = {tuple(x) for x in ccls}
                    left_out = [known(r, c) for r, c in cells_a - selected]
                    if None not in left_out:
                        total += cs - sum(left_out)
                    else:
                        part = cells_a & selected
                        total += sum(board[r][c] for r, c in part)
                        open_cells += sum(1 for r, c in part if not board[r][c])
                for r, c in selected:
                    if (r, c) not in cell_cage_map:  # uncaged cells
                        total += board[r][c]
                        open_cells += not board[r][c]
                line = f"{len(sel_areas)} cages selected, total {total}"
                if open_cells:
                    line += f" + {open_cells} open cell{'s' if open_cells != 1 else ''}"
                lines = [line]
            elif sel_areas[0][1] is None:
                lines = ["Your mark has no sum", "Re-mark it with one to get combinations"]
            else:
                lines = [f"Your mark: sum {sel_areas[0][1]}",
                         "Its cells don't all see each other, so digits can repeat"]
            for i, line in enumerate(lines):
                t = (font_top if i == 0 else font_info).render(line, True, T["text"] if i == 0 else T["muted"])
                screen.blit(t, (bar_x, bar_y + 6 + i * 22))

        # --- The list: one row per cage or mark, "sum = [chips]", and a bin on marks ---
        marks_panel_rect = None
        mark_trash_rects = []
        mark_row_rects = []
        if marks_open and visible_marks:
            row_h = 40
            marks_panel_rect = pygame.Rect(GRID_OFFSET_X - 4, COMBO_Y + 36, GRID_SIZE + 8, 12 + row_h * len(list_rows))
            pygame.draw.rect(screen, T["panel"], marks_panel_rect, border_radius=12)
            pygame.draw.rect(screen, T["key_edge"], marks_panel_rect, 1, border_radius=12)
            if len(panel_rows) > LIST_ROWS:
                track = pygame.Rect(marks_panel_rect.right - 7, marks_panel_rect.y + 8, 3, marks_panel_rect.h - 16)
                thumb_h = max(12, track.h * LIST_ROWS // len(panel_rows))
                thumb_y = track.y + (track.h - thumb_h) * marks_scroll // (len(panel_rows) - LIST_ROWS)
                pygame.draw.rect(screen, T["grid"], track, border_radius=2)
                pygame.draw.rect(screen, T["chip_edge"], (track.x, thumb_y, track.w, thumb_h), border_radius=2)
            for row, (kind, idx) in enumerate(list_rows):
                ry = marks_panel_rect.y + 6 + row * row_h
                x0 = marks_panel_rect.x + 12
                row_rect = pygame.Rect(marks_panel_rect.x + 4, ry - 1, marks_panel_rect.w - 14, row_h - 2)
                mark_row_rects.append((row_rect, (kind, idx)))
                in_bar = (kind == "mark" and idx == selected_mark) or (
                    kind == "cage" and selected_mark is None and len(sel_areas) == 1 and sel_areas[0][0] == idx)
                if in_bar or row_rect.collidepoint(mouse):
                    pygame.draw.rect(screen, T["key_hover"] if in_bar else T["chip"], row_rect, border_radius=8)
                if kind == "cage":
                    cs, ccls, _ = cages[idx]
                    filled = [board[r][c] for r, c in ccls if board[r][c]]
                    head = font_combo_head.render(f"{cs - sum(filled)} =", True, T["text"])
                    screen.blit(head, (x0, ry + 3))
                    draw_chips(idx, cs, ccls, x0 + head.get_width() + 10, ry + 5, marks_panel_rect.right - 12, 1)
                    continue
                mi = idx
                uc = user_cages[mi]
                trash = pygame.Rect(marks_panel_rect.right - 42, ry + 4, 30, 30)
                mark_trash_rects.append((trash, mi))
                tc = T["digit_bad"] if trash.collidepoint(mouse) else T["text"]
                pygame.draw.rect(screen, tc, (trash.x + 8, trash.y + 10, 14, 16), 2, border_radius=3)
                pygame.draw.line(screen, tc, (trash.x + 5, trash.y + 8), (trash.x + 24, trash.y + 8), 2)
                pygame.draw.line(screen, tc, (trash.x + 12, trash.y + 5), (trash.x + 17, trash.y + 5), 2)
                pygame.draw.line(screen, tc, (trash.x + 13, trash.y + 14), (trash.x + 13, trash.y + 22), 1)
                pygame.draw.line(screen, tc, (trash.x + 17, trash.y + 14), (trash.x + 17, trash.y + 22), 1)
                if uc["sum"] is None:
                    t = font_info.render(f"{len(uc['cells'])} cells, no sum", True, T["muted"])
                    screen.blit(t, (x0, ry + 11))
                    continue
                head = font_combo_head.render(f"{uc['sum']} =", True, uc["color"])
                screen.blit(head, (x0, ry + 3))
                if not uc["distinct"]:
                    t = font_info.render("cells don't all see each other: digits can repeat", True, T["muted"])
                    screen.blit(t, (x0 + head.get_width() + 10, ry + 11))
                    continue
                draw_chips(mark_key(uc), uc["sum"], uc["cells"], x0 + head.get_width() + 10, ry + 5, trash.x - 8, 1)

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
            for hr, hc in hint_panel["cells"]:
                x, y = cell_xy(hr, hc)
                pygame.draw.rect(screen, T["hl"], (x + 2, y + 2, CELL_SIZE - 4, CELL_SIZE - 4), 3, border_radius=8)
            panel = pygame.Rect(GRID_OFFSET_X - 8, MSG_Y - 4, GRID_SIZE + 16, WINDOW_H - MSG_Y - 4)
            pygame.draw.rect(screen, T["tip"], panel, border_radius=10)
            pygame.draw.rect(screen, T["hl"], panel, 1, border_radius=10)
            title = font_top.render(f"Hint: {hint_panel['title']}", True, T["hl"])
            screen.blit(title, (panel.x + 12, panel.y + 8))
            wrapped = wrap_text(hint_panel["lines"], font_tooltip, panel.w - 28)
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
                and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE \
                and not (marks_panel_rect is not None and marks_panel_rect.collidepoint(mouse)):
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
                draw_tooltip(screen, tip_lines, bold_rows, (mx, my), (font_tooltip, font_tooltip_bold),
                             (WINDOW_W, WINDOW_H))

        if screen is not window:
            pygame.transform.smoothscale(screen, window.get_size(), window)
        pygame.display.flip()
        clock.tick(60)

    save_progress()
    pygame.quit()


def _dpi_aware():
    """Draw in real screen pixels on Windows. Without this, a 125% display
    stretches the window as a bitmap and the text goes soft."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per monitor
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


def main():
    _dpi_aware()
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
        play_mode(cages, solution, save_path=os.path.join(SAVES_DIR, filename))
        return

    cages, solution, steps = load_and_solve(filename)
    if not steps:
        print("No solution steps found.")
        return

    if print_mode:
        print_steps(cages, solution, steps)
        return

    # --- Pygame setup: step-through solver in the same dark style as play mode ---
    pygame.init()
    T = THEME
    CELL_SIZE = 60
    GRID_SIZE = CELL_SIZE * 9
    GRID_OFFSET_X = 20
    GRID_OFFSET_Y = 52
    PANEL_X = GRID_OFFSET_X + GRID_SIZE + 20
    PANEL_W = 380
    WINDOW_W = PANEL_X + PANEL_W + 20
    WINDOW_H = GRID_OFFSET_Y + GRID_SIZE + 44

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(f"Killer Sudoku — {filename}")

    font_num = pygame.font.SysFont("segoeui", 30, bold=True)
    font_pencil = pygame.font.SysFont("segoeui", 12)
    font_cage_sum = pygame.font.SysFont("segoeui", 12, bold=True)
    font_top = pygame.font.SysFont("segoeui", 16, bold=True)
    font_head = pygame.font.SysFont("segoeui", 17, bold=True)
    font_explain = pygame.font.SysFont("segoeui", 14)
    font_controls = pygame.font.SysFont("segoeui", 12)
    font_tooltip = pygame.font.SysFont("segoeui", 14)
    font_tooltip_bold = pygame.font.SysFont("segoeui", 14, bold=True)

    cell_cage_map = build_cell_cage_map(cages)
    caged_cells = set(cell_cage_map)

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

    def step_forward():
        nonlocal current_step, highlight_cell, candidates_dirty, explain_scroll
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
                        step_forward()
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
            step_forward()
            last_auto_time = now
            if current_step >= len(steps) - 1:
                auto_play = False

        # Recompute candidates when board changes
        if candidates_dirty:
            prev_live_candidates = dict(live_candidates)
            live_candidates = _compute_candidates(board, cages)
            candidates_dirty = False

        # --- Draw ---
        screen.fill(T["bg"])
        cell_bg = {}
        for r in range(9):
            for c in range(9):
                x = GRID_OFFSET_X + c * CELL_SIZE
                y = GRID_OFFSET_Y + r * CELL_SIZE
                bg = T["cell"] if (r, c) in caged_cells else T["uncaged"]
                cell_bg[(r, c)] = bg
                pygame.draw.rect(screen, bg, (x, y, CELL_SIZE, CELL_SIZE))
        draw_grid_lines(screen, GRID_OFFSET_X, GRID_OFFSET_Y, CELL_SIZE)
        draw_cages(screen, cages, cell_bg, font_cage_sum, GRID_OFFSET_X, GRID_OFFSET_Y, CELL_SIZE)

        # Candidates this step removed are shown struck on red; the source is the
        # step's own snapshot, or the live grid for steps without one
        step_cands, prev_cands = {}, {}
        if current_step >= 0:
            s = steps[current_step]
            step_cands = s.get("candidates") or live_candidates
            if current_step > 0:
                prev_cands = steps[current_step - 1].get("candidates") or prev_live_candidates
        sub = (CELL_SIZE - 16) / 3
        for r in range(9):
            for c in range(9):
                x = GRID_OFFSET_X + c * CELL_SIZE
                y = GRID_OFFSET_Y + r * CELL_SIZE
                val = board[r][c]
                if val:
                    txt = font_num.render(str(val), True, T["digit"])
                    screen.blit(txt, (x + (CELL_SIZE - txt.get_width()) // 2,
                                      y + (CELL_SIZE - txt.get_height()) // 2 + 2))
                    if highlight_cell == (r, c):
                        pygame.draw.rect(screen, T["hl"], (x + 4, y + 4, CELL_SIZE - 8, CELL_SIZE - 8), 3,
                                         border_radius=8)
                    continue
                if current_step < 0:
                    continue
                key = f"{_COL[c]}{r+1}"
                cur = set(step_cands.get(key, []))
                removed = set(prev_cands.get(key, [])) - cur
                for n in sorted(cur | removed):
                    cx = x + 8 + ((n - 1) % 3 + 0.5) * sub
                    cy = y + 13 + ((n - 1) // 3 + 0.5) * sub
                    if n in removed:
                        pygame.draw.rect(screen, T["removed_bg"], (cx - sub / 2 + 1, cy - sub / 2 + 1, sub - 2, sub - 2),
                                         border_radius=3)
                    ptxt = font_pencil.render(str(n), True, T["pencil_bad"] if n in removed else T["pencil"])
                    screen.blit(ptxt, (cx - ptxt.get_width() / 2, cy - ptxt.get_height() / 2))

        # --- Top bar: step counter and auto-play ---
        if current_step >= 0:
            stype = steps[current_step].get("type", "placement")
            label = {"info": "Info", "elimination": "Elimination", "placement": "Placement"}.get(stype, "Step")
            colour = {"info": T["info"], "elimination": T["elim"], "placement": T["place"]}.get(stype, T["text"])
            top = font_top.render(f"Step {current_step + 1} / {len(steps)}   {label}", True, colour)
        else:
            top = font_top.render(f"{len(steps)} steps   Press SPACE to start", True, T["muted"])
        screen.blit(top, (GRID_OFFSET_X, (GRID_OFFSET_Y - top.get_height()) // 2))
        auto = font_controls.render(f"Auto {'ON' if auto_play else 'off'}  {auto_delay} ms", True,
                                    T["place"] if auto_play else T["muted"])
        screen.blit(auto, (WINDOW_W - 20 - auto.get_width(), (GRID_OFFSET_Y - auto.get_height()) // 2))

        # --- Explanation panel (right) ---
        panel = pygame.Rect(PANEL_X, GRID_OFFSET_Y, PANEL_W, GRID_SIZE)
        pygame.draw.rect(screen, T["tip"], panel, border_radius=10)
        pygame.draw.rect(screen, T["tip_edge"], panel, 1, border_radius=10)
        if current_step >= 0:
            s = steps[current_step]
            if s.get("type") == "placement":
                rc = s.get("cell", (0, 0))
                head = f"{_COL[rc[1]]}{rc[0]+1} = {s['value']}"
                sub_head = s.get("strategy") or s.get("text", "")
            else:
                head, sub_head = s.get("text", ""), ""
            lines = wrap_text([head], font_head, PANEL_W - 28)
            for j, line in enumerate(lines):
                screen.blit(font_head.render(line, True, T["text"]), (panel.x + 14, panel.y + 12 + j * 22))
            ey = panel.y + 18 + len(lines) * 22
            if sub_head:
                t = font_explain.render(sub_head, True, T["muted"])
                screen.blit(t, (panel.x + 14, ey - 4))
                ey += 20
            wrapped = wrap_text((s.get("explanation") or "").split("\n"), font_explain, PANEL_W - 28)
            max_visible = (panel.bottom - ey - 30) // 18
            explain_scroll = min(explain_scroll, max(0, len(wrapped) - max_visible))
            for line in wrapped[explain_scroll:explain_scroll + max_visible]:
                screen.blit(font_explain.render(line, True, T["text"]), (panel.x + 14, ey))
                ey += 18
            if len(wrapped) > max_visible:
                more = font_controls.render(
                    f"lines {explain_scroll + 1}-{min(explain_scroll + max_visible, len(wrapped))} of {len(wrapped)}"
                    "   UP/DOWN or wheel to scroll", True, T["muted"])
                screen.blit(more, (panel.x + 14, panel.bottom - 22))
        else:
            for j, line in enumerate(["Step through the solver's reasoning:",
                                      "each placement, and each elimination",
                                      "that made one possible.",
                                      "",
                                      "Removed candidates show struck on red."]):
                screen.blit(font_explain.render(line, True, T["muted"]), (panel.x + 14, panel.y + 14 + j * 20))

        controls = font_controls.render(
            "SPACE / -> next   <- back   UP/DOWN scroll   A auto   +/- speed   R reset   Q quit", True, T["muted"])
        screen.blit(controls, (GRID_OFFSET_X, WINDOW_H - 26))

        # --- Cage tooltip on hover ---
        mx, my = pygame.mouse.get_pos()
        grid_r = (my - GRID_OFFSET_Y) // CELL_SIZE
        grid_c = (mx - GRID_OFFSET_X) // CELL_SIZE
        if 0 <= grid_r < 9 and 0 <= grid_c < 9 and GRID_OFFSET_X <= mx < GRID_OFFSET_X + GRID_SIZE \
                and GRID_OFFSET_Y <= my < GRID_OFFSET_Y + GRID_SIZE:
            cage_idx = cell_cage_map.get((grid_r, grid_c))
            if cage_idx is not None:
                cage_sum, cage_cells, _ = cages[cage_idx]
                tip_cands = (steps[current_step].get("candidates") or live_candidates) if current_step >= 0 else None
                combos = _cage_combos(board, cage_sum, cage_cells, candidates=tip_cands)
                filled = [(r, c) for r, c in cage_cells if board[r][c] != 0]
                empty = [(r, c) for r, c in cage_cells if board[r][c] == 0]
                tip_lines = [f"Cage: sum = {cage_sum}, {len(cage_cells)} cells"]
                if filled:
                    tip_lines.append(f"Filled: {' + '.join(str(board[r][c]) for r, c in filled)}"
                                     f" = {sum(board[r][c] for r, c in filled)}")
                if empty:
                    remaining = cage_sum - sum(board[r][c] for r, c in filled)
                    tip_lines.append(f"Need: {remaining} in {len(empty)} cell{'s' if len(empty) > 1 else ''}")
                    if combos:
                        line = "Combos: "
                        for cs in ["{" + ",".join(str(x) for x in c) + "}" for c in combos]:
                            if len(line) + len(cs) > 45:
                                tip_lines.append(line)
                                line = "        " + cs + " "
                            else:
                                line += cs + " "
                        tip_lines.append(line)
                        tip_lines.append(f"({len(combos)} possible)")
                    else:
                        tip_lines.append("No valid combos!")
                else:
                    tip_lines.append("(complete)")
                draw_tooltip(screen, tip_lines, {0}, (mx, my), (font_tooltip, font_tooltip_bold), (WINDOW_W, WINDOW_H))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
