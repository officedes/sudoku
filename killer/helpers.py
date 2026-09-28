"""Cell naming, formatting, and house helpers."""

COL_LETTERS = "ABCDEFGHI"


def cell(r, c):
    """Cell name: column letter + row number, e.g. A1, E5, I9."""
    return f"{COL_LETTERS[c]}{r + 1}"


def parse_cell(key):
    """Parse 'A1' back to (row=0, col=0)."""
    return int(key[1:]) - 1, COL_LETTERS.index(key[0])


def cells(cell_list):
    """Format a list of (r,c) tuples as 'A1, B2, C3'."""
    return ", ".join(cell(r, c) for r, c in cell_list)


def fmt_combos(combos, limit=6):
    """Format combos compactly: {1,2,3} {4,5,6}."""
    parts = ["{" + ",".join(str(x) for x in sorted(co)) + "}" for co in combos[:limit]]
    s = " ".join(parts)
    if len(combos) > limit:
        s += f" (+{len(combos) - limit} more)"
    return s


def house_name(house_type, i):
    """Human name for a house: 'row 1', 'column 5', 'box 3'."""
    names = {"row": "row", "col": "column", "box": "box"}
    return f"{names[house_type]} {i + 1}"


def cage_desc(cage_sum, cells_list, board):
    """Describe a cage's current state for explanations."""
    filled = [(r, c) for r, c in cells_list if board[r][c] != 0]
    empty = [(r, c) for r, c in cells_list if board[r][c] == 0]
    desc = f"Cage(sum={cage_sum}, cells=[{cells(cells_list)}])"
    if filled:
        filled_vals = [str(board[r][c]) for r, c in filled]
        remaining = cage_sum - sum(board[r][c] for r, c in filled)
        desc += f" -- filled: {'+'.join(filled_vals)}={sum(board[r][c] for r,c in filled)}"
        desc += f", need {remaining} in [{cells(empty)}]"
    return desc


def get_house_cells(house_type, i):
    """Return the 9 cells in a row, column, or box."""
    if house_type == "row":
        return [(i, j) for j in range(9)]
    elif house_type == "col":
        return [(j, i) for j in range(9)]
    else:
        br, bc = (i // 3) * 3, (i % 3) * 3
        return [(br + r, bc + c) for r in range(3) for c in range(3)]
