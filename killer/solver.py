"""Main solver, step-by-step explainer, and difficulty estimator."""

from functools import partial

from killer.helpers import cell, cells, parse_cell, fmt_combos, get_house_cells, house_name
from killer.sudoku import (
    is_solved, digit_combos, can_assign_combo, build_candidates, candidates_to_dict, snapshot_candidates,
)
from killer.strategies import (
    apply_cage_deduction, apply_rule_of_45, apply_clock_arithmetic,
    apply_consistent_numbers, apply_rule_of_necessity, apply_cage_candidates,
    apply_limited_possible_sums, apply_cage_complements, apply_rule_of_k,
    apply_naked_singles, apply_hidden_single_house, apply_candidate_elimination,
    eliminate_naked_subsets, eliminate_pointing, eliminate_box_line,
    eliminate_cage_claiming, eliminate_cage_pointing, eliminate_cage_box_reduction,
    eliminate_x_wing, eliminate_hidden_subsets, eliminate_xy_wing,
    eliminate_generalized_outies, eliminate_cage_interaction,
    eliminate_innies_outies, eliminate_large_sums, eliminate_hidden_killer_subsets,
    eliminate_naked_killer_subsets, eliminate_common_peers, eliminate_conflicting_combos,
    eliminate_leftovers, eliminate_house_combos, eliminate_cage_pairs,
    eliminate_killer_fish, eliminate_als_xz,
    eliminate_by_contradiction, filter_cage_combos,
)

# =============================================================================
# Strategy lists
# =============================================================================

# Easiest first, so each step is explained with the simplest technique that
# works and the difficulty rating reflects what the puzzle actually needs.
NAMED_STRATEGIES = [
    ("cage deduction",        apply_cage_deduction),
    ("Rule of 45",            apply_rule_of_45),
    ("naked single",          apply_naked_singles),
    ("consistent numbers",    apply_consistent_numbers),
    ("cage candidates",       apply_cage_candidates),
    ("limited possible sums", apply_limited_possible_sums),
    ("hidden single",         apply_hidden_single_house),
    ("Rule of Necessity",     apply_rule_of_necessity),
    ("Rule of K",             apply_rule_of_k),
    ("Clock Arithmetic",      apply_clock_arithmetic),
    ("cage complement",       apply_cage_complements),
    ("candidate elimination", apply_candidate_elimination),
]

ALL_STRATEGIES = [fn for _, fn in NAMED_STRATEGIES]

DIRECT_STRATEGIES = [fn for fn in ALL_STRATEGIES if fn is not apply_candidate_elimination]

# Technique levels, each adding to the one before:
#   1 direct strategies, 2 candidate elimination, 3 + advanced killer logic
#   (rule of 45 over several houses, killer subsets, common peers, conflicting
#   combos, leftovers, house combos, cage pairs, killer fish, ALS-XZ), 4 +
#   first-order contradiction.
LEVEL_NAMES = {1: "Direct", 2: "Candidate elimination", 3: "Advanced killer logic", 4: "Contradiction"}
LEVEL_STRATEGIES = {
    1: DIRECT_STRATEGIES,
    2: DIRECT_STRATEGIES + [partial(apply_candidate_elimination, innies=False, contradiction=False)],
    3: DIRECT_STRATEGIES + [partial(apply_candidate_elimination, contradiction=False)],
    4: ALL_STRATEGIES,
}


# =============================================================================
# Solver
# =============================================================================

def create_board():
    return [[0] * 9 for _ in range(9)]


def solve_killer_sudoku(board, cages, verbose=True, level=4, stats=None):
    """Solve using strategies only (no backtracking), up to the given technique level.

    A `stats` dict collects "contradictions": how many first-order
    contradiction sweeps it needed (level 4 only).
    """
    strategies = LEVEL_STRATEGIES[level]
    if stats is not None and level == 4:
        strategies = DIRECT_STRATEGIES + [partial(apply_candidate_elimination, stats=stats)]
    for _ in range(200):
        if is_solved(board):
            if verbose:
                print("Solved with strategies!")
            return board, True
        if not any(fn(board, cages) for fn in strategies):
            break
    if is_solved(board):
        if verbose:
            print("Solved with strategies!")
        return board, True
    filled = sum(1 for r in range(9) for c in range(9) if board[r][c] != 0)
    if verbose:
        print(f"Stuck after strategies. {filled}/81 cells filled.")
    return board, False


def required_level(cages):
    """Lowest technique level that solves the puzzle, or None if even level 4 can't.

    Solving by sound logic alone also proves the solution is unique.
    """
    for level in LEVEL_STRATEGIES:
        _, solved = solve_killer_sudoku(create_board(), cages, verbose=False, level=level)
        if solved:
            return level
    return None


# Log prefixes of the level-3 and level-4 eliminations in the explained solve
ADVANCED_STEP_PREFIXES = (
    "Innies/outies", "Large sum", "Common peers", "Cage pair", "Conflicting combos", "Hidden killer subset",
    "Naked killer subset", "Leftovers", "House combos", "Killer fish", "ALS-XZ", "Contradiction",
)


def advanced_steps(cages):
    """How many steps of the explained solve - the one hints walk through - need
    level-3 techniques or a contradiction sweep.

    A finer measure than the level: the explainer's cage-combination filtering
    is stronger than the level-2 solver's, so a puzzle the solver rates level 3
    can still explain itself with no advanced step at all.
    """
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        _, steps = solve_and_explain(cages)
    return sum(s["type"] == "elimination" and s["text"].startswith(ADVANCED_STEP_PREFIXES) for s in steps)


# =============================================================================
# Detailed elimination steps (for visualizer)
# =============================================================================

def _find_placement(board, candidates, initial):
    """Check for naked single or hidden single in the candidate grid."""
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0 and len(candidates[r][c]) == 1:
                num = next(iter(candidates[r][c]))
                before = sorted(initial.get((r, c), set()))
                return {
                    "type": "placement", "cell": (r, c), "value": num,
                    "text": f"{cell(r, c)} = {num}  (candidate elimination)",
                    "explanation": f"{cell(r, c)} started with {before}, now only {{{num}}} remains",
                    "candidates": candidates_to_dict(candidates),
                }
    for house_type in ["row", "col", "box"]:
        for i in range(9):
            hcells = get_house_cells(house_type, i)
            for num in range(1, 10):
                positions = [(r, c) for r, c in hcells if board[r][c] == 0 and num in candidates[r][c]]
                if len(positions) == 1:
                    r, c = positions[0]
                    hn = house_name(house_type, i)
                    return {
                        "type": "placement", "cell": (r, c), "value": num,
                        "text": f"{cell(r, c)} = {num}  (hidden single in {hn})",
                        "explanation": f"After elimination, {num} can only go in {cell(r, c)} in {hn}",
                        "candidates": candidates_to_dict(candidates),
                    }
    return None


def get_candidate_elimination_steps(board, cages, prior_refined=None):
    """Run candidate elimination returning intermediate steps for the visualizer."""
    candidates = build_candidates(board, cages)
    if prior_refined:
        for r in range(9):
            for c in range(9):
                key = cell(r, c)
                if key in prior_refined and candidates[r][c]:
                    candidates[r][c] &= set(prior_refined[key])
    initial = {(r, c): set(candidates[r][c]) for r in range(9) for c in range(9) if candidates[r][c]}
    steps = []

    if prior_refined:
        removed = []
        for key in prior_refined:
            ri, ci = parse_cell(key)
            before = set(prior_refined[key])
            after = candidates[ri][ci] if board[ri][ci] == 0 else set()
            gone = before - after
            if gone and board[ri][ci] == 0:
                removed.append(f"{key}: -{sorted(gone)}")
        if removed:
            detail = ", ".join(removed[:10]) + (f" +{len(removed)-10} more" if len(removed) > 10 else "")
            steps.append({
                "type": "elimination",
                "text": f"Cage combo filtering: narrowed {len(removed)} cells",
                "explanation": f"Re-filtered by cage sum constraints:\n{detail}",
                "candidates": candidates_to_dict(candidates),
            })
            p = _find_placement(board, candidates, initial)
            if p:
                steps.append(p)
                return steps

    for _ in range(1000):
        changed = False
        def _cage_claim(cands, log, single_step):
            return eliminate_cage_claiming(cands, board, cages, log, single_step)
        def _cage_pointing(cands, log, single_step):
            return eliminate_cage_pointing(cands, board, cages, log, single_step)
        def _cage_box(cands, log, single_step):
            return eliminate_cage_box_reduction(cands, board, cages, log, single_step)
        def _outies(cands, log, single_step):
            return eliminate_generalized_outies(cands, board, cages, log, single_step)
        def _cage_interact(cands, log, single_step):
            return eliminate_cage_interaction(cands, board, cages, log, single_step)
        def _contradiction(cands, log, single_step):
            return eliminate_by_contradiction(cands, board, cages, log, single_step)
        advanced = [lambda cands, log, single_step, fn=fn: fn(cands, board, cages, log, single_step)
                    for fn in (eliminate_innies_outies, eliminate_hidden_killer_subsets,
                               eliminate_naked_killer_subsets, eliminate_common_peers,
                               eliminate_conflicting_combos, eliminate_leftovers, eliminate_house_combos,
                               eliminate_large_sums, eliminate_cage_pairs, eliminate_killer_fish, eliminate_als_xz)]
        for elim_fn in [eliminate_naked_subsets, eliminate_pointing, eliminate_box_line,
                         _cage_claim, _cage_pointing, _cage_box, eliminate_x_wing,
                         eliminate_hidden_subsets, eliminate_xy_wing, _outies,
                         _cage_interact, *advanced]:
            fn_log = []
            if elim_fn(candidates, fn_log, single_step=True):
                changed = True
                steps.append({
                    "type": "elimination", "text": fn_log[0], "explanation": fn_log[0],
                    "candidates": candidates_to_dict(candidates),
                })
                p = _find_placement(board, candidates, initial)
                if p:
                    steps.append(p)
                    return steps
                if filter_cage_combos(candidates, board, cages):
                    steps.append({
                        "type": "elimination",
                        "text": "Cage combo re-filtering after elimination",
                        "explanation": "Re-filtered candidates by valid cage sum combinations",
                        "candidates": candidates_to_dict(candidates),
                    })
                    p = _find_placement(board, candidates, initial)
                    if p:
                        steps.append(p)
                        return steps
                break
        if not changed:
            if filter_cage_combos(candidates, board, cages):
                changed = True
                steps.append({
                    "type": "elimination",
                    "text": "Cage combo filtering",
                    "explanation": "Re-filtered candidates by valid cage sum combinations",
                    "candidates": candidates_to_dict(candidates),
                })
                p = _find_placement(board, candidates, initial)
                if p:
                    steps.append(p)
                    return steps
        if not changed:
            fn_log = []
            if _contradiction(candidates, fn_log, single_step=True):
                changed = True
                steps.append({
                    "type": "elimination", "text": fn_log[0], "explanation": fn_log[0],
                    "candidates": candidates_to_dict(candidates),
                })
                p = _find_placement(board, candidates, initial)
                if p:
                    steps.append(p)
                    return steps
        if not changed:
            break

    p = _find_placement(board, candidates, initial)
    if p:
        steps.append(p)
    return steps


# =============================================================================
# Step-by-step solver for visualizer
# =============================================================================

def solve_and_explain(cages, board=None, stop_after=None):
    """Solve a puzzle and return (board, steps) with candidates and explanations.

    `board` starts from a partly filled grid (it is copied, not changed);
    `stop_after` stops once that many cells have been placed, which is how a
    hint explains just the next move from the player's position.
    """
    import io, sys
    board = [row[:] for row in board] if board else create_board()
    steps = []
    placements = 0

    # Info steps
    sizes = sorted([len(c[1]) for c in cages])
    init = snapshot_candidates(board, cages)
    steps.append({
        "type": "info",
        "text": f"Killer Sudoku: {len(cages)} cages, sizes {min(sizes)}-{max(sizes)}",
        "explanation": (f"{len(cages)} cages, sizes: {', '.join(f'{s}-cell: {sizes.count(s)}' for s in sorted(set(sizes)))}\n"
                        f"Cage sums total: {sum(c[0] for c in cages)} (must be 405 = 45x9)"),
        "candidates": init,
    })
    tight = [(k, v) for k, v in init.items() if len(v) <= 3]
    if tight:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(tight)[:10])
        steps.append({
            "type": "info",
            "text": f"{len(tight)} cells start with 3 or fewer candidates",
            "explanation": f"Most constrained cells:\n{detail}",
            "candidates": init,
        })

    last_refined = None

    for _ in range(200):
        if is_solved(board):
            break
        pre_grid = build_candidates(board, cages)
        cands = candidates_to_dict(pre_grid)
        if last_refined:
            for key in cands:
                if key in last_refined:
                    cands[key] = sorted(set(cands[key]) & set(last_refined[key]))

        old = sys.stdout
        sys.stdout = io.StringIO()
        placed = any(fn(board, cages) for fn in DIRECT_STRATEGIES)
        output = sys.stdout.getvalue()
        sys.stdout = old

        if placed:
            lines = output.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]
                if line.startswith("Set cell"):
                    parts = line.split(" via ")
                    strategy = parts[1] if len(parts) > 1 else "unknown"
                    cell_part = line.split("Set cell ")[1].split(" to ")
                    rc = cell_part[0].strip("()")
                    r, c = int(rc.split(",")[0]), int(rc.split(",")[1])
                    val = int(cell_part[1].split(" via")[0])
                    explanation_lines = []
                    while i + 1 < len(lines) and lines[i + 1].startswith("  "):
                        i += 1
                        explanation_lines.append(lines[i].strip())
                    explanation = "\n".join(explanation_lines)

                    post = snapshot_candidates(board, cages)
                    if last_refined:
                        for key in post:
                            if key in last_refined:
                                post[key] = sorted(set(post[key]) & set(last_refined[key]))

                    steps.append({
                        "type": "placement", "cell": (r, c), "value": val,
                        "strategy": strategy, "explanation": explanation,
                        "text": f"{cell(r, c)} = {val}  ({strategy})",
                        "candidates": post,
                    })

                    # Per-cage complement elimination
                    running = [[set() for _ in range(9)] for _ in range(9)]
                    for ri in range(9):
                        for ci in range(9):
                            key = cell(ri, ci)
                            if key in post:
                                running[ri][ci] = set(post[key])
                    if last_refined:
                        for ri in range(9):
                            for ci in range(9):
                                key = cell(ri, ci)
                                if key in last_refined and running[ri][ci]:
                                    running[ri][ci] &= set(last_refined[key])

                    for cs, cls, _ in cages:
                        empty_c = [(cr, cc) for cr, cc in cls if board[cr][cc] == 0]
                        if not empty_c:
                            continue
                        filled_nums = set(board[cr][cc] for cr, cc in cls if board[cr][cc] != 0)
                        rem_sum = cs - sum(board[cr][cc] for cr, cc in cls if board[cr][cc] != 0)
                        cc_map = {cl: running[cl[0]][cl[1]] for cl in empty_c}
                        sum_combos = digit_combos(len(empty_c), rem_sum, filled_nums)
                        valid = [combo for combo in sum_combos if can_assign_combo(combo, empty_c, cc_map)]
                        removals = []
                        after_set = set()
                        for cr, cc in empty_c:
                            allowed = set()
                            for combo in valid:
                                for num in combo:
                                    if num not in running[cr][cc]:
                                        continue
                                    rest = [n for n in combo if n != num]
                                    others = [cl for cl in empty_c if cl != (cr, cc)]
                                    if not rest:
                                        allowed.add(num)
                                        after_set.add(combo)
                                    else:
                                        oc = {cl: running[cl[0]][cl[1]] - {num} for cl in others}
                                        if can_assign_combo(rest, others, oc):
                                            allowed.add(num)
                                            after_set.add(combo)
                            gone = running[cr][cc] - allowed
                            if gone:
                                removals.append((cell(cr, cc), sorted(gone)))
                                running[cr][cc] = allowed
                        if removals:
                            snap = candidates_to_dict(running)
                            impossible = [co for co in sum_combos if co not in after_set]
                            lines_exp = [f"Cage sum={cs} [{cells(cls)}]:"]
                            if impossible:
                                lines_exp.append(f"  Combos eliminated: {fmt_combos(impossible)}")
                            lines_exp.append(f"  Combos remaining:  {fmt_combos(list(after_set)) if after_set else '(solved)'}")
                            for cn, gn in removals:
                                lines_exp.append(f"  {cn} lost {gn}")
                            rem_str = ", ".join(f"{cn} -{gn}" for cn, gn in removals)
                            steps.append({
                                "type": "elimination",
                                "text": f"Cage sum={cs} [{cells(cls)}]: {rem_str}",
                                "explanation": "\n".join(lines_exp),
                                "candidates": snap,
                            })
                    last_refined = candidates_to_dict(running)
                i += 1
            placements += 1
            if stop_after and placements >= stop_after:
                break
            continue

        prior = last_refined or (steps[-1].get("candidates", {}) if steps else {})
        elim_steps = get_candidate_elimination_steps(board, cages, prior_refined=prior)
        if not elim_steps:
            break
        for es in elim_steps:
            steps.append(es)
        last_with_cands = next((s for s in reversed(elim_steps) if s.get("candidates")), None)
        if last_with_cands:
            last_refined = last_with_cands["candidates"]
        placement = next((s for s in reversed(elim_steps) if s.get("type") == "placement"), None)
        if placement:
            r, c = placement["cell"]
            board[r][c] = placement["value"]
            post_grid = build_candidates(board, cages)
            post_dict = candidates_to_dict(post_grid)
            if last_refined:
                for key in post_dict:
                    if key in last_refined:
                        post_dict[key] = sorted(set(post_dict[key]) & set(last_refined[key]))
            placement["candidates"] = post_dict
            last_refined = post_dict
            placements += 1
            if stop_after and placements >= stop_after:
                break
        else:
            break

    return board, steps


# =============================================================================
# Difficulty estimation
# =============================================================================

STRATEGY_DESCRIPTIONS = {
    "cage deduction":        "Last cell in cage -- just subtraction",
    "Rule of 45":            "Sum of a house is always 45",
    "naked single":          "Only one candidate left in a cell",
    "consistent numbers":    "A digit must appear in all cage combos",
    "cage candidates":       "Filter candidates by cage combinations",
    "limited possible sums": "Filter combos by cell assignment feasibility",
    "hidden single":         "Digit can only go in one place in a house",
    "Rule of Necessity":     "Digit in all combos + only one cell by Sudoku",
    "Rule of K":             "Naked pairs/triples/quads lock digits in a house",
    "Clock Arithmetic":      "Outie/innie deduction from partial cage overlap",
    "cage complement":       "Large cage complement reasoning",
    "candidate elimination": "Chained eliminations on the candidate grid",
}

LEVEL_LABELS = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Expert"}


def estimate_difficulty(cages):
    """Rate a puzzle by the weakest technique level that solves it.

    Levels (see LEVEL_NAMES): 1 Easy = direct strategies, 2 Medium = candidate
    elimination, 3 Hard = advanced killer logic, 4 Expert = contradiction.
    Returns level (None if even level 4 is stuck), label, rating (stars),
    contradictions (times stuck, each broken by a first-order contradiction sweep),
    breakdown (placements per strategy at that level) and a text summary.
    """
    import io
    from contextlib import redirect_stdout
    for level, strategies in LEVEL_STRATEGIES.items():
        stats = {}
        named = [(name, fn) for name, fn in NAMED_STRATEGIES if fn is not apply_candidate_elimination]
        if level == 4:
            named.append(("candidate elimination", partial(apply_candidate_elimination, stats=stats)))
        elif level > 1:
            named.append(("candidate elimination", strategies[-1]))
        board = create_board()
        counts = {}
        with redirect_stdout(io.StringIO()):
            for _ in range(200):
                if is_solved(board):
                    break
                name = next((name for name, fn in named if fn(board, cages)), None)
                if name is None:
                    break
                counts[name] = counts.get(name, 0) + 1
        if is_solved(board):
            break
    else:
        return {"level": None, "label": "Unsolvable", "rating": 0, "contradictions": None,
                "breakdown": {}, "summary": "Could not solve with strategies alone"}

    label = LEVEL_LABELS[level]
    contradictions = stats.get("contradictions", 0)
    steps = f" ({contradictions} contradiction sweep{'s' if contradictions != 1 else ''})" if level == 4 else ""
    techniques = [f"  {name}: {n}x -- {STRATEGY_DESCRIPTIONS[name]}"
                  for name, n in sorted(counts.items(), key=lambda x: -x[1])]
    summary = (f"Difficulty: {label} ({'*' * level}{'.' * (4 - level)}),"
               f" needs level {level}: {LEVEL_NAMES[level]}{steps}\n"
               f"{len(cages)} cages, avg size {81 / len(cages):.1f}\n"
               f"Techniques ({sum(counts.values())} placements):\n" + "\n".join(techniques))
    return {"level": level, "label": label, "rating": level, "contradictions": contradictions,
            "breakdown": counts, "summary": summary}
