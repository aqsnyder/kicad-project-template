"""boardgeom: what a mechanical drawing needs from a .kicad_pcb, read without pcbnew.

    import boardgeom
    b = boardgeom.Board('hw/main-board/main-board.kicad_pcb')
    b.outline      # [('line', p, q) | ('arc', start, mid, end) | ('circle', centre, radius) | ('poly', [p...])]
    b.bbox         # (x0, y0, x1, y1) of the outline, board mm (y down, as in the board editor); None: no outline
    b.footprints   # [Footprint]: ref, value, lib_id, side, x, y, rot, box, drill, dnp
    b.stackup      # [(layer, type, thickness mm or None, material)], top to bottom; b.finish, b.thickness

The outline is every graphic on Edge.Cuts, the board's own and those inside footprints (a footprint's graphics
are stored in its own frame: they are turned and moved to the board here). Standard library and schdraw's parser
only; the board file is read, never written.
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schdraw as D  # noqa: E402


def _xy(node):
    return (float(node[1]), float(node[2]))


def _turn(p, deg):
    """A footprint-frame point turned by the footprint's angle, the way KiCad does it (y points down)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c + p[1] * s, p[1] * c - p[0] * s)


def arc_points(start, mid, end, n=24):
    """Points along the arc through three points (for extents and for drawing it as a polyline)."""
    (ax, ay), (bx, by), (cx, cy) = start, mid, end
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [start, mid, end]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a0, a1, a2 = (math.atan2(p[1] - uy, p[0] - ux) for p in (start, mid, end))
    two_pi = 2 * math.pi
    sweep = (a2 - a0) % two_pi                         # go from a0 to a2 through a1: pick the turn that passes it
    if (a1 - a0) % two_pi > sweep:
        sweep -= two_pi
    return [(ux + r * math.cos(a0 + sweep * i / n), uy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


class Footprint:
    def __init__(self, node):
        self.lib_id = node[1]
        at = D.first(node, 'at')
        self.x, self.y = float(at[1]), float(at[2])
        self.rot = float(at[3]) if len(at) > 3 else 0.0
        self.side = 'bottom' if D.first(node, 'layer')[1].startswith('B.') else 'top'
        props = {p[1]: p[2] for p in D.find(node, 'property')}
        self.ref, self.value = props.get('Reference', ''), props.get('Value', '')
        attrs = [str(a) for attr in D.find(node, 'attr') for a in attr[1:]]
        self.dnp = 'dnp' in attrs
        self.edge = []                                   # Edge.Cuts shapes, board frame
        court, pads = [], []
        self.drill = 0.0
        for g in node[2:]:
            if not isinstance(g, list):
                continue
            if g[0] == 'pad':
                pat = D.first(g, 'at')
                c = self.place((float(pat[1]), float(pat[2])))
                size = D.first(g, 'size')
                half = max(float(size[1]), float(size[2])) / 2
                pads += [(c[0] - half, c[1] - half), (c[0] + half, c[1] + half)]
                drill = D.first(g, 'drill')
                if drill is not None:
                    nums = [float(v) for v in drill[1:] if re.match(r'^-?[\d.]+$', str(v))]
                    if nums:
                        self.drill = max(self.drill, max(nums))
            elif str(g[0]).startswith('fp_'):
                layer = D.first(g, 'layer')
                layer = layer[1] if layer else ''
                shape = self._shape(g)
                if shape is None:
                    continue
                if layer == 'Edge.Cuts':
                    self.edge.append(shape)
                elif layer.endswith('.CrtYd'):
                    court += shape_points(shape)
        pts = court or pads or [(self.x, self.y)]
        self.box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))

    def place(self, p):
        q = _turn(p, self.rot)
        return (self.x + q[0], self.y + q[1])

    def _shape(self, g):
        kind = str(g[0])[3:]
        if kind == 'line':
            return ('line', self.place(_xy(D.first(g, 'start'))), self.place(_xy(D.first(g, 'end'))))
        if kind == 'rect':
            (x0, y0), (x1, y1) = _xy(D.first(g, 'start')), _xy(D.first(g, 'end'))
            return ('poly', [self.place(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])
        if kind == 'arc':
            return ('arc',) + tuple(self.place(_xy(D.first(g, k))) for k in ('start', 'mid', 'end'))
        if kind == 'circle':
            c, e = _xy(D.first(g, 'center')), _xy(D.first(g, 'end'))
            return ('circle', self.place(c), math.hypot(e[0] - c[0], e[1] - c[1]))
        if kind == 'poly':
            return ('poly', [self.place(_xy(p)) for p in D.find(D.first(g, 'pts'), 'xy')])
        return None


def shape_points(shape):
    """Points that bound a shape."""
    kind = shape[0]
    if kind == 'line':
        return [shape[1], shape[2]]
    if kind == 'arc':
        return arc_points(*shape[1:])
    if kind == 'circle':
        (cx, cy), r = shape[1], shape[2]
        return [(cx - r, cy - r), (cx + r, cy + r)]
    return list(shape[1])


class Board:
    def __init__(self, path):
        self.path = path
        tree = D.parse(open(path, encoding='utf-8').read())
        assert tree[0] == 'kicad_pcb', path
        self.outline = []
        for g in tree[1:]:
            if not isinstance(g, list) or not str(g[0]).startswith('gr_'):
                continue
            layer = D.first(g, 'layer')
            if layer is None or layer[1] != 'Edge.Cuts':
                continue
            kind = str(g[0])[3:]
            if kind == 'line':
                self.outline.append(('line', _xy(D.first(g, 'start')), _xy(D.first(g, 'end'))))
            elif kind == 'rect':
                (x0, y0), (x1, y1) = _xy(D.first(g, 'start')), _xy(D.first(g, 'end'))
                self.outline.append(('poly', [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
            elif kind == 'arc':
                self.outline.append(('arc',) + tuple(_xy(D.first(g, k)) for k in ('start', 'mid', 'end')))
            elif kind == 'circle':
                c, e = _xy(D.first(g, 'center')), _xy(D.first(g, 'end'))
                self.outline.append(('circle', c, math.hypot(e[0] - c[0], e[1] - c[1])))
            elif kind == 'poly':
                self.outline.append(('poly', [_xy(p) for p in D.find(D.first(g, 'pts'), 'xy')]))
        self.footprints = [Footprint(f) for f in D.find(tree, 'footprint')]
        for f in self.footprints:
            self.outline += f.edge
        pts = [p for s in self.outline for p in shape_points(s)]
        self.bbox = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts),
                     max(p[1] for p in pts)) if pts else None
        general = D.first(tree, 'general')
        thick = D.first(general, 'thickness') if general else None
        self.thickness = float(thick[1]) if thick else None
        self.stackup, self.finish = [], None
        setup = D.first(tree, 'setup')
        stack = D.first(setup, 'stackup') if setup else None
        if stack:
            for layer in D.find(stack, 'layer'):
                t = D.first(layer, 'thickness')
                m = D.first(layer, 'material')
                self.stackup.append((layer[1], D.first(layer, 'type')[1] if D.first(layer, 'type') else '',
                                     float(t[1]) if t else None, m[1] if m else ''))
            fin = D.first(stack, 'copper_finish')
            self.finish = fin[1] if fin else None

    @property
    def size(self):
        x0, y0, x1, y1 = self.bbox
        return (x1 - x0, y1 - y0)

    def holes(self):
        """Mounting holes: footprints named H<n> or from a MountingHole library, with their drill."""
        out = [f for f in self.footprints
               if re.match(r'^H\d+$', f.ref) or 'MountingHole' in f.lib_id]
        return sorted(out, key=lambda f: _ref_key(f.ref))

    def connectors(self, extra=()):
        """Footprints J<n>, and any reference named in `extra`."""
        out = [f for f in self.footprints if re.match(r'^J\d+$', f.ref) or f.ref in extra]
        return sorted(out, key=lambda f: _ref_key(f.ref))

    def tabs(self):
        """Break-off tabs: footprints MB<n> or from a mouse-bite footprint (a row of stamp holes)."""
        out = [f for f in self.footprints if re.match(r'^MB\d+$', f.ref) or 'MouseBite' in f.lib_id]
        return sorted(out, key=lambda f: _ref_key(f.ref))

    def rails(self):
        """(left, top, right, bottom) in mm: how far the cuts inside the outline (a panel's routed slots) stay
        from its bounding box. None for a board with no cut inside, or one that is not a rectangle."""
        if not self.bbox:
            return None
        x0, y0, x1, y1 = self.bbox
        eps = 1e-6

        def on_edge(p):
            return abs(p[0] - x0) < eps or abs(p[0] - x1) < eps or abs(p[1] - y0) < eps or abs(p[1] - y1) < eps

        inner, edge_len = [], 0.0
        for s in self.outline:
            pts = shape_points(s)
            if all(on_edge(p) for p in pts):
                if s[0] == 'line':
                    edge_len += math.hypot(s[2][0] - s[1][0], s[2][1] - s[1][1])
                elif s[0] == 'poly':
                    edge_len += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:] + pts[:1]))
            else:
                inner += pts
        if not inner or edge_len < 2 * (x1 - x0 + y1 - y0) - 1e-3:       # the outline is not the whole rectangle
            return None
        out = (min(p[0] for p in inner) - x0, min(p[1] for p in inner) - y0,
               x1 - max(p[0] for p in inner), y1 - max(p[1] for p in inner))
        return tuple(round(v, 4) for v in out) if min(out) > 0.5 else None


def _ref_key(ref):
    m = re.match(r'^([A-Za-z#]+)(\d*)', ref)
    return (m.group(1), int(m.group(2) or 0)) if m else (ref, 0)


if __name__ == '__main__':
    b = Board(sys.argv[1])
    print('outline: %d shapes, bbox %s' % (len(b.outline), b.bbox))
    for f in b.holes() + b.connectors(sys.argv[2:]):
        print('%-5s %-12s %-6s at %.2f, %.2f  box %s  drill %.2f%s' % (
            f.ref, f.value, f.side, f.x, f.y, tuple(round(v, 2) for v in f.box), f.drill, '  DNP' if f.dnp else ''))
    for row in b.stackup:
        print(row)
    print('finish', b.finish, 'thickness', b.thickness)
