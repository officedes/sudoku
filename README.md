# Killer Sudoku

A Killer Sudoku game, solver and puzzle generator in plain Python.

- **Play** puzzles in a desktop window: pencil marks, combination chips, hints
  that explain themselves, undo, save/resume, stats.
- **Solve** any Killer Sudoku by human-style logic only (no guessing) and
  show every step with the reasoning behind it.
- **Generate** new puzzles at a chosen difficulty level.

## Killer Sudoku in one paragraph

The usual Sudoku rules apply (each row, column and 3x3 box holds 1-9 once),
but the grid starts empty. Instead it is divided into **cages**: groups of
cells with a sum printed in the corner. The digits in a cage add up to that
sum and never repeat inside the cage. A 2-cell cage of 3 must be {1,2}; a
3-cell cage of 24 must be {7,8,9}. Since every row, column and box adds up to
45, comparing that with the cages inside it ("Rule of 45") pins down more
cells. The solver builds on these two ideas.

## Getting started

Needs Python 3.10+ and one package:

```
pip install -r requirements.txt
python visualizer.py
```

That opens the start screen: pick a level, then a puzzle. Your game saves
itself every few seconds and when you close the window, and it comes back the
next time you open the puzzle.

Other ways in:

```
python visualizer.py puzzle_001 --play    play one puzzle directly
python visualizer.py puzzle_001           watch the solver, step by step (Space = next, Left = back, A = auto)
python visualizer.py puzzle_001 --print   the same walkthrough as text in the terminal
python main.py --level 3                  generate a new level-3 puzzle into puzzles/
python main.py --list                     list the saved puzzles
python main.py --help                     every generator option
```

### Playing

| Do this | To |
|---|---|
| click a cell / drag / Shift-click | select one or more cells |
| right-click | select a whole cage |
| 1-9 or the keypad | place a digit (with several cells selected: pencil it in) |
| P or the Pencil button | switch between placing and pencilling |
| 0, Delete, Backspace or Erase | clear the selected cells |
| 1-9 with nothing selected | highlight that digit everywhere |
| Ctrl+Z or Undo | undo |
| Hint | the next logical step, explained in words, with an optional visual walkthrough |
| Check | show or hide the wrong digits in red |
| Fill / Fill All | pencil every possible digit into the selection / the whole grid |
| Mark | draw your own cage over the selected cells (for sums you worked out) |
| Reset | clears the board; click it twice within 4 s, so it can't happen by accident |

Click a combination chip in the bar above the grid to rule it out; the pencil
marks follow. When a row, column, box or cage has only one empty cell left,
the game fills it in for you.

## How the code is laid out

```
visualizer.py      the desktop app: play mode, the step-through solver view, hint wording
start_screen.py    the start screen: levels, puzzle tiles, stats, "new puzzle"
main.py            command line: generate, list and rate puzzles; load/save puzzle files
killer/            the engine, no UI code
  helpers.py         cell names (A1..I9), rows/columns/boxes, text formatting
  sudoku.py          candidates, cage combinations, the digit bitmasks
  strategies.py      every solving technique, one function each
  solver.py          runs the techniques in order, rates difficulty, records explanations
  generator.py       random solved grids, cage layouts, growing a puzzle to a level
puzzles/           the puzzle files (JSON)
levels.json        cached difficulty of each puzzle (rebuilt automatically when missing)
tests/             checks for the solver and a headless UI test
saves/             your games in progress and solve history (created on first play, not in git)
```

The dependency direction is one way: `killer/` knows nothing about the UI or
files; `main.py` uses `killer/`; `visualizer.py` and `start_screen.py` use both.

### Words used throughout the code

- **cell** - a `(row, col)` pair, both 0-8. On screen and in text it is
  named column letter + row number: `(0, 0)` is `A1`, `(4, 7)` is `H5`.
- **board** - a 9x9 list of lists; 0 means empty.
- **cage** - a tuple `(sum, [cells], color)`. The color is an ANSI code from
  the terminal days; the UI ignores it.
- **house** - a row, a column or a box (the 27 groups that must hold 1-9).
- **candidates** - the digits still possible in a cell, as a 9x9 grid of sets.
- **mask** - the same set packed into an int, digit `d` = bit `d`
  (`{1, 3}` is `0b1010`). The hot loops of the solver use masks because set
  operations on ints are much faster; `to_mask` / `mask_to_set` convert.
- **combo** - one set of distinct digits that makes a cage's sum, e.g. a
  3-cell 10 has combos {1,2,7}, {1,3,6}, {1,4,5}, {2,3,5}.

### The puzzle file

`puzzles/puzzle_001.json`:

```json
{
"cages": [
  [10, [[7, 0], [7, 1]], 41],
  ...
],
"solution": [
  [4, 3, 8, 7, 9, 1, 5, 2, 6],
  ...
]
}
```

Each cage is `[sum, [[row, col], ...], color]`. Some puzzles leave cells out
of every cage; those are plain Sudoku cells.

## How the solver works

The solver never guesses. It repeats one loop until the grid is full:
*try each technique, easiest first; as soon as one makes progress, start
again from the easiest*. Trying the easy ones first means every step is
explained with the simplest reason that works, and the hardest technique a
puzzle needed is its difficulty.

There are two kinds of technique (both in `killer/strategies.py`):

1. **`apply_*` functions place a digit.** They look at the board directly:
   a cage with one possible combo, the Rule of 45, a cell with one
   candidate left, a digit with one place left in a house, and so on. Each
   takes `(board, cages)`, writes at most one digit, prints why, and returns
   True if it placed something.
2. **`eliminate_*` functions only remove candidates.** They work on the
   candidate grid and chain together: pairs/triples, pointing, X-wing,
   innies/outies, killer subsets, ALS-XZ, ... none of them places anything,
   but together they shrink the candidates until a cell has only one left.
   `apply_candidate_elimination` is the driver that runs them and places
   the digit that falls out.

The order lives in `NAMED_STRATEGIES` at the top of `killer/solver.py`.

### Difficulty levels

Each level allows everything below it plus one more group of techniques:

| Level | Name | Adds |
|---|---|---|
| 1 | Direct | the `apply_*` techniques only |
| 2 | Candidate elimination | Sudoku-style elimination (subsets, pointing, X-wing, ...) |
| 3 | Advanced killer logic | sum-based elimination over several cages and houses |
| 4 | Contradiction | "if this cell were 5, something breaks one step later" |

`required_level(cages)` solves a puzzle at level 1, then 2, ... and returns
the first that works. Because only sound logic is used, solving it also
proves the puzzle has exactly one solution.

### Explanations and hints

`solve_and_explain(cages)` solves the puzzle while recording every step as a
dict (`type` "placement" or "elimination", the text, the cells involved,
the candidates before and after). The step-through viewer plays those steps
back. In play mode, Hint runs the same thing from your current board and
`explain_step` in `visualizer.py` turns the step into plain sentences.

## The app, in more detail

`play_mode()` in `visualizer.py` is one long function, organised like a
classic game loop:

1. **setup** - layout constants, fonts, and the game state as local
   variables (`board`, `pencil`, `selected`, `history`, ...);
2. **helpers** - small nested functions for the actions (`do_hint`,
   `do_undo`, `do_reset`, `save_progress`, ...);
3. **the loop** - every frame: handle the events (mouse, keys, buttons),
   then redraw everything from the state, top to bottom.

To change what a button does, find its name in the event section (search
for `btn_name == "Hint"`); to change how something looks, find the matching
`# --- ... ---` header in the drawing part.

Everything is drawn at a fixed design size (580 x 936) and scaled down on
smaller screens, so all coordinates in the code are design coordinates.

### What gets written to disk

All under `saves/`:

- `puzzle_NNN.json` - the game in progress (digits, pencil marks, timer,
  marks, ruled-out combos). Deleted when you solve it.
- `moves/puzzle_NNN.jsonl` - every move, one JSON line each, with a timestamp.
  It is enough to rebuild a game, e.g. after an accidental reset.
- `solved.jsonl` - one line per finished puzzle (time, hints); the Stats
  screen reads it.

## Tests

```
python tests/run_all.py          about ten minutes; --full for the whole hard set
```

It runs:

- `check_saved.py` - every puzzle in `puzzles/` has exactly one solution and
  the solver reaches it without ever placing a wrong digit;
- `check_trail.py` - each explained step really follows from the one before;
- `ui_smoke.py` - drives the start screen and play mode headless with fake
  clicks and keys; screenshots land in `tests/output/`;
- `check_hard.py` - 150 hard puzzles from dailykillersudoku.com, krazydad
  and elsewhere (`tests/hard_puzzles/`), each must be solved by logic alone.

## Further reading

The techniques are the ones human solvers use; the
[Killer Sudoku article on Wikipedia](https://en.wikipedia.org/wiki/Killer_sudoku)
explains the basic ones (combinations, Rule of 45, clock arithmetic).
