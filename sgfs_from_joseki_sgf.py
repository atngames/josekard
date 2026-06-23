# python3 -m venv .venv
# source .venv/bin/activate

from sgfmill import sgf
from pathlib import Path
# from copy import copy, deepcopy

REPO = Path(__file__).parent

JOSEKI_DIR = REPO / "joseki/sgfs/"
PROBLEMS_DIR = JOSEKI_DIR / "problems"
SOLUTIONS_DIR = JOSEKI_DIR / "solutions"


CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# MINCHARS = "abcdefghijklmnopqrstuvwxyz"


# def move_to_raw(x, y):
#     return f"{MINCHARS[x]}{MINCHARS[y]}"

def create_game_setup(p_game):
    old_moves_b = list(p_game.get_root().get_setup_stones()[0])
    old_moves_w = list(p_game.get_root().get_setup_stones()[1])
    for node in p_game.get_main_sequence():
        if node.get_move()[0] == "b" and node.get_move()[1] != None:
            old_moves_b.append(node.get_move()[1])
        elif node.get_move()[0] == "w" and node.get_move()[1] != None:
            old_moves_w.append(node.get_move()[1])
    new_game = sgf.Sgf_game(19)
    new_game.get_root().set_setup_stones(old_moves_b, old_moves_w)
    return new_game


def build_solution_from_here(current_node, created_name, created_game):
    pass



# TODO solutions should have same names as problems
def build_pbs_sols_sgf(current_node, created_name, created_game):
    if len(current_node) == 0:
        return

    name_to_add = f"{created_name}_t-t"
    if current_node.get_move()[1] != None:
        name_to_add = f"{created_name}_{19 - current_node.get_move()[1][0]}-{19 - current_node.get_move()[1][1]}"

    this_name_to_add = name_to_add
    # The current node is the current problem
    # It is showing current moves as setup stones
    new_game = create_game_setup(created_game)
    with open(f"{PROBLEMS_DIR}/joseki{name_to_add}.sgf", "wb") as file:
        file.write(new_game.serialise())

    # We want to go to the next forking path
    # Store those non forking moves as regular moves in the game after the problem setup
    iter_node = current_node
    while len(iter_node) == 1 :
        iter_node = iter_node[0]
        if iter_node.get_move()[1] == None:
            name_to_add = f"{name_to_add}_t-t"
        else:
            name_to_add = f"{name_to_add}_{19 - iter_node.get_move()[1][0]}-{19 - iter_node.get_move()[1][1]}"
        new_child = new_game.get_last_node().new_child()
        new_child.set_move(*(iter_node.get_move()))

    # At a fork, iterate on all children
    for child in iter_node:
        child_game = create_game_setup(new_game)
        new_child = child_game.get_last_node().new_child()
        new_child.set_move(*(child.get_move()))
        build_pbs_sols_sgf(child, name_to_add, child_game)

    # In addition to the moves, add the next children as Labels after the fork
    # Tenuki in comment if needed
    children_arr = []
    i = 0
    for child in iter_node:
        if child.get_move()[1] == None:
            new_game.get_last_node().set("C","Tenuki")
        else:
            children_arr.append((child.get_move()[1], CHARS[i]))
            i += 1
    if children_arr:
        new_game.get_last_node().set("LB",children_arr)
    
    # We can now write the solution sgf
    with open(f"{SOLUTIONS_DIR}/joseki{this_name_to_add}.sgf", "wb") as file:
        file.write(new_game.serialise())


def main():
    with open("katago_joseki/katago_rating_joseki.sgf", "rb") as f:
        game = sgf.Sgf_game.from_bytes(f.read())

    winner = game.get_winner()
    board_size = game.get_size()
    root_node = game.get_root()
    b_player = root_node.get("PB")
    w_player = root_node.get("PW")

    # build the pbs and sols from the first children
    # to avoid an empty root everywhere
    for child in root_node:
        child_game = sgf.Sgf_game(19)
        new_child = child_game.get_root().new_child()
        new_child.set_move(*(child.get_move()))
        build_pbs_sols_sgf(child, "", child_game)


if __name__ == '__main__':
    main()
 
