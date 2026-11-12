#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""archdiagram.py: architecture (block) diagrams for a board's schematic, as SVG. Standard library only.

A diagram is one description file, a Python module with a build() function that returns a Diagram:

    from archdiagram import Diagram
    def build():
        d = Diagram('main-board_architecture', 'Main board architecture', 380, 252, keepout=(200, 204, 380, 252))
        d.split = (200, 204)
        d.region(44, 5, 96, 53, 'POWER')
        j1 = d.block('J1', 48, 30, 38, 'Supply input', ['J1 screw terminal', '5 V, 1 A'], note=1)
        jp = d.pill('JP1', 104, j1.cy, 'JP1')
        d.line('power', [j1.R(), jp.L()], label={'s': 'VIN', 'at': 'above'})
        d.legend(1, 38, 36)
        d.footnotes(1, 205, 198, {1: 'A fact a reader would get wrong.'})
        return d

    python3 hw/tools/archdiagram.py hw/main-board/architecture/main-board_architecture.py
                           writes main-board_architecture.svg beside the description and prints the check result
    ... -o out             writes into the folder out instead
    ... --png              and <name>.png (svg2png.py: headless Edge or Chrome)
    ... --png --split      and split/<name>_top.png and _notes.png, cut where d.split says
    ... --preview          and preview/<name>_on_page_colour.png, 150 dpi, for looking at
    ... --hw DIR           the hw folder whose projects give the revision and the page numbers

A description lives in hw/<board>/architecture/ with its rendered SVG. frontpages.py beside this file puts the drawing
on the board's Architecture page (frontpages.json: "architecture": "architecture/<name>.py"): it renders the
description itself, and embeds it again whenever the SVG it gets differs from the one on the page.

All coordinates are millimetres on the canvas, x to the right and y down. The canvas is drawn 1:1 on the
schematic page, so a 2.6 mm text is 2.6 mm on paper. Nothing is laid out automatically: blocks sit where the
description puts them and every line lists its corners. What the generator adds:

  * text measured with the real font (Arial Narrow's advance widths, read from the .ttf), so boxes, labels,
    wrapped notes and tables fit before a browser ever renders them;
  * line furniture: arrowheads, labels that cut the line they sit on, bundle ticks, junction dots, hops where
    two lines cross, the analog squiggle;
  * a legend built from what the drawing uses, so every style on the page is explained and nothing else is;
  * a check, run by render(): text that overflows its box or overlaps other text, lines through boxes or
    through text, lines on top of each other, text or a box across the edge of a region, a line label closer
    than 0.7 mm to an arrowhead, 1.0 mm to a block or 1.2 mm to the edge of a region, a junction dot under an
    arrowhead or against a block, anything outside the canvas or inside the title-block keep-out, text below
    the minimum size, footnote marks without a footnote and footnotes without a mark. The issues are in
    Diagram.issues; the command line prints them and fails.

Colours come from the schematic's net classes (LINES below; the project files hold the same values), so a
line here and the wire on the schematic page have the same colour.
"""
import importlib.util
import os
import struct
import sys
from xml.sax.saxutils import escape

MIN_TEXT = 2.6        # mm; nothing on the page is set smaller
FS = 2.6              # part lines, facts, labels, legend, footnotes
TS = 3.2              # block titles
RS = 4.0              # region titles
PITCH = 3.2           # line pitch of FS text inside a block
LABEL_TO_HEAD = 0.7   # a line label keeps this far from every arrowhead,
LABEL_TO_BLOCK = 1.0  # ... from every block
LABEL_TO_EDGE = 1.2   # ... and from the outline of every region and of the board
DOT_TO_HEAD = 0.5     # a junction dot keeps this far from every arrowhead
DOT_TO_BLOCK = 1.0    # ... and from every block
SHORT_DASH = 8.0      # a dashed run shorter than this takes a finer dash, so that it still reads as dashed
OPTION_INSET = 0.65   # the second outline of an option block, inside the first

INK = '#16201C'       # text and outlines
INK2 = '#39453F'      # second-level text
REGION_FILL = '#EDF1EC'
REGION_EDGE = '#A7B2AA'
REGION_TITLE = '#2C5A4A'
BOARD_EDGE = '#4B5750'
NOTE_FILL, NOTE_EDGE, NOTE_TEXT = '#FFF3C4', '#7A5B00', '#4F3B00'
PAGE_COLOUR = '#F5F4EF'   # the schematic page under the Altium theme, for previews only: the PNG is transparent
DNP_EDGE, DNP_TEXT = '#8A8F8C', '#4D5350'

# line classes: colour, width, default arrow, legend text. All but 'cable' follow the schematic's net classes
# ('ctl' is the Bus class drawn thin, 'power_local' the Power class drawn thin).
LINES = {
    'power':       ('#C20000', 0.80, 'end', 'Power: a supply rail, with its name and voltage'),
    'power_local': ('#C20000', 0.45, 'end', 'Power: a local rail, switched or filtered'),
    'gnd':         ('#008400', 0.50, 'none', 'GND'),
    'rf':          ('#C200C2', 0.60, 'end', 'RF_50R: the radio path'),
    'analog':      ('#CC6600', 0.42, 'end', 'Analog: ADC inputs, references and sense lines'),
    'bus':         ('#000084', 0.60, 'both', 'Bus: I2C or SPI data, both ways'),
    'ctl':         ('#000084', 0.32, 'end', 'Bus: a one-way enable, interrupt or GPIO'),
    'debug':       ('#848400', 0.50, 'end', 'Debug: SWD and reset'),
    'uart':        ('#840084', 0.50, 'both', 'UART'),
    'clock':       ('#848484', 0.50, 'end', 'Clock: clocks, crystals and oscillators'),
    'usb':         ('#00C2C2', 0.60, 'both', 'USB'),
    'cable':       ('#4A4A4A', 1.50, 'none', 'Off-board cable'),
}
LINE_ORDER = ['power', 'power_local', 'gnd', 'rf', 'analog', 'bus', 'ctl', 'debug', 'uart', 'clock', 'usb',
              'cable']
RAIL_TINT = {'power': '#FBE4E1', 'power_local': '#FBE4E1', 'gnd': '#DFF0DF', 'analog': '#FBEBD9'}

LEGEND_TEXT = {
    'wig': 'Squiggle: an analog signal, marked once on its way',
    'air': 'Dotted: coupling with no copper path',
    'dnp': 'Dashed: open as built, through a part that is not fitted',
    'off': 'Heavier: leaves the board',
    'bundle': 'n wires drawn as one',
    'hop': 'Hop: crossing, not joined',
    'dot': 'Dot: joined',
    'arrows': 'Head: the way power or a signal flows. No head: a passive link',
    'fitted': 'Fitted block',
    'option': 'Double outline: an option, fitted here to be measured',
    'variant': 'Dashed outline: not on every variant',
    'dnp_box': 'Not fitted (DNP)',
    'off_box': 'Off-board',
    'pill': 'Solder jumper, bridged as built',
    'rail': 'Name in a pill: on that rail',
    'gndsym': 'Ground',
    'note': 'Footnote',
    'board': 'Board edge',
    'region': 'Region: one function',
}
LEGEND_ORDER = ['wig', 'air', 'dnp', 'off', 'bundle', 'hop', 'dot', 'arrows', 'fitted', 'option', 'variant',
                'dnp_box', 'off_box', 'pill', 'rail', 'gndsym', 'note', 'region', 'board']


# --------------------------------------------------------------------------------------------- font metrics
FAMILY = "'Arial Narrow', 'Liberation Sans Narrow', 'Nimbus Sans Narrow', 'DejaVu Sans Condensed', Arial, sans-serif"
FACES = {  # face: (file names to try, css weight, css style, fallback em width)
    'n': (('ARIALN.TTF', 'LiberationSansNarrow-Regular.ttf'), 'normal', 'normal', 0.44),
    'b': (('ARIALNB.TTF', 'LiberationSansNarrow-Bold.ttf'), 'bold', 'normal', 0.47),
    'i': (('ARIALNI.TTF', 'LiberationSansNarrow-Italic.ttf'), 'normal', 'italic', 0.44),
}
FONT_DIRS = [os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts'), '/usr/share/fonts/truetype/liberation',
             '/usr/share/fonts/truetype/msttcorefonts', '/Library/Fonts', os.path.expanduser('~/.fonts')]


def _ttf_widths(path):
    """Advance width of every mapped character, in em, from a TrueType file (head, hhea, hmtx, cmap format 4)."""
    with open(path, 'rb') as f:
        data = f.read()
    where = {}
    for i in range(struct.unpack_from('>H', data, 4)[0]):
        tag, _sum, offset, _length = struct.unpack_from('>4sLLL', data, 12 + 16 * i)
        where[tag] = offset
    em = struct.unpack_from('>H', data, where[b'head'] + 18)[0]
    count = struct.unpack_from('>H', data, where[b'hhea'] + 34)[0]
    advance = struct.unpack_from('>' + 'Hh' * count, data, where[b'hmtx'])[0::2]
    cmap = where[b'cmap']
    widths = {}
    for i in range(struct.unpack_from('>H', data, cmap + 2)[0]):
        platform, encoding, offset = struct.unpack_from('>HHL', data, cmap + 4 + 8 * i)
        sub = cmap + offset
        if (platform, encoding) != (3, 1) or struct.unpack_from('>H', data, sub)[0] != 4:
            continue
        nseg = struct.unpack_from('>H', data, sub + 6)[0] // 2
        last = struct.unpack_from('>%dH' % nseg, data, sub + 14)
        first = struct.unpack_from('>%dH' % nseg, data, sub + 16 + 2 * nseg)
        delta = struct.unpack_from('>%dh' % nseg, data, sub + 16 + 4 * nseg)
        ranges_at = sub + 16 + 6 * nseg
        ranges = struct.unpack_from('>%dH' % nseg, data, ranges_at)
        for k in range(nseg):
            for code in range(first[k], min(last[k], 0xFFFE) + 1):
                if ranges[k]:
                    glyph = struct.unpack_from('>H', data, ranges_at + 2 * k + ranges[k] + 2 * (code - first[k]))[0]
                    glyph = (glyph + delta[k]) & 0xFFFF if glyph else 0
                else:
                    glyph = (code + delta[k]) & 0xFFFF
                if glyph:
                    widths[code] = advance[min(glyph, count - 1)] / float(em)
    return widths


_WIDTHS = {}


def _face(face):
    if face not in _WIDTHS:
        _WIDTHS[face] = None
        for name in FACES[face][0]:
            for folder in FONT_DIRS:
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    try:
                        _WIDTHS[face] = _ttf_widths(path)
                    except Exception:      # an unreadable font only costs accuracy
                        _WIDTHS[face] = None
                    break
            if _WIDTHS[face]:
                break
    return _WIDTHS[face]


def text_width(s, size=FS, face='n', spacing=0.0):
    table = _face(face)
    fallback = FACES[face][3]
    em = sum((table.get(ord(ch), fallback) if table else fallback) for ch in s)
    return em * size + spacing * max(len(s) - 1, 0)


def wrap(s, width, size=FS, face='n'):
    """Greedy word wrap to a width in mm. A line break in the text is kept."""
    out = []
    for para in s.split('\n'):
        line = ''
        for word in para.split(' '):
            trial = word if not line else line + ' ' + word
            if line and text_width(trial, size, face) > width:
                out.append(line)
                line = word
            else:
                line = trial
        out.append(line)
    return out


def _n(v):
    s = '%.3f' % v
    return s.rstrip('0').rstrip('.') if '.' in s else s


# --------------------------------------------------------------------------------------------------- shapes
class Box(object):
    """A rectangle with anchor points for lines: L, R, T, B take an absolute coordinate or an offset from centre."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)

    x2 = property(lambda s: s.x + s.w)
    y2 = property(lambda s: s.y + s.h)
    cx = property(lambda s: s.x + s.w / 2.0)
    cy = property(lambda s: s.y + s.h / 2.0)
    rect = property(lambda s: (s.x, s.y, s.x + s.w, s.y + s.h))

    def L(self, y=None, dy=0.0):
        return (self.x, (self.cy if y is None else y) + dy)

    def R(self, y=None, dy=0.0):
        return (self.x2, (self.cy if y is None else y) + dy)

    def T(self, x=None, dx=0.0):
        return ((self.cx if x is None else x) + dx, self.y)

    def B(self, x=None, dx=0.0):
        return ((self.cx if x is None else x) + dx, self.y2)


class Block(Box):
    def __init__(self, key, x, y, w, h, kind):
        Box.__init__(self, x, y, w, h)
        self.key, self.kind = key, kind
        self.title, self.lines = '', []
        self.tag = self.tagcls = self.note = None
        self.pins = []
        self.vtext = None
        self.valign = 't'
        self.align = 'l'
        self.tsize = TS
        self.extra, self.marks = [], []
        self.dashed = False

    def text(self, x, y, s, face='n', anchor='middle', size=FS):
        """One more line of text inside the block, at an absolute position."""
        self.extra.append((x, y, s, face, anchor, size))

    def mark(self, n, x, y):
        """A footnote mark inside the block, at an absolute position (note=n puts one in the top right corner)."""
        self.marks.append((n, x, y))

    def pin(self, side, at, text=None, bold=False):
        """A labelled pin on an edge; returns the point where a line meets the block."""
        self.pins.append((side, float(at), text, bold))
        return {'l': (self.x, at), 'r': (self.x2, at), 't': (at, self.y), 'b': (at, self.y2)}[side]


class Line(object):
    def __init__(self, cls, pts):
        self.cls, self.pts = cls, pts
        self.colour, self.width, self.arrow = LINES[cls][:3]
        self.labels, self.dots = [], []
        self.n = None
        self.dnp = self.air = self.off = False
        self.wig = None
        self.pieces = []


def _hits(a, b, pad=0.0):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


# -------------------------------------------------------------------------------------------------- diagram
class Diagram(object):
    def __init__(self, name, title, width, height, keepout=None, background=None):
        self.name, self.title = name, title
        self.W, self.H = float(width), float(height)
        self.keepout = keepout
        self.background = background
        self.split = None                     # (x, y): the PNG is also cut into a top part above y and a notes
        #                                       part below y and left of x; the keep-out is what neither holds
        self.rail_sample = ('VDD', 'power')   # the name and line class in the legend's sample of a rail pill
        self.regions, self.blocks, self.lines = [], [], []
        self.free, self.tables, self.gnds, self.notes_at = [], [], [], []
        self.board_edge = None
        self._legend = self._footnotes = None
        self.used = set()
        self.legend_text = dict(LEGEND_TEXT)
        self.line_text = dict((k, v[3]) for k, v in LINES.items())
        self.issues = []
        self._texts, self._areas = [], []     # filled while rendering, read by check()
        self._heads, self._dots = [], []      # arrowheads and junction dots, as boxes, for check()

    # ---- description API
    def region(self, x, y, w, h, title, tpos='tl'):
        """A functional region: a tinted, titled rectangle behind its blocks. tpos: tl, tr, bl or br."""
        box = Box(x, y, w, h)
        self.regions.append((box, title, tpos, None))
        self.used.add('region')
        return box

    def region_poly(self, points, title, tpos='tl'):
        """A region with a rectilinear outline (an L, say), given as its corners in order."""
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        box = Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        self.regions.append((box, title, tpos, [(float(px), float(py)) for px, py in points]))
        self.used.add('region')
        return box

    def board(self, x, y, w, h, caption=None):
        self.board_edge = (Box(x, y, w, h), caption)
        self.used.add('board')

    def block(self, key, x, y, w, title, lines=(), kind='fitted', h=None, tag=None, tagcls='power', note=None,
              valign='t', align='l', vtext=None, tsize=TS):
        """kind: fitted, option (a second outline inside the first: fitted, but not part of the baseline design),
        variant (dashed: not on every variant of the board), dnp or off. Height follows the text unless h is
        given. tag: a rail name in a pill in the title row."""
        lines = list(lines)
        if h is None:
            h = 1.3 + 0.78 * tsize + PITCH * len(lines) + 1.5 + (0.5 if kind == 'option' else 0.0)
        b = Block(key, x, y, w, h, kind)
        b.title, b.lines, b.tag, b.tagcls, b.note = title, lines, tag, tagcls, note
        b.valign, b.align, b.vtext, b.tsize = valign, align, vtext, tsize
        self.blocks.append(b)
        self.used.add({'fitted': 'fitted', 'option': 'option', 'variant': 'variant', 'dnp': 'dnp_box',
                       'off': 'off_box'}[kind])
        if tag:
            self.used.add('rail')
        if note:
            self.used.add('note')
        return b

    def pill(self, key, cx, cy, text, w=None, dashed=False):
        """A solder jumper drawn in the line it breaks. dashed: as a variant block, not on every variant."""
        w = w or text_width(text, FS, 'b') + 3.4
        b = Block(key, cx - w / 2.0, cy - 2.3, w, 4.6, 'pill')
        b.title, b.dashed = text, dashed
        if dashed:
            self.used.add('variant')
        self.blocks.append(b)
        self.used.add('pill')
        return b

    def flag(self, key, cx, cy, text, cls='power'):
        """A rail or net name in a pill: a line that starts here is on the rail or net of that name, as at a
        power symbol or a net label on a schematic."""
        w = text_width(text, FS, 'b') + 3.0
        b = Block(key, cx - w / 2.0, cy - 2.1, w, 4.2, 'flag')
        b.title, b.tagcls = text, cls
        self.blocks.append(b)
        self.used.add('rail')
        return b

    def gnd(self, x, y):
        """A ground symbol hanging from (x, y)."""
        self.gnds.append((x, y))
        self.used.add('gndsym')
        return (x, y)

    def note(self, n, x, y):
        """A footnote mark at a free position (blocks take note=n)."""
        self.notes_at.append((n, x, y))
        self.used.add('note')

    def text(self, x, y, s, size=FS, face='n', fill=INK, anchor='start', spacing=0.0):
        self.free.append((x, y, s, size, face, fill, anchor, spacing))

    def line(self, cls, pts, label=None, arrow=None, n=None, dnp=False, air=False, off=False, dot='', dots=(),
             wig=None):
        """An orthogonal line through pts. label: text, a dict (s, seg, t, x, y, at, dx, dy) or a list of
        either; at is on (the label cuts the line), above, below, left or right; t is the place along the run
        (0 to 1), or x (on a horizontal run) or y (on a vertical one) gives it in mm. arrow: end, start, both,
        none. n: a bundle of n wires (an int, or a dict n, seg, t). dot: 's', 'e' or 'se' joins that end to the
        line it lands on. wig: (seg, t) puts the analog squiggle there."""
        pts = [(float(px), float(py)) for px, py in pts]
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6:
                raise ValueError('%s line: %r to %r is not horizontal or vertical' % (cls, a, b))
        ln = Line(cls, pts)
        if arrow:
            ln.arrow = arrow
        ln.dnp, ln.air, ln.off, ln.wig = dnp, air, off, wig
        if label:
            for item in (label if isinstance(label, list) else [label]):
                ln.labels.append(dict(item) if isinstance(item, dict) else {'s': item})
        if n:
            ln.n = dict(n) if isinstance(n, dict) else {'n': n}
            self.used.add('bundle')
        if 's' in dot:
            ln.dots.append(pts[0])
        if 'e' in dot:
            ln.dots.append(pts[-1])
        ln.dots.extend(dots)
        self.lines.append(ln)
        self.used.add('line:' + cls)
        self.used.add('arrows')
        for flag_, name in ((dnp, 'dnp'), (air, 'air'), (off, 'off'), (wig, 'wig'), (ln.dots, 'dot')):
            if flag_:
                self.used.add(name)
        return ln

    def table(self, x, y, widths, rows, head=True, size=FS, pad=1.2, title=None, rowpad=1.4, bold_first=True):
        """A ruled table; cells wrap to their column. Returns its Box."""
        self.tables.append([x, y, widths, rows, head, size, pad, title, None, rowpad, bold_first])
        height = 0.0
        for r, row in enumerate(rows):
            face = 'b' if head and r == 0 else 'n'
            most = max(len(wrap(c, widths[i] - 2 * pad, size, face)) for i, c in enumerate(row))
            height += most * (size + 0.6) + rowpad
        box = Box(x, y, sum(widths), height + (5.2 if title else 0.0))
        self.tables[-1][8] = box
        return box

    def legend(self, x, y, w, title='LEGEND', max_y=None, cols=1, gap=3.0):
        self._legend = (x, y, w, title, max_y, cols, gap)

    def footnotes(self, x, y, w, notes, title='FOOTNOTES', cols=1, gap=6.0, max_y=None, between=1.15, lead=6.0,
                  mark_r=1.75):
        """The numbered notes. between: the space after each note; lead: from y to the top of the first;
        mark_r: the radius of the marks in the list (a list of one-line notes pitched under 3.9 mm needs 1.6)."""
        self._footnotes = (x, y, w, notes, title, cols, gap, max_y, between, lead, mark_r)

    # ---- drawing helpers
    def _t(self, out, x, y, s, size=FS, face='n', fill=INK, anchor='start', owner=None, spacing=0.0, rot=False):
        """Emit one text; x, y is the baseline start, middle or end. Records its box for check()."""
        w = text_width(s, size, face, spacing)
        if rot:      # rotated a quarter turn anticlockwise about (x, y): it reads upward
            y0 = {'start': y - w, 'middle': y - w / 2.0, 'end': y}[anchor]
            box = (x - 0.76 * size, y0, x + 0.24 * size, y0 + w)
        else:
            x0 = {'start': x, 'middle': x - w / 2.0, 'end': x - w}[anchor]
            box = (x0, y - 0.76 * size, x0 + w, y + 0.24 * size)
        self._texts.append({'box': box, 's': s, 'size': size, 'owner': owner})
        _file, weight, style, _em = FACES[face]
        attrs = 'x="%s" y="%s" font-size="%s" fill="%s"' % (_n(x), _n(y), _n(size), fill)
        if weight != 'normal':
            attrs += ' font-weight="%s"' % weight
        if style != 'normal':
            attrs += ' font-style="%s"' % style
        if anchor != 'start':
            attrs += ' text-anchor="%s"' % anchor
        if spacing:
            attrs += ' letter-spacing="%s"' % _n(spacing)
        if rot:
            attrs += ' transform="rotate(-90 %s %s)"' % (_n(x), _n(y))
        out.append('<text %s>%s</text>' % (attrs, escape(s)))
        return w

    def _note_mark(self, out, n, cx, cy, owner=None, r=1.9):
        out.append('<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" stroke-width="0.3"/>'
                   % (_n(cx), _n(cy), _n(r), NOTE_FILL, NOTE_EDGE))
        self._t(out, cx, cy + 0.36 * FS, str(n), FS, 'b', NOTE_TEXT, 'middle', owner=owner or ('note', n))
        self._texts[-1]['box'] = (cx - r - 0.15, cy - r - 0.15, cx + r + 0.15, cy + r + 0.15)   # the circle

    def _rail_pill(self, out, x, y, w, h, text, cls, owner):
        colour = LINES[cls][0]
        out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" stroke="%s" stroke-width="0.3"/>'
                   % (_n(x), _n(y), _n(w), _n(h), _n(h / 2.0), RAIL_TINT.get(cls, '#F2F2F2'), colour))
        self._t(out, x + w / 2.0, y + h / 2.0 + 0.36 * FS, text, FS, 'b', colour, 'middle', owner=owner)

    def _box_shape(self, out, kind, x, y, w, h):
        if kind == 'off':
            style = 'fill="#FFFFFF" stroke="%s" stroke-width="0.8"' % INK
        elif kind == 'variant':
            style = 'fill="#FFFFFF" stroke="%s" stroke-width="0.4" stroke-dasharray="2.2 1.1"' % INK
        elif kind == 'dnp':
            style = 'fill="url(#hatch)" stroke="%s" stroke-width="0.35" stroke-dasharray="0.9 0.8"' % DNP_EDGE
        else:
            style = 'fill="#FFFFFF" stroke="%s" stroke-width="0.4"' % INK
        out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="1.2" %s/>' % (_n(x), _n(y), _n(w), _n(h), style))
        if kind == 'option':             # fitted, so a solid outline; the second one inside marks the option
            i = OPTION_INSET
            out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="0.7" fill="none" stroke="%s" '
                       'stroke-width="0.22"/>' % (_n(x + i), _n(y + i), _n(w - 2 * i), _n(h - 2 * i), INK))

    def _draw_block(self, out, b):
        owner = ('block', b.key)
        if b.kind == 'pill':
            out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="#FFFFFF" stroke="%s" '
                       'stroke-width="0.45"%s/>' % (_n(b.x), _n(b.y), _n(b.w), _n(b.h), _n(b.h / 2.0), INK,
                                                    ' stroke-dasharray="2.2 1.1"' if b.dashed else ''))
            self._t(out, b.cx, b.cy + 0.36 * FS, b.title, FS, 'b', INK, 'middle', owner=owner)
            return
        if b.kind == 'flag':
            self._rail_pill(out, b.x, b.y, b.w, b.h, b.title, b.tagcls, owner)
            return
        self._box_shape(out, b.kind, b.x, b.y, b.w, b.h)
        ink, ink2 = (DNP_TEXT, DNP_TEXT) if b.kind == 'dnp' else (INK, INK2)
        texth = 0.78 * b.tsize + PITCH * len(b.lines)
        if b.vtext:                      # title and lines read upward, in columns from left to right
            rows = [(b.title, b.tsize, 'b', ink)] + [(s, FS, 'n', ink2) for s in b.lines]
            pitch = PITCH + 0.2
            span = pitch * (len(rows) - 1)
            x0 = {'c': b.cx - span / 2.0 + 0.26 * FS, 'r': b.x2 - 1.5 - span, 'l': b.x + 3.0}[b.vtext]
            for i, (s, size, face, fill) in enumerate(rows):
                self._t(out, x0 + i * pitch, b.cy, s, size, face, fill, 'middle', owner=owner, rot=True)
        else:
            top = {'t': b.y + 1.3 + (0.25 if b.kind == 'option' else 0.0), 'c': b.y + (b.h - texth) / 2.0 - 0.1,
                   'b': b.y2 - texth - 1.5}[b.valign]
            tx, anchor = (b.x + 1.6, 'start') if b.align == 'l' else (b.cx, 'middle')
            base = top + 0.78 * b.tsize
            if b.title:
                self._t(out, tx, base, b.title, b.tsize, 'b', ink, anchor, owner=owner)
            for i, s in enumerate(b.lines):
                self._t(out, tx, base + PITCH * (i + 1), s, FS, 'n', ink2, anchor, owner=owner)
        ix, iy = (OPTION_INSET + 0.2, 0.3) if b.kind == 'option' else (0.0, 0.0)    # clear of the second outline
        right = b.x2 - 1.0 - ix
        if b.note:
            self._note_mark(out, b.note, right - 1.9, b.y + 2.9 + iy, owner)
            right -= 4.6
        if b.tag:
            tw = text_width(b.tag, FS, 'b') + 2.6
            self._rail_pill(out, right - tw, b.y + 1.0 + iy, tw, 3.7, b.tag, b.tagcls, owner)
        for x, y, s, face, anchor, size in b.extra:
            self._t(out, x, y, s, size, face, ink2, anchor, owner=owner)
        for n, x, y in b.marks:
            self._note_mark(out, n, x, y, owner)
        for side, at, text, bold in b.pins:
            if not text:
                continue
            face = 'b' if bold else 'n'
            if side == 'l':
                self._t(out, b.x + 1.2, at + 0.36 * FS, text, FS, face, ink, 'start', owner=owner)
            elif side == 'r':
                self._t(out, b.x2 - 1.2, at + 0.36 * FS, text, FS, face, ink, 'end', owner=owner)
            elif side == 't':
                self._t(out, at, b.y + 1.0 + 0.76 * FS, text, FS, face, ink, 'middle', owner=owner)
            else:
                self._t(out, at, b.y2 - 1.3, text, FS, face, ink, 'middle', owner=owner)

    # ---- lines
    def _find_hops(self):
        """Where a horizontal run of one line crosses a vertical run of another: {(line, segment): [x, ...]}."""
        hops = {}
        runs = []
        for li, ln in enumerate(self.lines):
            for si, (a, b) in enumerate(zip(ln.pts, ln.pts[1:])):
                runs.append((li, si, a, b))
        for li, si, a, b in runs:
            if abs(a[1] - b[1]) > 1e-6:
                continue
            x0, x1 = sorted((a[0], b[0]))
            for lj, _sj, c, e in runs:
                if lj == li or abs(c[0] - e[0]) > 1e-6:
                    continue
                y0, y1 = sorted((c[1], e[1]))
                if x0 + 0.3 < c[0] < x1 - 0.3 and y0 + 0.3 < a[1] < y1 - 0.3:
                    hops.setdefault((li, si), []).append(c[0])
        return hops

    def _draw_line(self, out, labels_out, li, ln, hops):
        colour, w = ln.colour, ln.width * (1.7 if ln.off else 1.0)
        if ln.air:
            w = max(w, 0.6)          # dots thinner than this do not print
        pts = ln.pts
        segs = list(zip(pts, pts[1:]))
        lengths = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs]
        longest = max(range(len(segs)), key=lambda i: lengths[i])
        al = 1.5 + 1.8 * w
        ah = 0.55 + 0.85 * w
        gaps = dict((i, []) for i in range(len(segs)))
        owner = ('line', li)

        # labels
        for lab in ln.labels:
            si = lab.get('seg', longest)
            if si < 0:
                si += len(segs)
            a, b = segs[si]
            t = lab.get('t', 0.5)
            at = lab.get('at', 'on')
            size = lab.get('size', FS)
            face = 'b' if lab.get('bold', ln.cls == 'power') else 'n'
            fill = lab.get('fill', colour if ln.cls in ('power', 'power_local') else INK)
            px, py = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            horizontal = abs(a[1] - b[1]) < 1e-6
            if horizontal and 'x' in lab:
                px = float(lab['x'])
            if not horizontal and 'y' in lab:
                py = float(lab['y'])
            px += lab.get('dx', 0.0)
            py += lab.get('dy', 0.0)
            tw = text_width(lab['s'], size, face)
            along = abs(px - a[0]) if horizontal else abs(py - a[1])
            if at == 'on':
                half = tw / 2.0 + 0.7 if horizontal else 0.62 * size + 0.3
                if ln.air:           # a dotted run starts with a dot: keep the first one off the label
                    half += 0.9
                gaps[si].append((along - half, along + half))
                self._t(labels_out, px, py + 0.36 * size, lab['s'], size, face, fill, 'middle', owner=owner)
            elif at == 'above':
                self._t(labels_out, px, py - w / 2.0 - 1.1, lab['s'], size, face, fill, 'middle', owner=owner)
            elif at == 'below':
                self._t(labels_out, px, py + w / 2.0 + 0.6 + 0.76 * size, lab['s'], size, face, fill, 'middle',
                        owner=owner)
            elif at == 'right':
                self._t(labels_out, px + w / 2.0 + 0.9, py + 0.36 * size, lab['s'], size, face, fill, 'start',
                        owner=owner)
            elif at == 'left':
                self._t(labels_out, px - w / 2.0 - 0.9, py + 0.36 * size, lab['s'], size, face, fill, 'end',
                        owner=owner)
            else:
                raise ValueError('label position %r' % at)

        # bundle tick
        if ln.n:
            si = ln.n.get('seg', longest)
            a, b = segs[si]
            t = ln.n.get('t', 0.14)
            px, py = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            labels_out.append('<path d="M%s %s L%s %s" stroke="%s" stroke-width="0.35" fill="none"/>'
                              % (_n(px - 0.9), _n(py + 1.3), _n(px + 0.9), _n(py - 1.3), INK))
            if abs(a[1] - b[1]) < 1e-6:
                self._t(labels_out, px + 0.2, py - 1.7, str(ln.n['n']), FS, 'b', INK, 'middle', owner=owner)
            else:
                self._t(labels_out, px + 1.6, py + 0.36 * FS, str(ln.n['n']), FS, 'b', INK, 'start', owner=owner)

        # squiggle
        wig_at = None
        if ln.wig:
            si, t = ln.wig
            a, b = segs[si]
            if abs(a[1] - b[1]) > 1e-6:
                raise ValueError('the squiggle needs a horizontal run')
            along = t * lengths[si]
            gaps[si].append((along - 2.4, along + 2.4))
            wig_at = (si, along)

        # the path, piece by piece
        d = []
        pen = None
        ln.pieces = []
        for si, (a, b) in enumerate(segs):
            length = lengths[si]
            if length < 1e-6:
                continue
            ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            s0, s1 = 0.0, length
            if si == 0 and ln.arrow in ('start', 'both'):
                s0 = al * 0.85
            if si == len(segs) - 1 and ln.arrow in ('end', 'both'):
                s1 = length - al * 0.85
            if s1 - s0 < 0.2:
                self.issues.append('line %d (%s): the run at %r is too short for its arrowhead' % (li, ln.cls, a))
            cuts = sorted(gaps[si])
            spans, cur = [], s0
            for g0, g1 in cuts:
                if g0 > cur:
                    spans.append((cur, min(g0, s1)))
                cur = max(cur, g1)
            if cur < s1:
                spans.append((cur, s1))
            hop_at = sorted(abs(hx - a[0]) for hx in hops.get((li, si), []))
            for p0, p1 in spans:
                if p1 - p0 < 1e-6:
                    continue
                start = (a[0] + ux * p0, a[1] + uy * p0)
                end = (a[0] + ux * p1, a[1] + uy * p1)
                if pen is None or abs(pen[0] - start[0]) > 1e-6 or abs(pen[1] - start[1]) > 1e-6:
                    d.append('M%s %s' % (_n(start[0]), _n(start[1])))
                for hp in hop_at:
                    if p0 + 1.0 < hp < p1 - 1.0:
                        d.append('L%s %s' % (_n(a[0] + ux * (hp - 0.9)), _n(a[1])))
                        d.append('A0.9 0.9 0 0 %d %s %s' % (1 if ux > 0 else 0, _n(a[0] + ux * (hp + 0.9)), _n(a[1])))
                        self.used.add('hop')
                    elif p0 - 0.2 < hp < p1 + 0.2:
                        self.issues.append('line %d (%s): a crossing at x=%.1f, y=%.1f is too close to a corner, '
                                           'label or end for a hop' % (li, ln.cls, a[0] + ux * hp, a[1]))
                d.append('L%s %s' % (_n(end[0]), _n(end[1])))
                pen = end
                ln.pieces.append((start, end))
            for hp in hop_at:
                if not any(p0 - 0.2 < hp < p1 + 0.2 for p0, p1 in spans):
                    self.issues.append('line %d (%s): a crossing at x=%.1f, y=%.1f falls inside a label'
                                       % (li, ln.cls, a[0] + ux * hp, a[1]))
        dash = ''
        if ln.dnp:
            drawn = sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in ln.pieces)
            if drawn < SHORT_DASH:       # at least two dashes, or the run does not read as dashed
                dash = ' stroke-dasharray="0.8 0.7"'
            else:
                dash = ' stroke-dasharray="%s %s"' % (_n(1.5), _n(1.0 + w))
        elif ln.air:
            dash = ' stroke-dasharray="0.01 %s"' % _n(0.9 + w)
        out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="round" '
                   'stroke-linecap="%s"%s/>' % (' '.join(d), colour, _n(w), 'round' if ln.air else 'butt', dash))
        if wig_at:
            si, along = wig_at
            a, b = segs[si]
            sx = 1.0 if b[0] > a[0] else -1.0
            x0 = a[0] + sx * (along - 2.4)
            q = sx * 0.6
            out.append('<path d="M%s %s q%s -1.5 %s 0 t%s 0 t%s 0 t%s 0" fill="none" stroke="%s" stroke-width="%s"/>'
                       % (_n(x0), _n(a[1]), _n(q), _n(2 * q), _n(2 * q), _n(2 * q), _n(2 * q), colour, _n(w)))
        for end, at, frm in (('end', pts[-1], pts[-2]), ('start', pts[0], pts[1])):
            if ln.arrow not in (end, 'both'):
                continue
            length = abs(at[0] - frm[0]) + abs(at[1] - frm[1])
            ux, uy = (at[0] - frm[0]) / length, (at[1] - frm[1]) / length
            bx, by = at[0] - ux * al, at[1] - uy * al
            out.append('<path d="M%s %s L%s %s L%s %s Z" fill="%s"/>'
                       % (_n(at[0]), _n(at[1]), _n(bx - uy * ah), _n(by + ux * ah), _n(bx + uy * ah),
                          _n(by - ux * ah), colour))
            xs = (at[0], bx - uy * ah, bx + uy * ah)
            ys = (at[1], by + ux * ah, by - ux * ah)
            self._heads.append((li, (min(xs), min(ys), max(xs), max(ys))))
        for px, py in ln.dots:
            r = 0.55 + 0.6 * w
            labels_out.append('<circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (_n(px), _n(py), _n(r), colour))
            self._dots.append((li, (px - r, py - r, px + r, py + r)))

    # ---- legend, footnotes, tables
    def _legend_sample(self, out, key, x, y):
        """Draw the sample for one legend entry in a 9 x 4 mm cell whose left middle is (x, y)."""
        if key.startswith('line:'):
            cls = key[5:]
            colour, w, arrow = LINES[cls][:3]
            x1 = x + 9.0
            al, ah = 1.5 + 1.8 * w, 0.55 + 0.85 * w
            s0 = x + (al * 0.85 if arrow == 'both' else 0)
            s1 = x1 - (al * 0.85 if arrow in ('end', 'both') else 0)
            out.append('<path d="M%s %s L%s %s" stroke="%s" stroke-width="%s" fill="none"/>'
                       % (_n(s0), _n(y), _n(s1), _n(y), colour, _n(w)))
            if arrow in ('end', 'both'):
                out.append('<path d="M%s %s L%s %s L%s %s Z" fill="%s"/>'
                           % (_n(x1), _n(y), _n(x1 - al), _n(y - ah), _n(x1 - al), _n(y + ah), colour))
            if arrow == 'both':
                out.append('<path d="M%s %s L%s %s L%s %s Z" fill="%s"/>'
                           % (_n(x), _n(y), _n(x + al), _n(y - ah), _n(x + al), _n(y + ah), colour))
            return
        grey = '#444444'
        if key == 'wig':
            colour, w = LINES['analog'][:2]
            out.append('<path d="M%s %s h2.1 q0.6 -1.5 1.2 0 t1.2 0 t1.2 0 t1.2 0 h2.1" stroke="%s" stroke-width="%s" '
                       'fill="none"/>' % (_n(x), _n(y), colour, _n(w)))
        elif key == 'air':
            out.append('<path d="M%s %s h9" stroke="%s" stroke-width="0.5" stroke-dasharray="0.01 1.7" '
                       'stroke-linecap="round" fill="none"/>' % (_n(x), _n(y), grey))
        elif key == 'dnp':
            out.append('<path d="M%s %s h9" stroke="%s" stroke-width="0.5" stroke-dasharray="1.5 1.5" fill="none"/>'
                       % (_n(x), _n(y), grey))
        elif key == 'off':
            out.append('<path d="M%s %s h9" stroke="%s" stroke-width="1.0" fill="none"/>' % (_n(x), _n(y), grey))
        elif key == 'bundle':
            out.append('<path d="M%s %s h9 M%s %s l1.8 -2.6" stroke="%s" stroke-width="0.4" fill="none"/>'
                       % (_n(x), _n(y), _n(x + 3.4), _n(y + 1.3), grey))
            self._t(out, x + 6.4, y - 0.8, 'n', FS, 'b', INK, 'middle', owner=('legend', key))
        elif key == 'hop':
            out.append('<path d="M%s %s h3.6 a0.9 0.9 0 0 1 1.8 0 h3.6 M%s %s v4" stroke="%s" stroke-width="0.4" '
                       'fill="none"/>' % (_n(x), _n(y), _n(x + 4.5), _n(y - 2.0), grey))
        elif key == 'dot':
            out.append('<path d="M%s %s h9 M%s %s v2.2" stroke="%s" stroke-width="0.4" fill="none"/>'
                       '<circle cx="%s" cy="%s" r="0.8" fill="%s"/>'
                       % (_n(x), _n(y), _n(x + 4.5), _n(y), grey, _n(x + 4.5), _n(y), grey))
        elif key == 'arrows':
            out.append('<path d="M%s %s h6.6" stroke="%s" stroke-width="0.4" fill="none"/>'
                       '<path d="M%s %s l-2.4 -1 v2 Z" fill="%s"/>' % (_n(x), _n(y), grey, _n(x + 9), _n(y), grey))
        elif key in ('fitted', 'option', 'variant', 'dnp_box', 'off_box'):
            kind = {'fitted': 'fitted', 'option': 'option', 'variant': 'variant', 'dnp_box': 'dnp',
                    'off_box': 'off'}[key]
            self._box_shape(out, kind, x + 0.4, y - 1.8, 8.2, 3.6)
        elif key == 'pill':
            out.append('<rect x="%s" y="%s" width="7.4" height="3.6" rx="1.8" fill="#FFFFFF" stroke="%s" '
                       'stroke-width="0.45"/>' % (_n(x + 0.8), _n(y - 1.8), INK))
        elif key == 'rail':
            name, cls = self.rail_sample
            self._rail_pill(out, x + 0.6, y - 1.85, 7.8, 3.7, name, cls, ('legend', key))
        elif key == 'gndsym':
            self._gnd(out, x + 4.5, y - 1.9)
        elif key == 'note':
            self._note_mark(out, 'n', x + 4.5, y)
        elif key == 'region':
            out.append('<rect x="%s" y="%s" width="8.2" height="3.6" rx="1" fill="%s" stroke="%s" stroke-width="0.4"/>'
                       % (_n(x + 0.4), _n(y - 1.8), REGION_FILL, REGION_EDGE))
        elif key == 'board':
            out.append('<path d="M%s %s h9" stroke="%s" stroke-width="0.7" stroke-dasharray="3.2 1.6" fill="none"/>'
                       % (_n(x), _n(y), BOARD_EDGE))

    def _gnd(self, out, x, y):
        c = LINES['gnd'][0]
        out.append('<path d="M%s %s v1.6 M%s %s h3.2 M%s %s h2 M%s %s h0.8" stroke="%s" stroke-width="0.45" '
                   'fill="none"/>' % (_n(x), _n(y), _n(x - 1.6), _n(y + 1.6), _n(x - 1.0), _n(y + 2.5),
                                      _n(x - 0.4), _n(y + 3.4), c))

    def _draw_legend(self, out):
        x, y, w, title, max_y, cols, gap = self._legend
        keys = ['line:' + c for c in LINE_ORDER if 'line:' + c in self.used]
        keys += [k for k in LEGEND_ORDER if k in self.used]
        colw = (w - gap * (cols - 1)) / float(cols)
        entries = []
        for key in keys:
            text = self.line_text[key[5:]] if key.startswith('line:') else self.legend_text[key]
            lines = wrap(text, colw - 13.0, FS)
            entries.append((key, lines, max(4.6, len(lines) * 3.0 + 1.3)))
        per = (len(entries) + cols - 1) // cols
        top = y + 6.6
        height = 0.0
        for c in range(cols):
            cy = top
            cx = x + c * (colw + gap)
            for key, lines, eh in entries[c * per:(c + 1) * per]:
                mid = cy + eh / 2.0
                self._legend_sample(out, key, cx + 1.6, mid)
                base = mid - (len(lines) - 1) * 1.5 + 0.36 * FS
                for i, s in enumerate(lines):
                    self._t(out, cx + 12.4, base + i * 3.0, s, FS, 'n', INK, owner=('legend', key))
                cy += eh
            height = max(height, cy - y)
        self._t(out, x + 1.6, y + 4.3, title, TS, 'b', INK, spacing=0.25, owner=('legend', 'title'))
        out.insert(0, '<rect x="%s" y="%s" width="%s" height="%s" rx="1" fill="none" stroke="#B5BDB8" '
                      'stroke-width="0.25"/>' % (_n(x), _n(y), _n(w), _n(height + 0.8)))
        self._areas.append(('legend', (x, y, x + w, y + height + 0.8)))
        if max_y is not None and y + height + 0.8 > max_y:
            self.issues.append('the legend ends at y=%.1f, below its limit %.1f' % (y + height + 0.8, max_y))

    def _draw_footnotes(self, out):
        x, y, w, notes, title, cols, gap, max_y, between, lead, mark_r = self._footnotes
        self._t(out, x, y + 3.0, title, TS, 'b', NOTE_TEXT, spacing=0.25, owner=('footnotes', 'title'))
        colw = (w - gap * (cols - 1)) / float(cols)
        items = sorted(notes.items())
        laid = [(n, wrap(s, colw - 5.6, FS)) for n, s in items]
        total = sum(len(lines) * 3.25 + between for _n_, lines in laid)
        cy, col, low = y + lead, 0, y
        for n, lines in laid:
            need = len(lines) * 3.25 + between
            if cols > 1 and col < cols - 1 and (cy - (y + lead)) + need > total / cols + 1.7:
                col, cy = col + 1, y + lead
            cx = x + col * (colw + gap)
            self._note_mark(out, n, cx + 1.9, cy + 1.6, r=mark_r)
            for i, s in enumerate(lines):
                self._t(out, cx + 5.6, cy + 2.55 + i * 3.25, s, FS, 'n', INK, owner=('footnote', n))
            cy += need
            low = max(low, cy)
        self._areas.append(('footnotes', (x, y, x + w, low)))
        if max_y is not None and low > max_y:
            self.issues.append('the footnotes end at y=%.1f, below their limit %.1f' % (low, max_y))

    def _draw_table(self, out, tb, index):
        x, y, widths, rows, head, size, pad, title, box, rowpad, bold_first = tb
        owner = ('table', index)
        if title:
            self._t(out, x, y + 3.3, title, TS, 'b', REGION_TITLE, spacing=0.25, owner=owner)
            y += 5.2
        total = sum(widths)
        cy = y
        rules = []
        for r, row in enumerate(rows):
            face = 'b' if head and r == 0 else 'n'
            cells = [wrap(c, widths[i] - 2 * pad, size, 'b' if (bold_first and i == 0) else face)
                     for i, c in enumerate(row)]
            rh = max(len(c) for c in cells) * (size + 0.6) + rowpad
            if head and r == 0:
                out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="#DCE4DE"/>'
                           % (_n(x), _n(cy), _n(total), _n(rh)))
            else:
                out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="#FFFFFF"/>'
                           % (_n(x), _n(cy), _n(total), _n(rh)))
            cx = x
            for i, lines in enumerate(cells):
                for k, s in enumerate(lines):
                    self._t(out, cx + pad, cy + rowpad / 2.0 + 0.78 * size + k * (size + 0.6), s, size,
                            'b' if (head and r == 0) or (bold_first and i == 0) else 'n', INK, owner=owner)
                cx += widths[i]
            cy += rh
            rules.append(cy)
        d = ['M%s %s h%s' % (_n(x), _n(ry), _n(total)) for ry in rules[:-1]]
        cx = x
        for wd in widths[:-1]:
            cx += wd
            d.append('M%s %s v%s' % (_n(cx), _n(y), _n(cy - y)))
        out.append('<path d="%s" stroke="#9BA6A0" stroke-width="0.2" fill="none"/>' % ' '.join(d))
        out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="%s" stroke-width="0.4"/>'
                   % (_n(x), _n(y), _n(total), _n(cy - y), INK))
        self._areas.append(('table', (x, y, x + total, cy)))

    # ---- render
    def render(self):
        self._texts, self._areas, self.issues = [], [], []
        self._heads, self._dots = [], []
        W, H = self.W, self.H
        head = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" viewBox="0 0 %s %s" '
                'font-family="%s">' % (_n(W), _n(H), _n(W), _n(H), FAMILY),
                '<title>%s</title>' % escape(self.title),
                '<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="1.5" height="1.5" '
                'patternTransform="rotate(45)"><rect width="1.5" height="1.5" fill="#F3F4F3"/>'
                '<path d="M0 0 v1.5" stroke="#CDD2CF" stroke-width="0.4"/></pattern></defs>']
        if self.background:
            head.append('<rect width="%s" height="%s" fill="%s"/>' % (_n(W), _n(H), self.background))
        g_region, g_line, g_block, g_label, g_extra = [], [], [], [], []
        for i, (box, title, tpos, poly) in enumerate(self.regions):
            if poly:                 # every corner rounded with a 2 mm quadratic curve
                d = []
                count = len(poly)
                for k in range(count):
                    u, v, w_ = poly[k - 1], poly[k], poly[(k + 1) % count]
                    lu = abs(u[0] - v[0]) + abs(u[1] - v[1])
                    lw = abs(w_[0] - v[0]) + abs(w_[1] - v[1])
                    a = (v[0] + 2.0 * (u[0] - v[0]) / lu, v[1] + 2.0 * (u[1] - v[1]) / lu)
                    b = (v[0] + 2.0 * (w_[0] - v[0]) / lw, v[1] + 2.0 * (w_[1] - v[1]) / lw)
                    d.append('%s%s %s Q%s %s %s %s' % ('L' if k else 'M', _n(a[0]), _n(a[1]), _n(v[0]), _n(v[1]),
                                                      _n(b[0]), _n(b[1])))
                g_region.append('<path d="%s Z" fill="%s" stroke="%s" stroke-width="0.4"/>'
                                % (' '.join(d), REGION_FILL, REGION_EDGE))
            else:
                g_region.append('<rect x="%s" y="%s" width="%s" height="%s" rx="2" fill="%s" stroke="%s" '
                                'stroke-width="0.4"/>' % (_n(box.x), _n(box.y), _n(box.w), _n(box.h), REGION_FILL,
                                                          REGION_EDGE))
            if title:
                owner = ('region', i)
                if tpos == 'tr':
                    self._t(g_region, box.x2 - 2.0, box.y + 4.4, title, RS, 'b', REGION_TITLE, 'end', owner, 0.3)
                elif tpos == 'bl':
                    self._t(g_region, box.x + 2.0, box.y2 - 1.8, title, RS, 'b', REGION_TITLE, 'start', owner, 0.3)
                elif tpos == 'br':
                    self._t(g_region, box.x2 - 2.0, box.y2 - 1.8, title, RS, 'b', REGION_TITLE, 'end', owner, 0.3)
                else:
                    self._t(g_region, box.x + 2.0, box.y + 4.4, title, RS, 'b', REGION_TITLE, 'start', owner, 0.3)
        if self.board_edge:
            box, caption = self.board_edge
            x, y, x2, y2, r = box.x, box.y, box.x2, box.y2, 2.5
            style = 'fill="none" stroke="%s" stroke-width="0.7" stroke-dasharray="3.2 1.6"' % BOARD_EDGE
            if caption:
                cw = self._t(g_region, x + 6.0, y2 + 0.36 * FS, caption, FS, 'n', INK2, owner=('caption', 0))
                g_region.append('<path d="M%s %s H%s A%s %s 0 0 1 %s %s V%s A%s %s 0 0 1 %s %s H%s A%s %s 0 0 1 %s %s '
                                'V%s A%s %s 0 0 1 %s %s H%s" %s/>'
                                % (_n(x + 4.6), _n(y2), _n(x + r), _n(r), _n(r), _n(x), _n(y2 - r), _n(y + r),
                                   _n(r), _n(r), _n(x + r), _n(y), _n(x2 - r), _n(r), _n(r), _n(x2), _n(y + r),
                                   _n(y2 - r), _n(r), _n(r), _n(x2 - r), _n(y2), _n(x + 7.4 + cw), style))
            else:
                g_region.append('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" %s/>'
                                % (_n(x), _n(y), _n(box.w), _n(box.h), _n(r), style))
        if any(b.marks for b in self.blocks):
            self.used.add('note')
        hops = self._find_hops()
        for li, ln in enumerate(self.lines):
            self._draw_line(g_line, g_label, li, ln, hops)
        for gx, gy in self.gnds:
            self._gnd(g_line, gx, gy)
        for b in self.blocks:
            self._draw_block(g_block, b)
        for n, x, y in self.notes_at:
            self._note_mark(g_label, n, x, y)
        for x, y, s, size, face, fill, anchor, spacing in self.free:
            self._t(g_extra, x, y, s, size, face, fill, anchor, owner=('free', s), spacing=spacing)
        for i, tb in enumerate(self.tables):
            self._draw_table(g_extra, tb, i)
        if self._footnotes:
            self._draw_footnotes(g_extra)
        if self._legend:
            legend = []
            self._draw_legend(legend)
            g_extra.extend(legend)
        parts = head
        for name, group in (('regions', g_region), ('lines', g_line), ('blocks', g_block), ('labels', g_label),
                            ('legend-notes-tables', g_extra)):
            parts.append('<g id="%s">' % name)
            parts.extend(group)
            parts.append('</g>')
        parts.append('</svg>')
        self._check()
        return '\n'.join(parts) + '\n'

    # ---- checks
    def _check(self):
        say = self.issues.append
        W, H = self.W, self.H
        blocks = [(('block', b.key), b.rect) for b in self.blocks]
        for owner, r in blocks:
            if r[0] < 0 or r[1] < 0 or r[2] > W or r[3] > H:
                say('%s is off the canvas' % (owner,))
            if self.keepout and _hits(r, self.keepout):
                say('%s is in the title-block keep-out' % (owner,))
        for i, a in enumerate(blocks):
            for b in blocks[i + 1:]:
                if _hits(a[1], b[1], pad=-0.01):
                    say('%s and %s overlap' % (a[0], b[0]))
        by_key = dict((b.key, b) for b in self.blocks)
        if len(by_key) != len(self.blocks):
            say('two blocks share a key')
        for t in self._texts:
            box, owner = t['box'], t['owner']
            if t['size'] < MIN_TEXT - 1e-6:
                say('text %r is %.2f mm, below the %.1f mm minimum' % (t['s'], t['size'], MIN_TEXT))
            if box[0] < 0.3 or box[1] < 0.3 or box[2] > W - 0.3 or box[3] > H - 0.3:
                say('text %r is off the canvas' % t['s'])
            if self.keepout and _hits(box, self.keepout):
                say('text %r is in the title-block keep-out' % t['s'])
            if owner and owner[0] == 'block':
                b = by_key[owner[1]]
                mx, my = 0.5, 0.3
                if b.kind == 'option':       # inside the second outline
                    mx, my = OPTION_INSET + 0.4, OPTION_INSET + 0.3
                if box[0] < b.x + mx or box[2] > b.x2 - mx or box[1] < b.y + my or box[3] > b.y2 - my:
                    say('text %r does not fit in block %s (%.1f mm over)'
                        % (t['s'], b.key, max(b.x + mx - box[0], box[2] - b.x2 + mx, b.y + my - box[1],
                                              box[3] - b.y2 + my)))
            else:
                label = bool(owner) and owner[0] == 'line'
                for bo, r in blocks:
                    if _hits(box, r, pad=LABEL_TO_BLOCK if label else 0.15):
                        say('text %r %s %s' % (t['s'], 'is closer than %.1f mm to' % LABEL_TO_BLOCK if label
                                               else 'overlaps', bo))
                if label:
                    for _li, head in self._heads:
                        if _hits(box, head, pad=LABEL_TO_HEAD):
                            say('label %r is closer than %.1f mm to the arrowhead at (%.1f, %.1f)'
                                % (t['s'], LABEL_TO_HEAD, (head[0] + head[2]) / 2.0, (head[1] + head[3]) / 2.0))
        for li, dot in self._dots:
            at = ((dot[0] + dot[2]) / 2.0, (dot[1] + dot[3]) / 2.0)
            for _lj, head in self._heads:
                if _hits(dot, head, pad=DOT_TO_HEAD):
                    say('the junction dot at (%.1f, %.1f) is under or against an arrowhead' % at)
            for bo, r in blocks:
                if _hits(dot, r, pad=DOT_TO_BLOCK):
                    say('the junction dot at (%.1f, %.1f) is closer than %.1f mm to %s' % (at + (DOT_TO_BLOCK, bo)))
        for i, a in enumerate(self._texts):
            for b in self._texts[i + 1:]:
                if _hits(a['box'], b['box'], pad=0.1):
                    say('texts %r and %r overlap' % (a['s'], b['s']))
        # no text across the outline of a region or of the board
        edges = []
        outlines = [(box, poly) for box, _title, _tpos, poly in self.regions]
        if self.board_edge:
            outlines.append((self.board_edge[0], None))
        for box, poly in outlines:
            pts = poly or [(box.x, box.y), (box.x2, box.y), (box.x2, box.y2), (box.x, box.y2)]
            for k in range(len(pts)):
                a, b = pts[k - 1], pts[k]
                edges.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
        for t in self._texts:
            if t['owner'] and t['owner'][0] == 'caption':
                continue
            if any(_hits(t['box'], e, pad=0.2) for e in edges):
                say('text %r lies across the edge of a region or of the board' % t['s'])
            elif t['owner'] and t['owner'][0] == 'line' and any(_hits(t['box'], e, pad=LABEL_TO_EDGE) for e in edges):
                say('label %r is closer than %.1f mm to the edge of a region or of the board'
                    % (t['s'], LABEL_TO_EDGE))
        for owner, r in blocks:
            if any(_hits(r, e, pad=0.2) for e in edges):
                say('%s lies across the edge of a region or of the board' % (owner,))
        # lines against boxes, text, each other
        pieces = []
        for li, ln in enumerate(self.lines):
            half = ln.width * (1.7 if ln.off else 1.0) / 2.0
            for a, b in ln.pieces:
                r = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
                pieces.append((li, ln, r, half))
                if r[0] < 0 or r[1] < 0 or r[2] > W or r[3] > H:
                    say('line %d (%s) leaves the canvas' % (li, ln.cls))
                if self.keepout and _hits(r, self.keepout):
                    say('line %d (%s) enters the title-block keep-out' % (li, ln.cls))
                for bo, br in blocks:
                    inner = (br[0] + 0.05, br[1] + 0.05, br[2] - 0.05, br[3] - 0.05)
                    if _hits(r, inner):
                        say('line %d (%s, from %r) runs through %s' % (li, ln.cls, ln.pts[0], bo))
                for name, ar in self._areas:
                    if _hits(r, ar):
                        say('line %d (%s) runs through the %s' % (li, ln.cls, name))
                across = (half, 0.0) if r[0] == r[2] else (0.0, half)     # a line is only wide across its run
                for t in self._texts:
                    fat = (r[0] - across[0], r[1] - across[1], r[2] + across[0], r[3] + across[1])
                    if _hits(fat, t['box'], pad=0.25) and not (t['owner'] and t['owner'][0] == 'block'):
                        say('line %d (%s, from %r) runs through text %r' % (li, ln.cls, ln.pts[0], t['s']))
        for i, (li, la, ra, ha) in enumerate(pieces):
            for lj, lb, rb, hb in pieces[i + 1:]:
                if li == lj:
                    continue
                for ax in (0, 1):          # 0: both vertical (same x), 1: both horizontal (same y)
                    o = 1 - ax
                    if ra[ax] == ra[ax + 2] and rb[ax] == rb[ax + 2] and abs(ra[ax] - rb[ax]) < ha + hb + 0.6:
                        if min(ra[o + 2], rb[o + 2]) - max(ra[o], rb[o]) > 0.5:
                            say('lines %d (%s) and %d (%s) run on top of or too close to each other near %r'
                                % (li, la.cls, lj, lb.cls, (ra[0], ra[1])))
        marks = set(b.note for b in self.blocks if b.note) | set(n for n, _x, _y in self.notes_at)
        marks |= set(n for b in self.blocks for n, _x, _y in b.marks)
        notes = set(self._footnotes[3]) if self._footnotes else set()
        for n in sorted(marks - notes, key=str):
            say('footnote mark %s has no footnote' % n)
        for n in sorted(notes - marks, key=str):
            say('footnote %s is never marked on the drawing' % n)
        if self.lines and not self._legend:
            say('the drawing has no legend')

    def save(self, path):
        svg = self.render()
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg)
        return svg


HW_DIR = os.environ.get('ARCHDIAGRAM_HW')     # the hw folder to read projects from; --hw sets it
PAGES = {}                                    # {board: {sheet name: page}}: page numbers that are not on disk yet
#                                               (frontpages.py numbers the pages and renders in the same run)


def project_file(board, here, ext):
    """The path of <board><ext> (.kicad_pro, .kicad_sch): in HW_DIR/<board>/ when --hw or ARCHDIAGRAM_HW names
    the hw folder, else beside the description, in the folder above it (a description in
    hw/<board>/architecture/) or in hw/<board>/ one to three folders up. None if not found."""
    folders = [os.path.join(HW_DIR, board)] if HW_DIR else []
    folders += [here, os.path.join(here, '..')]
    folders += [os.path.join(here, *(['..'] * up + ['hw', board])) for up in (1, 2, 3)]
    for folder in folders:
        path = os.path.join(folder, board + ext)
        if os.path.isfile(path):
            return path
    return None


def project_vars(board, here, **defaults):
    """Text variables (BOARD_NAME, REVISION, ...) of the KiCad project <board>.kicad_pro (see project_file());
    the defaults if it is not found."""
    import json
    out = dict(defaults)
    path = project_file(board, here, '.kicad_pro')
    if path:
        try:
            with open(path, encoding='utf-8') as f:
                out.update(json.load(f).get('text_variables') or {})
        except (IOError, OSError, ValueError):
            pass
    return out


def sheet_pages(board, here):
    """{sheet name: page number} of the sheets on the root sheet <board>.kicad_sch (see project_file()); empty
    if it is not found. A description uses it to write the page into a region's title. PAGES[board] wins over
    the file."""
    import re
    if board in PAGES:
        return dict((name, str(page)) for name, page in PAGES[board].items())
    path = project_file(board, here, '.kicad_sch')
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except (IOError, OSError):
        return {}
    pages = {}
    for chunk in re.split(r'\n\t\(sheet\b', text)[1:]:      # one chunk per sheet symbol
        name = re.search(r'\(property "Sheetname" "([^"]*)"', chunk)
        page = re.search(r'\(page "([^"]*)"\)', chunk)
        if name and page:
            pages[name.group(1)] = page.group(1)
    return pages


def paged(title, pages, sheet):
    """'POWER' becomes 'POWER · page 3' when the page of that sheet is known."""
    return '%s · page %s' % (title, pages[sheet]) if sheet in pages else title


def load(path):
    """Import a description file and return its Diagram."""
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (here, os.path.dirname(os.path.abspath(path))):
        if folder not in sys.path:
            sys.path.insert(0, folder)
    sys.modules.setdefault('archdiagram', sys.modules[__name__])
    spec = importlib.util.spec_from_file_location(os.path.splitext(os.path.basename(path))[0], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Render architecture diagram descriptions to SVG (and PNG).')
    ap.add_argument('descriptions', nargs='+', help='description files (each defines build())')
    ap.add_argument('-o', '--out', default=None, help='output folder (default: beside each description)')
    ap.add_argument('--png', action='store_true', help='also render a PNG with svg2png.py')
    ap.add_argument('--split', action='store_true',
                    help='with --png: also <out>/split/<name>_top.png and _notes.png, cut where the description '
                         'sets Diagram.split, for a page whose title block must stay free')
    ap.add_argument('--preview', action='store_true',
                    help='also <out>/preview/<name>_on_page_colour.png: 150 dpi on the page colour, to look at')
    ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--background', default=None, help='page colour behind the drawing (default: transparent)')
    ap.add_argument('--hw', default=None,
                    help='the hw folder whose projects give the revision and the page numbers (default: '
                         'ARCHDIAGRAM_HW, else looked for beside and above each description)')
    ap.add_argument('--lenient', action='store_true', help='report check issues without failing')
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):      # a console that cannot print an ohm sign must not stop the run
        sys.stdout.reconfigure(errors='replace')
    if args.hw:
        global HW_DIR
        HW_DIR = os.path.abspath(args.hw)
        sys.modules.setdefault('archdiagram', sys.modules[__name__]).HW_DIR = HW_DIR
    failed = False
    for path in args.descriptions:
        d = load(path)
        if args.background:
            d.background = args.background
        folder = args.out or os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            os.makedirs(folder)
        svg_path = os.path.join(folder, d.name + '.svg')
        d.save(svg_path)
        print('%s: %g x %g mm, %d blocks, %d lines, %d texts, smallest text %.1f mm'
              % (svg_path, d.W, d.H, len(d.blocks), len(d.lines), len(d._texts),
                 min(t['size'] for t in d._texts) if d._texts else 0))
        if d.issues:
            failed = True
            print('  %d issue(s):' % len(d.issues))
            for issue in d.issues:
                print('   - ' + issue)
        else:
            print('  check: 0 issues')
        if args.png or args.preview:
            import svg2png
        if args.png:
            svg2png.convert(svg_path, os.path.join(folder, d.name + '.png'), dpi=args.dpi)
            if args.split and d.split:
                sx, sy = d.split
                part = os.path.join(folder, 'split')
                if not os.path.isdir(part):
                    os.makedirs(part)
                svg2png.convert(svg_path, os.path.join(part, d.name + '_top.png'), dpi=args.dpi,
                                crop=(0, 0, d.W, sy))
                svg2png.convert(svg_path, os.path.join(part, d.name + '_notes.png'), dpi=args.dpi,
                                crop=(0, sy, sx, d.H))
        if args.preview:
            part = os.path.join(folder, 'preview')
            if not os.path.isdir(part):
                os.makedirs(part)
            svg2png.convert(svg_path, os.path.join(part, d.name + '_on_page_colour.png'), dpi=150,
                            background=PAGE_COLOUR)
    return 1 if failed and not args.lenient else 0


if __name__ == '__main__':
    sys.exit(main())
