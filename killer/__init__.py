"""Killer Sudoku solver package."""

from killer.helpers import COL_LETTERS, cell, parse_cell, cells, fmt_combos, house_name, cage_desc, get_house_cells
from killer.sudoku import (
    get_possible_values, get_possible_combinations, digit_combos, get_cage_candidates,
    can_assign_combo, is_solved, check_cages,
    build_candidates, candidates_to_dict, snapshot_candidates,
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
    eliminate_leftovers, eliminate_by_contradiction, filter_cage_combos,
)
from killer.solver import (
    create_board, solve_killer_sudoku, solve_and_explain,
    get_candidate_elimination_steps, estimate_difficulty,
    ALL_STRATEGIES, DIRECT_STRATEGIES, STRATEGY_DESCRIPTIONS, LEVEL_LABELS,
    LEVEL_NAMES, LEVEL_STRATEGIES, required_level,
)
from killer.generator import (
    populate_board, generate_cages, generate_sparse_cages,
    generate_to_level,
    COLOR_PALETTE, is_valid,
)
