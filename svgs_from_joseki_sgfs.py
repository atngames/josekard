#!/usr/bin/env python3
 
"""Convert Katago SGF problems to SVGs."""
 
import argparse
import io
import re
import time
import uuid
import zipfile
from pathlib import Path
import xml.sax.saxutils as saxutils
from sgfmill import sgf



REPO = Path(__file__).parent
 
SGFS_DIR = REPO / "joseki/sgfs"
PROBLEMS_DIR = SGFS_DIR / "problems"
SOLUTIONS_DIR = SGFS_DIR / "solutions"
SVGS_DIR = REPO / "joseki/svgs"
 
WIDTH, HEIGHT = 800, 1024
 
# IS_UNIVERSAL = False
UI_SCALE = 1.0  # scales fonts/text positions relative to 480px reference width
B_EXPAND = 1.035 # Black stones are drawn slightly wider to compensate for optical illusion
 
  
 
# --- Board geometry ---
 
MARGIN_TOP = 40   # space above board for problem number label
PADDING = 16      # min margin around board on all other sides
 
STONE_FRAC = 0.44  # stone_r = cell * STONE_FRAC

HOSHI = {(3, 3), (9, 3), (15, 3), (3, 9), (9, 9), (15, 9), (3, 15), (9, 15), (15, 15)}
 
 
def cell_size(c0, c1, r0, r1, avail_w, avail_h):
    n_x = c1 - c0
    n_y = r1 - r0
    cell = min(avail_w / (n_x + 2 * STONE_FRAC),
               avail_h / (n_y + 2 * STONE_FRAC))
    return max(cell, 16)
 
 
# --- SVG helpers ---
 
def _esc(s):
    return saxutils.escape(str(s))
 
 
class SVG:
    """Lightweight SVG builder."""
 
    def __init__(self, width, height):
        self.w = width
        self.h = height
        self._parts = []
 
    def rect(self, x, y, w, h, fill='white', stroke=None, stroke_width=1):
        s = f'stroke="{_esc(stroke)}" stroke-width="{stroke_width}"' if stroke else ''
        self._parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" {s}/>')
 
    def line(self, x1, y1, x2, y2, stroke='black', width=1):
        self._parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{width:.2f}"/>')
 
    def circle(self, cx, cy, r, fill='black', stroke=None, stroke_width=1):
        s = f'stroke="{_esc(stroke)}" stroke-width="{stroke_width:.2f}"' if stroke else ''
        self._parts.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" {s}/>')
 
    def text(self, x, y, content, font_size=16, anchor='middle',
         fill='black', font_weight='normal'):
        self._parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{font_size:.1f}" '
            f'text-anchor="{anchor}" dy="0em" '
            f'fill="{fill}" font-weight="{font_weight}" '
            f'font-family="Helvetica,Arial,sans-serif">{_esc(content)}</text>')        
 
    def build(self):
        inner = '\n'.join(self._parts)
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}">\n'
                f'{inner}\n'
                f'</svg>')
 
 
# --- Board drawing into SVG ---
 
def _draw_grid(svg, c0, c1, r0, r1, x0, y0, cell):
    n_cols = c1 - c0 + 1
    n_rows = r1 - r0 + 1
    board_w = (c1 - c0) * cell
    board_h = (r1 - r0) * cell
 
    thick = max(2, cell / 12)
    thin = max(0.5, cell / 30)
    dot_r = max(2, cell / 10)
 
    for ci in range(n_cols):
        col = c0 + ci
        is_board_edge = (col == 0 or col == 18)
        is_crop_edge = (ci == 0 or ci == n_cols - 1) and not is_board_edge
        if is_crop_edge:
            continue
        x = x0 + ci * cell
        w = thick if is_board_edge else thin
        svg.line(x, y0, x, y0 + board_h, width=w)
 
    for ri in range(n_rows):
        row = r0 + ri
        is_board_edge = (row == 0 or row == 18)
        is_crop_edge = (ri == 0 or ri == n_rows - 1) and not is_board_edge
        if is_crop_edge:
            continue
        y = y0 + ri * cell
        w = thick if is_board_edge else thin
        svg.line(x0, y, x0 + board_w, y, width=w)
 
    for ci in range(n_cols):
        for ri in range(n_rows):
            if (c0 + ci, r0 + ri) in HOSHI:
                svg.circle(x0 + ci * cell, y0 + ri * cell, dot_r)
 
 
def _draw_stones(svg, board, c0, c1, r0, r1, x0, y0, cell, move_history=None):
    stone_r = cell * STONE_FRAC
 
    thin = max(0.5, cell / 30)
    num_font = max(10, cell * 0.55)
    num_offset = round(num_font * 0.35)
 
    pos_to_num = {}
    if move_history:
        for num, col, row in move_history:
            if (col, row) not in pos_to_num:
                pos_to_num[(col, row)] = num
 
    for (col, row), color in board.items():
        if not (c0 <= col <= c1 and r0 <= row <= r1):
            continue
        cx = x0 + (col - c0) * cell
        cy = y0 + (row - r0) * cell
        num = pos_to_num.get((col, row))
 
        if color == 'B':
            svg.circle(cx, cy, stone_r*B_EXPAND, fill='black', stroke='black')
            if num is not None:
                svg.text(cx, cy+num_offset, str(num), font_size=num_font, fill='white')
        else:
            svg.circle(cx, cy, stone_r, fill='white', stroke='black',
                       stroke_width=max(0.5, thin + 0.5))
            if num is not None:
                svg.text(cx, cy+num_offset, str(num), font_size=num_font, fill='black')
 

def _draw_labels(svg, board, c0, c1, r0, r1, x0, y0, cell, labels, last_color_played):
    stone_r = cell * STONE_FRAC
    num_font = max(10, cell * 0.55)
    num_offset = round(num_font * 0.35)

    fill_color = "darkgray" if last_color_played == "B" else "lightgray"
    stroke_color = "white" if last_color_played == "B" else "black"
    txt_color = "white" if last_color_played == "B" else "black"

    for (col, row), label in labels:
        if not (c0 <= col <= c1 and r0 <= row <= r1):
            continue
        cx = x0 + (col - c0) * cell
        cy = y0 + (row - r0) * cell
        # num = pos_to_num.get((col, row)) 

        svg.circle(cx, cy, stone_r*B_EXPAND, fill=fill_color, stroke=stroke_color)
        svg.text(cx, cy+num_offset, label, font_size=num_font, fill=txt_color)


# --- Full-page SVG generators ---
 
def _wrap_lines(text, font_size, max_w):
    """Very rough word-wrap: estimates char width as ~0.55 * font_size."""
    char_w = font_size * 0.55
    words = text.split()
    lines, current = [], []
    for word in words:
        test = ' '.join(current + [word])
        if len(test) * char_w <= max_w or not current:
            current.append(word)
        else:
            lines.append(' '.join(current))
            current = [word]
    if current:
        lines.append(' '.join(current))
    return lines
 
 
def make_problem_svg(blacks, whites, color_to_play) :

    c0, c1, r0, r1 = 9, 18, 9, 18
    svg = SVG(WIDTH, HEIGHT)
 
    U = UI_SCALE
    margin_top = MARGIN_TOP * U
    avail_w = WIDTH - 2 * PADDING
    avail_h = HEIGHT - margin_top - PADDING
 
    cell = cell_size(c0, c1, r0, r1, avail_w, avail_h)
    board_w = (c1 - c0) * cell
    board_h = (r1 - r0) * cell
    x0 = (WIDTH - board_w) / 2
    y0 = margin_top + (avail_h - board_h) / 2
 
    _draw_grid(svg, c0, c1, r0, r1, x0, y0, cell)
 
    stone_r = cell * STONE_FRAC
    thin = max(0.5, cell / 30)
    for col, row in blacks:
        if c0 <= col <= c1 and r0 <= row <= r1:
            svg.circle(x0 + (col - c0) * cell, y0 + (row - r0) * cell, stone_r * B_EXPAND, fill='black', stroke='black', stroke_width=max(0.5, thin + 0.5))
    for col, row in whites:
        if c0 <= col <= c1 and r0 <= row <= r1:
            svg.circle(x0 + (col - c0) * cell, y0 + (row - r0) * cell,
                       stone_r, fill='white', stroke='black',
                       stroke_width=max(0.5, thin + 0.5))
 
    color = color_to_play
    stone_r = cell * STONE_FRAC
    ann_font = 48 * U
    ann_lh = ann_font * 1.5
    ann_y = y0 + board_h + stone_r + 48 * U
    svg.text(WIDTH / 2, ann_y, f"{color} to play", font_size=ann_font)

    return svg.build()
 
 
def make_solution_svg(blacks, whites, solution_moves, color_to_play, labels, tenuki):#, c0, c1, r0, r1):

    c0, c1, r0, r1 = 9, 18, 9, 18


    board = {}
    for c, r in blacks:
        board[(c, r)] = 'B'
    for c, r in whites:
        board[(c, r)] = 'W'
 
    history = []
    first_at = {}
    annotations = []
 
    color = color_to_play[0]
    black_started = 0 if color_to_play == "Black" else 1
    for i, (col, row) in enumerate(solution_moves):
        color = 'B' if i % 2 == black_started else 'W'
        if col != -1:
            if (col, row) not in board:
                board[(col, row)] = color
            history.append((i + 1, col, row))
            if (col, row) in first_at:
                annotations.append(f"{i + 1} at {first_at[(col, row)]}")
            else:
                first_at[(col, row)] = i + 1

    if tenuki:
        annotations.append(f"or {color} Tenuki")

    U = UI_SCALE
    header = 44 * U
    avail_w = WIDTH - 2 * PADDING
    avail_h = HEIGHT - header - PADDING
 
    cell = cell_size(c0, c1, r0, r1, avail_w, avail_h)
    board_w = (c1 - c0) * cell
    board_h = (r1 - r0) * cell
    gx0 = (WIDTH - board_w) / 2
    gy0 = header + (avail_h - board_h) / 2
 
    svg = SVG(WIDTH, HEIGHT)
 
    # label_size = 36 * U
 
    _draw_grid(svg, c0, c1, r0, r1, gx0, gy0, cell)
    _draw_stones(svg, board, c0, c1, r0, r1, gx0, gy0, cell, history)
    _draw_labels(svg, board, c0, c1, r0, r1, gx0, gy0, cell, labels, color)
 
    if annotations:
        stone_r = cell * STONE_FRAC
        ann_font = 48 * U
        ann_lh = ann_font * 1.5
        ann_y = gy0 + board_h + stone_r + 48 * U
        for ann in annotations:
            svg.text(WIDTH / 2, ann_y, ann, font_size=ann_font)
            ann_y += ann_lh
 
    return svg.build()
 
 
 
# --- main ---
 
def main():
    pb_svgs = {}
    sol_svgs = {}
    zip_path = SVGS_DIR / "josekis.zip"

    for f in sorted(PROBLEMS_DIR.glob('*.sgf')):

        problem = sgf.Sgf_game.from_string(f.read_text())
        sol_path = SOLUTIONS_DIR / f.name
        solution = sgf.Sgf_game.from_string(sol_path.read_text())

        setup_stones = solution.get_root().get_setup_stones()
        blacks = list(setup_stones[0])
        whites = list(setup_stones[1])

        next_color = problem.get_root().get("C")

        move_sequence = []
        for node in solution.get_main_sequence()[0]:
            if node.get_move()[1] != None:
                move_sequence.append(node.get_move()[1])
            else:
                move_sequence.append((-1,-1))

        labels = []
        if solution.get_last_node().has_property("LB"):
            labels = solution.get_last_node().get("LB")

        tenuki = False
        if solution.get_last_node().has_property("C"):
            comments = solution.get_last_node().get("C")
            if "Tenuki" in comments:
                tenuki = True

        pb_svgs[f.stem] = make_problem_svg(blacks, whites, next_color)
        sol_svgs[f.stem] = make_solution_svg(blacks, whites, move_sequence, next_color, labels, tenuki)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # zf.writestr('mimetype', 'application/zip', compress_type=zipfile.ZIP_STORED)
        zf.mkdir("josekis")
        i = 0
        for name, svg_data in pb_svgs.items():
            i += 1
            zf.writestr(f'josekis/p{i:04}.svg', svg_data)
        i = 0
        for name, svg_data in sol_svgs.items():
            i += 1
            zf.writestr(f'josekis/s{i:04}.svg', svg_data)
 
    # size_kb = out_path.stat().st_size // 1024
    # print(f"  -> {out_path.name} ({size_kb} KB)")

 
if __name__ == '__main__':
    main()
 