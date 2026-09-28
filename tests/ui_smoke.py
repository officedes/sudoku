"""Headless run of play mode and the step-through solver with scripted input.

Fails on any exception; saves screenshots to tests/output/ to eyeball.
The layout numbers below mirror play_mode's portrait layout.

    python tests/ui_smoke.py
"""

import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"

from common import OUTPUT_DIR, ROOT  # noqa: E402

import pygame  # noqa: E402

os.chdir(ROOT)
import visualizer  # noqa: E402
from main import load_puzzle  # noqa: E402

CELL, GX = 60, 20
GY = 44 + 4 + 62 + 6
TOOLS_Y = GY + 540 + 8 + 26
PAD_Y = TOOLS_Y + 44
KEY_H = 46


def cell_pt(r, c):
    return GX + c * CELL + 30, GY + r * CELL + 30


def pad_pt(n, block):
    """Centre of digit n on the Digits (0) or Candidates (1) keypad."""
    block_w = (540 - 16) // 2
    key_w = (block_w - 12) // 3
    bx = GX + block * (block_w + 16)
    return bx + ((n - 1) % 3) * (key_w + 6) + key_w // 2, PAD_Y + ((n - 1) // 3) * (KEY_H + 6) + KEY_H // 2


def btn_pt(name, with_del=False):
    pygame.font.init()  # each app run ends with pygame.quit()
    font = pygame.font.SysFont("segoeui", 13, bold=True)
    names = ["Undo", "Pencil", "Hint", "Check", "Fill", "Fill All", "Mark"] \
        + (["Del Mark"] if with_del else []) + ["Reset"]
    widths = [font.size(b)[0] + 18 for b in names]
    gap = (540 - sum(widths)) / (len(names) - 1)
    x = GX
    for b, w in zip(names, widths):
        if b == name:
            return int(x) + w // 2, TOOLS_Y + 15
        x += w + gap
    raise ValueError(name)


def click(pt, button=1, shift=False):
    return [("mods", shift), pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pt, button=button)]


def key(k, uni=""):
    return [pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=uni, scancode=0)]


def run(script, start, mouse=(-100, -100)):
    """Feed script[frame] events to the app started by start(); 'shot:name' saves a screenshot."""
    frame, mods = [0], [0]
    real_get, real_mods, real_mouse = pygame.event.get, pygame.key.get_mods, pygame.mouse.get_pos

    def fake_get(*_a, **_k):
        frame[0] += 1
        out = []
        for item in script.get(frame[0], []):
            if isinstance(item, tuple):
                mods[0] = pygame.KMOD_SHIFT if item[1] else 0
            elif isinstance(item, str):
                pygame.image.save(pygame.display.get_surface(), os.path.join(OUTPUT_DIR, item[5:] + ".png"))
            else:
                out.append(item)
        return real_get() + out

    last = max(script) + 2
    script.setdefault(last, []).append(pygame.event.Event(pygame.QUIT))
    pygame.event.get, pygame.key.get_mods, pygame.mouse.get_pos = fake_get, (lambda: mods[0]), (lambda: mouse)
    try:
        start()
    finally:
        pygame.event.get, pygame.key.get_mods, pygame.mouse.get_pos = real_get, real_mods, real_mouse


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pygame.font.init()
    cages, sol = load_puzzle("puzzle_032.json")
    d = sol[4][4]

    run({3: click(cell_pt(0, 0)),
         6: click(pad_pt(1, 1)), 9: click(pad_pt(4, 1)), 12: click(pad_pt(sol[0][0], 1)),
         15: ["shot:play_candidates"],
         18: click(pad_pt(sol[0][0], 0)),
         24: click(cell_pt(3, 3)), 26: click(cell_pt(3, 4), shift=True), 28: click(cell_pt(4, 4), shift=True),
         30: click(btn_pt("Mark")),
         32: key(pygame.K_1, "1"), 33: key(pygame.K_5, "5"), 34: key(pygame.K_RETURN),
         38: click(cell_pt(3, 3)),
         41: ["shot:play_mark_selected"],
         43: click(btn_pt("Fill", with_del=True)),
         48: click(cell_pt(6, 6), button=3),
         51: ["shot:play_cage_selected"]},
        lambda: visualizer.play_mode(cages, sol))

    first_chip = (GX + 104, 48 + 14)  # first chip right of the "15 =" heading
    run({3: click(cell_pt(3, 3)), 5: click(cell_pt(3, 4), shift=True), 7: click(cell_pt(4, 4), shift=True),
         9: click(btn_pt("Mark")), 11: key(pygame.K_1, "1"), 12: key(pygame.K_5, "5"), 13: key(pygame.K_RETURN),
         15: click(cell_pt(3, 3)),
         17: click(first_chip),
         20: ["shot:play_mark_combo_excluded"]},
        lambda: visualizer.play_mode(cages, sol))

    # The marks list: select a marked cell, open the list from the chevron, rule out a combo, delete the mark
    toggle = (GX + 17, 48 + 15)
    panel_row = 48 + 36 + 6
    run({3: click(cell_pt(3, 3)), 5: click(cell_pt(3, 4), shift=True), 7: click(cell_pt(4, 4), shift=True),
         9: click(btn_pt("Mark")), 11: key(pygame.K_1, "1"), 12: key(pygame.K_5, "5"), 13: key(pygame.K_RETURN),
         15: click(cell_pt(3, 3)), 17: click(toggle),
         19: click((GX + 12 + 60, panel_row + 18)),
         22: ["shot:play_marks_panel"],
         24: click((GX + 540 - 22, panel_row + 19)),
         27: ["shot:play_marks_deleted"]},
        lambda: visualizer.play_mode(cages, sol))

    run({3: click(btn_pt("Fill All")),
         6: click(cell_pt(4, 4)), 8: click(pad_pt(d, 0)),
         11: key(pygame.K_ESCAPE),
         13: click(pad_pt(d, 0)),
         16: ["shot:play_highlight"]},
        lambda: visualizer.play_mode(cages, sol))

    hard_cages, hard_sol = load_puzzle("puzzle_034.json")
    run({3: click(btn_pt("Hint")),
         10: click(btn_pt("Hint")), 12: key(pygame.K_SPACE), 14: click(btn_pt("Hint")),
         16: key(pygame.K_SPACE), 18: click(btn_pt("Hint")),
         21: ["shot:play_hint"]},
        lambda: visualizer.play_mode(hard_cages, hard_sol))

    script = {i: key(pygame.K_SPACE) for i in range(3, 43)}
    script[45] = ["shot:solver_view"]
    sys.argv = ["visualizer.py", "puzzle_026"]
    run(script, visualizer.main, mouse=(GX + 4 * CELL + 30, 52 + 4 * CELL + 30))

    shots = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png"))
    print(f"ui smoke: ok, screenshots in tests/output: {', '.join(shots)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
