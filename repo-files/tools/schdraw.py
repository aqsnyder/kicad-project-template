"""schdraw: redraw one KiCad 10 schematic sheet from a short script, without touching its netlist.

    import schdraw as D
    sh = D.Sheet.load('hw/main-board/power.kicad_sch')    # keeps every part, drops the old drawing
    c = sh.place('C17', 101.6, 76.2)                   # same uuid, fields, flags; new position
    sh.wire(c.pin('1'), (101.6, 63.5))                 # orthogonal, on the 1.27 mm grid
    sh.power('GND', c.pin('2'))
    sh.block(20, 40, 130, 120, 'CELL AND SUPPLY')
    sh.save()

What is kept from the sheet on disk: its uuid, paper, title block, every non-power symbol (uuid, reference, value,
all fields, DNP / BOM / board flags, unit, pin uuids, instance path) and any hierarchical sheet symbols. What is
dropped and drawn again by the script: wires, junctions, labels, no-connects, power symbols, PWR_FLAGs, text,
shapes. save() refuses to write if a kept part was not placed, adds the junctions, and prints lint warnings
(overlaps, crossings, dangling ends). Sheet.load(path, netlist=baseline.xml) also gives net() and stub(), which
end a pin the way the netlist says.

A generator starts from nothing instead (a script that draws the sheets of a panel of test coupons, say):
Sheet.new() for an empty sheet, add_symbol() for each part, then place(), wire() and the rest as above.

This is the one copy of the module: frontpages.py beside it (cover, Architecture, Mechanical, Revision History
and the page headings) uses its parser and writer, and its CALLOUT table is the key the cover's DESIGN
CONSIDERATIONS row shows. A design sheet keeps its top clear for the "[page] Title" heading: frontpages.CLEAR_TOP
says where the drawing may start on each paper size.

Standard library only (Python 3.9+). KiCad's stock symbol libraries are needed only for symbols that are not yet
in the sheet (power symbols, or parts added with add_symbol): KICAD_SHARE, or the default install folder.
"""
import copy
import glob
import os
import re
import uuid as _uuid

GRID = 1.27
SHARE = os.environ.get('KICAD_SHARE') or ('C:/Program Files/KiCad/10.0/share/kicad' if os.name == 'nt'
                                           else '/usr/share/kicad')
PAPER = {'A4': (297.0, 210.0), 'A3': (420.0, 297.0), 'A2': (594.0, 420.0)}
MARGIN = 10.0                                   # drawing sheet border
TITLE_BLOCK = (189.0, 44.0)                     # width, height kept clear at the bottom right, inside the border
#                                                 (hw/drawing-sheet.kicad_wks, drawn by titleblock.py)

# ---------------------------------------------------------------- style
FIELD_SIZE = 1.27
SHOW_GND_TEXT = False                           # the ground symbol says it; other rails show their name
SHOW_FLAG_TEXT = False
FRAME = dict(width=0.2, style='dash', color=(132, 132, 132))
HEADING = dict(size=2.0, bold=True, color=(0, 0, 132))
SUBHEAD = dict(size=1.27, color=(96, 96, 96))
NOTE = dict(size=1.27)                          # the theme's note colour (blue under Altium_Theme)
LEGEND = [                                      # Sheet.legend() and the front pages' NET COLOURS key: class
    (('Power',), 'supply rails'),               # names that share a row, and what they are for. The template's
    (('RF_50R',), '50 ohm lines'),              # classes; a class that is not here shows its name patterns
    (('GND',), 'ground'),
    (('Debug',), 'SWD, JTAG and reset'),
    (('UART',), 'serial ports'),
    (('Bus',), 'I2C, SPI and GPIO'),
    (('Clock',), 'clocks, crystals and oscillators'),
    (('Analog',), 'ADC inputs, references and sense lines'),
    (('USB',), 'USB data'),
]
CALLOUT = {                                     # boxed notes: border colour and width, text colour, bold
    'info': ((200, 200, 200), 0.6, None, False),            # the five colours of the cover's DESIGN
    'bringup': ((255, 165, 0), 0.6, None, False),           # CONSIDERATIONS row (frontpages.py draws it from
    'caution': ((250, 236, 0), 0.6, None, False),           # this table): a note on a sheet and its sample on
    'critical': ((255, 0, 0), 0.9, (255, 0, 0), True),      # the cover always agree
    'layout': ((0, 0, 255), 0.9, (0, 0, 255), True),
}
CALLOUT_WAS = {}                                # {border colour: kind} of boxed notes drawn in other colours
#                                                 before: frontpages.py brings such a box up to CALLOUT


# ---------------------------------------------------------------- S-expressions
class Sym(str):
    """An unquoted atom (keyword or number), written back as it was read."""


_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_UNESC = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"'}


def parse(text):
    stack, cur = [], []
    for tok in _TOKEN.findall(text):
        if tok == '(':
            stack.append(cur)
            cur = []
        elif tok == ')':
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif tok[0] == '"':
            cur.append(re.sub(r'\\(.)', lambda m: _UNESC.get(m.group(1), m.group(0)), tok[1:-1]))
        else:
            cur.append(Sym(tok))
    assert not stack and len(cur) == 1, 'unbalanced parentheses'
    return cur[0]


def fmt(v):
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, int):
        return str(v)
    s = ('%.4f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def _atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, (int, float)):
        return fmt(x)
    return '"%s"' % (str(x).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                     .replace('\r', '\\r').replace('\t', '\\t'))


def dump(node, depth=0):
    """Write a list the way KiCad's formatter does: child lists on their own lines, runs of (xy ...) on one,
    and a long run of plain values (a table's row heights) broken once the line passes column 72."""
    out = ['(']
    col = depth + 1
    had_list = False
    prev_xy = False
    first = True
    for x in node:
        if isinstance(x, list):
            is_xy = bool(x) and x[0] == 'xy'
            s = dump(x, depth + 1)
            if is_xy and prev_xy and col < 99:
                out.append(' ' + s)
                col += 1 + len(s)
            else:
                out.append('\n' + '\t' * (depth + 1) + s)
                col = len(s) - s.rfind('\n') - 1 if '\n' in s else depth + 1 + len(s)
            prev_xy = is_xy
            had_list = True
        else:
            s = _atom(x)
            if first:
                out.append(s)
                col += len(s)
            elif col >= 72:
                out.append('\n' + '\t' * (depth + 1) + s)
                col = depth + 1 + len(s)
                had_list = True                 # the closing parenthesis then goes on its own line
            else:
                out.append(' ' + s)
                col += len(s) + 1
            prev_xy = False
        first = False
    out.append('\n' + '\t' * depth + ')' if had_list else ')')
    return ''.join(out)


def S(*items):
    """Build a list node: S('at', 1, 2, 0) -> (at 1 2 0). The first item is the keyword."""
    return [Sym(items[0])] + list(items[1:])


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def first(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def put(node, child, after=None):
    """Replace the child list with the same keyword, or insert it (after the named keyword, else at the end)."""
    for i, x in enumerate(node):
        if isinstance(x, list) and x and x[0] == child[0]:
            node[i] = child
            return
    if after:
        for i, x in enumerate(node):
            if isinstance(x, list) and x and x[0] == after:
                node.insert(i + 1, child)
                return
    node.append(child)


def drop(node, key):
    node[:] = [x for x in node if not (isinstance(x, list) and x and x[0] == key)]


# ---------------------------------------------------------------- geometry
def R(v):
    return round(float(v), 4) + 0.0


def P(p):
    return (R(p[0]), R(p[1]))


def on_grid(v, grid=GRID):
    return abs(v / grid - round(v / grid)) < 1e-6


def snap(v, grid=GRID):
    return R(round(v / grid) * grid)


def matrix(rot=0, mirror=None):
    """Sheet-frame matrix (a, b, c, d) of a symbol placed with (at x y rot) and (mirror x|y).

    A point of the library symbol at (px, py), y up, lands at x + a*px + b*(-py), y + c*px + d*(-py). KiCad
    turns the symbol counter-clockwise by rot first, then mirrors it on the page: 'x' swaps top and bottom,
    'y' swaps left and right (all twelve cases were checked against kicad-cli's netlist).
    """
    assert rot in (0, 90, 180, 270) and mirror in (None, 'x', 'y'), (rot, mirror)
    a, b, c, d = 1, 0, 0, 1
    for _ in range(rot // 90):
        a, b, c, d = c, d, -a, -b
    if mirror == 'x':
        c, d = -c, -d
    elif mirror == 'y':
        a, b = -a, -b
    return a, b, c, d


def apply(m, dx, dy):
    return (m[0] * dx + m[1] * dy, m[2] * dx + m[3] * dy)


DIRS = {'right': (1, 0), 'left': (-1, 0), 'up': (0, -1), 'down': (0, 1)}
SIDE_ANGLE = {'right': 0, 'up': 90, 'left': 180, 'down': 270}
_CCW = ['up', 'left', 'down', 'right']          # a symbol turned counter-clockwise goes through these


def field_just(m, h='left', v='center'):
    """File angle and justification for a symbol field that should read horizontally on the page.

    h: 'left' (text runs right from the anchor), 'center', 'right'. v: 'bottom' (text sits above the anchor),
    'center', 'top'. KiCad applies the symbol's rotation and mirror to a field's box, so both swap with them.
    """
    a, b, c, d = m
    ang = 90 if b != 0 else 0
    along = (1, 0) if ang == 0 else (0, -1)
    up = (0, -1) if ang == 0 else (-1, 0)
    if a * along[0] + b * along[1] < 0:
        h = {'left': 'right', 'right': 'left'}.get(h, h)
    if c * up[0] + d * up[1] > 0:
        v = {'top': 'bottom', 'bottom': 'top'}.get(v, v)
    return ang, h, v


# ---------------------------------------------------------------- text size estimate (KiCad stroke font)
_W = {' ': 0.70, '#': 1.13, '%': 1.16, "'": 0.49, '(': 0.65, ')': 0.65, '*': 0.78, '+': 1.29, ',': 0.44,
      '-': 1.17, '.': 0.46, '/': 1.01, ':': 0.45, ';': 0.41, '<': 1.02, '=': 1.16, '>': 1.2, 'A': 0.85,
      'B': 1.01, 'C': 1.04, 'D': 1.06, 'E': 0.91, 'F': 0.85, 'G': 1.06, 'H': 1.08, 'I': 0.47, 'J': 0.82,
      'K': 0.98, 'L': 0.83, 'M': 1.21, 'N': 1.09, 'O': 1.03, 'P': 1.01, 'Q': 1.01, 'R': 1.03, 'S': 0.98,
      'T': 0.79, 'U': 1.09, 'V': 0.91, 'W': 1.19, 'X': 0.98, 'Y': 0.85, 'Z': 0.74, '_': 0.76, 'a': 0.92,
      'b': 0.98, 'c': 0.84, 'd': 0.91, 'e': 0.88, 'f': 0.58, 'g': 0.93, 'h': 0.93, 'i': 0.53, 'j': 0.55,
      'k': 0.86, 'l': 0.55, 'm': 1.34, 'n': 0.92, 'o': 0.9, 'p': 0.94, 'q': 0.94, 'r': 0.64, 's': 0.8,
      't': 0.56, 'u': 0.9, 'v': 0.74, 'w': 1.08, 'x': 0.81, 'y': 0.8, 'z': 0.7}


def text_width(s, size=1.27, bold=False):
    s = re.sub(r'[~{}]', '', s)
    return sum(_W.get(ch, 1.0) for ch in s) * size * (1.06 if bold else 1.0)


def text_box(s, x, y, size=1.27, h='left', v='bottom', angle=0, bold=False):
    """Approximate (x0, y0, x1, y1) of a text; angle 0 or 90."""
    lines = s.split('\n')
    w = max(text_width(ln, size, bold) for ln in lines)
    ht = size * (1.0 + 1.62 * (len(lines) - 1))
    x0 = {'left': 0, 'center': -w / 2, 'right': -w}[h]
    y0 = {'top': 0, 'center': -ht / 2, 'bottom': -ht}[v]
    if angle in (90, 270):
        return (x + y0, y - x0 - w, x + y0 + ht, y - x0)
    return (x + x0, y + y0, x + x0 + w, y + y0 + ht)


# ---------------------------------------------------------------- symbol libraries
_libs = {}


def _lib_path(lib, lib_dir):
    if lib_dir:
        p = os.path.join(lib_dir, lib + '.kicad_sym')
        if os.path.exists(p):
            return p
    p = os.path.join(SHARE, 'symbols', lib + '.kicad_sym')
    return p if os.path.exists(p) else os.path.join(SHARE, 'symbols', lib + '.kicad_symdir')


def _load_lib(lib, lib_dir):
    key = (lib, lib_dir)
    if key not in _libs:
        p = _lib_path(lib, lib_dir)
        files = sorted(os.path.join(p, f) for f in os.listdir(p)) if os.path.isdir(p) else [p]
        syms = {}
        for fn in files:
            for s in find(parse(open(fn, encoding='utf-8').read()), 'symbol'):
                syms[s[1]] = s
        _libs[key] = syms
    return _libs[key]


def lib_symbol(lib_id, lib_dir=None):
    """A library symbol as KiCad embeds it in a sheet: 'extends' resolved, named by its lib_id."""
    lib, name = lib_id.split(':', 1)
    syms = _load_lib(lib, lib_dir)
    if name not in syms:
        raise KeyError('%s is not in library %s (%s)' % (name, lib, _lib_path(lib, lib_dir)))

    def flat(nm):
        s = syms[nm]
        ext = first(s, 'extends')
        if not ext:
            return copy.deepcopy(s)
        parent = flat(ext[1])
        out = [Sym('symbol'), nm]
        child_props = {p[1]: p for p in find(s, 'property')}
        for x in parent[2:]:
            if isinstance(x, list) and x[0] == 'property' and x[1] in child_props:
                out.append(copy.deepcopy(child_props.pop(x[1])))
            elif isinstance(x, list) and x[0] == 'symbol':
                out.append([x[0], x[1].replace(ext[1] + '_', nm + '_', 1)] + x[2:])
            else:
                out.append(x)
        idx = next(i for i, x in enumerate(out) if isinstance(x, list) and x[0] == 'symbol')
        for p in child_props.values():
            out.insert(idx, copy.deepcopy(p))
            idx += 1
        for x in s[2:]:
            if isinstance(x, list) and x[0] not in ('property', 'extends', 'symbol'):
                out = [y for y in out if not (isinstance(y, list) and y[0] == x[0])]
                out.insert(2, x)
        return out

    node = flat(name)
    node[1] = lib_id
    return node


def _units(sub_name):
    m = re.match(r'.*_(\d+)_(\d+)$', sub_name)
    return int(m.group(1)), int(m.group(2))


def sym_pins(symbol, unit=1):
    """Pins of one unit: list of dicts (number, name, type, x, y, angle, length, hidden), library frame."""
    res = []
    for sub in find(symbol, 'symbol'):
        u, style = _units(sub[1])
        if u not in (0, unit) or style not in (0, 1):
            continue
        for p in find(sub, 'pin'):
            at = first(p, 'at')
            hide = first(p, 'hide')
            res.append(dict(number=first(p, 'number')[1], name=first(p, 'name')[1], type=str(p[1]),
                            x=float(at[1]), y=float(at[2]), angle=int(float(at[3])) if len(at) > 3 else 0,
                            length=float(first(p, 'length')[1]),
                            hidden=bool(hide is not None and hide[1] == 'yes') or 'hide' in p))
    return res


def sym_box(symbol, unit=1):
    """Body extent (x0, y0, x1, y1) in the library frame (y up), from the unit's graphics; pins as a fallback."""
    xs, ys = [], []
    for sub in find(symbol, 'symbol'):
        u, style = _units(sub[1])
        if u not in (0, unit) or style not in (0, 1):
            continue
        for r in find(sub, 'rectangle'):
            for k in ('start', 'end'):
                xs.append(float(first(r, k)[1]))
                ys.append(float(first(r, k)[2]))
        for kind in ('polyline', 'bezier'):
            for pl in find(sub, kind):
                for xy in find(first(pl, 'pts'), 'xy'):
                    xs.append(float(xy[1]))
                    ys.append(float(xy[2]))
        for c in find(sub, 'circle'):
            cx, cy = (float(v) for v in first(c, 'center')[1:3])
            r = float(first(c, 'radius')[1])
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        for a in find(sub, 'arc'):
            for k in ('start', 'mid', 'end'):
                if first(a, k):
                    xs.append(float(first(a, k)[1]))
                    ys.append(float(first(a, k)[2]))
    if not xs:
        for p in sym_pins(symbol, unit):
            xs.append(p['x'])
            ys.append(p['y'])
    if not xs:
        return (-1.27, -1.27, 1.27, 1.27)
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------- a placed symbol
class Part:
    """A symbol on the sheet. pin('3') or pin('VOUT') gives the absolute position of that pin's wire end."""

    def __init__(self, sheet, node, libsym, ref, unit, x, y, rot, mirror, power=False):
        self.sheet, self.node, self.libsym = sheet, node, libsym
        self.ref, self.unit, self.power = ref, unit, power
        self.x, self.y, self.rot, self.mirror = R(x), R(y), rot, mirror
        self.m = matrix(rot, mirror)
        self.pins = {}
        for p in sym_pins(libsym, unit):
            dx, dy = apply(self.m, p['x'], -p['y'])
            ang = p['angle']
            ox, oy = {0: (-1, 0), 90: (0, 1), 180: (1, 0), 270: (0, -1)}[ang]      # away from the body, sheet frame
            ox, oy = apply(self.m, ox, oy)
            self.pins[p['number']] = dict(p, at=P((self.x + dx, self.y + dy)), out=(ox, oy))
        bx0, by0, bx1, by1 = sym_box(libsym, unit)
        c = [apply(self.m, px, -py) for px in (bx0, bx1) for py in (by0, by1)]
        self.box = (R(self.x + min(p[0] for p in c)), R(self.y + min(p[1] for p in c)),
                    R(self.x + max(p[0] for p in c)), R(self.y + max(p[1] for p in c)))
        self.texts = []                          # (string, box) of the visible fields, for the overlap check

    def _find(self, key):
        key = str(key)
        if key in self.pins:
            return self.pins[key]
        hits = [p for p in self.pins.values() if p['name'] == key]
        if len(hits) == 1 or (hits and len({p['at'] for p in hits}) == 1):
            return hits[0]
        raise KeyError('%s has no single pin %r (pins: %s)' % (
            self.ref, key, ', '.join('%s=%s' % (n, p['name']) for n, p in sorted(self.pins.items()))))

    def pin(self, key):
        """Absolute (x, y) of a pin's connection point, by number or by (unique) name."""
        return self._find(key)['at']

    def out(self, key, n=2):
        """The point n grid steps (1.27 mm each) straight out of a pin: the far end of a stub."""
        p = self._find(key)
        return P((p['at'][0] + p['out'][0] * n * GRID, p['at'][1] + p['out'][1] * n * GRID))

    def side(self, key):
        """Which way a wire leaves the pin: 'left', 'right', 'up' or 'down'."""
        o = self._find(key)['out']
        return next(k for k, v in DIRS.items() if v == (round(o[0]), round(o[1])))

    @property
    def center(self):
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)


class Netlist:
    """Pin-to-net map of a kicadxml netlist (the export made before the redraw): the truth to draw to."""

    def __init__(self, path):
        import xml.etree.ElementTree as ET
        root = ET.parse(path).getroot()
        self.pins, self.nets = {}, {}
        for n in root.iter('net'):
            nodes = [(x.get('ref'), x.get('pin')) for x in n.iter('node')]
            self.nets[n.get('name')] = nodes
            for node in nodes:
                self.pins[node] = n.get('name')

    def net(self, ref, pin):
        """Net name of a pin, or None if the pin is on no net."""
        return self.pins.get((ref, str(pin)))

    def refs(self, net):
        return sorted({r for r, _ in self.nets.get(net, [])})


def _effects(size=1.27, h='center', v='center', bold=False, italic=False, color=None, face=None):
    font = S('font')
    if face:
        font.append(S('face', face))
    font.append(S('size', size, size))
    if bold:
        font.append(S('bold', Sym('yes')))
    if italic:
        font.append(S('italic', Sym('yes')))
    if color:
        font.append(S('color', *_rgba(color)))
    e = S('effects', font)
    j = [Sym(t) for t in (h, v) if t != 'center']
    if j:
        e.append([Sym('justify')] + j)
    return e


def _rgba(c):
    return (c[0], c[1], c[2], c[3] if len(c) > 3 else 1)


def _stroke(width=0, style='default', color=None):
    s = S('stroke', S('width', width), S('type', Sym(style)))
    if color:
        s.append(S('color', *_rgba(color)))
    return s


def _prop(name, value, x, y, angle=0, h='center', v='center', hide=False, size=FIELD_SIZE):
    p = S('property', name, value, S('at', R(x), R(y), angle))
    if hide:
        p.append(S('hide', Sym('yes')))
    p += [S('show_name', Sym('no')), S('do_not_autoplace', Sym('no')), _effects(size, h, v)]
    return p


# ---------------------------------------------------------------- the sheet
class Sheet:
    def __init__(self):
        self.path = None
        self.head = []                 # version, generator, uuid, paper, title_block
        self.tail = []                 # sheet_instances, embedded_fonts
        self.cache = {}                # lib_symbols of the sheet on disk, by name
        self.kept = {}                 # (ref, unit) -> symbol node of a real part
        self.sheets = []               # hierarchical sheet symbols
        self.old = []                  # the dropped drawing items (old text is in here if you want to reuse it)
        self.parts = []                # placed Parts, in order
        self.items = []                # new drawing nodes other than wires, junctions and symbols
        self.segs = []                 # wire segments ((x1, y1), (x2, y2))
        self.labels = []               # (kind, name, (x, y), side, box)
        self.ncs = []
        self.extra_junctions = set()
        self.boxes = []                # (what, box) of notes, headings and callouts, for the overlap check
        self.frames = []
        self.project = None
        self.inst_path = None
        self.page = 1
        self.lib_dir = None
        self.uuid = None
        self._n = {}
        self._pwr = 0
        self._flg = 0
        self.warnings = []
        self.netlist = None

    # ------------------------------------------------------------ loading
    @classmethod
    def load(cls, path, lib_dir=None, netlist=None):
        """Read a sheet. Real parts are kept for place(); everything drawn is dropped.

        netlist: the kicadxml export made before the redraw (baseline/<board>.xml); net() and stub() read it.
        """
        self = cls()
        self.netlist = Netlist(netlist) if netlist else None
        self.path = os.path.abspath(path)
        tree = parse(open(self.path, encoding='utf-8').read())
        assert tree[0] == 'kicad_sch', path
        d = os.path.dirname(self.path)
        self.lib_dir = lib_dir or os.path.join(d, '..', 'lib', 'lib_sym')
        for x in tree[1:]:
            k = x[0] if isinstance(x, list) else None
            if k in ('version', 'generator', 'generator_version', 'uuid', 'paper', 'title_block'):
                self.head.append(x)
            elif k == 'lib_symbols':
                self.cache = {s[1]: s for s in find(x, 'symbol')}
            elif k in ('sheet_instances', 'embedded_fonts', 'symbol_instances'):
                self.tail.append(x)
            elif k == 'sheet':
                self.sheets.append(x)
            elif k == 'symbol':
                ref, unit = self._ref_unit(x)
                lib_id = first(x, 'lib_id')[1]
                if lib_id.startswith('power:') or ref.startswith('#'):
                    self.old.append(x)
                else:
                    assert (ref, unit) not in self.kept, 'two symbols are %s unit %d' % (ref, unit)
                    self.kept[(ref, unit)] = x
            else:
                self.old.append(x)
        self.uuid = first(tree, 'uuid')[1]
        self._context(d)
        return self

    @classmethod
    def new(cls, path, uuid, project, inst_path, page=1, paper='A4', title='', lib_dir=None):
        """An empty sheet for a generator (parts come from add_symbol). inst_path: '/<root uuid>/<sheet uuid>'."""
        self = cls()
        self.path = os.path.abspath(path)
        self.uuid, self.project, self.inst_path, self.page = uuid, project, inst_path, page
        self.lib_dir = lib_dir or os.path.join(os.path.dirname(self.path), '..', 'lib', 'lib_sym')
        self.head = [S('version', Sym('20260306')), S('generator', 'eeschema'), S('generator_version', '10.0'),
                     S('uuid', uuid), S('paper', paper),
                     S('title_block', S('title', title), S('date', '${RELEASE_DATE}'), S('rev', '${REVISION}'),
                       S('company', '${COMPANY}'))]
        self.tail = [S('embedded_fonts', Sym('no'))]
        return self

    @staticmethod
    def _ref_unit(node):
        inst = first(node, 'instances')
        if inst:
            path = first(first(inst, 'project'), 'path')
            return first(path, 'reference')[1], int(first(path, 'unit')[1])
        ref = next(p[2] for p in find(node, 'property') if p[1] == 'Reference')
        return ref, int(first(node, 'unit')[1])

    def _context(self, d):
        """Project name, instance path and page number, from the root sheet next to this one."""
        pros = glob.glob(os.path.join(d, '*.kicad_pro'))
        for node in self.kept.values():
            proj = first(first(node, 'instances'), 'project')
            self.project, self.inst_path = proj[1], first(proj, 'path')[1]
            break
        if len(pros) != 1:
            assert self.inst_path, 'no project file beside %s and no symbol to take the instance path from' % d
            return
        name = os.path.basename(pros[0])[:-len('.kicad_pro')]
        root_file = os.path.join(d, name + '.kicad_sch')
        root = parse(open(root_file, encoding='utf-8').read())
        root_uuid = first(root, 'uuid')[1]
        self.project = self.project or name
        if os.path.abspath(root_file) == self.path:
            path, self.page = '/' + root_uuid, 1
        else:
            fn = os.path.basename(self.path)
            for sh in find(root, 'sheet'):
                if any(p[1] == 'Sheetfile' and p[2] == fn for p in find(sh, 'property')):
                    path = '/%s/%s' % (root_uuid, first(sh, 'uuid')[1])
                    pg = first(first(first(first(sh, 'instances'), 'project'), 'path'), 'page')
                    self.page = int(pg[1])
                    break
            else:
                raise ValueError('%s is not a sheet of %s' % (fn, root_file))
        assert self.inst_path in (None, path), (self.inst_path, path)
        self.inst_path = path

    # ------------------------------------------------------------ small things
    def _uid(self, what):
        """Deterministic uuid for a new item: the same script gives the same file."""
        n = self._n.get(what, 0)
        self._n[what] = n + 1
        return str(_uuid.uuid5(_uuid.UUID(self.uuid), '%s#%d' % (what, n)))

    @property
    def paper(self):
        return str(self._head('paper')[1])

    @paper.setter
    def paper(self, size):
        """'A4', 'A3', 'A2', or (width, height) in mm for a custom page."""
        node = self._head('paper')
        if isinstance(size, str):
            assert size in PAPER, size
            node[1:] = [size]
        else:
            node[1:] = ['User', R(size[0]), R(size[1])]

    @property
    def page_size(self):
        node = self._head('paper')
        if node[1] == 'User':
            return float(node[2]), float(node[3])
        w, h = PAPER[str(node[1])]
        return (h, w) if 'portrait' in node else (w, h)

    def _head(self, key):
        return next(x for x in self.head if x[0] == key)

    @property
    def title(self):
        return first(self._head('title_block'), 'title')[1]

    @title.setter
    def title(self, text):
        first(self._head('title_block'), 'title')[1] = text

    @property
    def area(self):
        """(x0, y0, x1, y1) inside the border. The title block takes the bottom right corner: see clear_of_title."""
        w, h = self.page_size
        return (MARGIN + 2, MARGIN + 2, w - MARGIN - 2, h - MARGIN - 2)

    @property
    def title_box(self):
        w, h = self.page_size
        return (w - MARGIN - TITLE_BLOCK[0], h - MARGIN - TITLE_BLOCK[1], w - MARGIN, h - MARGIN)

    def old_text(self):
        """The text and text boxes of the sheet as it was on disk: [(kind, string, x, y)]."""
        out = []
        for x in self.old:
            if x[0] in ('text', 'text_box'):
                at = first(x, 'at')
                out.append((str(x[0]), x[1], float(at[1]), float(at[2])))
        return out

    def old_flags(self):
        """Nets that carried a PWR_FLAG in the sheet as it was on disk: [(kind, name)], kind 'power', 'label'
        or 'global_label'. ERC needs a flag on each of them again (flags are not in the netlist)."""
        segs, tags = [], []
        for x in self.old:
            if x[0] == 'wire':
                a, b = [P((float(q[1]), float(q[2]))) for q in find(first(x, 'pts'), 'xy')]
                segs.append((a, b))
            elif x[0] in ('label', 'global_label'):
                at = first(x, 'at')
                tags.append((str(x[0]), x[1], P((float(at[1]), float(at[2])))))
            elif x[0] == 'symbol' and first(x, 'lib_id')[1] != 'power:PWR_FLAG':
                at = first(x, 'at')
                value = next(p[2] for p in find(x, 'property') if p[1] == 'Value')
                tags.append(('power', value, P((float(at[1]), float(at[2])))))

        def on(p, s):
            (ax, ay), (bx, by) = s
            return min(ax, bx) <= p[0] <= max(ax, bx) and min(ay, by) <= p[1] <= max(ay, by) and \
                (ax == bx == p[0] or ay == by == p[1])

        out = []
        for x in self.old:
            if x[0] == 'symbol' and first(x, 'lib_id')[1] == 'power:PWR_FLAG':
                at = first(x, 'at')
                pts, seen, grew = {P((float(at[1]), float(at[2])))}, set(), True
                while grew:
                    grew = False
                    for i, s in enumerate(segs):
                        if i not in seen and any(on(p, s) for p in pts):
                            seen.add(i)
                            pts |= set(s)
                            grew = True
                hit = [(k, n) for k, n, p in tags if p in pts or any(on(p, segs[i]) for i in seen)]
                out.append(hit[0] if hit else ('?', 'flag at %s' % (tuple(at[1:3]),)))
        return sorted(set(out))

    def unplaced(self):
        done = {(p.ref, p.unit) for p in self.parts}
        return sorted(k for k in self.kept if k not in done)

    # ------------------------------------------------------------ symbols
    def _libsym(self, node):
        name = first(node, 'lib_name')
        key = name[1] if name else first(node, 'lib_id')[1]
        if key not in self.cache:
            self.cache[key] = lib_symbol(first(node, 'lib_id')[1], self.lib_dir)
        return self.cache[key]

    def place(self, ref, x, y, rot=0, mirror=None, unit=1, fields='auto', ref_at=None, val_at=None,
              value=True):
        """Put a kept part at (x, y). Returns the Part (ask it for pin positions).

        rot: 0, 90, 180, 270 (counter-clockwise). mirror: None, 'x' (top and bottom swap on the page) or 'y'
        (left and right swap on the page), applied after the rotation as KiCad does.
        fields: where Reference and Value go: 'auto', 'right', 'left', 'above', 'below', 'split' (reference
        above, value below), 'tl' / 'tr' (above the top left / right corner), 'bl' / 'br' (below the bottom
        corners). ref_at / val_at = (x, y) or (x, y, 'left'|'center'|'right') override one field, absolute.
        value=False hides the Value field.
        """
        key = (ref, unit)
        if key not in self.kept:
            raise KeyError('%s unit %d is not on this sheet (parts: %s)' % (
                ref, unit, ' '.join('%s%s' % (r, '' if u == 1 else '.%d' % u) for r, u in sorted(self.kept))))
        assert not any((p.ref, p.unit) == key for p in self.parts), '%s is placed twice' % ref
        node = self.kept[key]
        part = Part(self, node, self._libsym(node), ref, unit, x, y, rot, mirror)
        self._check_grid(part)
        put(node, S('at', part.x, part.y, rot))
        drop(node, 'mirror')
        if mirror:
            put(node, S('mirror', Sym(mirror)), after='at')
        drop(node, 'fields_autoplaced')
        self._fields(part, fields, ref_at, val_at, value)
        self.parts.append(part)
        return part

    def add_symbol(self, ref, lib_id, value=None, footprint=None, fields=None, unit=1, uuid=None, dnp=False,
                   in_bom=True, on_board=True):
        """Create a part that is not on the sheet yet (for generators). Place it with place() afterwards.

        fields: dict of extra fields (MPN, Manufacturer, ...); Datasheet and Description default to the
        library's. uuid: pass a stable one (uuid5 of the reference) so a board keeps its link.
        """
        assert (ref, unit) not in self.kept, ref
        lib = lib_symbol(lib_id, self.lib_dir) if lib_id not in self.cache else self.cache[lib_id]
        self.cache.setdefault(lib_id, lib)
        libprops = {p[1]: p[2] for p in find(lib, 'property')}
        fields = dict(fields or {})
        node = S('symbol', S('lib_id', lib_id), S('at', 0, 0, 0), S('unit', unit), S('body_style', 1),
                 S('exclude_from_sim', Sym('no')), S('in_bom', in_bom and not dnp), S('on_board', on_board),
                 S('in_pos_files', Sym('yes')), S('dnp', dnp),
                 S('uuid', uuid or self._uid('sym:%s:%d' % (ref, unit))))
        node.append(_prop('Reference', ref, 0, 0))
        node.append(_prop('Value', value if value is not None else libprops.get('Value', ''), 0, 0))
        node.append(_prop('Footprint', footprint if footprint is not None else libprops.get('Footprint', ''),
                          0, 0, hide=True))
        for k in ('Datasheet', 'Description'):
            node.append(_prop(k, fields.pop(k, libprops.get(k, '')), 0, 0, hide=True))
        for k, v in fields.items():
            node.append(_prop(k, v, 0, 0, hide=True))
        for p in sym_pins(lib, unit):
            node.append(S('pin', p['number'], S('uuid', self._uid('pin:%s:%s' % (ref, p['number'])))))
        node.append(S('instances', S('project', self.project,
                                     S('path', self.inst_path, S('reference', ref), S('unit', unit)))))
        self.kept[(ref, unit)] = node
        return node

    def _check_grid(self, part):
        for n, p in part.pins.items():
            if not (on_grid(p['at'][0]) and on_grid(p['at'][1])):
                raise ValueError('%s pin %s lands off the %.2f mm grid at %s: move the part' % (
                    part.ref, n, GRID, p['at']))

    def _fields(self, part, where, ref_at, val_at, value):
        x0, y0, x1, y1 = part.box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sides = {part.side(n) for n in part.pins}
        if where == 'auto':
            if len(part.pins) <= 2:
                where = 'right' if sides <= {'up', 'down'} else 'split'
            elif 'up' not in sides:
                where = 'tl'
            elif 'right' not in sides:
                where = 'right'
            elif 'down' not in sides:
                where = 'bl'
            elif 'left' not in sides:
                where = 'left'
            else:
                where = 'tl'
        pin_top = min([p['at'][1] for p in part.pins.values()] + [y0])
        pin_bot = max([p['at'][1] for p in part.pins.values()] + [y1])
        spots = {
            'right': ((x1 + 1.27, cy - 1.27, 'left', 'center'), (x1 + 1.27, cy + 1.27, 'left', 'center')),
            'left': ((x0 - 1.27, cy - 1.27, 'right', 'center'), (x0 - 1.27, cy + 1.27, 'right', 'center')),
            'split': ((cx, y0 - 0.9, 'center', 'bottom'), (cx, y1 + 0.9, 'center', 'top')),
            'above': ((cx, y0 - 3.2, 'center', 'bottom'), (cx, y0 - 0.9, 'center', 'bottom')),
            'below': ((cx, y1 + 0.9, 'center', 'top'), (cx, y1 + 3.2, 'center', 'top')),
            'tl': ((x0, pin_top - 3.4, 'left', 'bottom'), (x0, pin_top - 1.1, 'left', 'bottom')),
            'tr': ((x1, pin_top - 3.4, 'right', 'bottom'), (x1, pin_top - 1.1, 'right', 'bottom')),
            'bl': ((x0, pin_bot + 1.1, 'left', 'top'), (x0, pin_bot + 3.4, 'left', 'top')),
            'br': ((x1, pin_bot + 1.1, 'right', 'top'), (x1, pin_bot + 3.4, 'right', 'top')),
        }
        if where not in spots:
            raise ValueError('fields=%r: use one of auto %s' % (where, ' '.join(spots)))
        rspot, vspot = spots[where]
        if not value and where in ('right', 'left'):          # the reference alone: centre it on the body
            rspot = (rspot[0], cy, rspot[2], 'center')
        if ref_at:
            rspot = (ref_at[0], ref_at[1], ref_at[2] if len(ref_at) > 2 else 'left',
                     ref_at[3] if len(ref_at) > 3 else 'center')
        if val_at:
            vspot = (val_at[0], val_at[1], val_at[2] if len(val_at) > 2 else 'left',
                     val_at[3] if len(val_at) > 3 else 'center')
        for prop in find(part.node, 'property'):
            name = prop[1]
            if name in ('Reference', 'Value'):
                fx, fy, h, v = rspot if name == 'Reference' else vspot
                hide = (name == 'Value' and not value)
                self._set_prop(part, prop, fx, fy, h, v, hide)
            else:
                hidden = first(prop, 'hide')
                if hidden is None or hidden[1] != 'yes':
                    self.warnings.append('%s: field %s is visible and was left at the part origin' % (
                        part.ref, name))
                put(prop, S('at', part.x, part.y, 0))

    def _set_prop(self, part, prop, fx, fy, h, v, hide):
        ang, fh, fv = field_just(part.m, h, v)
        put(prop, S('at', R(fx), R(fy), ang))
        drop(prop, 'hide')
        if hide:
            put(prop, S('hide', Sym('yes')), after='at')
        eff = first(prop, 'effects')
        size = FIELD_SIZE
        put(prop, _effects(size, fh, fv))
        if eff is not None and first(eff, 'hide'):          # KiCad 8 files kept (hide yes) inside effects
            pass
        if not hide:
            part.texts.append((prop[2], text_box(prop[2], fx, fy, size, h, v)))

    # ------------------------------------------------------------ power symbols and flags
    def _power_symbol(self, lib_id, ref, value, at, direction, show):
        at = P(at)
        if lib_id not in self.cache:
            self.cache[lib_id] = lib_symbol(lib_id, self.lib_dir)
        lib = self.cache[lib_id]
        bx0, by0, bx1, by1 = sym_box(lib, 1)
        natural = 'up' if (by0 + by1) / 2 >= 0 else 'down'
        rot = ((_CCW.index(direction) - _CCW.index(natural)) % 4) * 90
        ext = max(abs(by0), abs(by1))
        node = S('symbol', S('lib_id', lib_id), S('at', at[0], at[1], rot), S('unit', 1), S('body_style', 1),
                 S('exclude_from_sim', Sym('no')), S('in_bom', Sym('yes')), S('on_board', Sym('yes')),
                 S('in_pos_files', Sym('yes')), S('dnp', Sym('no')), S('uuid', self._uid('pwr:' + ref)))
        part = Part(self, node, lib, ref, 1, at[0], at[1], rot, None, power=True)
        dx, dy = DIRS[direction]
        tx, ty = at[0] + dx * (ext + 0.6), at[1] + dy * (ext + 0.6)
        h = {'right': 'left', 'left': 'right'}.get(direction, 'center')
        v = {'up': 'bottom', 'down': 'top'}.get(direction, 'center')
        ang, fh, fv = field_just(part.m, h, v)
        node.append(_prop('Reference', ref, at[0], at[1], hide=True))
        vp = _prop('Value', value, tx, ty, ang, fh, fv, hide=not show)
        node.append(vp)
        for k in ('Footprint', 'Datasheet', 'Description'):
            node.append(_prop(k, '', at[0], at[1], hide=True))
        for p in sym_pins(lib, 1):
            node.append(S('pin', p['number'], S('uuid', self._uid('pin:%s:%s' % (ref, p['number'])))))
        node.append(S('instances', S('project', self.project,
                                     S('path', self.inst_path, S('reference', ref), S('unit', 1)))))
        if show:
            part.texts.append((value, text_box(value, tx, ty, FIELD_SIZE, h, v)))
        self.parts.append(part)
        return part

    def power(self, name, at, direction=None, text=None):
        """A power symbol (power:<name>, for example GND or VDD) with its pin at `at`.

        direction: where the symbol sits from the wire end: 'down' for grounds and 'up' for rails by default.
        text: show the net name beside it (default: yes for rails, SHOW_GND_TEXT for GND).
        """
        ground = name.upper().startswith(('GND', 'VSS', 'EARTH'))
        direction = direction or ('down' if ground else 'up')
        if text is None:
            text = SHOW_GND_TEXT if ground else True
        self._pwr += 1
        return self._power_symbol('power:' + name, '#PWR%d' % (self.page * 1000 + self._pwr), name, at,
                                  direction, text)

    def flag(self, at, direction='up', text=None):
        """A PWR_FLAG with its pin at `at` (tells ERC the net is driven)."""
        self._flg += 1
        return self._power_symbol('power:PWR_FLAG', '#FLG%d' % (self.page * 1000 + self._flg), 'PWR_FLAG', at,
                                  direction, SHOW_FLAG_TEXT if text is None else text)

    # ------------------------------------------------------------ wires
    def wire(self, *pts):
        """Orthogonal wire through the points. Junctions are added by save() where three or more ends meet."""
        pts = [P(p) for p in pts]
        assert len(pts) >= 2, 'a wire needs two points'
        for p in pts:
            if not (on_grid(p[0]) and on_grid(p[1])):
                raise ValueError('wire point %s is off the %.2f mm grid' % (p, GRID))
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError('wire %s to %s is not horizontal or vertical: add a corner point' % (a, b))
            self.segs.append((a, b))
        return pts[-1]

    def hv(self, a, b):
        """Wire from a to b: horizontal first, then vertical."""
        return self.wire(a, (b[0], a[1]), b)

    def vh(self, a, b):
        """Wire from a to b: vertical first, then horizontal."""
        return self.wire(a, (a[0], b[1]), b)

    def junction(self, at):
        """Force a junction dot (save() adds the needed ones itself)."""
        self.extra_junctions.add(P(at))

    def nc(self, at):
        """No-connect mark on a pin."""
        at = P(at)
        self.ncs.append(at)
        self.items.append(S('no_connect', S('at', at[0], at[1]), S('uuid', self._uid('nc:%s,%s' % at))))

    # ------------------------------------------------------------ labels
    def _label(self, kind, name, at, side, shape, size):
        at = P(at)
        assert side in SIDE_ANGLE, side
        if not (on_grid(at[0]) and on_grid(at[1])):
            raise ValueError('label %s at %s is off the grid' % (name, at))
        ang = SIDE_ANGLE[side]
        h = 'left' if side in ('right', 'up') else 'right'
        node = S(kind, name)
        if kind != 'label':
            node.append(S('shape', Sym(shape)))
        node.append(S('at', at[0], at[1], ang))
        node.append(_effects(size, h, 'bottom' if kind == 'label' else 'center'))
        node.append(S('uuid', self._uid('%s:%s:%s,%s' % (kind, name, at[0], at[1]))))
        if kind == 'global_label':
            pr = S('property', 'Intersheetrefs', '${INTERSHEET_REFS}', S('at', at[0], at[1], ang),
                   S('hide', Sym('yes')), S('show_name', Sym('no')), S('do_not_autoplace', Sym('no')),
                   _effects(size, h, 'center'))
            node.append(pr)
        self.items.append(node)
        w = text_width(name, size)
        dx, dy = DIRS[side]
        if kind == 'label':                       # the text sits on the wire: above it, or to its left
            box = (min(at[0], at[0] + dx * w) - abs(dy) * size * 1.3,
                   min(at[1], at[1] + dy * w) - abs(dx) * size * 1.3,
                   max(at[0], at[0] + dx * w), max(at[1], at[1] + dy * w))
        else:
            ln, hw = w + size * 2.2, size * 0.95  # the outline adds a point and margins
            box = (min(at[0], at[0] + dx * ln) - abs(dy) * hw, min(at[1], at[1] + dy * ln) - abs(dx) * hw,
                   max(at[0], at[0] + dx * ln) + abs(dy) * hw, max(at[1], at[1] + dy * ln) + abs(dx) * hw)
        self.labels.append((kind, name, at, side, box))
        return at

    def label(self, name, at, side='right', size=1.27):
        """Local label; its text runs to `side` of the connection point ('right', 'left', 'up', 'down')."""
        return self._label('label', name, at, side, None, size)

    def net(self, part, key):
        """Net name of a pin in the baseline netlist given to load(), or None (unconnected)."""
        assert self.netlist, 'pass netlist=... to Sheet.load() first'
        name = self.netlist.net(part.ref, part._find(key)['number'])
        return None if name is None or name.startswith('unconnected-') else name

    def stub(self, part, key, n=2, shape='bidirectional'):
        """End a pin the way the baseline netlist says, on a stub n grid steps long. Returns the stub's end.

        An unconnected pin gets a no-connect mark; a net with a power symbol (GND, VDD) gets that symbol; a
        net of this sheet (/Sheet/NAME) gets the local label NAME; any other net gets a global label. Use it
        for pins whose net leaves the block; wire the rest. n=0 puts the label or symbol on the pin itself.
        """
        p = part._find(key)
        name = self.net(part, key)
        if name is None:
            if p['type'] != 'no_connect':
                self.nc(p['at'])
            return None
        end = part.out(key, n)
        if n:
            self.wire(p['at'], end)
        side = part.side(key)
        if name.startswith('/'):
            self.label(name.rsplit('/', 1)[1], end, side)
        else:
            try:
                lib_symbol('power:' + name, self.lib_dir)
            except KeyError:
                self.glabel(name, end, side, shape)
            else:
                self.power(name, end, side)
        return end

    def glabel(self, name, at, side='right', shape='bidirectional', size=1.27):
        """Global label (a net that crosses sheets). shape: input, output, bidirectional, passive."""
        return self._label('global_label', name, at, side, shape, size)

    def hlabel(self, name, at, side='right', shape='bidirectional', size=1.27):
        """Hierarchical label."""
        return self._label('hierarchical_label', name, at, side, shape, size)

    # ------------------------------------------------------------ graphics and text
    def rect(self, x0, y0, x1, y1, width=0.15, style='solid', color=None, fill=None):
        node = S('rectangle', S('start', R(x0), R(y0)), S('end', R(x1), R(y1)), _stroke(width, style, color),
                 S('fill', S('type', Sym('color')), S('color', *_rgba(fill))) if fill else
                 S('fill', S('type', Sym('none'))),
                 S('uuid', self._uid('rect:%s,%s,%s,%s' % (x0, y0, x1, y1))))
        self.items.append(node)

    def line(self, *pts, width=0.15, style='solid', color=None):
        node = S('polyline', [Sym('pts')] + [S('xy', R(p[0]), R(p[1])) for p in pts], _stroke(width, style, color),
                 S('fill', S('type', Sym('none'))), S('uuid', self._uid('line:%s' % (pts,))))
        self.items.append(node)

    def text(self, s, x, y, size=1.27, bold=False, italic=False, color=None, justify='left top', face=None,
             angle=0, what='text'):
        """Free text. justify: '<left|center|right> <top|center|bottom>' relative to (x, y)."""
        h, v = (justify.split() + ['center'])[:2]
        node = S('text', s, S('exclude_from_sim', Sym('no')), S('at', R(x), R(y), angle),
                 _effects(size, h, v, bold, italic, color, face), S('uuid', self._uid('text:%s' % s[:40])))
        self.items.append(node)
        self.boxes.append((what + ' "%s"' % s.split('\n')[0][:30], text_box(s, x, y, size, h, v, angle, bold)))

    def textbox(self, s, x, y, w, h, size=1.27, bold=False, color=None, border=None, fill=None,
                justify='left top', margin=1.0, face=None, what='text box'):
        """Text wrapped in a box of w x h at (x, y). border: (width, colour) or None for no outline."""
        jh, jv = (justify.split() + ['center'])[:2]
        node = S('text_box', s, S('exclude_from_sim', Sym('no')), S('at', R(x), R(y), 0), S('size', R(w), R(h)),
                 S('margins', margin, margin, margin, margin),
                 _stroke(border[0], 'solid', border[1]) if border else _stroke(-0.0001, 'default'),
                 S('fill', S('type', Sym('color')), S('color', *_rgba(fill))) if fill else
                 S('fill', S('type', Sym('none'))),
                 _effects(size, jh, jv, bold, False, color, face), S('uuid', self._uid('tbox:%s' % s[:40])))
        self.items.append(node)
        self.boxes.append((what + ' "%s"' % s.split('\n')[0][:30], (x, y, x + w, y + h)))

    def block(self, x0, y0, x1, y1, title, sub=None):
        """A function block: dashed frame with a heading at its top left (and a grey one-line subtitle)."""
        self.rect(x0, y0, x1, y1, **FRAME)
        self.frames.append((title, (x0, y0, x1, y1)))
        self.text(title, x0 + 2.0, y0 + 1.6, justify='left top', what='heading', **HEADING)
        if sub:
            self.text(sub, x0 + 2.0, y0 + 1.6 + HEADING['size'] + 1.4, justify='left top', what='subheading',
                      **SUBHEAD)

    def note(self, s, x, y, justify='left top', size=None, bold=False, color=None):
        """A note beside what it explains (the theme's note colour). Break lines with \\n yourself."""
        self.text(s, x, y, size=size or NOTE['size'], bold=bold, color=color, justify=justify, what='note')

    def callout(self, s, x, y, w, h, kind='info'):
        """A boxed design note; the cover's DESIGN CONSIDERATIONS row is its key. kind: info, bringup, caution,
        critical, layout."""
        col, width, tcol, bold = CALLOUT[kind]
        self.textbox(s, x, y, w, h, bold=bold, color=tcol, border=(width, col), what='callout')

    def legend(self, x, y, pitch=4.0, title='NET COLOURS'):
        """A key to the net class colours, read from the project file beside the sheet (for the cover page)."""
        import json
        pros = glob.glob(os.path.join(os.path.dirname(self.path), '*.kicad_pro'))
        classes = {c['name']: c for c in json.load(open(pros[0], encoding='utf-8'))['net_settings']['classes']}
        self.text(title, x, y, justify='left top', what='heading', **dict(HEADING, size=1.6))
        row = y + 5.0
        for names, what in LEGEND:
            names = [n for n in names if n in classes]
            if not names:
                continue
            cl = classes[names[0]]
            m = re.match(r'rgba?\((\d+), (\d+), (\d+)', cl.get('schematic_color', ''))
            if not m:
                continue
            self.line((x, row), (x + 10.0, row), width=max(cl.get('wire_width', 6) * 0.0254, 0.4),
                      color=tuple(int(v) for v in m.group(1, 2, 3)))
            self.text('%s (%s)' % (what, ', '.join(names)), x + 12.5, row, justify='left center', what='legend')
            row += pitch
        return row

    def sheet_box(self, name, x, y, w=None, h=None):
        """Move (and resize) a hierarchical sheet symbol of this sheet, by sheet name. Keeps uuid and pins."""
        for sh in self.sheets:
            props = {p[1]: p for p in find(sh, 'property')}
            if props['Sheetname'][2] == name:
                size = first(sh, 'size')
                w, h = (w or float(size[1])), (h or float(size[2]))
                put(sh, S('at', R(x), R(y)))
                put(sh, S('size', R(w), R(h)))
                put(props['Sheetname'], S('at', R(x), R(y - 0.7116), 0))
                put(props['Sheetfile'], S('at', R(x), R(y + h + 0.5846), 0))
                assert not find(sh, 'pin'), 'sheet pins are not moved by sheet_box'
                self.boxes.append(('sheet ' + name, (x, y - 2.5, x + w, y + h + 2.5)))
                return
        raise KeyError('no sheet symbol named %s' % name)

    # ------------------------------------------------------------ writing
    def _wires(self):
        """Split wires where something connects in their middle, merge straight runs, find the junctions."""
        pin_pts = {}
        for part in self.parts:
            for p in part.pins.values():
                pin_pts[p['at']] = pin_pts.get(p['at'], 0) + 1
        segs = {(min(a, b), max(a, b)) for a, b in self.segs}
        cut = set(pin_pts) | self.extra_junctions
        for a, b in segs:
            cut.add(a)
            cut.add(b)
        pieces = set()
        for a, b in segs:
            if a[1] == b[1]:
                inner = sorted(p for p in cut if p[1] == a[1] and a[0] < p[0] < b[0])
            else:
                inner = sorted(p for p in cut if p[0] == a[0] and a[1] < p[1] < b[1])
            chain = [a] + inner + [b]
            for p, q in zip(chain, chain[1:]):
                pieces.add((p, q))
        ends = {}
        for a, b in pieces:
            ends.setdefault(a, []).append((a, b))
            ends.setdefault(b, []).append((a, b))
        junctions = set(self.extra_junctions)
        for p, lst in ends.items():
            if len(lst) >= 3 or (len(lst) >= 2 and p in pin_pts):
                junctions.add(p)
        # merge straight runs that pass through a point with nothing else on it
        merged = True
        while merged:
            merged = False
            for p, lst in list(ends.items()):
                if len(lst) == 2 and p not in junctions and p not in pin_pts:
                    (a1, b1), (a2, b2) = lst
                    if (a1[0] == b1[0] == a2[0] == b2[0]) or (a1[1] == b1[1] == a2[1] == b2[1]):
                        lo, hi = min(a1, a2), max(b1, b2)
                        for s in lst:
                            pieces.discard(s)
                            for e in s:
                                ends[e].remove(s)
                        pieces.add((lo, hi))
                        ends[lo].append((lo, hi))
                        ends[hi].append((lo, hi))
                        del ends[p]
                        merged = True
        return sorted(pieces), sorted(junctions), ends, pin_pts

    def lint(self, pieces, junctions, ends, pin_pts):
        """Overlap and tidiness checks. Returns a list of strings (empty is good)."""
        out = list(self.warnings)
        eps = 0.25

        def hit(a, b, pad=0.0):
            return (a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad)

        def fmt_box(b):
            return '(%.1f, %.1f)' % ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

        texts = []                                # (owner, what, box)
        for part in self.parts:
            for s, box in part.texts:
                texts.append((part, '%s field "%s"' % (part.ref, s), box))
        for kind, name, at, side, box in self.labels:
            texts.append((None, '%s %s' % (kind.replace('_', ' '), name), box))
        for what, box in self.boxes:
            texts.append((None, what, box))
        for i, (o1, w1, b1) in enumerate(texts):
            for o2, w2, b2 in texts[i + 1:]:
                if hit(b1, b2, eps):
                    out.append('text over text: %s and %s near %s' % (w1, w2, fmt_box(b1)))
        for part in self.parts:
            if part.power and part.rot and first(part.node, 'lib_id')[1] != 'power:PWR_FLAG':
                out.append('power symbol %s at (%.2f, %.2f) is not upright: wire it to the rail or the ground '
                           'level' % (next(p[2] for p in find(part.node, 'property') if p[1] == 'Value'),
                                      part.x, part.y))
        bodies = [(p, p.box) for p in self.parts if not p.power]
        for part, box in bodies:
            for o, what, tb in texts:
                if o is not part and hit(box, tb, eps) and not what.startswith(('text box', 'callout')):
                    out.append('text over a symbol: %s on %s near %s' % (what, part.ref, fmt_box(tb)))
                elif o is part and hit(box, tb, eps + 0.2):
                    out.append('field over its own symbol: %s' % what)
        for i, (p1, b1) in enumerate(bodies):
            for p2, b2 in bodies[i + 1:]:
                if hit(b1, b2, 0.05):
                    out.append('symbols overlap: %s and %s' % (p1.ref, p2.ref))
        for a, b in pieces:
            seg = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            for part, box in bodies:
                inner = (box[0] + 0.2, box[1] + 0.2, box[2] - 0.2, box[3] - 0.2)
                if inner[0] < inner[2] and inner[1] < inner[3] and \
                        seg[0] < inner[2] and inner[0] < seg[2] and seg[1] < inner[3] and inner[1] < seg[3]:
                    out.append('wire through a symbol: %s to %s crosses %s' % (a, b, part.ref))
            for o, what, tb in texts:
                if what.startswith(('text box', 'callout')):
                    continue
                inner = (tb[0] + 0.3, tb[1] + 0.3, tb[2] - 0.3, tb[3] - 0.3)
                if inner[0] < inner[2] and inner[1] < inner[3] and \
                        seg[0] < inner[2] and inner[0] < seg[2] and seg[1] < inner[3] and inner[1] < seg[3]:
                    out.append('wire through text: %s to %s crosses %s' % (a, b, what))
        # wires that cross without a junction (legal, but avoid them), dangling ends, stray labels
        hs = [(a, b) for a, b in pieces if a[1] == b[1]]
        vs = [(a, b) for a, b in pieces if a[0] == b[0]]
        for ha, hb in hs:
            for va, vb in vs:
                if ha[0] < va[0] < hb[0] and va[1] < ha[1] < vb[1]:
                    out.append('wires cross without joining at (%.2f, %.2f): if they should connect, end one '
                               'of them there' % (va[0], ha[1]))
        label_pts = {at for _, _, at, _, _ in self.labels}
        for p, lst in ends.items():
            if len(lst) == 1 and p not in pin_pts and p not in label_pts and p not in self.ncs:
                out.append('wire end at %s connects to nothing' % (p,))
            if len(lst) + pin_pts.get(p, 0) >= 4:
                out.append('four-way junction at %s: move one branch 2.54 mm aside' % (p,))
        for kind, name, at, side, box in self.labels:
            on_wire = any((a[0] == b[0] == at[0] and a[1] <= at[1] <= b[1]) or
                          (a[1] == b[1] == at[1] and a[0] <= at[0] <= b[0]) for a, b in pieces)
            if not on_wire and at not in pin_pts:
                out.append('%s %s at %s is not on a wire or a pin' % (kind, name, at))
        # the page: inside the border, clear of the title block, inside its block frame
        ax0, ay0, ax1, ay1 = self.area
        tb = self.title_box
        everything = [(w, b) for _, w, b in texts] + [(p.ref, p.box) for p in self.parts] + \
                     [('frame ' + t, b) for t, b in self.frames]
        for what, b in everything:
            if b[0] < ax0 or b[1] < ay0 or b[2] > ax1 or b[3] > ay1:
                out.append('outside the page border: %s' % what)
            elif hit(b, tb):
                out.append('over the title block: %s' % what)
        for a, b in pieces:
            for p in (a, b):
                if not (ax0 <= p[0] <= ax1 and ay0 <= p[1] <= ay1) or \
                        (tb[0] < p[0] < tb[2] and tb[1] < p[1] < tb[3]):
                    out.append('wire point %s is off the drawing area' % (p,))
        seen, uniq = set(), []
        for s in out:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        return uniq

    def _power_refs_elsewhere(self):
        refs = set()
        for fn in glob.glob(os.path.join(os.path.dirname(self.path), '*.kicad_sch')):
            if os.path.abspath(fn) != self.path:
                refs |= set(re.findall(r'\(reference "(#[A-Z]+\d+)"\)', open(fn, encoding='utf-8').read()))
        return refs

    def save(self, path=None, quiet=False):
        """Write the sheet (in place by default). Returns the list of lint warnings."""
        missing = self.unplaced()
        if missing:
            raise RuntimeError('not placed: ' + ' '.join('%s%s' % (r, '' if u == 1 else ' unit %d' % u)
                                                         for r, u in missing))
        clash = {p.ref for p in self.parts if p.power} & self._power_refs_elsewhere()
        if clash:
            raise RuntimeError('power references already used on another sheet: %s' % ' '.join(sorted(clash)))
        pieces, junctions, ends, pin_pts = self._wires()
        body = []
        for j in junctions:
            body.append(S('junction', S('at', j[0], j[1]), S('diameter', 0), S('color', 0, 0, 0, 0),
                          S('uuid', self._uid('junction:%s,%s' % j))))
        order = ['no_connect', 'rectangle', 'polyline', 'text', 'text_box']
        for kind in order:
            body += [x for x in self.items if x[0] == kind]
        for a, b in pieces:
            body.append(S('wire', S('pts', S('xy', a[0], a[1]), S('xy', b[0], b[1])), _stroke(0, 'default'),
                          S('uuid', self._uid('wire:%s,%s,%s,%s' % (a + b)))))
        for kind in ('label', 'global_label', 'hierarchical_label'):
            body += [x for x in self.items if x[0] == kind]
        used = {}
        for part in self.parts:
            name = first(part.node, 'lib_name')
            key = name[1] if name else first(part.node, 'lib_id')[1]
            used[key] = self.cache[key]
            body.append(part.node)
        libs = [Sym('lib_symbols')] + [used[k] for k in sorted(used)]
        tree = [Sym('kicad_sch')] + self.head + [libs] + body + self.sheets + self.tail
        out = path or self.path
        with open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(dump(tree) + '\n')
        warn = self.lint(pieces, junctions, ends, pin_pts)
        if not quiet:
            print('%s: %d parts, %d wires, %d junctions, %d labels, %d power symbols; %d lint warning%s' % (
                os.path.basename(out), sum(1 for p in self.parts if not p.power), len(pieces), len(junctions),
                len(self.labels), sum(1 for p in self.parts if p.power), len(warn), '' if len(warn) == 1 else 's'))
            for w in warn:
                print('  lint:', w)
        return warn
