#!/usr/bin/env python3
 
"""extract josekis (SVG-based)."""
 
import argparse
import io
import re
import time
import uuid
import zipfile
from pathlib import Path
from pysgf import SGF
import xml.sax.saxutils as saxutils
 
REPO = Path(__file__).parent
 
JOSEKI_SGF = REPO / "katago_joseki/katago_rating_joseki.sgf"
# BOOKS_DIR = REPO / "books"
PROBLEMS_DIR = REPO / "problems"
 
WIDTH, HEIGHT = 1024, 1024
 
OUT_DIR = REPO / "josekis"
 
IS_UNIVERSAL = False
UI_SCALE = 1.0  # scales fonts/text positions relative to 480px reference width
B_EXPAND = 1.035 # Black stones are drawn slightly wider to compensate for optical illusion
 
 
 
# --- Board geometry ---
 
MARGIN_TOP = 40   # space above board for problem number label
PADDING = 16      # min margin around board on all other sides
 
STONE_FRAC = 0.44  # stone_r = cell * STONE_FRAC
 
_LATEX_MACRON = {'a': 'ā', 'e': 'ē', 'i': 'ī', 'o': 'ō', 'u': 'ū',
                 'A': 'Ā', 'E': 'Ē', 'I': 'Ī', 'O': 'Ō', 'U': 'Ū'}
 
HOSHI = {(3, 3), (9, 3), (15, 3), (3, 9), (9, 9), (15, 9), (3, 15), (9, 15), (15, 15)}
 
 
def decode_latex(s):
    s = re.sub(r'\\=([aeiouAEIOU])', lambda m: _LATEX_MACRON[m.group(1)], s)
    return s.replace('~', ' ').replace('\\&', '&')
 
 
def sgf_coord(s):
    return ord(s[0]) - ord('a'), ord(s[1]) - ord('a')
 
 
def parse_sgf(text):
    ab = re.findall(r'AB((?:\[[a-z]{2}\])+)', text)
    aw = re.findall(r'AW((?:\[[a-z]{2}\])+)', text)
    blacks = [sgf_coord(m) for ab_group in ab for m in re.findall(r'\[([a-z]{2})\]', ab_group)]
    whites = [sgf_coord(m) for aw_group in aw for m in re.findall(r'\[([a-z]{2})\]', aw_group)]
    moves = re.findall(r';[BW]\[([a-z]{2})\]', text)
    return blacks, whites, [sgf_coord(m) for m in moves]
 
 
def compute_viewport(blacks, whites, solution_moves):
    all_coords = blacks + whites + solution_moves
    if not all_coords:
        return 0, 8, 0, 8
    cols = [c for c, r in all_coords]
    rows = [r for c, r in all_coords]
    c0 = max(0, min(cols) - 1)
    c1 = min(18, max(cols) + 1)
    r0 = max(0, min(rows) - 1)
    r1 = min(18, max(rows) + 1)
    return c0, c1, r0, r1
 
 
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
 
 
def make_problem_svg(blacks, whites, c0, c1, r0, r1, problem_num):
    svg = SVG(WIDTH, HEIGHT)
    # ATN MODIFIED BELOW
    # svg.rect(0, 0, WIDTH, HEIGHT, fill='white')
 
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
 
    label_size = 36 * U
    # svg.text(WIDTH / 2, 80 * U, f"Problem {problem_num}",
    #          font_size=label_size, font_weight='bold')
 
    return svg.build()
 
 
def make_solution_svgs(blacks, whites, solution_moves, c0, c1, r0, r1, problem_num):
    if not solution_moves:
        return []
 
    board = {}
    for c, r in blacks:
        board[(c, r)] = 'B'
    for c, r in whites:
        board[(c, r)] = 'W'
 
    history = []
    first_at = {}
    annotations = []
 
    for i, (col, row) in enumerate(solution_moves):
        color = 'B' if i % 2 == 0 else 'W'
        if (col, row) not in board:
            board[(col, row)] = color
        history.append((i + 1, col, row))
        if (col, row) in first_at:
            annotations.append(f"{i + 1} at {first_at[(col, row)]}")
        else:
            first_at[(col, row)] = i + 1
 
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
    # ATN MODIFIED BELOW
    # svg.rect(0, 0, WIDTH, HEIGHT, fill='white')
 
    label_size = 36 * U
    # svg.text(WIDTH / 2, 80 * U, f"Solution {problem_num}",
    #          font_size=label_size, font_weight='bold')
 
    _draw_grid(svg, c0, c1, r0, r1, gx0, gy0, cell)
    _draw_stones(svg, board, c0, c1, r0, r1, gx0, gy0, cell, history)
 
    if annotations:
        stone_r = cell * STONE_FRAC
        ann_font = 48 * U
        ann_lh = ann_font * 1.5
        ann_y = gy0 + board_h + stone_r + 48 * U
        for ann in annotations:
            svg.text(WIDTH / 2, ann_y, ann, font_size=ann_font)
            ann_y += ann_lh
 
    return [svg.build()]
 
 
# --- epub building ---
 
CONTAINER_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
 
 
def opf(book_id, title, spine_items):
    manifest = '\n'.join(
        f'    <item id="{sid}" href="pages/{sid}.xhtml" media-type="application/xhtml+xml"/>\n'
        f'    <item id="{sid}-svg" href="images/{sid}.svg" media-type="image/svg+xml"/>'
        for sid in spine_items
    )
    spine = '\n'.join(f'    <itemref idref="{sid}"/>' for sid in spine_items)
 
    if IS_UNIVERSAL:
        layout_meta = ''
    else:
        layout_meta = f'''    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">portrait</meta>
    <meta property="rendition:spread">none</meta>
    <meta property="rendition:viewport">width={WIDTH}; height={HEIGHT}</meta>
    <meta property="rendition:align-x-center">center</meta>'''
 
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">{book_id}</dc:identifier>
    <dc:title>{_esc(title)}</dc:title>
    <dc:language>en</dc:language>
{layout_meta}
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{manifest}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>'''
 
 
def page_xhtml(sid):
    if IS_UNIVERSAL:
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <style>
    html, body {{ margin: 0; padding: 0; background: white; }}
    img {{ display: block; width: 100%; height: auto; }}
  </style>
</head>
<body><img src="../images/{sid}.svg" alt=""/></body>
</html>'''
 
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta name="viewport" content="width={WIDTH}, height={HEIGHT}"/>
  <style>
    html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background: white;
                 display: flex; justify-content: center; align-items: center; }}
    img {{ display: block; width: {WIDTH}px; height: {HEIGHT}px; flex-shrink: 0; }}
  </style>
</head>
<body><img src="../images/{sid}.svg" alt=""/></body>
</html>'''
 
 
def nav_xhtml(title, spine_items, labels):
    items = '\n'.join(
        f'      <li><a href="pages/{sid}.xhtml">{_esc(labels[sid])}</a></li>'
        for sid in spine_items if sid == 'title' or sid.startswith('p'))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{_esc(title)}</title></head>
<body>
  <nav epub:type="toc">
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>'''
 
 
def ncx(book_id, title, spine_items, labels):
    problem_items = [sid for sid in spine_items if sid == 'title' or sid.startswith('p')]
    points = '\n'.join(
        f'''    <navPoint id="np-{i}" playOrder="{i + 1}">
      <navLabel><text>{_esc(labels[sid])}</text></navLabel>
      <content src="pages/{sid}.xhtml"/>
    </navPoint>'''
        for i, sid in enumerate(problem_items)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="{book_id}"/></head>
  <docTitle><text>{_esc(title)}</text></docTitle>
  <navMap>
{points}
  </navMap>
</ncx>'''
 
 
# --- tex parsing ---
 
def parse_tex(tex_path):
    text = tex_path.read_text()
 
    def extract(key):
        m = re.search(rf'\\def\\{key}\{{([^}}]+)\}}', text)
        return decode_latex(m.group(1)) if m else ''
 
    title = extract('entitle') or tex_path.stem
    jp_title = extract('jptitle')
    level = extract('level')
    source = extract('source')
    problems = re.findall(r'\\p\{(\d+)\}\{(\d+)\}', text)
    return title, jp_title, level, source, problems
 
 
# --- main ---
 
def convert_book(tex_path, book_slug):
    title, jp_title, level, source, problem_refs = parse_tex(tex_path)
    print(f"  {title}: {len(problem_refs)} problems")
 
    book_id = f"urn:uuid:{uuid.uuid4()}"
    out_path = OUT_DIR / f"{book_slug}.zip"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
 
    spine_items = []
    # labels = {}   # sid -> human-readable TOC label
    # pages = {}    # sid -> xhtml str
    svgs = {}     # sid -> svg str
 
    # Title page
    spine_items.append('title')
    # labels['title'] = 'Title Page'
    # pages['title'] = page_xhtml('title')
    # svgs['title'] = make_title_svg(title, jp_title, level, len(problem_refs), source)
 
    for prob_num, (chapter_id, problem_id) in enumerate(problem_refs, 1):
        sgf_path = PROBLEMS_DIR / book_slug / chapter_id / f"{problem_id}.sgf"
        sol_path = PROBLEMS_DIR / book_slug / chapter_id / f"{problem_id}.solution"
 
        if not sgf_path.exists():
            print(f"    WARNING: missing {sgf_path}")
            continue
 
        sgf_text = sgf_path.read_text()
        blacks, whites, moves = parse_sgf(sgf_text)
 
        COLS_MAP = list('ABCDEFGHJKLMNOPQRST')
        solution_moves = []
        if sol_path.exists():
            for token in sol_path.read_text().strip().split():
                if len(token) >= 2 and token[0] in COLS_MAP:
                    solution_moves.append((COLS_MAP.index(token[0]), 19 - int(token[1:])))
 
        c0, c1, r0, r1 = compute_viewport(blacks, whites, solution_moves)
 
        # ATN MODIFIED BELOW
        # Problem page
        p_sid = f"p{prob_num:04d}"
        spine_items.append(p_sid)
        # labels[p_sid] = f"Problem {prob_num}"
        # pages[p_sid] = page_xhtml(p_sid)
        svgs[p_sid] = make_problem_svg(blacks, whites, c0, c1, r0, r1, prob_num)
 
        # Solution page(s)
        sol_svg_list = make_solution_svgs(blacks, whites, solution_moves,
                                          c0, c1, r0, r1, prob_num)
        total_sol = len(sol_svg_list)
        for si, sol_svg in enumerate(sol_svg_list):
            s_sid = f"s{prob_num:04d}" if total_sol == 1 else f"s{prob_num:04d}p{si}"
            spine_items.append(s_sid)
            # labels[s_sid] = (f"Solution {prob_num}" if total_sol == 1
            #                  else f"Solution {prob_num} ({si + 1}/{total_sol})")
            # pages[s_sid] = page_xhtml(s_sid)
            svgs[s_sid] = sol_svg
 
    if len(spine_items) <= 1:
        print(f"  SKIP: no problems found")
        return
 
    # ATN MODIFIED BELOW
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # zf.writestr('mimetype', 'application/zip', compress_type=zipfile.ZIP_STORED)

        for sid, svg_data in svgs.items():
            zf.writestr(f'{sid}.svg', svg_data)
 
    size_kb = out_path.stat().st_size // 1024
    print(f"  -> {out_path.name} ({size_kb} KB)")
 
 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('books', nargs='*', help='book slugs to convert (default: all)')
    parser.add_argument('--device', choices=['kindle', 'x4', 'x3', 'universal', 'both', 'all'],
                        default='both',
                        help='target device (both=x3+x4, all=x3+x4+universal)')
    args = parser.parse_args()
 
    # tex_files = sorted(BOOKS_DIR.glob('*.tex'))
    # tex_files = [t for t in tex_files if t.name != 'header.tex']
 
    root = SGF.parse_file(JOSEKI_SGF)

    # if args.books:
    #     names = set(args.books)
    #     tex_files = [t for t in tex_files if t.stem in names]
 
    print(f"Converting katago josekis for tsumegogo ({WIDTH}x{HEIGHT})...")
    print(f"here we go. {JOSEKI_SGF} {root.get_list_property('B')}")
    # for tex_path in tex_files:
    #     convert_book(tex_path, tex_path.stem)

 
if __name__ == '__main__':
    main()
 