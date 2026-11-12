"""Check the starter board's coloured net classes, the Architecture page's colour key and the colour theme.

usage:
  python3 tests/check_netclasses.py [--project PRO]              the class table, the colour key, the theme and the
                                                                 sample nets below; no KiCad needed
  python3 tests/check_netclasses.py --kicad BOARD_DIR            the same sample nets, asked of KiCad itself
                                                                 (a python that imports pcbnew, i.e. KiCad's)
  python3 tests/check_netclasses.py --write-sch DIR [--project PRO]
                                                                 DIR/netcolours.kicad_sch: one labelled wire per
                                                                 sample net, with a copy of the project file
  python3 tests/check_netclasses.py --svg FILE [--project PRO]   the wire colours in kicad-cli's plot of that
                                                                 schematic (sch export svg --theme Altium_Theme)
Exits 1 on any difference.

What the table promises, and these checks hold it to:
  - Power and GND set rules (track width, clearance, vias). Every other class sets colours only, so its nets keep
    the Default class's rules whatever their names match.
  - A net whose name matches several classes takes each property from the class with the lowest priority number
    that sets it. Power, RF_50R and GND come first, so they also win the colour.
  - The priorities are in the file (net settings version 5). KiCad gives a version 3 file new ones by position.
"""
import argparse
import json
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROJECT = os.path.join(ROOT, 'templates', 'starter-board', 'starter-board.kicad_pro')
THEME = os.path.join(ROOT, 'themes', 'Altium_Theme.json')

# In priority order: (name, colour, sets rules).
CLASSES = [
    ('Power', 'rgb(194, 0, 0)', True),
    ('RF_50R', 'rgb(194, 0, 194)', False),
    ('GND', 'rgb(0, 132, 0)', True),
    ('Debug', 'rgb(132, 132, 0)', False),
    ('UART', 'rgb(132, 0, 132)', False),
    ('Bus', 'rgb(0, 0, 132)', False),
    ('Clock', 'rgb(132, 132, 132)', False),
    ('Analog', 'rgb(204, 102, 0)', False),
    ('USB', 'rgb(0, 194, 194)', False),
]
RULE_KEYS = ('clearance', 'diff_pair_gap', 'diff_pair_via_gap', 'diff_pair_width', 'microvia_diameter',
             'microvia_drill', 'track_width', 'via_diameter', 'via_drill')
BOARD_COLOUR = {'Bus': 'rgb(70, 130, 255)'}     # navy is too dark on the board editor's background
NO_COLOUR = 'rgba(0, 0, 0, 0.000)'
DEFAULT_PRIORITY = 2147483647
WIRE_MILS, DEFAULT_WIRE_MILS = 10, 6

# Net name -> the classes its name matches, highest priority first. A leading / is a local label's sheet path.
SAMPLES = [
    ('+3V3', ['Power']),
    ('VBAT', ['Power']),
    ('VBUS', ['Power']),
    ('VIN', ['Power']),
    ('VBAT_SENSE', ['Power', 'Analog']),        # Power's rules and colour: it comes first
    ('GND', ['GND']),
    ('GNDA', ['GND']),
    ('AGND', []),                               # GND* is anchored at the start, as it was in 0.2.0
    ('NET1', []),
    ('SW', []),                                 # a buck converter's switch node is not SWD
    ('SWOUT', []),
    ('i2c_scl', []),                            # patterns are case sensitive
    ('ANT_RF_50R', ['RF_50R']),
    ('/Radio/RF_50R_FEED', ['RF_50R']),
    ('SWDIO', ['Debug']),
    ('SWDCLK', ['Debug', 'Clock']),
    ('SWCLK', ['Debug', 'Clock']),
    ('SWO', ['Debug']),
    ('/MCU/SWO', ['Debug']),
    ('JTAG_TMS', ['Debug']),
    ('NRST', ['Debug']),
    ('Net-(U1-SWDIO)', ['Debug']),              # an unlabelled net is named after a pin
    ('UART_TX', ['UART']),
    ('/MCU/USART1_RX', ['UART']),
    ('LPUART1_TX', ['UART']),
    ('USB_UART_TX', ['UART', 'USB']),
    ('I2C_SCL', ['Bus']),
    ('/I2C_SDA', ['Bus']),
    ('SDA', ['Bus']),
    ('SPI_MOSI', ['Bus']),
    ('SPI_CLK', ['Bus', 'Clock']),
    ('GPIO12', ['Bus']),
    ('/MCU/GPIO_LED', ['Bus']),
    ('ADC_SCLK', ['Bus', 'Clock', 'Analog']),
    ('CLK_32K', ['Clock']),
    ('XTAL_IN', ['Clock']),
    ('/MCU/OSC_OUT', ['Clock']),
    ('ADC_CLK', ['Clock', 'Analog']),
    ('ADC_IN1', ['Analog']),
    ('VREF', ['Analog']),
    ('/ISENSE', ['Analog']),
    ('USB_DP', ['USB']),
    ('/USB/CC1', ['USB']),                      # every local net of a sheet called USB
    ('USB_VBUS', ['USB']),                      # VBUS* is anchored at the start too
]

X1, X2, Y0, PITCH = 50.8, 76.2, 25.4, 5.08      # the sample wires in the --write-sch schematic, in mm


class Report:
    def __init__(self):
        self.bad = 0

    def check(self, ok, what):
        if not ok:
            self.bad += 1
            print('FAIL ' + what)
        return ok


def load_project(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)['net_settings']


def kicad_match(pattern, name):
    """As KiCad matches a net class pattern: against the whole net name, as a regular expression or as a wildcard
    (* any characters, ? one character). Either one matching is enough."""
    try:
        if re.fullmatch(pattern, name):
            return True
    except re.error:
        pass
    wild = ''.join('.*' if c == '*' else '.' if c == '?' else re.escape(c) for c in pattern)
    return re.fullmatch(wild, name) is not None


def classes_of(ns, name):
    """The classes a net name matches, highest priority (lowest number) first."""
    prio = {c['name']: c['priority'] for c in ns['classes']}
    hit = {p['netclass'] for p in ns['netclass_patterns'] if kicad_match(p['pattern'], name)}
    return sorted(hit, key=lambda n: (prio[n], n))


def expected(ns, classes):
    """What a net with these classes must come out as, by KiCad's rule: each property from the first class that
    sets it, else Default's. The colour is None when no class gives one."""
    by_name = {c['name']: c for c in ns['classes']}
    chain = [by_name[n] for n in classes] + [by_name['Default']]

    def first(key):
        return next(c[key] for c in chain if key in c)

    colour = next((c['schematic_color'] for c in chain if c.get('schematic_color', NO_COLOUR) != NO_COLOUR), None)
    board = next((c['pcb_color'] for c in chain if c.get('pcb_color', NO_COLOUR) != NO_COLOUR), None)
    return {'colour': colour, 'pcb_colour': board, 'wire_mils': first('wire_width'), 'clearance': first('clearance'),
            'track_width': first('track_width'), 'via_diameter': first('via_diameter'),
            'via_drill': first('via_drill')}


def hex_colour(css):
    r, g, b = (int(v) for v in re.match(r'rgba?\((\d+), (\d+), (\d+)', css).groups())
    return '#%02X%02X%02X' % (r, g, b)


# ---------------------------------------------------------------------------------------------------------------
# no KiCad

def check_table(ns, rep):
    rep.check(ns['meta']['version'] == 5, 'net_settings meta.version is %s, not 5: KiCad would renumber the '
              'priorities of an older file by position' % ns['meta']['version'])
    classes = ns['classes']
    rep.check([c['name'] for c in classes] == ['Default'] + [n for n, _, _ in CLASSES],
              'classes are %s' % [c['name'] for c in classes])
    by_name = {c['name']: c for c in classes}
    default = by_name.get('Default', {})
    rep.check(default.get('priority') == DEFAULT_PRIORITY, 'Default priority is %s' % default.get('priority'))
    rep.check(default.get('schematic_color') == NO_COLOUR and default.get('pcb_color') == NO_COLOUR,
              'Default has a colour')
    rep.check(default.get('wire_width') == DEFAULT_WIRE_MILS, 'Default wire width is %s' % default.get('wire_width'))
    rep.check(all(k in default for k in RULE_KEYS), 'Default lacks a rule value')
    for prio, (name, colour, sets_rules) in enumerate(CLASSES):
        c = by_name.get(name)
        if not rep.check(c is not None, 'no class %s' % name):
            continue
        rep.check(c.get('priority') == prio, '%s priority is %s, expected %d' % (name, c.get('priority'), prio))
        board = BOARD_COLOUR.get(name, colour)
        rep.check(c.get('schematic_color') == colour and c.get('pcb_color') == board,
                  '%s colours are %s / %s, expected %s / %s'
                  % (name, c.get('schematic_color'), c.get('pcb_color'), colour, board))
        rep.check(c.get('wire_width') == WIRE_MILS, '%s wire width is %s' % (name, c.get('wire_width')))
        have = [k for k in RULE_KEYS if k in c]
        if sets_rules:
            rep.check(len(have) == len(RULE_KEYS), '%s must set every rule value; it lacks %s'
                      % (name, [k for k in RULE_KEYS if k not in c]))
        else:
            rep.check(not have, '%s is a colour class but sets %s, so it would change its nets\' rules' % (name, have))
    power, gnd = by_name.get('Power', {}), by_name.get('GND', {})
    rep.check(all(power.get(k) == gnd.get(k) for k in RULE_KEYS),
              'GND rules differ from Power\'s (GND* nets were in Power before the classes had colours)')
    rule_names = {n for n, _, r in CLASSES if r}
    for p in ns['netclass_patterns']:
        rep.check(p['netclass'] in by_name, 'pattern %s names the unknown class %s' % (p['pattern'], p['netclass']))
        # "ABC*" is also the regular expression AB, ABC, ABCC...: KiCad tries both readings. A leading * is not a
        # valid expression, so such a pattern has the wildcard reading only.
        rep.check(p['netclass'] in rule_names or p['pattern'].startswith('*'),
                  'pattern %s (%s) must start with *' % (p['pattern'], p['netclass']))
    have = {(p['netclass'], p['pattern']) for p in ns['netclass_patterns']}
    for want in (('Power', '+*'), ('Power', 'VBAT*'), ('Power', 'VBUS*'), ('Power', 'VIN*'), ('GND', 'GND*')):
        rep.check(want in have, 'pattern %s -> %s is gone' % (want[1], want[0]))
    rep.check({p for c, p in have if c in rule_names} == {'+*', 'VBAT*', 'VBUS*', 'VIN*', 'GND*'},
              'the patterns of the classes that set rules changed, which changes the rules of the nets they match')


def check_samples(ns, rep):
    for name, want in SAMPLES:
        got = classes_of(ns, name)
        rep.check(got == want, 'net %-22s matches %s, expected %s' % (name, got, want))


def check_legend(ns, rep, page):
    """The Architecture page's NET COLOURS key, which frontpages.py draws from the project file, has a row for
    every class: a line in its colour, and its name in brackets after what it is for."""
    if not rep.check(os.path.exists(page), 'no %s: run frontpages.py on the board folder' % page):
        return
    with open(page, encoding='utf-8') as f:
        t = f.read()
    texts = {}
    for m in re.finditer(r'\(text "((?:[^"\\]|\\.)*)"\s+\(exclude_from_sim \w+\)\s+\(at ([-\d.]+) ([-\d.]+)', t):
        texts.setdefault(float(m.group(3)), []).append(m.group(1))
    lines = {}
    for m in re.finditer(r'\(polyline\s+\(pts\s+\(xy [-\d.]+ ([-\d.]+)\) \(xy [-\d.]+ ([-\d.]+)\)\s+\)\s+\(stroke\s+'
                         r'\(width [\d.]+\)\s+\(type \w+\)\s+\(color (\d+) (\d+) (\d+) [\d.]+\)', t):
        if m.group(1) == m.group(2):
            lines[float(m.group(1))] = 'rgb(%s, %s, %s)' % m.group(3, 4, 5)
    by_name = {c['name']: c for c in ns['classes']}
    for name, _, _ in CLASSES:
        named = re.compile(r'\((?:[^()]*, )?%s(?:, [^()]*)?\)$' % re.escape(name))
        y = next((y for y, row in texts.items() if any(named.search(s) for s in row)), None)
        if not rep.check(y is not None, 'the NET COLOURS key has no row for %s' % name):
            continue
        rep.check(lines.get(y) == by_name[name]['schematic_color'],
                  'NET COLOURS line for %s is %s, the class is %s' % (name, lines.get(y),
                                                                     by_name[name]['schematic_color']))


def check_theme(rep, path=THEME):
    with open(path, encoding='utf-8') as f:
        theme = json.load(f)
    rep.check(theme['meta']['name'] == os.path.basename(path)[:-len('.json')],
              'theme meta.name %r differs from its file name' % theme['meta']['name'])
    rep.check(theme['meta']['version'] == 5, 'theme version is %s; KiCad 10 writes 5' % theme['meta']['version'])
    # With this on, KiCad draws labels in the theme's label colour, not their net class's.
    rep.check(theme['schematic'].get('override_item_colors') is False, 'theme overrides item colours')
    return theme


# ---------------------------------------------------------------------------------------------------------------
# with KiCad

def check_kicad(board_dir, rep):
    import glob
    import pcbnew
    pro = glob.glob(os.path.join(board_dir, '*.kicad_pro'))[0]
    ns = load_project(pro)
    board = pcbnew.LoadBoard(pro[:-len('.kicad_pro')] + '.kicad_pcb')
    settings = board.GetDesignSettings().m_NetSettings
    for name, want in SAMPLES:
        nc = settings.GetEffectiveNetClass(name)
        exp = expected(ns, want)
        exp = dict(exp, colour=exp['colour'] or NO_COLOUR, pcb_colour=exp['pcb_colour'] or NO_COLOUR)
        got = {'colour': nc.GetSchematicColor().ToCSSString(), 'pcb_colour': nc.GetPcbColor().ToCSSString(),
               'wire_mils': round(nc.GetWireWidth() / 254.0, 3),
               'clearance': pcbnew.ToMM(nc.GetClearance()), 'track_width': pcbnew.ToMM(nc.GetTrackWidth()),
               'via_diameter': pcbnew.ToMM(nc.GetViaDiameter()), 'via_drill': pcbnew.ToMM(nc.GetViaDrill())}
        diff = {k: (got[k], exp[k]) for k in exp if got[k] != exp[k]}
        rep.check(not diff, 'KiCad: net %-22s (%s) %s' % (
            name, nc.GetName(), ', '.join('%s is %s, expected %s' % (k, g, e) for k, (g, e) in diff.items())))
    print('KiCad %s resolved %d sample nets of %s' % (pcbnew.GetBuildVersion(), len(SAMPLES), os.path.basename(pro)))


def plotted(samples=SAMPLES):
    """The sample nets the one-sheet schematic can hold: global names, and local names on the root sheet."""
    return [(n, w) for n, w in samples if n.count('/') == 0 or (n.startswith('/') and n.count('/') == 1)]


def write_sch(out_dir, project):
    os.makedirs(out_dir, exist_ok=True)
    with open(project, encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('meta', {})['filename'] = 'netcolours.kicad_pro'
    data.pop('sheets', None)
    with open(os.path.join(out_dir, 'netcolours.kicad_pro'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    out = ['(kicad_sch', '\t(version 20260306)', '\t(generator "eeschema")', '\t(generator_version "10.0")',
           '\t(uuid "%s")' % uuid.uuid4(), '\t(paper "A4" portrait)', '\t(lib_symbols)']
    for i, (name, _) in enumerate(plotted()):
        y = Y0 + i * PITCH
        out.append('\t(wire\n\t\t(pts\n\t\t\t(xy %s %s) (xy %s %s)\n\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n'
                   '\t\t\t(type default)\n\t\t)\n\t\t(uuid "%s")\n\t)' % (X1, y, X2, y, uuid.uuid4()))
        kind, text, x, extra, justify = ('label', name[1:], X1, '', 'left bottom') if name.startswith('/') else \
            ('global_label', name, X2, '\t\t(shape input)\n', 'left')
        out.append('\t(%s "%s"\n%s\t\t(at %s %s 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
                   '\t\t\t(justify %s)\n\t\t)\n\t\t(uuid "%s")\n\t)' % (kind, text, extra, x, y, justify, uuid.uuid4()))
    out += ['\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)', ')']
    sch = os.path.join(out_dir, 'netcolours.kicad_sch')
    with open(sch, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print('wrote %s: %d sample nets' % (sch, len(plotted())))


def check_svg(svg, ns, theme, rep):
    with open(svg, encoding='utf-8') as f:
        t = f.read()
    styles = [(m.start(), m.group(1).upper(), float(m.group(2)))
              for m in re.finditer(r'stroke:(#[0-9A-Fa-f]{6}); stroke-width:([0-9.]+)', t)]
    wires = {}
    for m in re.finditer(r'M%.4f ([0-9.]+)\s*L%.4f ([0-9.]+)' % (X1, X2), t):
        style = [s for s in styles if s[0] < m.start()][-1]
        wires[round((float(m.group(1)) - Y0) / PITCH)] = style[1:]
    samples = plotted()
    rep.check(len(wires) == len(samples), 'the plot has %d sample wires, expected %d' % (len(wires), len(samples)))
    theme_wire = hex_colour(theme['schematic']['wire'])
    for i, (name, want) in enumerate(samples):
        exp = expected(ns, want)
        colour = hex_colour(exp['colour']) if exp['colour'] else theme_wire
        width = round(exp['wire_mils'] * 0.0254, 4)
        got = wires.get(i)
        rep.check(got == (colour, width), 'plot: net %-14s is %s, expected %s %s mm%s' % (
            name, got, colour, width, '' if exp['colour'] else ' (the theme\'s wire colour: is the theme installed?)'))
    sheet = hex_colour(theme['schematic']['background'])
    rep.check(re.search('fill:%s' % sheet, t, re.I) is not None, 'plot: no %s background' % sheet)
    print('plot: %d sample wires in %s' % (len(wires), svg))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--project', default=PROJECT, help='the .kicad_pro to check (default: the starter board)')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--kicad', metavar='BOARD_DIR', help='ask KiCad for the sample nets of this board (needs pcbnew)')
    g.add_argument('--write-sch', metavar='DIR', help='write the sample-net schematic there')
    g.add_argument('--svg', metavar='FILE', help='check kicad-cli\'s plot of the sample-net schematic')
    a = p.parse_args(argv)
    rep = Report()
    if a.kicad:
        check_kicad(a.kicad, rep)
    elif a.write_sch:
        write_sch(a.write_sch, a.project)
    elif a.svg:
        check_svg(a.svg, load_project(a.project), check_theme(rep), rep)
    else:
        ns = load_project(a.project)
        check_table(ns, rep)
        check_samples(ns, rep)
        check_legend(ns, rep, os.path.join(os.path.dirname(os.path.abspath(a.project)), 'architecture.kicad_sch'))
        check_theme(rep)
        print('%d classes, %d patterns, %d sample nets, colour key and theme checked in %s'
              % (len(ns['classes']), len(ns['netclass_patterns']), len(SAMPLES), os.path.relpath(a.project)))
    if rep.bad:
        print('%d check(s) failed' % rep.bad)
    return 1 if rep.bad else 0


if __name__ == '__main__':
    sys.exit(main())
