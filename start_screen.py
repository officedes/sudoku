"""Start screen: pick a level, then a puzzle (or carry on with the last game).

    choose() -> "puzzle_042.json" | None

Levels come from killer.solver.required_level, which solves each puzzle up to
four times, so they are cached in levels.json keyed by a hash of the
cages. Missing ones are rated in worker processes while the screen is up -
processes, not threads, because the solver keeps module-level caches that a
game's hints use too.
"""

import concurrent.futures
import contextlib
import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time

import pygame

from killer.solver import ADVANCED_STEP_PREFIXES, LEVEL_NAMES, required_level, solve_and_explain
from main import DEFAULT_WORKERS, PUZZLES_DIR, load_puzzle
from visualizer import SAVES_DIR, THEME

# Beside puzzles/, not in it: everything else reads every .json there as a puzzle
LEVELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "levels.json")
LEVEL_BLURBS = {
    1: "Cage sums, the rule of 45 and singles - no pencil marks needed.",
    2: "Pencil marks: pairs, pointing, box-line and cage combinations.",
    3: "Killer logic: innies/outies over several houses, killer subsets, cage pairs.",
    4: "Needs 'what if' reasoning: some candidate only fails after following it through.",
}

W, H = 580, 936  # play mode's design size, so the window doesn't jump between screens
PAD = 20
TAB_Y, TAB_H = 196, 92
TILE_Y0 = 352
TILE_W, TILE_H, TILE_GAP, COLS = 127, 76, 10, 4
LIST_BOTTOM = H - 96
BTN_Y, BTN_H = H - 60, 40
ROOT = os.path.dirname(os.path.abspath(__file__))


def _cages_hash(cages):
    canon = sorted((s, sorted(map(list, cells))) for s, cells, _ in cages)
    return hashlib.sha1(json.dumps(canon).encode()).hexdigest()[:16]


def _rate(cages):
    """Level, plus the explained solve's advanced and total elimination steps -
    the order within a level (levels 1-2 never take an advanced step).
    Without the strategies' explanation printing."""
    with contextlib.redirect_stdout(io.StringIO()):
        level = required_level(cages)
        if not level:
            return {"level": None, "advanced": None, "eliminations": None}
        _, steps = solve_and_explain(cages)
    elims = [st["text"] for st in steps if st["type"] == "elimination"]
    return {"level": level, "advanced": sum(t.startswith(ADVANCED_STEP_PREFIXES) for t in elims),
            "eliminations": len(elims)}


def _puzzle_files():
    return sorted(f for f in os.listdir(PUZZLES_DIR) if f.endswith(".json"))


def _load_levels():
    try:
        with open(LEVELS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_levels(levels):
    tmp = LEVELS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(levels.items())), f, indent=1)
        f.write("\n")
    os.replace(tmp, LEVELS_PATH)


class _Rater:
    """Rates puzzles missing from levels.json in the background, across games."""

    def __init__(self):
        self.levels = _load_levels()
        self.pool = None
        self.pending = {}  # future -> (name, hash)

    def start(self, puzzles):
        stale = [(name, h, cages) for name, (cages, h) in puzzles.items()
                 if not self._current(name, h)
                 and name not in {n for n, _ in self.pending.values()}]
        if not stale:
            return
        if self.pool is None:
            self.pool = concurrent.futures.ProcessPoolExecutor(DEFAULT_WORKERS)
        for name, h, cages in stale:
            self.pending[self.pool.submit(_rate, cages)] = (name, h)

    def harvest(self):
        done = [f for f in self.pending if f.done()]
        for f in done:
            name, h = self.pending.pop(f)
            try:
                rating = f.result()
            except Exception:  # a crashed worker leaves the puzzle unrated, not the menu dead
                continue
            self.levels[name[:-5]] = {"hash": h, **rating}
        if done:
            _save_levels(self.levels)
        return bool(done)

    def _current(self, name, h):
        entry = self.levels.get(name[:-5])
        return entry if entry and entry.get("hash") == h and "eliminations" in entry else None

    def level(self, name, h):
        entry = self._current(name, h)
        return entry["level"] if entry else None

    def hardness(self, name, h):
        entry = self._current(name, h)
        return (entry["advanced"] or 0, entry["eliminations"] or 0) if entry else (0, 0)

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.pool = None
            self.pending.clear()


_RATER = _Rater()


def _spawn_generator(level, log):
    """main.py's generator as its own process: it runs its own worker pool, and
    a game can be played meanwhile. Left running if the app closes - it only
    saves its puzzle."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.Popen([sys.executable, os.path.join(ROOT, "main.py"), "generate", "--level", str(level)],
                            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)


class _Generator:
    """One background puzzle generation at a time, kept across games."""

    def __init__(self):
        self.proc = self.log = None
        self.level = self.started = None
        self.result = None  # (level, file name or None) of the last finished run

    def start(self, level):
        if self.proc:
            return
        self.log = tempfile.TemporaryFile()  # a file, not a pipe: the output can't fill up and stall it
        self.level, self.started, self.result = level, time.time(), None
        self.proc = _spawn_generator(level, self.log)

    def poll(self):
        """True once when the running generation has just finished."""
        if not self.proc or self.proc.poll() is None:
            return False
        self.log.seek(0)
        m = re.search(r"Saved to .*?(puzzle_\d+\.json)", self.log.read().decode("utf-8", "replace"))
        self.log.close()
        self.result = (self.level, m.group(1) if m else None)
        self.proc = self.log = None
        return True


_GENERATOR = _Generator()


def _progress():
    """(solved: name -> best seconds, in_progress: name -> (filled, elapsed, mtime))."""
    solved = {}
    try:
        with open(os.path.join(SAVES_DIR, "solved.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                name = e["puzzle"] + ".json"
                solved[name] = min(solved.get(name, e["seconds"]), e["seconds"])
    except OSError:
        pass
    in_progress = {}
    if os.path.isdir(SAVES_DIR):
        for f in os.listdir(SAVES_DIR):
            path = os.path.join(SAVES_DIR, f)
            if not (f.startswith("puzzle_") and f.endswith(".json")):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    state = json.load(fh)
            except (OSError, ValueError):
                continue
            filled = sum(1 for row in state.get("board", []) for v in row if v)
            in_progress[f] = (filled, state.get("elapsed", 0), os.path.getmtime(path))
    return solved, in_progress


def _clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}" if seconds >= 3600 \
        else f"{seconds // 60}:{seconds % 60:02d}"


def _thumbnail(cages, size):
    """Tiny cage map: box lines plus a stroke wherever two cells sit in different cages."""
    T = THEME
    surf = pygame.Surface((size, size))
    surf.fill(T["cell"])
    cage_of = {tuple(c): i for i, (_, cells, _) in enumerate(cages) for c in cells}
    step = size / 9
    for r in range(9):
        for c in range(9):
            if (r, c) not in cage_of:
                pygame.draw.rect(surf, T["uncaged"], (round(c * step), round(r * step), round(step), round(step)))
            if c < 8 and cage_of.get((r, c)) != cage_of.get((r, c + 1)):
                x = round((c + 1) * step)
                pygame.draw.line(surf, T["pencil"], (x, round(r * step)), (x, round((r + 1) * step)))
            if r < 8 and cage_of.get((r, c)) != cage_of.get((r + 1, c)):
                y = round((r + 1) * step)
                pygame.draw.line(surf, T["pencil"], (round(c * step), y), (round((c + 1) * step), y))
    for k in (3, 6):
        p = round(k * step)
        pygame.draw.line(surf, T["chip_edge"], (p, 0), (p, size))
        pygame.draw.line(surf, T["chip_edge"], (0, p), (size, p))
    pygame.draw.rect(surf, T["chip_edge"], (0, 0, size, size), 1)
    return surf


def _check(screen, color, x, cy):
    """A tick: segoeui has no glyph for one."""
    pygame.draw.lines(screen, color, False, [(x, cy), (x + 4, cy + 4), (x + 11, cy - 4)], 2)


def _text(screen, font, text, color, pos, anchor="topleft"):
    img = font.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    screen.blit(img, rect)
    return rect


def choose():
    """Show the start screen; return the chosen puzzle's file name, or None to quit."""
    T = THEME
    pygame.init()
    scale = 1.0
    if pygame.display.get_driver() != "dummy":
        desk_w, desk_h = pygame.display.get_desktop_sizes()[0]
        scale = min(1.0, (desk_h - 48 - 32 - 8) / H)  # same taskbar + title bar allowance as play mode
        if scale < 1.0:
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{(desk_w - round(W * scale)) // 2},32"
    window = pygame.display.set_mode((round(W * scale), round(H * scale)))
    screen = window if scale == 1.0 else pygame.Surface((W, H))
    pygame.display.set_caption("Killer Sudoku")

    font_title = pygame.font.SysFont("segoeui", 34, bold=True)
    font_sub = pygame.font.SysFont("segoeui", 15)
    font_tab_num = pygame.font.SysFont("segoeui", 30, bold=True)
    font_tab = pygame.font.SysFont("segoeui", 13, bold=True)
    font_small = pygame.font.SysFont("segoeui", 13)
    font_tile = pygame.font.SysFont("segoeui", 20, bold=True)
    font_btn = pygame.font.SysFont("segoeui", 16, bold=True)

    puzzles = {}

    def scan():
        for name in _puzzle_files():
            if name in puzzles:
                continue
            try:
                cages, _ = load_puzzle(name)
            except (OSError, ValueError, KeyError):
                continue
            puzzles[name] = (cages, _cages_hash(cages))
        _RATER.start(puzzles)

    scan()
    thumbs = {}
    solved, in_progress = _progress()

    def by_level():
        groups = {lv: [] for lv in LEVEL_NAMES}
        for name, (_, h) in puzzles.items():
            lv = _RATER.level(name, h)
            if lv in groups:
                groups[lv].append(name)
        for lv in groups:  # easiest first
            groups[lv].sort(key=lambda n: (_RATER.hardness(n, puzzles[n][1]), n))
        return groups

    groups = by_level()
    level = next((lv for lv in LEVEL_NAMES if any(n not in solved for n in groups[lv])), 1)
    scroll = 0
    last = max(in_progress, key=lambda n: in_progress[n][2]) if in_progress else None
    if last not in puzzles:
        last = None

    def to_design(pos):
        return (pos[0] / scale, pos[1] / scale) if scale != 1.0 else pos

    def tile_rect(i):
        row, col = divmod(i, COLS)
        return pygame.Rect(PAD + col * (TILE_W + TILE_GAP), TILE_Y0 + row * (TILE_H + TILE_GAP) - scroll,
                           TILE_W, TILE_H)

    def tab_rect(lv):
        w = (W - 2 * PAD - 3 * 8) // 4
        return pygame.Rect(PAD + (lv - 1) * (w + 8), TAB_Y, w, TAB_H)

    continue_rect = pygame.Rect(PAD, 112, W - 2 * PAD, 64)
    random_rect = pygame.Rect(PAD, BTN_Y, 220, BTN_H)
    new_rect = pygame.Rect(random_rect.right + 12, BTN_Y, W - PAD - random_rect.right - 12, BTN_H)

    def random_pick():
        pool = [n for n in groups[level] if n not in solved] or groups[level]
        return random.choice(pool) if pool else None

    clock = pygame.time.Clock()
    while True:
        if _GENERATOR.poll() and _GENERATOR.result[1]:
            scan()
        if _RATER.harvest():
            groups = by_level()
        fresh = _GENERATOR.result[1] if _GENERATOR.result else None
        names = groups[level]
        rows = (len(names) + COLS - 1) // COLS
        max_scroll = max(0, TILE_Y0 + rows * (TILE_H + TILE_GAP) - LIST_BOTTOM)
        mouse = to_design(pygame.mouse.get_pos())

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _RATER.close()
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    _RATER.close()
                    return None
                if event.unicode in ("1", "2", "3", "4"):
                    level, scroll = int(event.unicode), 0
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    pick = random_pick()
                    if pick:
                        return pick
            elif event.type == pygame.MOUSEWHEEL:
                scroll = min(max_scroll, max(0, scroll - event.y * 40))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = to_design(event.pos)
                if last and continue_rect.collidepoint(pos):
                    return last
                for lv in LEVEL_NAMES:
                    if tab_rect(lv).collidepoint(pos):
                        level, scroll = lv, 0
                if random_rect.collidepoint(pos):
                    pick = random_pick()
                    if pick:
                        return pick
                if new_rect.collidepoint(pos):
                    _GENERATOR.start(level)
                if TILE_Y0 <= pos[1] < LIST_BOTTOM:
                    for i, name in enumerate(names):
                        if tile_rect(i).collidepoint(pos):
                            return name

        screen.fill(T["bg"])
        _text(screen, font_title, "Killer Sudoku", T["label"], (PAD, 26))
        rated = sum(len(g) for g in groups.values())
        sub = f"{len(puzzles)} puzzles  ·  {sum(1 for n in puzzles if n in solved)} solved"
        if in_progress:
            sub += f"  ·  {len(in_progress)} in progress"
        _text(screen, font_sub, sub, T["muted"], (PAD, 74))

        if last:
            hover = continue_rect.collidepoint(mouse)
            pygame.draw.rect(screen, T["btn_hover"] if hover else T["btn"], continue_rect, border_radius=10)
            pygame.draw.rect(screen, T["btn_active"], continue_rect, 2, border_radius=10)
            filled, elapsed, _ = in_progress[last]
            lv = _RATER.level(last, puzzles[last][1])
            _text(screen, font_btn, f"Continue  {last[7:-5]}", T["label"], (continue_rect.x + 16, continue_rect.y + 10))
            detail = f"{filled}/81 filled  ·  {_clock(elapsed)}" + (f"  ·  level {lv}" if lv else "")
            _text(screen, font_small, detail, T["muted"], (continue_rect.x + 16, continue_rect.y + 36))
            cx, cy = continue_rect.right - 26, continue_rect.centery
            pygame.draw.polygon(screen, T["place"], [(cx, cy - 9), (cx, cy + 9), (cx + 14, cy)])
        else:
            _text(screen, font_small, "Pick a level, then a puzzle. Your games save as you play.",
                  T["muted"], (PAD, 130))

        for lv, title in LEVEL_NAMES.items():
            rect = tab_rect(lv)
            sel = lv == level
            bg = T["selected"] if sel else (T["btn_hover"] if rect.collidepoint(mouse) else T["chip"])
            pygame.draw.rect(screen, bg, rect, border_radius=10)
            pygame.draw.rect(screen, T["selected_edge"] if sel else T["chip_edge"], rect, 2 if sel else 1,
                             border_radius=10)
            _text(screen, font_tab_num, str(lv), T["label"], (rect.x + 12, rect.y + 4))
            done = sum(1 for n in groups[lv] if n in solved)
            _text(screen, font_small, f"{done}/{len(groups[lv])}", T["place"] if done else T["muted"],
                  (rect.right - 10, rect.y + 14), "topright")
            words, line, y = title.split(), "", rect.y + 46
            for word in words:  # names like "Candidate elimination" wrap onto two lines
                trial = f"{line} {word}".strip()
                if font_tab.size(trial)[0] > rect.w - 20 and line:
                    _text(screen, font_tab, line, T["text"], (rect.x + 12, y))
                    line, y = word, y + 17
                else:
                    line = trial
            _text(screen, font_tab, line, T["text"], (rect.x + 12, y))
        _text(screen, font_small, LEVEL_BLURBS[level] + "  Easiest first.", T["muted"], (PAD, TAB_Y + TAB_H + 12))

        clip = screen.get_clip()
        screen.set_clip(pygame.Rect(0, TILE_Y0 - 6, W, LIST_BOTTOM - TILE_Y0 + 6))
        if not names:
            msg = "Rating puzzles..." if _RATER.pending else "No puzzles at this level yet."
            _text(screen, font_sub, msg, T["muted"], (W // 2, TILE_Y0 + 30), "midtop")
        for i, name in enumerate(names):
            rect = tile_rect(i)
            if rect.bottom < TILE_Y0 - 6 or rect.top > LIST_BOTTOM:
                continue
            hover = rect.collidepoint(mouse) and TILE_Y0 <= mouse[1] < LIST_BOTTOM
            pygame.draw.rect(screen, T["btn_hover"] if hover else T["btn"], rect, border_radius=8)
            if name in solved:
                edge, status, color = T["place"], _clock(solved[name]), T["place"]
            elif name in in_progress:
                edge, status, color = T["hl"], f"{in_progress[name][0]}/81", T["hl"]
            else:
                edge, status, color = T["chip_edge"], "new", T["muted"]
            if name == fresh and name not in solved and name not in in_progress:
                edge, status, color = T["info"], "fresh", T["info"]
            pygame.draw.rect(screen, edge, rect, 2 if hover or name == fresh else 1, border_radius=8)
            if name not in thumbs:
                thumbs[name] = _thumbnail(puzzles[name][0], 58)
            screen.blit(thumbs[name], (rect.x + 9, rect.y + 9))
            label = name[7:-5] if name.startswith("puzzle_") else "Ex"
            _text(screen, font_tile, label, T["label"], (rect.right - 10, rect.y + 8), "topright")
            if name in solved:
                _check(screen, color, rect.right - 22, rect.y + 44)
            _text(screen, font_small, status, color, (rect.right - 10, rect.bottom - 7), "bottomright")
        screen.set_clip(clip)
        if max_scroll:
            track = LIST_BOTTOM - TILE_Y0
            bar_h = max(30, track * track // (track + max_scroll))
            bar_y = TILE_Y0 + (track - bar_h) * scroll // max_scroll
            pygame.draw.rect(screen, T["chip_edge"], (W - 8, bar_y, 4, bar_h), border_radius=2)

        hover = random_rect.collidepoint(mouse)
        pygame.draw.rect(screen, T["btn_hover"] if hover else T["btn"], random_rect, border_radius=8)
        pygame.draw.rect(screen, T["chip_edge"], random_rect, 1, border_radius=8)
        _text(screen, font_btn, "Random unsolved", T["label"], random_rect.center, "center")
        running = _GENERATOR.proc is not None
        hover = new_rect.collidepoint(mouse) and not running
        pygame.draw.rect(screen, T["btn_hover"] if hover else T["btn"], new_rect, border_radius=8)
        pygame.draw.rect(screen, T["hl"] if running else T["chip_edge"], new_rect, 1, border_radius=8)
        label = (f"Generating level {_GENERATOR.level}...  {_clock(time.time() - _GENERATOR.started)}"
                 if running else f"New level {level} puzzle")
        _text(screen, font_btn, label, T["hl"] if running else T["label"], new_rect.center, "center")

        if _RATER.pending:
            status = f"Rating {len(_RATER.pending)} puzzle{'s' if len(_RATER.pending) != 1 else ''}..."
        elif _GENERATOR.result and not running:
            lv, made = _GENERATOR.result
            status = (f"New puzzle {made[7:-5]} added to level {lv}" if made
                      else f"Couldn't generate a level {lv} puzzle - try again")
        else:
            status = f"1-4 level  ·  Enter random  ·  {rated} rated"
        _text(screen, font_small, status, T["muted"], (W - PAD, BTN_Y - 12), "midright")

        if screen is not window:
            pygame.transform.smoothscale(screen, window.get_size(), window)
        pygame.display.flip()
        clock.tick(30)
