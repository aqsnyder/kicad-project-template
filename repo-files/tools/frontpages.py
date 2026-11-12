#!/usr/bin/env python3
"""frontpages: the cover, Architecture, Mechanical and Revision History pages of a board's schematic, and the
"[page] Title" heading on every other sheet.

usage:
  python3 hw/tools/frontpages.py PROJECT_DIR... [--no-render] [--check]
  python3 hw/tools/frontpages.py embed SHEET.kicad_sch IMAGE.png [--box X0,Y0,X1,Y1] [--key NAME]

  PROJECT_DIR   a board folder (hw/main-board): one .kicad_pro, its root sheet and, if there is one, its board
  --no-render   leave the board views on the cover and the architecture drawing as they are (no kicad-cli and
                no browser needed)
  --check       write nothing; exit 1 if a file on disk differs from what a run would write (the CR LF line ends
                that KiCad writes on Windows are no difference). Before a commit or in CI use --check --no-render:
                it does not depend on how a machine renders the board views
  embed         put a PNG into a sheet (the architecture diagram into architecture.kicad_sch): see embed_image()

Close the project in KiCad first. What a run does, in this order:

  project file  adds the text variables the title block shows and the project lacks (TEXT_VARS).
  design sheets every sheet that is not one of the four pages below: the title becomes the sheet's name (the
                words that followed it move to the title block's Comments), a "[page] Title" heading goes at the
                top centre, the drawing moves down by whole 2.54 mm steps if it sits where the heading goes, and
                boxed notes take the colours of the cover's DESIGN CONSIDERATIONS row. A note that "callouts" in
                frontpages.json names becomes a boxed note of the kind given there, where it stands (see "Boxed
                notes" below). No symbol, wire or label changes otherwise: the netlist, every uuid and every
                instance path stay as they are.
  cover         the root sheet, A3: board name, variant, date, revision, the contents table (40 rows, filled from
                the sheets in page order), TOP VIEW and BOTTOM VIEW (kicad-cli pcb render of the board beside the
                project, rendered again on every run), NOTES, the release date and the DESIGN CONSIDERATIONS row.
                The sheet symbols keep their uuid and file and are parked left of the page frame.
  Architecture  architecture.kicad_sch, A3, page 2: the architecture drawing at 1:1, heading above it, its
                footnotes left of the title block (see "The architecture drawing" below). A project without a
                drawing gets a frame that says so, how the sheets connect, the net colour key and the overview.
  Mechanical    mechanical.kicad_sch, A4, last but one: the board outline with its overall dimensions, mounting
                holes and connectors (read from the board file), on a panel also the rails and the tabs with
                stamp holes, then the ordering notes, the stackup and the table of holes and connectors.
  Revision History  revision_history.kicad_sch, A4, the last page: a table, and the overview when the drawing
                has taken the Architecture page.

Pages are numbered Cover, Architecture, the design sheets in the order they had, Mechanical, Revision History.

What the pages say comes from PROJECT_DIR/frontpages.json (every key is optional; a list of strings is joined
into lines):

  comment     one line under NOTES on the cover
  status      DRAFT, PRELIMINARY, CHECKED or RELEASED: that line of the cover's key is drawn dark
  views       [["TOP VIEW", "top"], ["BOTTOM VIEW", "bottom"]]: a title and a side of the board for each box
  architecture  "architecture/main-board_architecture.py": the description of the architecture drawing, a path
              from the board folder (archdiagram.py beside this file draws it)
  overview    the OVERVIEW block: on the Architecture page, or on the Revision History page under a drawing
  sheets      {"Power": "what is on it", ...}: shown in each sheet's box on an Architecture page without a drawing
  titles      {"IO": "Inputs and outputs", ...}: a page title for a sheet whose name is not one (default: the name)
  callouts    {"Power": {"J1: external supply": "critical", ...}, ...}: for a design sheet (by sheet name),
              the first words of a note and the kind of boxed note it becomes: info, bringup, caution, critical
              or layout
  diagram     how the sheets connect, on an Architecture page without a drawing: columns, links, over, outside,
              caption (see sheet_diagram())
  planned     [["Power", "what will be on it"], ...]: sheets that are not drawn yet
  net_colours {"Bus": "I2C, SPI and GPIO", ...}: what a net class is for, in the NET COLOURS key of an
              Architecture page without a drawing (default: schdraw.LEGEND, else the class's patterns)
  ordering    the ORDERING NOTES block on the Mechanical page
  mark        references to draw on the outline besides J<n> and the mounting holes
  labels      {"J1": ["USB", "USB-C socket"], ...}: for a part of the outline, what to write over the board's
              top edge in place of its reference and what to call it in the table (one string: both)
  positions   a line or two under the Mechanical page's table of holes and connectors
  revisions   [[rev, changes, date, fab / status], ...], oldest first
  revisions_note  the note under that table, for a project whose frontpages.json is written by a script (a
              panel generator, say): it says where a row is added. Default: in "revisions" of frontpages.json
  written_by  the script that writes frontpages.json, if one does: the hint below the cover then says to edit
              that script, not the file

Boxed notes. The cover's DESIGN CONSIDERATIONS row is the key to five kinds of boxed note: grey information,
orange bring-up, yellow caution, red critical, blue layout (schdraw.CALLOUT). "callouts" says which notes of a
design sheet are boxed and as what: each entry names a note by the first words of its first line. A plain
note becomes a text box around the same words in the same place (same uuid), with that kind's border and text
colour. A note that is boxed already takes the kind's colours, and a kind word at the start of its title
("CAUTION: HOT SURFACE") is changed to match ("CRITICAL: HOT SURFACE"). After that the box is an ordinary item of
the sheet: move or reword it in KiCad. A run reports an entry that names no note, or two, and a box that lies
over a wire, a symbol or another note, and goes on.

The architecture drawing. With "architecture" in frontpages.json a run renders the description to SVG
(archdiagram.py beside this file; the run stops if the drawing's own check finds anything), writes the SVG
beside the description, and compares it with the one the Architecture page was made from: the page carries
the first 16 digits of the SVG's sha256 in a line below its frame. If they differ, or the page has no drawing,
the SVG is turned into PNGs at 300 px per inch with headless Edge or Chrome (svg2png.py) and embedded at 1:1
with its top left corner at DIAGRAM_AT: the drawing above the title block and its footnotes left of it, cut
where the description's Diagram.split says, so that nothing lies over the title block. If they agree nothing
is rendered and no browser is needed. The drawing shows the page of every sheet, so it is embedded again by
the run that renumbers the pages. The drawing's text is measured with Arial Narrow or Liberation Sans Narrow
(archdiagram.py reads the font file). On a machine with neither, the SVG would come out different with nothing
wrong, so a run does not compare the drawing there: it says so and leaves the page and the SVG as they are.
That keeps --check --no-render usable on any machine, and a panel build does not stop there.

Every item this tool draws carries a uuid that starts with f407a9e5 (uuid5 of a fixed namespace and the item's
name, first group replaced). A run removes the items with that mark and draws them again, so anything a person
adds to these pages in KiCad stays. Edit frontpages.json, not the drawn items. Images put in with embed_image()
start with f407a9e6 and are kept. On the root sheet a first run also removes what an earlier script drew there
(graphics with a version-5 uuid) and the cover that a project made from kicad-project-template 0.2.0 has
(TEMPLATE_COVER: a box of that cover whose words frontpages.json does not carry yet stays, and the run says
so). Two runs give the same bytes, and the cover and the three pages are written in the order KiCad saves a
sheet, so opening and saving them in KiCad changes nothing either.

On a design sheet a run writes the heading as the last item in the file, after the symbols. KiCad lists the
unit uuids of a multi-unit part (an MCU drawn in units) in the netlist in the order its spatial index yields them; an
item loaded before the symbols can change that order, one loaded after them does not. The order is no part of
the design (the board finds the part by any of the uuids, and KiCad itself reorders it when it saves the
sheet), but a strict netlist comparison sees it. When KiCad saves a design sheet it sorts the items and the
heading moves up in the file. A later run leaves a heading that is as it would draw it where KiCad put it, so
saving a sheet in KiCad never makes --check fail.

Standard library, kicad-cli (KICAD_CLI, PATH or the default install folder), schdraw.py and boardgeom.py beside
this file; archdiagram.py and svg2png.py beside it for a project with an architecture drawing. As a module:
build(folder, content=None, render_views=True, check=False) and embed_image(sheet, png, box=None,
key='diagram'); CLEAR_TOP says where a generator may start a sheet's drawing.
"""
import base64
import glob
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boardgeom  # noqa: E402
import schdraw as D  # noqa: E402

S, Sym = D.S, D.Sym

# ---------------------------------------------------------------- ownership
NS = uuid.UUID('5b0b7c1e-2f0a-4d39-9a57-3f6f0e1c8a42')       # never change it: every uuid below hangs on it
OWN = 'f407a9e5'                                             # drawn on every run
KEPT = 'f407a9e6'                                            # put in by embed_image(), kept by a run


def own_uuid(scope, key, mark=OWN):
    """The uuid of the item `key` on the page `scope` ('<project>:<sheet file>')."""
    return mark + str(uuid.uuid5(NS, '%s/%s' % (scope, key)))[8:]


def uuid_of(node):
    u = D.first(node, 'uuid')
    return u[1] if u else ''


def is_own(node, mark=OWN):
    return uuid_of(node).startswith(mark)


# ---------------------------------------------------------------- the template's numbers (mm)
PAGE = D.PAPER
BORDER = 12.0                                    # the inner frame line
TITLE_BLOCK = D.TITLE_BLOCK                      # width, height at the bottom right, from the 10 mm margin
SERIF, SANS = 'Times New Roman', 'Arial'
CRIMSON, BLUE, BLACK = (162, 22, 34), (53, 60, 207), (0, 0, 0)
GREY, PALE, RED = (140, 140, 140), (200, 200, 200), (255, 0, 0)
DOTS = '.' * 43
HEADING_BOX = {'A3': (144.595, 20.32, 130.81, 12.7), 'A4': (83.095, 12.7, 130.81, 12.7)}     # x, y, w, h
CLEAR_TOP = {p: b[1] + b[3] + 2.54 for p, b in HEADING_BOX.items()}     # where a sheet's drawing should start
CLEAR_MIN = {p: b[1] + b[3] for p, b in HEADING_BOX.items()}            # ... and where it may, on a full page
STEP = 2.54                                      # a drawing moves by whole steps of two grid units
PARK = (-43.18, 6.35, 35.56, 5.08, 11.43)        # sheet symbols: x, first y, width, height, pitch
COMPANIONS = (                                   # key, sheet name, file, paper
    ('architecture', 'Architecture', 'architecture.kicad_sch', 'A3'),
    ('mechanical', 'Mechanical', 'mechanical.kicad_sch', 'A4'),
    ('revisions', 'Revision History', 'revision_history.kicad_sch', 'A4'),
)
COVER_TITLE = 'Cover Page'
TEMPLATE_COVER = {                               # what a project made from kicad-project-template 0.2.0 has on its root
    '47593305-817e-4e0a-9afa-ffa460ddffb5': None,            # sheet, by the uuids the template gives them: the
    'c8984b53-81a7-48bf-b099-83cc0dd58338': None,            # board's name and the "Sheets" box (the cover draws
    '27c055a3-b7d7-4904-a625-3e29cec36877': 'revisions',     # both anew), and three boxes whose words this tool
    'e64cb460-4461-47bc-a55b-b973c825fcdc': 'overview',      # shows from that key of frontpages.json. A box goes
    'fe8e1702-2ceb-4baa-bf66-4e05289f4293': 'ordering',      # from the cover once its key is there.
}
TEXT_VARS = (('PROJECT_NAME', 'Project name'), ('REVIEWER', ''), ('VARIANT', ''))   # added when missing
TOOLS = 'hw/tools'                               # where a repository keeps these scripts: the pages say so
SOURCE_NOTE = 'Drawn by %s/frontpages.py from frontpages.json' % TOOLS
STATUS = (
    ('DRAFT', 'early work, expect anything to change.'),
    ('PRELIMINARY', 'drawn in full and close to final, not yet reviewed.'),
    ('CHECKED', 'reviewed. If you find a mistake, tell the designer.'),
    ('RELEASED', 'a board has been ordered from this schematic.'),
)
LEGEND = (                                       # the cover's key to the boxed notes: schdraw.CALLOUT kind, text
    ('info', 'INFORMATION:\nWhat a block is for and where to read more.'),
    ('bringup', 'BRING-UP:\nWhat to measure or try on the bench, and how.'),
    ('caution', 'CAUTION:\nWhat can harm the board or spoil a reading.'),
    ('critical', 'CRITICAL:\nBreak this rule and the board or its data is lost.'),
    ('layout', 'LAYOUT:\nA rule the board layout must keep.'),
)
KIND_WORD = {kind: words.split(':')[0] for kind, words in LEGEND}       # the word a boxed note's title may open with
NOTE_MARGIN = 1.0                                # of a note boxed from "callouts": schdraw.Sheet.callout()'s
NOTE_DROP = 0.25                                 # KiCad draws a box's text that far below a plain text's place
UNITS = frozenset('mm cm m um V mV A mA uA nA mAh Hz kHz MHz GHz pF nF uF R k Ohm kOhm MOhm s ms us ns h % dB dBm '
                  'W mW uW K ppm px mil'.split())  # wrap() never parts a number from one of these
ARCH_BOX = (20.32, 35.56, 399.68, 194.31)        # the frame on an Architecture page that has no drawing yet
DIAGRAM_AT = (20.0, 32.0)                        # top left corner of the architecture drawing on its A3 page
DIAGRAM_KEYS = ('diagram', 'notes')              # its two images: above the title block, left of it
TABS_RED = (200, 30, 30)                         # tabs with stamp holes on the Mechanical page
VIEW_BOX = 77.47                                 # side of the TOP VIEW and BOTTOM VIEW boxes
VIEW_FILL = 70.0                                 # printed side of the square render inside a view box
RENDER_PX = 1100                                 # asked of kicad-cli; the board fills the square's long side
PPI = 300.0                                      # KiCad's resolution for an image that names none
GRAPHICS = ('text', 'text_box', 'polyline', 'rectangle', 'circle', 'arc', 'bezier', 'image', 'table')
FIXED = ('version', 'generator', 'generator_version', 'uuid', 'paper', 'title_block', 'lib_symbols',
         'sheet_instances', 'symbol_instances', 'embedded_fonts', 'embedded_files')
SCALES = (10, 8, 6, 5, 4, 3, 2.5, 2, 1.5, 1, 0.75, 2.0 / 3, 0.5, 0.4, 1.0 / 3, 0.25, 0.2, 0.1)


# ---------------------------------------------------------------- nodes
def rgba(c):
    return (c[0], c[1], c[2], c[3] if len(c) > 3 else 1)


def effects(size, justify='center center', face=None, bold=False, color=None, thickness=None, href=None):
    font = S('font')
    if face:
        font.append(S('face', face))
    font.append(S('size', size, size))
    if thickness:
        font.append(S('thickness', thickness))
    if bold:
        font.append(S('bold', Sym('yes')))
    if color:
        font.append(S('color', *rgba(color)))
    e = S('effects', font)
    just = [Sym(t) for t in justify.split() if t != 'center']
    if just:
        e.append([Sym('justify')] + just)
    if href:
        e.append(S('href', href))
    return e


def stroke(width=0, style='default', color=None):
    s = S('stroke', S('width', width), S('type', Sym(style)))
    if color:
        s.append(S('color', *rgba(color)))
    return s


def fill(color=None):
    if color:
        return S('fill', S('type', Sym('color')), S('color', *rgba(color)))
    return S('fill', S('type', Sym('none')))


def lines_of(value):
    """A frontpages.json text: a string, or a list of lines."""
    if value is None:
        return ''
    return '\n'.join(value) if isinstance(value, (list, tuple)) else str(value)


def wrap(text, width, size=1.27, per_mm=None):
    """Break `text` at spaces so every line fits `width` mm; an item that starts with '- ' hangs by two spaces.

    KiCad wraps a text box itself, but without the hanging indent and without telling how many lines it made.
    Widths are schdraw's estimate of KiCad's own font (per_mm: a flat estimate instead, mm per character).
    A number stays on the line of the unit that follows it ("20 mm").
    """
    def measure(s):
        return len(s) * per_mm if per_mm else D.text_width(s, size)

    out = []
    for para in text.split('\n'):
        body = para.lstrip(' ')
        lead = para[:len(para) - len(body)]
        hang = lead + ('  ' if body.startswith('- ') else '')
        line = ''
        words = []
        for word in body.split(' '):
            if words and re.fullmatch(r'[\d.,x]*\d', words[-1]) and word.rstrip('.,;:)') in UNITS:
                words[-1] += ' ' + word
            else:
                words.append(word)
        for word in words:
            trial = line + ' ' + word if line else lead + word
            if line and measure(trial) > 0.95 * width:
                out.append(line)
                line = hang + word
            else:
                line = trial
        out.append(line)
    return '\n'.join(out)


def text_height(text, size=1.27):
    return size * (1.0 + 1.62 * text.count('\n'))


class Page:
    """The items this tool draws on one sheet. Every item has a name; its uuid follows from the name."""

    def __init__(self, scope):
        self.scope, self.items, self.keys = scope, [], set()

    def uid(self, key, mark=OWN):
        assert key not in self.keys, 'two items are named %r on %s' % (key, self.scope)
        self.keys.add(key)
        return own_uuid(self.scope, key, mark)

    def text(self, key, s, x, y, size=1.27, justify='left bottom', angle=0, **style):
        self.items.append(S('text', s, S('exclude_from_sim', Sym('no')), S('at', D.R(x), D.R(y), angle),
                            effects(size, justify, **style), S('uuid', self.uid(key))))

    def box(self, key, s, x, y, w, h, size=1.27, justify='left top', margin=1.0, border=None, **style):
        """Text wrapped by KiCad in a box. border: (width, line type, colour) or None for no outline."""
        self.items.append(S('text_box', s, S('exclude_from_sim', Sym('no')), S('at', D.R(x), D.R(y), 0),
                            S('size', D.R(w), D.R(h)), S('margins', margin, margin, margin, margin),
                            stroke(*border) if border else stroke(-0.0001, 'default'), fill(),
                            effects(size, justify, **style), S('uuid', self.uid(key))))

    def line(self, key, pts, width=0.15, color=None, style='solid', filled=False):
        node = S('polyline', [Sym('pts')] + [S('xy', D.R(p[0]), D.R(p[1])) for p in pts],
                 stroke(width, style, color))
        if len(pts) > 2:                         # KiCad writes no fill on a two-point line
            node.append(fill(color if filled else None))
        node.append(S('uuid', self.uid(key)))
        self.items.append(node)

    def rect(self, key, x0, y0, x1, y1, width=0.15, color=None, style='solid', fill_color=None):
        self.items.append(S('rectangle', S('start', D.R(x0), D.R(y0)), S('end', D.R(x1), D.R(y1)),
                            stroke(width, style, color), fill(fill_color), S('uuid', self.uid(key))))

    def circle(self, key, cx, cy, r, width=0.15, color=None, style='solid'):
        self.items.append(S('circle', S('center', D.R(cx), D.R(cy)), S('radius', D.R(r)),
                            stroke(width, style, color), fill(), S('uuid', self.uid(key))))

    def arc(self, key, start, mid, end, width=0.15, color=None, style='solid'):
        self.items.append(S('arc', S('start', D.R(start[0]), D.R(start[1])), S('mid', D.R(mid[0]), D.R(mid[1])),
                            S('end', D.R(end[0]), D.R(end[1])), stroke(width, style, color), fill(),
                            S('uuid', self.uid(key))))

    def arrow(self, key, tip, direction, color, length=1.9, half=0.75):
        """A filled triangle with its point at `tip`, pointing 'left', 'right', 'up' or 'down'."""
        dx, dy = D.DIRS[direction]
        bx, by = tip[0] - dx * length, tip[1] - dy * length
        self.line(key, [tip, (bx - dy * half, by + dx * half), (bx + dy * half, by - dx * half), tip],
                  width=0, color=color, filled=True)

    def image(self, key, chunks, cx, cy, scale, mark=OWN):
        node = S('image', S('at', D.R(cx), D.R(cy)))
        if abs(scale - 1.0) > 1e-9:
            node.append(S('scale', round(scale, 6)))
        node += [S('uuid', self.uid(key, mark)), [Sym('data')] + list(chunks)]
        self.items.append(node)

    def table(self, key, x, y, widths, rows, size=1.27, wrap_cols=True, row_h=3.81):
        """A KiCad table with a bold header row. Returns its height. Cells are wrapped to their column here;
        row_h is the height of a one-line row."""
        margin, pitch = 0.9525, size * 1.62
        cells_text = [[wrap(str(c), w - 2 * margin, size) if wrap_cols else str(c) for c, w in zip(row, widths)]
                      for row in rows]
        heights = [D.R(row_h + pitch * max(c.count('\n') for c in row)) for row in cells_text]
        cells = [Sym('cells')]
        cy = y
        for r, row in enumerate(cells_text):
            cx = x
            for c, (s, w) in enumerate(zip(row, widths)):
                cells.append(S('table_cell', s, S('exclude_from_sim', Sym('no')), S('at', D.R(cx), D.R(cy), 0),
                               S('size', D.R(w), heights[r]), S('margins', margin, margin, margin, margin),
                               S('span', 1, 1), fill(), effects(size, 'left top', bold=(r == 0)),
                               S('uuid', self.uid('%s:%d:%d' % (key, r, c)))))
                cx += w
            cy += heights[r]
        self.items.append(S(
            'table', S('column_count', len(widths)),
            S('border', S('external', Sym('yes')), S('header', Sym('yes')), stroke(0, 'solid')),
            S('separators', S('rows', Sym('yes')), S('cols', Sym('yes')), stroke(0, 'solid')),
            [Sym('column_widths')] + [D.R(w) for w in widths], [Sym('row_heights')] + heights,
            S('uuid', self.uid(key)), cells))
        return sum(heights)

    # the block style of the design sheets
    def block(self, key, x0, y0, x1, y1, title, sub=None):
        self.rect(key + ':frame', x0, y0, x1, y1, D.FRAME['width'], D.FRAME['color'], D.FRAME['style'])
        self.heading(key, x0 + 2.0, y0 + 1.6, title, sub)

    def heading(self, key, x, y, title, sub=None):
        self.text(key + ':title', title, x, y, D.HEADING['size'], 'left top', bold=True, color=D.HEADING['color'])
        if sub:
            self.text(key + ':sub', sub, x, y + D.HEADING['size'] + 1.4, D.SUBHEAD['size'], 'left top',
                      color=D.SUBHEAD['color'])

    def text_block(self, key, x, y, w, title, text, h=None):
        """A framed block that holds only text, as high as the text needs (or h). Returns its height."""
        text = wrap(text, w - 4.0 - 2.0)
        need = D.snap(6.0 + 2.0 + text_height(text) + 1.27)
        h = max(h or 0, need)
        self.block(key, x, y, x + w, y + h, title)
        self.box(key + ':text', text, x + 2.0, y + 6.0, w - 4.0, h - 7.0)
        return h


# ---------------------------------------------------------------- files
def read_tree(path):
    tree = D.parse(io.open(path, encoding='utf-8').read())
    assert tree[0] == 'kicad_sch', '%s is not a schematic sheet' % path
    return tree


def dump_image(node):
    """An image as KiCad writes it: the base64 text 76 characters a line."""
    out = ['(image']
    for x in node[1:]:
        if x[0] == 'data':
            chunks = x[1:]
            out.append('\t\t(data "%s"' % chunks[0])
            out += ['\t\t\t"%s"' % c for c in chunks[1:]]
            out.append('\t\t)')
        else:
            out.append('\t\t' + D.dump(x, 2))
    return '\n'.join(out) + '\n\t)'


def sheet_text(tree):
    parts = ['(' + str(tree[0])]
    for x in tree[1:]:
        parts.append('\n\t' + (dump_image(x) if x[0] == 'image' else D.dump(x, 1)))
    return ''.join(parts) + '\n)\n'


def new_tree(file_uuid, paper, title, comments=()):
    return [Sym('kicad_sch'), S('version', Sym('20260306')), S('generator', 'eeschema'),
            S('generator_version', '10.0'), S('uuid', file_uuid), S('paper', paper),
            title_block(title, comments), S('lib_symbols')]


_RANK = {'rectangle': 0, 'circle': 0, 'arc': 0, 'bezier': 0, 'text': 1, 'text_box': 2, 'junction': 3,
         'no_connect': 4, 'bus_entry': 5, 'wire': 6, 'bus': 6, 'image': 7, 'table': 8, 'label': 9,
         'global_label': 10, 'hierarchical_label': 11, 'symbol': 13, 'sheet': 14}


def canonical(tree):
    """Put a sheet's drawing in the order KiCad 10 saves it: by kind of item (shapes, text, text boxes, lines,
    images, tables, sheets), then by uuid. A page this tool owns is written that way, so that opening and
    saving it in KiCad changes nothing in the file. Never used on a sheet with symbols: see append_drawn()."""
    def key(x):
        k = str(x[0])
        if k == 'polyline':                      # two points: a line; more: a shape
            rank = 6 if len(D.find(D.first(x, 'pts'), 'xy')) == 2 else 0
        else:
            rank = _RANK.get(k, 12)
        return (rank, uuid_of(x))

    head, drawn, tail = split(tree)
    assert not any(x[0] == 'symbol' for x in drawn), 'canonical() is for pages without symbols'
    tree[1:] = head + sorted(drawn, key=key) + tail


def title_block(title, comments=()):
    tb = S('title_block', S('title', title), S('date', '${RELEASE_DATE}'), S('rev', '${REVISION}'),
           S('company', '${COMPANY}'))
    for i, c in enumerate(comments):
        tb.append(S('comment', i + 1, c))
    return tb


def set_title(tree, title, comments=None):
    """Set a sheet's title; comments: None keeps what is there."""
    tb = D.first(tree, 'title_block')
    if tb is None:
        tree.insert(next(i for i, x in enumerate(tree) if isinstance(x, list) and x[0] == 'paper') + 1,
                    title_block(title, comments or ()))
        return
    D.put(tb, S('title', title))
    if comments is not None:
        D.drop(tb, 'comment')
        for i, c in enumerate(comments):
            tb.append(S('comment', i + 1, c))


def paper_of(tree):
    p = D.first(tree, 'paper')
    name = str(p[1])
    if name not in PAGE or 'portrait' in p:
        raise RuntimeError('paper %s: this tool knows landscape %s' % (' '.join(str(v) for v in p[1:]),
                                                                       ', '.join(sorted(PAGE))))
    return name


def split(tree):
    """(head, drawn, tail) of a sheet: the fixed nodes before the drawing, the drawing, the fixed nodes after."""
    head, drawn, tail = [], [], []
    for x in tree[1:]:
        k = x[0]
        if k in ('sheet_instances', 'symbol_instances', 'embedded_fonts', 'embedded_files'):
            tail.append(x)
        elif k in FIXED:
            head.append(x)
        else:
            drawn.append(x)
    return head, drawn, tail


def png_size(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise RuntimeError('not a PNG image')
    return struct.unpack('>II', data[16:24])


def png_without_phys(data):
    """The PNG without its pHYs chunk, so that KiCad sizes it at 300 pixels per inch whatever made it."""
    out, pos = [data[:8]], 8
    while pos < len(data):
        n = struct.unpack('>I', data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] != b'pHYs':
            out.append(data[pos:pos + 12 + n])
        pos += 12 + n
    return b''.join(out)


def b64_chunks(data):
    s = base64.b64encode(data).decode('ascii')
    return [s[i:i + 76] for i in range(0, len(s), 76)]


def kicad_cli():
    exe = os.environ.get('KICAD_CLI') or shutil.which('kicad-cli')
    if not exe:
        def version(c):
            return [int(n) for n in re.findall(r'\d+', c.split(os.sep)[-3])]
        for c in sorted(glob.glob(r'C:\Program Files\KiCad\*\bin\kicad-cli.exe'), key=version, reverse=True) + \
                ['/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli']:
            if os.path.exists(c):
                return c
        raise RuntimeError('kicad-cli not found: install KiCad 10, set KICAD_CLI, or pass --no-render')
    return exe


def render(pcb, side, px=RENDER_PX):
    """kicad-cli's view of one side of the board as PNG bytes (a square, transparent around the board), or
    None if it draws nothing. Quality 'basic' gives the same bytes on every run; 'high' does not."""
    tmp = tempfile.mkdtemp(prefix='frontpages_')
    try:
        out = os.path.join(tmp, side + '.png')
        r = subprocess.run([kicad_cli(), 'pcb', 'render', '--side', side, '--quality', 'basic',
                            '--use-board-stackup-colors', '--background', 'transparent', '-w', str(px),
                            '-h', str(px), '--zoom', '1', '-o', out, pcb],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if r.returncode or not os.path.exists(out):
            raise RuntimeError('kicad-cli pcb render failed on %s:\n%s' % (pcb, r.stdout[-1500:]))
        return open(out, 'rb').read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- the project
class Project:
    def __init__(self, folder):
        self.dir = os.path.abspath(folder)
        pros = sorted(glob.glob(os.path.join(self.dir, '*.kicad_pro')))
        if len(pros) != 1:
            raise RuntimeError('%s: expected one .kicad_pro, found %d' % (folder, len(pros)))
        self.pro = pros[0]
        self.name = os.path.basename(self.pro)[:-len('.kicad_pro')]
        self.root = os.path.join(self.dir, self.name + '.kicad_sch')
        pcb = os.path.join(self.dir, self.name + '.kicad_pcb')
        self.pcb = pcb if os.path.exists(pcb) else None
        self.files = {}                          # path -> text to write
        self.notes = []
        self._board = False

    @property
    def board(self):
        """The board beside the project (boardgeom.Board), or None."""
        if self._board is False:
            self._board = boardgeom.Board(self.pcb) if self.pcb else None
        return self._board

    def scope(self, path):
        return '%s:%s' % (self.name, os.path.basename(path))

    def path(self, filename):
        return os.path.join(self.dir, filename)

    def colours(self):
        """{net class: (r, g, b)} of the classes that carry a schematic colour."""
        out = {}
        pro = json.load(io.open(self.pro, encoding='utf-8'))
        for cl in pro.get('net_settings', {}).get('classes', []):
            m = re.match(r'rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)', cl.get('schematic_color', ''))
            if m and cl['name'] != 'Default' and float(m.group(4) or 1):
                out[cl['name']] = tuple(int(v) for v in m.group(1, 2, 3))
        return out

    def classes(self):
        """[(net class, (r, g, b), [name patterns])] of the classes that carry a schematic colour, by priority."""
        pro = json.load(io.open(self.pro, encoding='utf-8'))
        ns = pro.get('net_settings', {})
        colours = self.colours()
        order = sorted((cl.get('priority', 0), i, cl['name']) for i, cl in enumerate(ns.get('classes', [])))
        return [(name, colours[name], [p['pattern'] for p in ns.get('netclass_patterns') or []
                                       if p.get('netclass') == name])
                for _, _, name in order if name in colours]

    def text_variables(self):
        """Add the title block's variables that the project lacks. Returns the names added. A project file that
        has them all is left alone, whoever wrote it last (KiCad's own JSON layout need not be Python's)."""
        raw = io.open(self.pro, encoding='utf-8', newline='').read()
        pro = json.loads(raw)
        tv = pro.setdefault('text_variables', {})
        added = [k for k, _ in TEXT_VARS if k not in tv]
        if not added:
            return added
        for k, v in TEXT_VARS:
            tv.setdefault(k, v)
        pro['text_variables'] = {k: tv[k] for k in sorted(tv)}
        self.files[self.pro] = json.dumps(pro, indent=2) + '\n'
        return added


def sheet_props(node):
    return {p[1]: p for p in D.find(node, 'property')}


def sheet_page(node):
    inst = D.first(D.first(D.first(node, 'instances'), 'project'), 'path')
    return D.first(inst, 'page')


def park(node, i, project, root_uuid, page):
    """Put a sheet symbol in its parking place left of the page frame; set its page number."""
    x, y0, w, h, pitch = PARK
    y = y0 + pitch * i
    if D.find(node, 'pin'):                      # a sheet with pins is wired on the root sheet: leave it there
        set_page(node, project, root_uuid, page)
        return False
    D.put(node, S('at', D.R(x), D.R(y)))
    D.put(node, S('size', w, h))
    D.drop(node, 'fields_autoplaced')
    D.put(node, stroke(0.1524, 'solid'))
    D.put(node, S('fill', S('color', 0, 0, 0, 0)))
    props = sheet_props(node)
    for name, px, py, eff in (
            ('Sheetname', x, y - 1.0291, effects(3, 'left bottom', face=SERIF, bold=True, color=BLACK)),
            ('Sheetfile', x + 1.27, y + 1.27, effects(1.27, 'left top', face=SANS))):
        p = props[name]
        p[3:] = [S('at', D.R(px), D.R(py), 0), S('show_name', Sym('no')), S('do_not_autoplace', Sym('no')), eff]
    set_page(node, project, root_uuid, page)
    return True


def set_page(node, project, root_uuid, page):
    """Set the page of a sheet symbol in this project (its other instances stay)."""
    inst = D.first(node, 'instances')
    if inst is None:
        inst = S('instances')
        node.append(inst)
    proj = next((p for p in D.find(inst, 'project') if p[1] == project), None)
    if proj is None:
        proj = S('project', project)
        inst.append(proj)
    path = next((q for q in D.find(proj, 'path') if q[1] == '/' + root_uuid), None)
    if path is None:
        proj[2:] = [S('path', '/' + root_uuid, S('page', str(page)))]
    else:
        D.put(path, S('page', str(page)))


def new_sheet_symbol(project, name, filename):
    eff = effects(1.27, 'left bottom')
    return S('sheet', S('at', 0, 0), S('size', 10, 10), S('exclude_from_sim', Sym('no')), S('in_bom', Sym('yes')),
             S('on_board', Sym('yes')), S('dnp', Sym('no')), stroke(0.1524, 'solid'),
             S('fill', S('color', 0, 0, 0, 0)), S('uuid', own_uuid(project, 'sheet:' + filename)),
             S('property', 'Sheetname', name, S('at', 0, 0, 0), eff),
             S('property', 'Sheetfile', filename, S('at', 0, 0, 0), eff))


# ---------------------------------------------------------------- design sheets
def _justify(node):
    eff = D.first(node, 'effects')
    just = D.first(eff, 'justify') if eff else None
    words = [str(w) for w in just[1:]] if just else []
    h = next((w for w in words if w in ('left', 'right')), 'center')
    v = next((w for w in words if w in ('top', 'bottom')), 'center')
    font = D.first(eff, 'font') if eff else None
    size = float(D.first(font, 'size')[1]) if font and D.first(font, 'size') else 1.27
    bold = bool(font and D.first(font, 'bold'))
    return h, v, size, bold


def _points(node, out):
    for x in node:
        if isinstance(x, list) and x:
            if x[0] in ('at', 'xy', 'start', 'end', 'mid', 'center') and len(x) >= 3:
                out.append((float(x[1]), float(x[2])))
            else:
                _points(x, out)


def extents(tree):
    """[(what, (x0, y0, x1, y1))] of everything drawn on a sheet, without this tool's own items. Text sizes are
    estimates; frames, wires and symbol bodies are exact."""
    libs_node = D.first(tree, 'lib_symbols')
    libs = {s[1]: s for s in D.find(libs_node, 'symbol')} if libs_node else {}
    out = []
    for x in split(tree)[1]:
        k = str(x[0])
        if is_own(x) or is_own(x, KEPT):
            continue
        box = None
        if k == 'rectangle':
            a, b = D.first(x, 'start'), D.first(x, 'end')
            box = (float(a[1]), float(a[2]), float(b[1]), float(b[2]))
        elif k == 'text_box':
            a, s = D.first(x, 'at'), D.first(x, 'size')
            box = (float(a[1]), float(a[2]), float(a[1]) + float(s[1]), float(a[2]) + float(s[2]))
        elif k == 'sheet':
            a, s = D.first(x, 'at'), D.first(x, 'size')
            box = (float(a[1]), float(a[2]) - 2.5, float(a[1]) + float(s[1]), float(a[2]) + float(s[2]) + 2.5)
        elif k == 'text':
            a = D.first(x, 'at')
            h, v, size, bold = _justify(x)
            box = D.text_box(x[1], float(a[1]), float(a[2]), size, h, v, int(float(a[3])) if len(a) > 3 else 0,
                             bold)
        elif k in ('label', 'global_label', 'hierarchical_label'):
            a = D.first(x, 'at')
            px, py, ang = float(a[1]), float(a[2]), int(float(a[3])) if len(a) > 3 else 0
            _, _, size, _ = _justify(x)
            w = D.text_width(x[1], size) + (0 if k == 'label' else size * 2.2)
            dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}.get(ang % 360, (1, 0))
            box = (min(px, px + dx * w) - abs(dy) * size, min(py, py + dy * w) - abs(dx) * size * 1.3,
                   max(px, px + dx * w) + abs(dy) * size, max(py, py + dy * w) + abs(dx) * size)
        elif k == 'circle':
            c, r = D.first(x, 'center'), float(D.first(x, 'radius')[1])
            box = (float(c[1]) - r, float(c[2]) - r, float(c[1]) + r, float(c[2]) + r)
        elif k == 'symbol':
            name = D.first(x, 'lib_name')
            lib = libs.get(name[1] if name else D.first(x, 'lib_id')[1])
            a = D.first(x, 'at')
            px, py = float(a[1]), float(a[2])
            pts = [(px, py)]
            if lib is not None:
                unit = int(D.first(x, 'unit')[1]) if D.first(x, 'unit') else 1
                mir = D.first(x, 'mirror')
                m = D.matrix(int(float(a[3])) % 360 if len(a) > 3 else 0, str(mir[1]) if mir else None)
                bx0, by0, bx1, by1 = D.sym_box(lib, unit)
                corners = [(cx, cy) for cx in (bx0, bx1) for cy in (by0, by1)]
                corners += [(p['x'], p['y']) for p in D.sym_pins(lib, unit)]
                for cx, cy in corners:
                    dx, dy = D.apply(m, cx, -cy)
                    pts.append((px + dx, py + dy))
            for p in D.find(x, 'property'):
                hide = D.first(p, 'hide')
                if hide is not None and hide[1] == 'yes':
                    continue
                pa = D.first(p, 'at')
                if pa is not None and p[2]:
                    w = D.text_width(p[2], 1.27)
                    fx, fy = float(pa[1]), float(pa[2])
                    if len(pa) > 3 and int(float(pa[3])) % 180 == 90:
                        pts += [(fx - 1.0, fy - w), (fx + 1.0, fy + w)]
                    else:
                        pts += [(fx - w, fy - 1.0), (fx + w, fy + 1.0)]
            box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        else:
            pts = []
            _points(x, pts)
            if pts:
                box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts),
                       max(p[1] for p in pts))
        if box:
            out.append((k, (min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3]))))
    return out


def title_rect(paper):
    w, h = PAGE[paper]
    return (w - 10.0 - TITLE_BLOCK[0], h - 10.0 - TITLE_BLOCK[1], w - 10.0, h - 10.0)


def off_page(boxes, paper, dy=0.0):
    """What would lie over the title block or below the frame after moving down by dy: a list of words."""
    w, h = PAGE[paper]
    tb = title_rect(paper)
    bad = []
    for what, b in boxes:
        y0, y1 = b[1] + dy, b[3] + dy
        if y1 > h - BORDER + 1e-6:
            bad.append('%s below the frame (y %.2f)' % (what, y1))
        elif b[2] > tb[0] + 1e-6 and y1 > tb[1] + 1e-6 and b[0] < tb[2] and y0 < tb[3]:
            bad.append('%s over the title block (x %.2f to %.2f, y to %.2f)' % (what, b[0], b[2], y1))
    return bad


def shift_down(tree, dy):
    """Move everything drawn on a sheet down by dy (this tool's own items stay)."""
    def walk(node):
        for x in node:
            if isinstance(x, list) and x:
                if x[0] in ('at', 'xy', 'start', 'end', 'mid', 'center') and len(x) >= 3:
                    x[2] = Sym(D.fmt(D.R(float(x[2]) + dy)))
                else:
                    walk(x)

    for x in split(tree)[1]:
        if not (is_own(x) or is_own(x, KEPT)):
            walk([x])


def restyle_callouts(tree):
    """Boxed notes in the colours they had before the cover carried its key take schdraw.CALLOUT's. Returns
    how many changed."""
    n = 0
    for x in D.find(tree, 'text_box'):
        st = D.first(x, 'stroke')
        col = D.first(st, 'color') if st else None
        if col is None or float(D.first(st, 'width')[1]) <= 0:
            continue
        kind = D.CALLOUT_WAS.get(tuple(int(float(v)) for v in col[1:4]))
        if kind is None:
            continue
        colour, width, tcol, bold = D.CALLOUT[kind]
        before = D.dump(x)
        D.put(x, stroke(width, 'solid', colour))
        if tcol:
            font = D.first(D.first(x, 'effects'), 'font')
            D.put(font, S('color', *rgba(tcol)))
        n += D.dump(x) != before
    return n


def note_title(text):
    """The first line of a note, without the kind word a boxed note's title may open with ("CAUTION: ")."""
    line = text.split('\n')[0].strip()
    for word in KIND_WORD.values():
        if line.startswith(word + ':'):
            return line[len(word) + 1:].strip()
    return line


def _rect_of(x):
    """(x0, y0, x1, y1) of a text box or a rectangle."""
    if x[0] == 'rectangle':
        a, b = D.first(x, 'start'), D.first(x, 'end')
        r = (float(a[1]), float(a[2]), float(b[1]), float(b[2]))
    else:
        a, s = D.first(x, 'at'), D.first(x, 'size')
        r = (float(a[1]), float(a[2]), float(a[1]) + float(s[1]), float(a[2]) + float(s[2]))
    return (min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3]))


def in_the_way(tree, node):
    """What lies under the border or inside a boxed note, as a list of words: wires, symbol bodies with their
    pins, labels, other notes. A frame around the note is not in its way, and a symbol's fields are not looked
    at (their place depends on how the symbol is turned)."""
    half = max(float(D.first(D.first(node, 'stroke'), 'width')[1]), 0.0) / 2
    r = _rect_of(node)
    r = (r[0] - half, r[1] - half, r[2] + half, r[3] + half)
    libs_node = D.first(tree, 'lib_symbols')
    libs = {s[1]: s for s in D.find(libs_node, 'symbol')} if libs_node else {}
    out = []
    for x in split(tree)[1]:
        k = str(x[0])
        if x is node or is_own(x) or is_own(x, KEPT):
            continue
        what, b = None, None
        if k in ('rectangle', 'text_box'):
            b = _rect_of(x)
            if b[0] <= r[0] and b[1] <= r[1] and b[2] >= r[2] and b[3] >= r[3]:
                continue                         # a frame around it
            what = 'the note "%s"' % note_title(x[1])[:30] if k == 'text_box' else 'a frame'
        elif k == 'text':
            a = D.first(x, 'at')
            h, v, size, bold = _justify(x)
            b = D.text_box(x[1], float(a[1]), float(a[2]), size, h, v, int(float(a[3])) if len(a) > 3 else 0, bold)
            what = 'the note "%s"' % x[1].split('\n')[0][:30]
        elif k in ('wire', 'bus', 'polyline'):
            pts = []
            _points(x, pts)
            b = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            what = 'a line' if k == 'polyline' else 'a wire'
        elif k in ('label', 'global_label', 'hierarchical_label'):
            a = D.first(x, 'at')
            b = (float(a[1]) - 0.5, float(a[2]) - 0.5, float(a[1]) + 0.5, float(a[2]) + 0.5)
            what = 'the label %s' % x[1]
        elif k == 'symbol':
            name = D.first(x, 'lib_name')
            lib = libs.get(name[1] if name else D.first(x, 'lib_id')[1])
            a = D.first(x, 'at')
            pts = [(float(a[1]), float(a[2]))]
            if lib is not None:
                unit = int(D.first(x, 'unit')[1]) if D.first(x, 'unit') else 1
                mir = D.first(x, 'mirror')
                m = D.matrix(int(float(a[3])) % 360 if len(a) > 3 else 0, str(mir[1]) if mir else None)
                bx0, by0, bx1, by1 = D.sym_box(lib, unit)
                for cx, cy in [(cx, cy) for cx in (bx0, bx1) for cy in (by0, by1)] + \
                        [(p['x'], p['y']) for p in D.sym_pins(lib, unit)]:
                    dx, dy = D.apply(m, cx, -cy)
                    pts.append((pts[0][0] + dx, pts[0][1] + dy))
            b = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
            ref = next((p[2] for p in D.find(x, 'property') if p[1] == 'Reference'), '?')
            what = 'the symbol %s' % ref
        if b and b[0] < r[2] and b[2] > r[0] and b[1] < r[3] and b[3] > r[1]:
            out.append(what)
    return out


def boxed_notes(tree, wanted, where, notes):
    """frontpages.json "callouts" for one design sheet: {the first words of a note: kind}. Each named note becomes
    a boxed note of that kind (schdraw.CALLOUT), where it stands: see "Boxed notes" in the module's text.
    Returns what was done, for the run's report; what a person should look at goes to `notes`."""
    did = []
    for words, kind in wanted.items():
        if kind not in D.CALLOUT:
            raise RuntimeError('frontpages.json "callouts": "%s" is no kind of boxed note (use %s)'
                               % (kind, ', '.join(D.CALLOUT)))
        colour, width, tcol, bold = D.CALLOUT[kind]
        hits = [x for x in split(tree)[1] if x[0] in ('text', 'text_box') and not (is_own(x) or is_own(x, KEPT))
                and note_title(x[1]).startswith(note_title(words))]
        if len(hits) != 1:
            notes.append('%s: "callouts" names a note that starts with "%s": %s' % (
                where, words, 'no note does' if not hits else '%d notes do' % len(hits)))
            continue
        x = hits[0]
        before = D.dump(x)
        if x[0] == 'text':                       # a plain note: a box around the same words, in the same place
            at = D.first(x, 'at')
            if len(at) > 3 and int(float(at[3])) % 360:
                notes.append('%s: the note "%s" is turned: box it in KiCad' % (where, words))
                continue
            h, v, size, _ = _justify(x)
            x0, y0, _x1, _y1 = D.text_box(x[1], float(at[1]), float(at[2]), size, h, v)
            wide = max(D.text_width(ln, size) for ln in x[1].split('\n'))
            m = NOTE_MARGIN
            x[:] = S('text_box', x[1], S('exclude_from_sim', Sym('no')),
                     S('at', D.R(x0 - m), D.R(y0 - m - NOTE_DROP), 0),
                     S('size', D.R(wide * 1.03 + 0.6 + 2 * m), D.R(text_height(x[1], size) + 0.45 + 2 * m)),
                     S('margins', m, m, m, m), stroke(width, 'solid', colour), fill(),
                     effects(size, 'left top', bold=bold, color=tcol), D.first(x, 'uuid'))
        else:                                    # boxed already: the kind's colours, and its word in the title
            lines = x[1].split('\n')
            for other in KIND_WORD.values():
                if other != KIND_WORD[kind] and lines[0].startswith(other + ':'):
                    lines[0] = KIND_WORD[kind] + lines[0][len(other):]
            x[1] = '\n'.join(lines)
            D.put(x, stroke(width, 'solid', colour))
            font = D.first(D.first(x, 'effects'), 'font')
            kept = {str(c[0]): c for c in font[1:]}
            font[1:] = [kept[k] for k in ('face', 'size', 'thickness') if k in kept] + \
                ([S('bold', Sym('yes'))] if bold else []) + [kept[k] for k in ('italic',) if k in kept] + \
                ([S('color', *rgba(tcol))] if tcol else []) + [kept[k] for k in ('line_spacing',) if k in kept]
        if D.dump(x) != before:
            did.append('note "%s" boxed as %s' % (words, kind))
        under = in_the_way(tree, x)
        if under:
            notes.append('%s: the boxed note "%s" lies over %s: move it in KiCad' % (
                where, words, ', '.join(sorted(set(under)))))
    return did


def heading_node(scope, paper):
    x, y, w, h = HEADING_BOX[paper]
    return S('text_box', '[${#}] ${TITLE}', S('exclude_from_sim', Sym('no')), S('at', D.R(x), D.R(y), 0),
             S('size', w, h), S('margins', 5.9999, 5.9999, 5.9999, 5.9999), stroke(-0.0001, 'solid'), fill(),
             effects(6, face=SERIF, bold=True, thickness=1.2, color=CRIMSON), S('uuid', own_uuid(scope, 'heading')))


def insert_drawn(tree, nodes):
    """Add drawing items to a sheet where KiCad keeps graphics: before the wires, labels, symbols and sheets."""
    later = ('wire', 'bus', 'bus_entry', 'label', 'global_label', 'hierarchical_label', 'netclass_flag',
             'rule_area', 'symbol', 'sheet', 'sheet_instances', 'symbol_instances', 'embedded_fonts',
             'embedded_files')
    at = next((i for i, x in enumerate(tree) if isinstance(x, list) and x[0] in later), len(tree))
    tree[at:at] = nodes


def append_drawn(tree, nodes):
    """Add drawing items to a sheet as the last things drawn, after its symbols.

    The heading goes into a design sheet this way. KiCad lists the units of a multi-unit part in the netlist in
    the order its spatial index yields them, and an item loaded before the symbols can change that order (the
    uuids stay the same, their order in the netlist does not). Loaded last, the heading leaves it alone.
    """
    tail = ('sheet_instances', 'symbol_instances', 'embedded_fonts', 'embedded_files')
    at = next((i for i, x in enumerate(tree) if isinstance(x, list) and x[0] in tail), len(tree))
    tree[at:at] = nodes


def design_sheet(prj, path, name, callouts=None):
    """Title, heading, room for the heading, note colours and the notes that frontpages.json "callouts" boxes
    ({first words: kind} for this sheet). Returns what was done, for the run's report."""
    tree = read_tree(path)
    paper = paper_of(tree)
    did = []
    tb = D.first(tree, 'title_block')
    old = D.first(tb, 'title')[1] if tb and D.first(tb, 'title') else ''
    comments = None
    if old != name:
        rest = old[len('${BOARD_NAME}: '):] if old.startswith('${BOARD_NAME}: ') else old
        if rest and rest != name and not (tb and D.find(tb, 'comment')):
            comments = wrap(rest[0].upper() + rest[1:], 31.0, per_mm=0.9).split('\n')[:4]
        did.append('title "%s"' % name)
    set_title(tree, name, comments)
    # The heading: one that is there and is as this run would draw it stays where it is in the file. KiCad sorts
    # a sheet's items when it saves, which moves the heading up; moving it back would change the file after
    # every save in KiCad. Anything else of this tool's goes, and the heading is written last (append_drawn()).
    heading = heading_node(prj.scope(path), paper)
    own = [x for x in tree if isinstance(x, list) and is_own(x)]
    if [D.dump(x) for x in own] != [D.dump(heading)]:
        tree[:] = [x for x in tree if not (isinstance(x, list) and is_own(x))]
        append_drawn(tree, [heading])
    n = restyle_callouts(tree)
    if n:
        did.append('%d boxed note%s recoloured' % (n, '' if n == 1 else 's'))
    did += boxed_notes(tree, callouts or {}, os.path.basename(path), prj.notes)
    boxes = extents(tree)
    if boxes:
        top = min(b[1] for _, b in boxes)
        for target in (CLEAR_TOP[paper], CLEAR_MIN[paper]):
            dy = math.ceil((target - top) / STEP - 1e-9) * STEP
            if dy <= 0:
                break
            bad = off_page(boxes, paper, dy)
            if not bad:
                shift_down(tree, dy)
                did.append('drawing moved down %.2f mm' % dy)
                break
        else:
            raise RuntimeError('%s: no room for the heading. The drawing starts at y %.2f and cannot move down: '
                               '%s. Use a larger paper or redraw the sheet below y %.2f.'
                               % (os.path.basename(path), top, bad[0], CLEAR_MIN[paper]))
        for b in off_page(extents(tree), paper):
            prj.notes.append('%s: %s' % (os.path.basename(path), b))
    prj.files[path] = sheet_text(tree)
    return did


# ---------------------------------------------------------------- the cover
def cover(prj, content, pages, renders):
    """The items of the cover page. pages: [(number, title)]. renders: {side: PNG bytes or None}."""
    pg = Page(prj.scope(prj.root))
    big = dict(face=SERIF, bold=True, thickness=1, color=CRIMSON)
    pg.text('board-name', '${BOARD_NAME}', 25.4, 40.64, 11, **big)
    pg.text('variant', 'Variant: ${VARIANT}', 25.4, 58.42, 8, **big)
    pg.text('date', '${CURRENT_DATE}', 388.62, 40.64, 11, 'right bottom', **big)
    pg.text('revision', 'Rev ${REVISION}', 388.62, 58.42, 11, 'right bottom', **big)

    # contents: four columns of ten rows
    assert len(pages) <= 40, 'the contents table holds 40 pages, the project has %d' % len(pages)
    names = dict(pages)
    for col in range(4):
        xp, xi = 35.56 + 99.06 * col, 45.72 + 99.06 * col
        pg.text('toc:head-page:%d' % col, 'Page', xp, 71.12, 4, 'right bottom', face=SERIF, bold=True, color=BLACK)
        pg.text('toc:head-index:%d' % col, 'Index', xi, 71.12, 4, face=SERIF, bold=True, color=BLACK)
        pg.line('toc:rule-page:%d' % col, [(xp - 17.78, 73.66), (xp, 73.66)], 1, BLACK, 'dot')
        pg.line('toc:rule-index:%d' % col, [(xi, 73.66), (xi + 60.96, 73.66)], 1, BLACK, 'dot')
        for row in range(10):
            n, y = col * 10 + row + 1, 83.82 + 7.62 * row
            href = '#%d' % n if n in names else None
            pg.text('toc:page:%d' % n, str(n), xp, y, 4, 'right bottom', face=SERIF, color=BLACK, href=href)
            pg.text('toc:index:%d' % n, names.get(n, DOTS), xi, y, 4, face=SERIF, color=BLACK, href=href)

    # the two views of the board
    views = content.get('views') or [['TOP VIEW', 'top'], ['BOTTOM VIEW', 'bottom']]
    assert len(views) <= 2, 'the cover has two view boxes'
    for i, (label, side) in enumerate(views):
        x, y = 26.67 + 101.6 * i, 166.37
        pg.text('view:title:%d' % i, label, x, y, 5, face=SANS, bold=True, color=BLUE)
        pg.box('view:box:%d' % i, '', x, y, VIEW_BOX, VIEW_BOX, 2, 'center center', 1.905, (0, 'solid', None),
               bold=True, thickness=0.508)
        png = renders.get(side)
        if png:
            w, h = png_size(png)
            scale = VIEW_FILL / (max(w, h) / PPI * 25.4)
            pg.image('view:image:%d' % i, b64_chunks(png), x + VIEW_BOX / 2, y + VIEW_BOX / 2, scale)
        else:
            pg.text('view:none:%d' % i, 'No board to draw yet.' if not prj.pcb else
                    'The board has no outline yet.' if not prj.board.bbox else
                    'Not rendered yet: run\n%s/frontpages.py\non the board folder.' % TOOLS,
                    x + VIEW_BOX / 2, y + VIEW_BOX / 2, 3, 'center center', face=SANS, color=GREY)

    # notes
    pg.text('notes:title', 'NOTES', 220.98, 167.005, 5, face=SANS, bold=True, color=BLUE)
    comment = wrap(lines_of(content.get('comment')) or 'Add a comment: "comment" in frontpages.json.', 172.0,
                   per_mm=1.95).split('\n')
    assert len(comment) <= 2, 'the cover comment takes two lines at most: shorten it'
    for i, ln in enumerate(comment):
        pg.text('notes:comment:%d' % i, ln, 222.25, 177.8 - 5.08 * (len(comment) - 1 - i), 3, face=SANS,
                color=BLACK)
    pg.text('notes:dnp', 'Parts that are not fitted (DNP) are crossed out:', 222.25, 187.96, 3, face=SANS,
            color=BLACK)
    pg.line('notes:cross:a', [(317.5, 181.61), (314.96, 187.96)], 1, RED, 'default')
    pg.line('notes:cross:b', [(314.96, 181.61), (317.5, 187.96)], 1, RED, 'default')
    status = (content.get('status') or '').upper()
    assert not status or status in dict(STATUS), 'status %r: use one of %s' % (status, ', '.join(dict(STATUS)))
    for i, (word, what) in enumerate(STATUS):
        pg.text('notes:status:%s' % word.lower(), '%s: %s' % (word, what), 222.25, 198.12 + 6.35 * i, 3,
                face=SERIF, bold=True, thickness=0.6, color=CRIMSON if word == status else GREY)
    pg.text('release-date', '${VARIANT} ${RELEASE_DATE}', 214.376, 237.998, 10.16, face=SERIF, bold=True,
            thickness=0.6, color=PALE)

    # the key to the boxed notes
    pg.text('legend:title', 'DESIGN CONSIDERATIONS', 26.67, 255.27, 1, face=SANS, bold=True, color=BLUE)
    for i, (kind, words) in enumerate(LEGEND):
        colour, _, tcol, bold = D.CALLOUT[kind]
        pg.box('legend:%s' % kind, words, 26.67 + 34.925 * i, 258.445, 30.48, 20.32, 2, 'left top',
               2.25 if bold else 2, (1.5 if bold else 1, 'solid', colour), face=SANS, bold=bold,
               thickness=0.4 if bold else None, color=tcol or BLACK)

    # below the page, for whoever opens the sheet in KiCad
    src = content.get('written_by')          # a script that writes frontpages.json (a panel generator, say)
    pg.box('hint', 'This page is drawn by %s/frontpages.py from frontpages.json beside the project: ' % TOOLS
           + ('%s writes that file on every build, so edit that script' % src if src else 'edit that file')
           + ', not the items here. Board name, revision and dates: File > Schematic Setup > Project > Text '
           'Variables.', 8.89, 300.99, 250.0, 8.89, 1.27, 'left top', 1.0, color=BLACK)
    return pg.items


# ---------------------------------------------------------------- the Architecture page
def sheet_diagram(pg, content, number, real, colours, x0, y0):
    """How the sheets connect, in a band 261.62 mm wide and 40.64 mm high at (x0, y0). number: {sheet name:
    page}; real: the design sheets' names in page order.

    frontpages.json "diagram":
      columns  [["Power", "Debug"], ["MCU"], ["Sensors", "Connectors"]]: sheet names, a column of one or two;
               a sheet alone in its column is drawn as high as two
      links    [[left sheet, right sheet, heads, net class, label], ...]: a line between two sheets of
               neighbouring columns; heads is ">" (left drives right), "<" or "<>"; at most three per sheet
      over     [[from sheet, to sheet, net class, label]]: a line over the top of the columns between them
      outside  [[sheet, heads, name, note, label]]: something that is not a sheet, right of the last column
      caption  one grey line above the diagram
    Without "diagram" the sheets stand in a row; "planned" sheets follow as dashed boxes.
    """
    spec = content.get('diagram') or {}
    what = content.get('sheets') or {}
    titles = content.get('titles') or {}
    link_w, bw, bh, gap_y, sub = 0.4, 40.64, 12.7, 5.08, D.SUBHEAD
    caption = lines_of(spec.get('caption'))
    planned = content.get('planned') or []
    columns = spec.get('columns')
    if not columns:
        if not caption:
            caption = ('The planned sheets, in page order. None is drawn yet.' if planned and not real else
                       'The sheets, in page order.')
        # a planned sheet that has been drawn meanwhile is shown once, as a real one
        boxes = [(name, False) for name in real] + [(p[0], True) for p in planned if p[0] not in real]
        if not boxes:
            return
        pg.text('links:caption', caption, x0, y0, sub['size'], 'left top', color=sub['color'])
        assert len(boxes) <= 8, 'the Architecture page shows eight sheets in a row; name "diagram" columns'
        pitch = (261.62 + 5.08) / max(len(boxes), 5)
        w, bodies = pitch - 5.08, []
        for i, (name, is_planned) in enumerate(boxes):
            words = dict(planned).get(name, '') if is_planned else what.get(name, '')
            bodies.append(('Planned' if is_planned else 'Page %d' % number[name])     # a planned sheet has no page
                          + ('\n' + wrap(words, w - 3.0) if words else ''))
        high = max([bh] + [text_height(b) + 3.0 for b in bodies])
        for i, (name, is_planned) in enumerate(boxes):
            x, y = x0 + i * pitch, y0 + 10.16
            pg.rect('links:box:%s' % name, x, y, x + w, y + high, D.FRAME['width'] if is_planned else 0.1524,
                    D.FRAME['color'] if is_planned else None, D.FRAME['style'] if is_planned else 'solid')
            pg.text('links:name:%s' % name, titles.get(name, name), x, y - 0.7, 1.27)
            pg.text('links:page:%s' % name, bodies[i], x + w / 2, y + high / 2, sub['size'], 'center center',
                    color=sub['color'])
        return

    pg.text('links:caption', caption, x0, y0, sub['size'], 'left top', color=sub['color'])
    ya = y0 + 10.16
    place = {}                                   # sheet -> (x, y, h)
    for c, col in enumerate(columns):
        assert 1 <= len(col) <= 2, 'a column of the diagram holds one or two sheets'
        for r, name in enumerate(col):
            assert name in number, 'diagram: there is no sheet named %s' % name
            high = bh if len(col) == 2 else 2 * bh + gap_y
            place[name] = (x0 + c * (bw + 48.26), ya + r * (bh + gap_y), high)
    for name, (x, y, high) in place.items():
        pg.rect('links:box:%s' % name, x, y, x + bw, y + high, 0.1524, None, 'solid', (255, 255, 194))
        pg.text('links:name:%s' % name, titles.get(name, name), x, y - 0.7, 1.27)
        body = 'Page %d' % number[name]
        if what.get(name):
            body += '\n' + wrap(what[name], bw - 3.0)
        pg.text('links:page:%s' % name, body, x + bw / 2, y + high / 2, sub['size'], 'center center',
                color=sub['color'])
    groups = {}                                  # the lower of the two sheets carries the lines
    for link in spec.get('links') or []:
        a, b = link[0], link[1]
        assert place[b][0] > place[a][0], 'diagram link %s: name the left sheet first' % link
        groups.setdefault(a if place[a][2] <= place[b][2] else b, []).append(link)
    for owner, links in groups.items():
        assert len(links) <= 3, 'diagram: %s carries %d links, three fit' % (owner, len(links))
        pitch = 5.08 if len(links) == 2 else 3.81
        for k, (a, b, heads, cls, label) in enumerate(links):
            y = place[owner][1] + bh / 2 - pitch * (len(links) - 1) / 2 + pitch * k
            xa, xb = place[a][0] + bw, place[b][0]
            colour = colours.get(cls, D.FRAME['color'])
            key = 'links:%s:%s:%d' % (a, b, k)
            pg.line(key, [(xa + (1.6 if '<' in heads else 0), y), (xb - (1.6 if '>' in heads else 0), y)],
                    link_w, colour)
            if '<' in heads:
                pg.arrow(key + ':left', (xa, y), 'left', colour)
            if '>' in heads:
                pg.arrow(key + ':right', (xb, y), 'right', colour)
            assert D.text_width(label) < xb - xa - 3.0, 'diagram label too long for the gap: %s' % label
            pg.text(key + ':label', label, (xa + xb) / 2, y - 0.75, 1.27, 'center bottom')
    for k, (a, b, cls, label) in enumerate(spec.get('over') or []):
        colour = colours.get(cls, D.FRAME['color'])
        xa, xb, yv = place[a][0] + bw / 2, place[b][0] + bw / 2, ya - 5.08
        pg.line('links:over:%d' % k, [(xa, place[a][1]), (xa, yv), (xb, yv), (xb, place[b][1] - 1.6)], link_w,
                colour)
        pg.arrow('links:over:%d:head' % k, (xb, place[b][1]), 'down', colour)
        pg.text('links:over:%d:label' % k, label, xb - bw / 2 - 24.13, yv - 0.75, 1.27, 'center bottom')
    for k, (name, heads, title, note, label) in enumerate(spec.get('outside') or []):
        x, y, high = place[name]
        xe, we = x + bw + 15.24, 27.94
        pg.rect('links:outside:%d' % k, xe, y, xe + we, y + high, D.FRAME['width'], D.FRAME['color'],
                D.FRAME['style'])
        pg.text('links:outside:%d:name' % k, title + ('\n' + note if note else ''), xe + we / 2, y + high / 2,
                sub['size'], 'center center', color=sub['color'])
        colour, ym, key = D.FRAME['color'], y + high / 2, 'links:outside:%d:line' % k
        pg.line(key, [(x + bw + (1.6 if '<' in heads else 0), ym), (xe - (1.6 if '>' in heads else 0), ym)],
                link_w, colour)
        if '<' in heads:
            pg.arrow(key + ':left', (x + bw, ym), 'left', colour)
        if '>' in heads:
            pg.arrow(key + ':right', (xe, ym), 'right', colour)
        pg.text(key + ':label', label, (x + bw + xe) / 2, ym - 0.75, 1.27, 'center bottom')


def net_key(pg, prj, content, x, y, w, h):
    """NET COLOURS: one row per colour of the project's net classes, in the order of their priority; classes
    that share a colour share a row, named in brackets. What a class is for comes from frontpages.json
    "net_colours" ({class: words}), else from schdraw.LEGEND, else the row shows the class's name patterns."""
    words = dict((n, what) for names, what in D.LEGEND for n in names)
    words.update(content.get('net_colours') or {})
    rows = []                                    # [colour, [class names], [patterns]]
    for name, colour, patterns in prj.classes():
        row = next((r for r in rows if r[0] == colour), None)
        if row is None:
            row = [colour, [], []]
            rows.append(row)
        row[1].append(name)
        row[2] += patterns
    pg.block('netkey', x, y, x + w, y + h, 'NET COLOURS', 'A wire takes the colour of its net class.')
    if not rows:
        pg.text('netkey:none', 'The project has no coloured net class.', x + 2.0, y + 11.0, 1.27, 'left center')
    pitch = min(3.81, (h - 12.0) / max(len(rows) - 1, 1))
    for i, (colour, names, patterns) in enumerate(rows):
        row = y + 10.5 + pitch * i
        what = next((words[n] for n in names if words.get(n)), None) or ', '.join(patterns)
        text = '%s (%s)' % (what, ', '.join(names)) if what else ', '.join(names)
        while D.text_width(text) > w - 16.5 and len(text) > 8:      # a long list of patterns is cut short
            text = text[:-5].rstrip(' ,') + ' ...'
        pg.line('netkey:line:%d' % i, [(x + 2.0, row), (x + 12.0, row)], 0.4, colour)
        pg.text('netkey:text:%d' % i, text, x + 14.5, row, 1.27, 'left center')


def stamp_of(path):
    """The sha256 digits an Architecture page carries for the drawing embedded in it, or None."""
    if not os.path.exists(path):
        return None
    m = re.search(r'\(sha256 ([0-9a-f]{16})\)', io.open(path, encoding='utf-8').read())
    return m.group(1) if m else None


def drawing(prj, content, number, render_png, check):
    """The architecture drawing of a project whose frontpages.json names its description ("architecture").

    Renders the description to SVG (the SVG file beside the description is written with the run's other files)
    and decides whether the Architecture page needs it embedded again: see "The architecture drawing" in the
    module's text. Returns None for a project without a description, else a dict:
      source  the SVG's path from the board folder, for the line under the page
      stamp   the sha256 digits of the SVG that is, or after this run will be, on the page (None: unknown)
      shown   whether the page has a drawing after this run
      images  [(key, PNG bytes, (x0, y0, x1, y1))] to embed, or None to keep the images on the page
    """
    name = content.get('architecture')
    if not name:
        return None
    desc = prj.path(name)
    if not os.path.isfile(desc):
        raise RuntimeError('frontpages.json names the architecture description %s: there is no such file' % name)
    import archdiagram
    archdiagram.PAGES[prj.name] = dict(number)   # the pages this run gives the sheets, not those on disk
    hw_before, archdiagram.HW_DIR = archdiagram.HW_DIR, os.path.dirname(prj.dir)
    cache_before, sys.dont_write_bytecode = sys.dont_write_bytecode, True     # no __pycache__ in a board folder
    page = prj.path(COMPANIONS[0][2])
    try:
        d = archdiagram.load(desc)
        keys = DIAGRAM_KEYS if d.split else DIAGRAM_KEYS[:1]
        on_page = all(has_kept_image(page, prj.scope(page), k) for k in keys)
        if archdiagram._face('n') is None:
            # a machine without the font the drawing's text is measured with: its SVG would come out
            # different there with nothing wrong, so the page and the SVG file stay as they are.
            prj.notes.append('the architecture drawing was not compared with %s: this machine has neither Arial '
                             'Narrow nor Liberation Sans Narrow to measure its text' % name)
            return dict(source=os.path.relpath(os.path.join(os.path.dirname(desc), d.name + '.svg'),
                                               prj.dir).replace(os.sep, '/'),
                        stamp=stamp_of(page) if on_page else None, shown=on_page, images=None)
        svg = d.render()
    finally:
        archdiagram.HW_DIR, sys.dont_write_bytecode = hw_before, cache_before
        del archdiagram.PAGES[prj.name]
    if d.issues:
        raise RuntimeError('%s: the drawing\'s check finds %d issue%s:\n  %s' % (
            name, len(d.issues), '' if len(d.issues) == 1 else 's', '\n  '.join(d.issues[:20])))
    svg_path = os.path.join(os.path.dirname(desc), d.name + '.svg')
    prj.files[svg_path] = svg
    stamp = hashlib.sha256(svg.encode('utf-8')).hexdigest()[:16]
    out = dict(source=os.path.relpath(svg_path, prj.dir).replace(os.sep, '/'), stamp=stamp, shown=True,
               images=None)
    if on_page and stamp_of(page) == stamp:
        return out                               # the page has this very drawing
    if check:
        return out                               # the new stamp alone makes the page differ from the file
    if not render_png:
        out['stamp'], out['shown'] = (stamp_of(page), True) if on_page else (None, False)
        prj.notes.append('the architecture drawing on the page is %s: run again without --no-render'
                         % ('not the one %s describes' % name if on_page else 'missing'))
        return out
    import svg2png
    tmp = tempfile.mkdtemp(prefix='frontpages_')
    try:
        src = os.path.join(tmp, d.name + '.svg')
        with io.open(src, 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg)
        if d.split:
            sx, sy = d.split
            crops = [(0, 0, d.W, sy), (0, sy, sx, d.H)]
        else:
            crops = [(0, 0, d.W, d.H)]
        images = []
        for key, crop in zip(keys, crops):
            png = os.path.join(tmp, key + '.png')
            try:
                w, h = svg2png.convert(src, png, dpi=int(PPI), crop=crop, quiet=True)
            except RuntimeError as e:
                raise RuntimeError('%s: the drawing has changed and cannot be rendered: %s' % (name, e))
            x0, y0 = (a + round(c / 25.4 * PPI) / PPI * 25.4 for a, c in zip(DIAGRAM_AT, crop))   # whole pixels
            images.append((key, open(png, 'rb').read(), (x0, y0, x0 + w / PPI * 25.4, y0 + h / PPI * 25.4)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    w, h = PAGE['A3']
    tb = title_rect('A3')
    for key, _png, r in images:
        if r[0] < BORDER or r[1] < BORDER or r[2] > w - BORDER or r[3] > h - BORDER:
            raise RuntimeError('%s: the %s image (x %.1f to %.1f, y %.1f to %.1f mm) leaves the page frame'
                               % ((name, key) + r))
        if r[2] > tb[0] and r[3] > tb[1]:
            raise RuntimeError('%s: the %s image lies over the title block (from x %.0f, y %.0f mm): set '
                               'Diagram.split in the description' % (name, key, tb[0], tb[1]))
    out['images'] = images
    return out


def architecture(prj, content, number, real, has_diagram, picture=None):
    """The items of the Architecture page. has_diagram: an embedded drawing is, or will be, on the page; it is
    placed 1:1 and fills the page down to the title block, so the page then holds the heading, the drawing and
    one line below the frame that says where the drawing comes from. picture: what drawing() returned."""
    pg = Page(prj.scope(prj.path(COMPANIONS[0][2])))
    x0, y0, x1, y1 = ARCH_BOX
    if has_diagram:
        if picture and picture['stamp']:
            pg.box('diagram:stamp', 'The drawing on this page is %s (sha256 %s), rendered from the description '
                   'beside it by %s/archdiagram.py. %s/frontpages.py embeds it again when the '
                   'description gives another SVG: edit the description, not the picture.'
                   % (picture['source'], picture['stamp'], TOOLS, TOOLS), 8.89, 300.99, 250.0, 8.89, 1.27,
                   'left top', 1.0,
                   color=BLACK)
        return pg.items
    pg.rect('placeholder:diagram:frame', x0, y0, x1, y1, D.FRAME['width'], D.FRAME['color'], D.FRAME['style'])
    pg.text('placeholder:diagram:title', 'ARCHITECTURE DIAGRAM: NOT DRAWN YET', (x0 + x1) / 2, (y0 + y1) / 2 - 3.0,
            D.HEADING['size'], 'center bottom', bold=True, color=D.HEADING['color'])
    pg.text('placeholder:diagram:text',
            'Not drawn yet. Describe it in architecture/%s_architecture.py beside the project (%s/'
            'archdiagram.py draws it) and name that file in frontpages.json:\n"architecture": '
            '"architecture/%s_architecture.py". The drawing then takes this page at 1:1: its legend and region '
            'titles stand for the two blocks below, and the overview moves to the Revision History page.'
            % (prj.name, TOOLS, prj.name), (x0 + x1) / 2, (y0 + y1) / 2, 1.27, 'center top',
            color=D.SUBHEAD['color'])
    ya = y1 + 5.08
    sheet_diagram(pg, content, number, real, prj.colours(), x0, ya)
    net_key(pg, prj, content, 289.56, ya, x1 - 289.56, 40.64)
    overview = lines_of(content.get('overview'))
    if overview:
        pg.text_block('overview', x0, 245.11, 195.58, 'OVERVIEW', overview)
    return pg.items


# ---------------------------------------------------------------- the Mechanical page
def scale_name(s):
    return '%g:1' % s if s >= 1 else '1:%g' % round(1 / s, 2)


def outline_drawing(pg, board, extra, labels, x0, y0, x1, y1):
    """The board outline in the box (x0, y0)-(x1, y1), top view, with its two overall dimensions, the mounting
    holes and the connectors; on a panel also two of its rails and its tabs. extra: references to draw besides
    J<n>; labels: {reference: a name to write over the board's top edge in place of the reference, or [that
    name, what to call the part in the table]}. Returns (scale, [table rows])."""
    bx0, by0, bx1, by1 = board.bbox
    bw, bh = bx1 - bx0, by1 - by0
    rails, tabs = board.rails(), board.tabs()
    left, below, pad = 14.0, 13.0, 5.0            # room for the two dimensions and around the drawing
    right = 14.0 if rails else 0.0                # ... for a panel's rail dimension
    above = 4.0 if labels else 0.0                # ... for the names over the top edge
    notes = []                                    # ... and for a line or two under the drawing
    if rails:
        notes.append('Rails: %s (the routed slots stay that far from the edge).' % (
            '%.2f mm on all four sides' % rails[0] if max(rails) - min(rails) < 0.005 else
            'left %.2f, top %.2f, right %.2f, bottom %.2f mm' % rails))
    if tabs:
        notes.append('Red: %d tabs with stamp holes (%s to %s).' % (len(tabs), tabs[0].ref, tabs[-1].ref))
    below += 3.0 * len(notes) + (2.0 if notes else 0.0)
    s = next((v for v in SCALES if bw * v <= x1 - x0 - left - right - 2 * pad
              and bh * v <= y1 - y0 - below - above - 2 * pad), SCALES[-1])
    ox = x0 + left + pad + (x1 - x0 - left - right - 2 * pad - bw * s) / 2
    oy = y0 + above + pad + (y1 - y0 - below - above - 2 * pad - bh * s) / 2
    for i, line in enumerate(notes):
        pg.text('outline:note:%d' % i, line, x0 + 2.0, y1 - 2.0 - 3.0 * (len(notes) - 1 - i), 1.27, 'left bottom',
                color=D.SUBHEAD['color'])

    def at(p):
        return (ox + (p[0] - bx0) * s, oy + (p[1] - by0) * s)

    for f in tabs:                               # under the outline, so the cut lines stay black
        a, b = at(f.box[:2]), at(f.box[2:])
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        hw, hh = max((b[0] - a[0]) / 2, 0.3), max((b[1] - a[1]) / 2, 0.3)
        pg.rect('tab:%s' % f.ref, cx - hw, cy - hh, cx + hw, cy + hh, 0, TABS_RED, 'solid', TABS_RED)

    for i, shape in enumerate(board.outline):
        kind, key = shape[0], 'outline:%d' % i
        if kind == 'line':
            pg.line(key, [at(shape[1]), at(shape[2])], 0.35, BLACK)
        elif kind == 'poly':
            pts = [at(p) for p in shape[1]]
            pg.line(key, pts + pts[:1], 0.35, BLACK)
        elif kind == 'arc':
            pg.arc(key, at(shape[1]), at(shape[2]), at(shape[3]), 0.35, BLACK)
        elif kind == 'circle':
            c = at(shape[1])
            pg.circle(key, c[0], c[1], shape[2] * s, 0.35, BLACK)
    grey, pale, rows = (96, 96, 96), (160, 160, 160), []
    parts = board.connectors(extra)
    under = [at(f.box[:2]) + at(f.box[2:]) for f in parts if f.side == 'bottom']

    def crossed(x, y, half):
        """Does the outline of a bottom-side part run through a name centred at (x, y)?"""
        return any(u[0] < x + half and x - half < u[2] and min(abs(y - u[1]), abs(y - u[3])) < 1.3
                   for u in under)

    for f in parts:
        a, b = at(f.box[:2]), at(f.box[2:])
        half = D.text_width(f.ref) / 2
        fits = b[0] - a[0] > 2 * half + 1.0 and b[1] - a[1] > 2.2
        name = labels.get(f.ref)                 # 'name', or ['on the drawing', 'in the table']
        name, in_table = (name, '%s (%s)' % (name, f.value)) if isinstance(name, str) else \
            (tuple(name) if name else (None, f.value))
        if name:                                 # its name over the board's top edge, in line with the part
            pg.rect('part:%s' % f.ref, a[0], a[1], b[0], b[1], 0.15, pale if f.side == 'bottom' else grey,
                    'dash' if f.side == 'bottom' else 'solid')
            pg.text('part:%s:ref' % f.ref, name, (a[0] + b[0]) / 2, oy - 1.2, 1.27, 'center bottom', bold=True)
        elif f.side == 'bottom':                 # seen through the board: dashed, named in its corner
            pg.rect('part:%s' % f.ref, a[0], a[1], b[0], b[1], 0.15, pale, 'dash')
            pg.text('part:%s:ref' % f.ref, f.ref + ' (bottom)', a[0] + 1.0, a[1] + 1.0, 1.27, 'left top',
                    color=pale)
        else:
            pg.rect('part:%s' % f.ref, a[0], a[1], b[0], b[1], 0.15, grey)
            if fits:
                cx = (a[0] + b[0]) / 2
                cy = next((y for y in ((a[1] + b[1]) / 2, a[1] + 1.8, b[1] - 1.8) if not crossed(cx, y, half)),
                          (a[1] + b[1]) / 2)
                pg.text('part:%s:ref' % f.ref, f.ref, cx, cy, 1.27, 'center center', color=grey)
            else:
                pg.text('part:%s:ref' % f.ref, f.ref, (a[0] + b[0]) / 2, a[1] - 0.5, 1.27, 'center bottom',
                        color=grey)
        rows.append([f.ref, in_table + (' (DNP)' if f.dnp else ''), f.side, '%.2f' % (f.x - bx0),
                     '%.2f' % (by1 - f.y)])
    hole_rows = []
    for f in board.holes():
        c, r = at((f.x, f.y)), max(f.drill, 0.3) * s / 2
        pg.circle('hole:%s' % f.ref, c[0], c[1], r, 0.25, BLACK)
        pg.line('hole:%s:h' % f.ref, [(c[0] - r - 1.0, c[1]), (c[0] + r + 1.0, c[1])], 0.1, grey)
        pg.line('hole:%s:v' % f.ref, [(c[0], c[1] - r - 1.0), (c[0], c[1] + r + 1.0)], 0.1, grey)
        above = c[1] - r - 1.2 - 1.6 > oy          # its name over the hole, between the hole and the board edge
        pg.text('hole:%s:ref' % f.ref, f.ref, c[0] + r + 0.6, c[1] - r - 1.2 if above else c[1] + r + 1.2, 1.27,
                'right bottom' if above else 'right top')
        hole_rows.append([f.ref, '%s, drill %.2f' % (f.value, f.drill), 'through', '%.2f' % (f.x - bx0),
                          '%.2f' % (by1 - f.y)])
    # the two overall dimensions
    xa, xb, ya, yb = ox, ox + bw * s, oy, oy + bh * s
    yd, xd = yb + 8.0, xa - 8.0
    pg.line('dim:w:ext:a', [(xa, yb + 1.5), (xa, yd + 1.5)], 0.1, grey)
    pg.line('dim:w:ext:b', [(xb, yb + 1.5), (xb, yd + 1.5)], 0.1, grey)
    pg.line('dim:w:line', [(xa + 1.6, yd), (xb - 1.6, yd)], 0.15, BLACK)
    pg.arrow('dim:w:left', (xa, yd), 'left', BLACK)
    pg.arrow('dim:w:right', (xb, yd), 'right', BLACK)
    pg.text('dim:w:text', '%.2f' % bw, (xa + xb) / 2, yd - 0.8, 1.6, 'center bottom')
    pg.line('dim:h:ext:a', [(xa - 1.5, ya), (xd - 1.5, ya)], 0.1, grey)
    pg.line('dim:h:ext:b', [(xa - 1.5, yb), (xd - 1.5, yb)], 0.1, grey)
    pg.line('dim:h:line', [(xd, ya + 1.6), (xd, yb - 1.6)], 0.15, BLACK)
    pg.arrow('dim:h:up', (xd, ya), 'up', BLACK)
    pg.arrow('dim:h:down', (xd, yb), 'down', BLACK)
    pg.text('dim:h:text', '%.2f' % bh, xd - 0.8, (ya + yb) / 2, 1.6, 'center bottom', angle=90)
    if rails:                                    # two of a panel's rails, with the arrows outside: they are narrow
        xr, yt = xb + 6.0, ya + rails[1] * s      # the top rail, right of the board
        pg.line('rail:t:ext:a', [(xb + 1.5, ya), (xr + 1.5, ya)], 0.1, grey)
        pg.line('rail:t:ext:b', [(xb + 1.5, yt), (xr + 1.5, yt)], 0.1, grey)
        pg.line('rail:t:line', [(xr, ya - 4.0), (xr, yt + 4.0)], 0.15, BLACK)
        pg.arrow('rail:t:a', (xr, ya), 'down', BLACK)
        pg.arrow('rail:t:b', (xr, yt), 'up', BLACK)
        pg.text('rail:t:text', '%.2f' % rails[1], xr + 1.2, (ya + yt) / 2, 1.27, 'left center')
        yr, xl = yb + 4.0, xa + rails[0] * s      # the left rail, under the board
        pg.line('rail:l:ext:b', [(xl, yb + 1.5), (xl, yr + 1.5)], 0.1, grey)
        pg.line('rail:l:line', [(xa - 4.0, yr), (xl + 4.0, yr)], 0.15, BLACK)
        pg.arrow('rail:l:a', (xa, yr), 'right', BLACK)
        pg.arrow('rail:l:b', (xl, yr), 'left', BLACK)
        pg.text('rail:l:text', '%.2f' % rails[0], xl + 4.8, yr, 1.27, 'left center')
    return s, hole_rows + rows


def mechanical(prj, content):
    pg = Page(prj.scope(prj.path(COMPANIONS[1][2])))
    board = prj.board
    lx0, ly0, lx1, ly1 = 20.32, 27.94, 149.86, 152.4
    rows = []
    if board is not None and board.bbox:
        s, rows = outline_drawing(pg, board, tuple(content.get('mark') or ()), content.get('labels') or {},
                                  lx0, ly0 + 10.0, lx1, ly1)
        pg.block('outline', lx0, ly0, lx1, ly1, 'BOARD OUTLINE',
                 '%s, top view, scale %s. Millimetres; in the table X is from the left edge, Y from the bottom '
                 'edge,\nto the footprint origin (pin 1 of a pin header, not its middle).'
                 % (os.path.basename(prj.pcb), scale_name(s)))
    else:
        pg.block('outline', lx0, ly0, lx1, ly1, 'BOARD OUTLINE',
                 'No board outline yet: draw it on Edge.Cuts and run %s/frontpages.py again.' % TOOLS)
    # the right column: ordering notes, then the stackup
    rx, y = 154.94, ly0
    ordering = lines_of(content.get('ordering'))
    if ordering:
        y += pg.text_block('ordering', rx, y, 127.0, 'ORDERING NOTES', ordering) + 5.08
    if board is not None and board.stackup:
        pg.heading('stackup', rx, y, 'STACKUP')
        names = {'copper': 'copper', 'prepreg': 'prepreg', 'core': 'core'}
        table = [['Layer', 'Type', 'Thickness (mm)', 'Material']]
        total = 0.0
        for layer, kind, thick, material in board.stackup:
            if thick is None:
                continue
            total += thick
            table.append([layer, names.get(kind, 'solder mask' if 'Mask' in kind else kind.lower()),
                          ('%.4f' % thick).rstrip('0').rstrip('.'), material or '-'])
        y += 5.08
        y += pg.table('stackup:table', rx, y, (30.48, 30.48, 30.48, 30.48), table) + 1.27
        pg.text('stackup:note', 'Total %s mm with the solder mask%s. Read from %s (Board Setup, Physical Stackup).'
                % (('%.4f' % total).rstrip('0').rstrip('.'),
                   '; copper finish %s' % board.finish if board.finish else '', os.path.basename(prj.pcb)),
                rx, y, 1.27, 'left top', color=D.SUBHEAD['color'])
        y += 2.54 + 5.08
    # holes and connectors: under the stackup if they fit above the title block, else left of the title block
    if rows:
        table = [['Ref', 'Part', 'Side', 'X (mm)', 'Y (mm)']] + rows
        widths, row_h = (11.43, 26.67, 12.7, 12.7, 12.7), 3.175
        tb_top = PAGE['A4'][1] - 10.0 - TITLE_BLOCK[1]
        room_right = int((tb_top - 1.5 - (y + 3.81)) / row_h) - 1
        room_left = int((PAGE['A4'][1] - BORDER - 1.0 - (157.48 + 3.81)) / row_h) - 1
        if len(rows) <= room_right or room_right >= room_left:
            tx, ty, room = rx, y, room_right
        else:
            tx, ty, room = lx0, 157.48, room_left
        if len(rows) > room:
            prj.notes.append('mechanical: %d holes and connectors, %d fit the table; the rest are in the board file'
                             % (len(rows), max(room, 0)))
            table = table[:max(room, 0) + 1]
        pg.heading('positions', tx, ty, 'HOLES AND CONNECTORS')
        high = 0.0
        if len(table) > 1:
            high = pg.table('positions:table', tx, ty + 3.81, widths, table, wrap_cols=False, row_h=row_h)
        note = lines_of(content.get('positions'))
        if note:
            pg.box('positions:note', note, tx, ty + 3.81 + high + 1.27, 127.0 if tx == rx else sum(widths), 10.16,
                   1.27, 'left top', 0.0, color=D.SUBHEAD['color'])
    elif board is not None and board.bbox:
        pg.heading('positions', rx, y, 'HOLES AND CONNECTORS',
                   'The board has no mounting hole and no connector (J<n>) yet.')
    return pg.items


# ---------------------------------------------------------------- the Revision History page
def revisions(prj, content, with_overview=False):
    """The items of the Revision History page. with_overview: the architecture drawing has the Architecture
    page to itself, so the OVERVIEW block stands here, under the table."""
    pg = Page(prj.scope(prj.path(COMPANIONS[2][2])))
    rows = content.get('revisions') or [['${REVISION}', 'First draft.', '${RELEASE_DATE}', '${FAB}']]
    for r in rows:
        assert len(r) == 4, 'a revision is [rev, changes, date, fab / status]: %r' % (r,)
    x, y = 57.15, 45.72
    widths = (26.67, 83.82, 26.67, 44.45)
    h = pg.table('table', x, y, widths, [['Rev', 'Changes', 'Date', 'Fab / status']] + [list(r) for r in rows])
    # where a row is added: in frontpages.json, unless a script writes that file and says so ("revisions_note")
    note = lines_of(content.get('revisions_note')) or (
        'Oldest first. The rows are the revisions list in frontpages.json beside the project: add one per '
        'revision, then run python3 %s/frontpages.py on the board folder. The newest row may use the text '
        'variables REVISION, RELEASE_DATE and FAB (File > Schematic Setup > Project > Text Variables); write '
        'their values out when the next revision starts.' % TOOLS)
    pg.box('note', note, x, y + h + 2.54, sum(widths), 12.7, 1.27, 'left top', 0.0, color=D.SUBHEAD['color'])
    overview = lines_of(content.get('overview'))
    if with_overview and overview:
        yo = D.snap(y + h + 2.54 + 12.7 + 5.08)
        ho = pg.text_block('overview', x, yo, sum(widths), 'OVERVIEW', overview)
        if yo + ho > title_rect('A4')[1] - 1.0:
            prj.notes.append('revision history: the overview ends at y %.1f mm, over the title block: shorten '
                             'it, or the table' % (yo + ho))
    return pg.items


# ---------------------------------------------------------------- a run
def kept_image(scope, key, png, box):
    """The node of an image that later runs keep: a PNG as large as fits `box`, centred in it. Returns the
    node and the image's rectangle. A resolution stored in the PNG is dropped: the box alone sets the size."""
    x0, y0, x1, y1 = box
    data = png_without_phys(png)
    w, h = png_size(data)
    scale = min((x1 - x0) / (w / PPI * 25.4), (y1 - y0) / (h / PPI * 25.4))
    wm, hm = w / PPI * 25.4 * scale, h / PPI * 25.4 * scale
    pg = Page(scope)
    pg.image('image:' + key, b64_chunks(data), (x0 + x1) / 2, (y0 + y1) / 2, scale, KEPT)
    return pg.items[0], ((x0 + x1 - wm) / 2, (y0 + y1 - hm) / 2, (x0 + x1 + wm) / 2, (y0 + y1 + hm) / 2)


def companion(prj, key, title, filename, paper, items, images=None):
    """Write one of the three pages: what a person drew on it and embedded images stay, the rest is drawn.
    images: [(key, PNG bytes, box)] to put in the place of the kept images of those keys."""
    path = prj.path(filename)
    scope = prj.scope(path)
    if os.path.exists(path):
        tree = read_tree(path)
        D.put(tree, S('paper', paper))
        set_title(tree, title, wrap(SOURCE_NOTE, 31.0, per_mm=0.9).split('\n'))
    else:
        tree = new_tree(own_uuid(prj.name, 'file:' + filename), paper, title,
                        wrap(SOURCE_NOTE, 31.0, per_mm=0.9).split('\n'))
    tree[:] = [x for x in tree if not (isinstance(x, list) and (is_own(x) or x[0] == 'embedded_fonts'))]
    if any(isinstance(x, list) and x[0] == 'symbol' for x in tree):         # (KiCad 10 writes no embedded_fonts)
        raise RuntimeError('%s holds components: keep them on a design sheet, this page is drawn by the tool'
                           % filename)
    if images is not None:
        stale = {own_uuid(scope, 'image:' + k, KEPT) for k in DIAGRAM_KEYS} | \
            {own_uuid(scope, 'image:' + k, KEPT) for k, _png, _box in images}
        tree[:] = [x for x in tree if not (isinstance(x, list) and uuid_of(x) in stale)]
        items = items + [kept_image(scope, k, png, box)[0] for k, png, box in images]
    insert_drawn(tree, [heading_node(scope, paper)] + items)
    canonical(tree)
    prj.files[path] = sheet_text(tree)


def has_kept_image(path, scope, key):
    if not os.path.exists(path):
        return False
    return own_uuid(scope, 'image:' + key, KEPT) in io.open(path, encoding='utf-8').read()


def build(folder, content=None, render_views=True, check=False, quiet=False):
    """Draw the front pages of the project in `folder`. content: a dict instead of folder/frontpages.json.
    Returns the list of files that changed (with check=True: that would change; nothing is written)."""
    prj = Project(folder)
    if content is None:
        cfile = prj.path('frontpages.json')
        content = json.load(io.open(cfile, encoding='utf-8')) if os.path.exists(cfile) else {}
    say = (lambda *a: None) if quiet else print
    added = prj.text_variables()
    if added:
        say('%s: text variables added: %s' % (os.path.basename(prj.pro), ', '.join(added)))

    root = read_tree(prj.root)
    root_uuid = D.first(root, 'uuid')[1]
    head, drawn, tail = split(root)
    if any(x[0] == 'symbol' for x in drawn):
        raise RuntimeError('%s holds components: this tool draws a cover on a root sheet that has none'
                           % os.path.basename(prj.root))
    sheets = [x for x in drawn if x[0] == 'sheet']
    by_file = {sheet_props(s)['Sheetfile'][2]: s for s in sheets}
    design = sorted((s for s in sheets if sheet_props(s)['Sheetfile'][2] not in [c[2] for c in COMPANIONS]),
                    key=lambda s: int(sheet_page(s)[1]))
    comp = {}
    for key, title, filename, paper in COMPANIONS:
        node = by_file.get(filename)
        if node is None:
            node = new_sheet_symbol(prj.name, title, filename)
            say('%s: new sheet %s' % (os.path.basename(prj.root), filename))
        sheet_props(node)['Sheetname'][2] = title
        comp[key] = node
    order = [comp['architecture']] + design + [comp['mechanical'], comp['revisions']]
    titles = content.get('titles') or {}         # a page title that differs from the sheet's name
    pages, number = [(1, COVER_TITLE)], {}
    for i, node in enumerate(order):
        name = sheet_props(node)['Sheetname'][2]
        if not park(node, i, prj.name, root_uuid, i + 2):
            prj.notes.append('sheet %s has pins: left where it is on the cover' % name)
        number[name] = i + 2
        pages.append((i + 2, titles.get(name, name) if node in design else name))

    callouts = content.get('callouts') or {}     # {sheet name: {first words of a note: kind of boxed note}}
    for name in callouts:
        if name not in [sheet_props(n)['Sheetname'][2] for n in design]:
            prj.notes.append('"callouts" names the sheet %s: the project has no design sheet of that name' % name)
    for node in design:
        props = sheet_props(node)
        name = props['Sheetname'][2]
        did = design_sheet(prj, prj.path(props['Sheetfile'][2]), titles.get(name, name), callouts.get(name))
        say('%s: page %s%s' % (props['Sheetfile'][2], sheet_page(node)[1], ''.join(', ' + d for d in did)))

    arch_path = prj.path(COMPANIONS[0][2])
    picture = drawing(prj, content, number, render_views, check)
    if picture and picture['images']:
        say('%s: architecture drawing %s embedded (sha256 %s)' % (COMPANIONS[0][2], picture['source'],
                                                                 picture['stamp']))
    has_diagram = picture['shown'] if picture else has_kept_image(arch_path, prj.scope(arch_path), 'diagram')
    companion(prj, *COMPANIONS[0], architecture(prj, content, number,
                                                [sheet_props(n)['Sheetname'][2] for n in design], has_diagram,
                                                picture), images=picture['images'] if picture else None)
    companion(prj, *COMPANIONS[1], mechanical(prj, content))
    companion(prj, *COMPANIONS[2], revisions(prj, content, with_overview=has_diagram))

    # the cover: what a person drew stays; this tool's items and an earlier script's go
    renders, old_images = {}, {uuid_of(x): x for x in drawn if x[0] == 'image'}
    views = content.get('views') or [['TOP VIEW', 'top'], ['BOTTOM VIEW', 'bottom']]
    for i, (_, side) in enumerate(views):
        if not prj.pcb:
            continue
        if render_views:
            if prj.board.bbox:
                renders[side] = render(prj.pcb, side)
        else:
            old = old_images.get(own_uuid(prj.scope(prj.root), 'view:image:%d' % i))
            if old is not None:
                renders[side] = base64.b64decode(''.join(D.first(old, 'data')[1:]))
    kept, gone = [], 0
    for x in drawn:
        if x[0] == 'sheet' or is_own(x):
            continue
        if x[0] in GRAPHICS and uuid_of(x)[14:15] == '5' and not is_own(x, KEPT):
            gone += 1
            continue
        if uuid_of(x) in TEMPLATE_COVER:         # the project template's cover: goes once its words have a home
            key = TEMPLATE_COVER[uuid_of(x)]
            if key is None or content.get(key):
                gone += 1
                continue
            prj.notes.append('the project template\'s box "%s" is still on the cover: put its words into '
                             'frontpages.json ("%s") and run again' % (str(x[1]).split('\n')[0], key))
        kept.append(x)
    if gone:
        say('%s: %d items of the earlier cover removed' % (os.path.basename(prj.root), gone))
    set_title(root, COVER_TITLE, wrap(SOURCE_NOTE, 31.0, per_mm=0.9).split('\n'))
    D.put(root, S('paper', 'A3'))
    head = [x for x in root[1:] if x[0] in FIXED and x not in tail]
    tree = [root[0]] + head + kept + cover(prj, content, pages, renders) + order + tail
    canonical(tree)
    prj.files[prj.root] = sheet_text(tree)

    changed = []
    for path, text in sorted(prj.files.items()):
        old = io.open(path, encoding='utf-8', newline='').read() if os.path.exists(path) else None
        if old is not None and old.replace('\r\n', '\n') == text:
            continue                             # the same; KiCad on Windows saves a file with CR LF line ends
        changed.append(path)
        if not check:
            with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
    for n in prj.notes:
        say('note: ' + n)
    say('%s: %d pages; %d file%s %s' % (prj.name, len(pages), len(changed), '' if len(changed) == 1 else 's',
                                        'would change' if check else 'written'))
    return changed


def embed_image(sheet, png, box=None, key='diagram'):
    """Put a PNG into a sheet, as large as fits `box` (x0, y0, x1, y1 in mm; default: the frame of an
    Architecture page without a drawing), centred, replacing the image an earlier call put there under the same
    key. The image survives every later run of this tool; the placeholder of that key goes. Returns the image's
    rectangle (x0, y0, x1, y1). A resolution stored in the PNG is ignored: the box alone sets the printed size.

    A run embeds the architecture drawing itself, with the same kind of node (drawing(), kept_image()). This
    function is for any other picture, for example a photograph on a design sheet:

        import frontpages
        frontpages.embed_image('hw/main-board/sensors.kicad_sch', 'photo.png', box=(300, 200, 380, 240),
                               key='photo')
    """
    sheet = os.path.abspath(sheet)
    prj = Project(os.path.dirname(sheet))
    scope = prj.scope(sheet)
    node, rect = kept_image(scope, key, open(png, 'rb').read(), box or ARCH_BOX)
    tree = read_tree(sheet)
    stale = {own_uuid(scope, 'placeholder:%s:%s' % (key, part)) for part in ('frame', 'title', 'text')}
    stale.add(uuid_of(node))
    tree[:] = [x for x in tree if not (isinstance(x, list) and uuid_of(x) in stale)]
    if any(isinstance(x, list) and x[0] == 'symbol' for x in tree):
        append_drawn(tree, [node])               # a design sheet: after its symbols, see append_drawn()
    else:
        insert_drawn(tree, [node])
        canonical(tree)                          # as build() and KiCad write the page
    with io.open(sheet, 'w', encoding='utf-8', newline='\n') as f:
        f.write(sheet_text(tree))
    return rect


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):      # a note may hold a character the console's code page lacks
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    folder = None
    try:
        if args[0] == 'embed':
            opts = {}
            for name in ('--box', '--key'):
                if name in args:
                    i = args.index(name)
                    opts[name] = args[i + 1]
                    del args[i:i + 2]
            box = tuple(float(v) for v in opts['--box'].split(',')) if '--box' in opts else None
            r = embed_image(args[1], args[2], box, opts.get('--key', 'diagram'))
            print('%s: image at x %.2f to %.2f, y %.2f to %.2f mm' % (os.path.basename(args[1]), r[0], r[2], r[1],
                                                                       r[3]))
            return 0
        flags = {a for a in args if a.startswith('--')}
        unknown = flags - {'--no-render', '--check'}
        if unknown:
            raise RuntimeError('unknown option %s' % ' '.join(sorted(unknown)))
        folders = [a for a in args if not a.startswith('--')]
        changed = []
        for folder in folders:
            changed += build(folder, render_views='--no-render' not in flags, check='--check' in flags)
        return 1 if '--check' in flags and changed else 0
    except (RuntimeError, AssertionError) as e:
        sys.stdout.flush()
        print('ERROR: %s\nNothing was written%s.' % (e, ' for %s' % folder if folder else ''), file=sys.stderr)
        return 2
    except Exception as e:                       # exit 2, never 1: that is --check's "a file would change"
        sys.stdout.flush()
        print('ERROR: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
