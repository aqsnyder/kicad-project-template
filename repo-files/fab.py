#!/usr/bin/env python3
"""Choose the board house (fab) for each board, and see which fabs can make it.

usage:
  python3 hw/fab.py list   [BOARD...]
  python3 hw/fab.py set    PROFILE (BOARD... | --all) [--force]
  python3 hw/fab.py verify [BOARD... | --all]
  python3 hw/fab.py check  [BOARD... | --all] [--markdown | --json]

A fab profile is hw/fabs/<profile>.kicad_dru: a KiCad custom-rules file with a header that names the fab, gives the
copper layer counts it covers ("# copper-layers: 1-2") and lists Board Setup minimums ("# board-setup: <key> <mm>").
To add a fab, copy a profile, rename it and change the numbers.

set     writes the profile into <board>/<project>.kicad_dru above the board's own rules, which are kept; writes the
        minimums into the project's Board Setup > Constraints; and sets the FAB text variable. Close the board in
        KiCad first: KiCad rewrites the project file when it saves.
list    shows the profiles and each board's fab.
verify  exits 1 when a board's fab rules or Board Setup minimums no longer match its profile in hw/fabs.
check   runs KiCad's DRC (errors only) on a temporary copy of each board once per profile and prints which fabs
        can make it. Needs kicad-cli (KiCad 10). The board itself is not changed. A profile whose copper-layers
        range leaves out the board's copper layer count shows "n/a (N layers)" and gets no DRC. Only DRC geometry
        and the layer count are checked, not board thickness, copper weight or stackup. KiCad silently ignores a
        whole rules file that has an error in it, so check adds a canary rule and item to each copy and reports
        RULES NOT LOADED when the canary does not fire. Exits 1 in that case, 2 when it cannot run, else 0.

BOARD is a board folder (hw/<board>) or just its name. --all means every folder next to this script that holds a
.kicad_pro. Standard library only; Python 3.9 or newer.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_MARK = '# ==== Board rules ===='
BOARD_INTRO = ("# This board's own rules go below. hw/fab.py keeps them when you switch fabs. When a rule here and a\n"
               "# fab rule above match the same objects, the rule here wins (KiCad: later rules take precedence).\n")
# Board Setup > Constraints keys a profile may set (the names in the .kicad_pro), all in mm.
BOARD_SETUP_KEYS = (
    'min_clearance', 'min_track_width', 'min_connection', 'min_via_diameter', 'min_via_annular_width',
    'min_through_hole_diameter', 'min_hole_clearance', 'min_hole_to_hole', 'min_copper_edge_clearance',
    'min_microvia_diameter', 'min_microvia_drill', 'min_silk_clearance', 'min_text_height', 'min_text_thickness',
)
CANARY = 'fab.py canary'
CANARY_RULE = ('\n(rule "%s"\n\t(severity error)\n\t(constraint text_height (min 50mm))\n'
               '\t(condition "A.Text == \'%s\'"))\n' % (CANARY, CANARY))
CANARY_TEXT = ('\t(gr_text "%s"\n\t\t(at -500 -500 0)\n\t\t(layer "F.SilkS")\n'
               '\t\t(uuid "00000000-fab0-4ca7-8a2a-000000000001")\n\t\t(effects\n\t\t\t(font\n'
               '\t\t\t\t(size 1.5 1.5)\n\t\t\t\t(thickness 0.2)\n\t\t\t)\n\t\t)\n\t)\n' % CANARY)
HEADER_RE = re.compile(r'^#\s*(fab-profile|fab-name|copper-layers|board-setup)\s*:\s*(.*?)\s*$')
LAYERS_RE = re.compile(r'^(\d+)(?:\s*-\s*(\d+))?$')
# A copper layer in the board's (layers ...) list, e.g. (0 "F.Cu" signal) or (4 "In1.Cu" power).
COPPER_RE = re.compile(r'^\s*\(\d+\s+"((?:F|B|In\d+)\.Cu)"\s+(?:signal|power|mixed|jumper)\b', re.M)
PROFILE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')


class FabError(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------
# profiles

class Profile:
    def __init__(self, path):
        self.path = path
        self.id = os.path.basename(path)[:-len('.kicad_dru')]
        with open(path, encoding='utf-8') as f:
            self.text = f.read().replace('\r\n', '\n')
        self.name = None
        self.layers = None          # (fewest, most) copper layers the fab makes
        self.board_setup = {}
        declared = None
        for line in self.text.split('\n'):
            m = HEADER_RE.match(line)
            if not m:
                continue
            key, val = m.groups()
            if key == 'fab-profile':
                declared = val
            elif key == 'fab-name':
                self.name = val
            elif key == 'copper-layers':
                m = LAYERS_RE.match(val)
                lo, hi = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else (0, 0)
                if not 1 <= lo <= hi:
                    raise FabError('%s: bad line "%s"; expected "# copper-layers: <fewest>-<most>", e.g. 1-2'
                                   % (path, line))
                self.layers = (lo, hi)
            else:
                parts = val.split()
                if len(parts) != 2 or parts[0] not in BOARD_SETUP_KEYS:
                    raise FabError('%s: bad line "%s"; expected "# board-setup: <key> <mm>" with key one of %s'
                                   % (path, line, ', '.join(BOARD_SETUP_KEYS)))
                try:
                    self.board_setup[parts[0]] = float(parts[1])
                except ValueError:
                    raise FabError('%s: "%s" is not a number in mm' % (path, parts[1]))
        if not PROFILE_ID_RE.match(self.id):
            raise FabError('%s: file name must be lower case letters, digits, - and _' % path)
        if declared != self.id:
            raise FabError('%s: needs a "# fab-profile: %s" line (the file name without .kicad_dru)' % (path, self.id))
        if not self.name:
            raise FabError('%s: needs a "# fab-name: <name>" line' % path)
        if not self.layers:
            raise FabError('%s: needs a "# copper-layers: <fewest>-<most>" line, e.g. "# copper-layers: 1-2" (the '
                           'copper layer counts the fab makes)' % path)
        if not self.text.lstrip().startswith('(version 1)'):
            raise FabError('%s: must start with (version 1)' % path)
        if BOARD_MARK in self.text:
            raise FabError('%s: a profile must not contain the board-rules marker' % path)
        problem = paren_problem(self.text)
        if problem:
            raise FabError('%s: %s (KiCad would silently ignore the whole file)' % (path, problem))
        if re.search(r'\(constraint\s+clearance\b', self.text):
            raise FabError('%s: has a clearance constraint. In KiCad a matching clearance rule replaces the net '
                           'class clearance; put the fab minimum in "# board-setup: min_clearance" instead' % path)

    def layer_text(self):
        lo, hi = self.layers
        return '%d-%d layers' % (lo, hi) if lo != hi else n_layers(lo)

    def makes(self, copper_layers):
        return self.layers[0] <= copper_layers <= self.layers[1]


def n_layers(n):
    return '%d layer%s' % (n, '' if n == 1 else 's')


def paren_problem(text):
    """A quick structural check of a rules file: balanced parentheses and quotes, ignoring # comments."""
    depth, quote = 0, False
    for n, line in enumerate(text.split('\n'), 1):
        if not quote and line.lstrip().startswith('#'):
            continue
        for ch in line:
            if ch == '"':
                quote = not quote
            elif not quote and ch == '(':
                depth += 1
            elif not quote and ch == ')':
                depth -= 1
                if depth < 0:
                    return 'unbalanced ")" on line %d' % n
    if quote:
        return 'unclosed quote'
    if depth:
        return '%d unclosed "("' % depth
    return None


def fabs_dir(arg=None):
    if arg:
        return os.path.abspath(arg)
    for d in (os.path.join(HERE, 'fabs'), os.path.join(os.path.dirname(HERE), 'fabs')):
        if os.path.isdir(d):
            return d
    raise FabError('no fabs folder next to %s; pass --fabs' % HERE)


def load_profiles(d):
    paths = sorted(glob.glob(os.path.join(d, '*.kicad_dru')))
    if not paths:
        raise FabError('no *.kicad_dru profiles in %s' % d)
    return {p.id: p for p in (Profile(x) for x in paths)}


# ---------------------------------------------------------------------------------------------------------------
# boards

class Board:
    def __init__(self, path):
        self.dir = os.path.abspath(path)
        pros = sorted(glob.glob(os.path.join(self.dir, '*.kicad_pro')))
        if len(pros) != 1:
            raise FabError('%s: expected one .kicad_pro, found %d' % (path, len(pros)))
        self.name = os.path.basename(pros[0])[:-len('.kicad_pro')]
        self.pro = pros[0]
        self.pcb = os.path.join(self.dir, self.name + '.kicad_pcb')
        self.dru = os.path.join(self.dir, self.name + '.kicad_dru')

    def label(self):
        return os.path.relpath(self.dir)

    def read_dru(self):
        if not os.path.exists(self.dru):
            return None, ''
        with open(self.dru, encoding='utf-8') as f:
            t = f.read().replace('\r\n', '\n')
        if BOARD_MARK in t:
            fab, board = t.split(BOARD_MARK, 1)
            return fab, board.split('\n', 1)[1] if '\n' in board else ''
        # no marker: a hand-made rules file. Keep its rules as board rules.
        body = re.sub(r'^\s*\(version\s+\d+\)\s*\n?', '', t)
        return None, body

    def copper_layers(self):
        """The number of copper layers in the board file; None without a board file or a copper layer list."""
        if not os.path.exists(self.pcb):
            return None
        with open(self.pcb, encoding='utf-8') as f:
            return len(set(COPPER_RE.findall(f.read()))) or None

    def current_profile(self):
        fab, _ = self.read_dru()
        for line in (fab or '').split('\n'):
            m = HEADER_RE.match(line)
            if m and m.group(1) == 'fab-profile':
                return m.group(2)
        return None


def find_boards(args_boards, all_flag, hw=None):
    hw = hw or HERE
    if all_flag:
        dirs = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(hw, '*', '*.kicad_pro')))
        if not dirs:
            raise FabError('no boards (folders with a .kicad_pro) in %s' % hw)
        return [Board(d) for d in dirs]
    out = []
    for b in args_boards:
        d = b if os.path.isdir(b) else os.path.join(hw, b)
        if not os.path.isdir(d):
            raise FabError('no board folder %s' % b)
        out.append(Board(d))
    return out


def compose(profile, board_rules):
    board_rules = re.sub(r'^\s*\(version\s+\d+\)\s*\n?', '', board_rules or '')
    if not board_rules.strip():
        board_rules = BOARD_INTRO
    return profile.text.rstrip('\n') + '\n\n' + BOARD_MARK + '\n' + board_rules.rstrip('\n') + '\n'


def write_json(path, data):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')


def set_pcb_property(pcb, key, value):
    if not os.path.exists(pcb):
        return
    with open(pcb, encoding='utf-8', newline='') as f:
        t = f.read()
    nl = '\r\n' if '\r\n' in t else '\n'
    line = '\t(property "%s" "%s")' % (key, value.replace('"', "'"))
    pat = re.compile(r'^\t\(property "%s" "[^"]*"\)$' % re.escape(key), re.M)
    if pat.search(t):
        t = pat.sub(lambda m: line, t, count=1)
    else:
        props = list(re.finditer(r'^\t\(property "([^"]+)" "[^"]*"\)\r?$', t, re.M))
        if not props:
            return          # the board carries no text variables; the project file is enough
        later = [m for m in props if m.group(1) > key]      # KiCad keeps these in alphabetical order
        if later:
            t = t[:later[0].start()] + line + nl + t[later[0].start():]
        else:
            t = t[:props[-1].end()] + nl + line + t[props[-1].end():]
    with open(pcb, 'w', encoding='utf-8', newline='') as f:
        f.write(t)


def locked(board):
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(board.dir, '*.lck')))


def apply(profile, board, force=False):
    """Write the profile into the board. Returns a list of notes."""
    notes = []
    lk = locked(board)
    if lk and not force:
        raise FabError('%s is open in KiCad (%s). Close it first: KiCad rewrites the project file when it saves. '
                       '--force skips this check' % (board.label(), ', '.join(lk)))
    old_fab, board_rules = board.read_dru()
    problem = paren_problem(board_rules)
    if problem:
        notes.append('the board rules have a problem: %s. KiCad ignores the whole rules file (fab rules too) until '
                      'it is fixed' % problem)
    if old_fab is None and board_rules.strip():
        notes.append('kept the existing rules in %s as board rules (below the marker); review them'
                     % os.path.basename(board.dru))
    layers = board.copper_layers()
    if layers and not profile.makes(layers):
        notes.append('the board has %s; %s covers %s' % (n_layers(layers), profile.id, profile.layer_text()))
    with open(board.dru, 'w', encoding='utf-8', newline='\n') as f:
        f.write(compose(profile, board_rules))
    with open(board.pro, encoding='utf-8') as f:
        data = json.load(f)
    rules = data.setdefault('board', {}).setdefault('design_settings', {}).setdefault('rules', {})
    for k, v in profile.board_setup.items():
        rules[k] = v
    data.setdefault('text_variables', {})['FAB'] = profile.name
    write_json(board.pro, data)
    set_pcb_property(board.pcb, 'FAB', profile.name)
    return notes


def state(board, profiles):
    """(profile id or None, list of differences)."""
    pid = board.current_profile()
    if pid is None:
        return None, ['no fab profile in %s' % os.path.basename(board.dru)]
    p = profiles.get(pid)
    if p is None:
        return pid, ['profile %s is not in the fabs folder' % pid]
    diffs = []
    fab, _ = board.read_dru()
    if fab.rstrip('\n') != p.text.rstrip('\n'):
        diffs.append('fab rules differ from %s' % os.path.relpath(p.path))
    with open(board.pro, encoding='utf-8') as f:
        data = json.load(f)
    rules = data.get('board', {}).get('design_settings', {}).get('rules', {})
    for k, v in p.board_setup.items():
        have = rules.get(k)
        if have is None or abs(float(have) - v) > 1e-6:
            diffs.append('Board Setup %s is %s, profile says %g' % (k, have, v))
    fabvar = data.get('text_variables', {}).get('FAB')
    if fabvar != p.name:
        diffs.append('FAB text variable is %r, profile says %r' % (fabvar, p.name))
    return pid, diffs


# ---------------------------------------------------------------------------------------------------------------
# commands

def cmd_list(a):
    profiles = load_profiles(fabs_dir(a.fabs))
    print('Fab profiles in %s:' % os.path.relpath(fabs_dir(a.fabs)))
    for p in profiles.values():
        print('  %-22s %-12s %s' % (p.id, p.layer_text(), p.name))
    try:
        boards = find_boards(a.boards, not a.boards)
    except FabError:
        boards = []
    if boards:
        print('Boards:')
    for b in boards:
        pid, diffs = state(b, profiles)
        print('  %-22s %s%s' % (b.label(), pid or '-', '' if not diffs else '  (' + '; '.join(diffs) + ')'))
    return 0


def cmd_set(a):
    profiles = load_profiles(fabs_dir(a.fabs))
    p = profiles.get(a.profile)
    if p is None:
        raise FabError('no profile %r; choose from %s' % (a.profile, ', '.join(profiles)))
    boards = find_boards(a.boards, a.all)
    if not boards:
        raise FabError('name the boards, or pass --all')
    for b in boards:
        old = b.current_profile()
        notes = apply(p, b, a.force)
        print('%s: %s -> %s (%s)' % (b.label(), old or '-', p.id, p.name))
        for n in notes:
            print('  note: ' + n)
    print('Board Setup minimums and FAB set; reopen the board in KiCad if it was open.')
    return 0


def cmd_verify(a):
    profiles = load_profiles(fabs_dir(a.fabs))
    bad = 0
    for b in find_boards(a.boards, a.all or not a.boards):
        pid, diffs = state(b, profiles)
        if diffs:
            bad += 1
            print('%s (%s):' % (b.label(), pid or 'no profile'))
            for d in diffs:
                print('  ' + d)
            print('  fix: python3 %s set %s %s' % (os.path.relpath(__file__), pid or '<profile>', b.label()))
        else:
            print('%s: %s, matches %s' % (b.label(), pid, os.path.relpath(profiles[pid].path)))
    return 1 if bad else 0


def kicad_cli():
    exe = os.environ.get('KICAD_CLI') or shutil.which('kicad-cli')
    if not exe:
        for c in glob.glob(r'C:\Program Files\KiCad\*\bin\kicad-cli.exe') + \
                ['/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli']:
            if os.path.exists(c):
                exe = c
        if not exe:
            raise FabError('kicad-cli not found: install KiCad 10 or set KICAD_CLI')
    return exe


def add_canary(board):
    """In a scratch copy only: a text item and a rule that must flag it, to prove KiCad loaded the rules."""
    with open(board.dru, 'a', encoding='utf-8', newline='\n') as f:
        f.write(CANARY_RULE)
    with open(board.pcb, encoding='utf-8') as f:
        t = f.read().replace('\r\n', '\n').rstrip()
    if not t.endswith(')'):
        raise FabError('%s does not end with ")"' % board.pcb)
    with open(board.pcb, 'w', encoding='utf-8', newline='\n') as f:
        f.write(t[:-1].rstrip('\n') + '\n' + CANARY_TEXT + ')\n')


def drc_errors(cli, pcb, report):
    """({type: count} of DRC errors without the canary's, True if the canary rule fired)."""
    r = subprocess.run([cli, 'pcb', 'drc', '--format', 'json', '--severity-error', '-o', report, pcb],
                       capture_output=True, text=True)
    try:
        with open(report, encoding='utf-8') as f:
            j = json.load(f)
    except (OSError, ValueError):
        raise FabError('DRC failed on %s:\n%s%s' % (pcb, r.stdout, r.stderr))
    types, fired = {}, False
    for v in j.get('violations', []):
        if CANARY in v.get('description', ''):
            fired = True
            continue
        if any(CANARY in i.get('description', '') for i in v.get('items', [])):
            continue
        if v.get('severity', 'error') == 'error':
            types[v.get('type', '?')] = types.get(v.get('type', '?'), 0) + 1
    return types, fired


def cmd_check(a):
    profiles = load_profiles(fabs_dir(a.fabs))
    boards = find_boards(a.boards, a.all or not a.boards)
    cli = kicad_cli()
    results = {}
    for b in boards:
        current = b.current_profile()
        layers = b.copper_layers()
        if not layers:
            raise FabError('%s: no copper layers found in %s' % (b.label(), os.path.basename(b.pcb)))
        row = results.setdefault(b.label(), {'current': current, 'copper_layers': layers, 'fabs': {}})
        for p in profiles.values():
            if not p.makes(layers):
                row['fabs'][p.id] = {'applies': False, 'errors': None, 'types': {}, 'rules_loaded': None}
                continue
            tmp = tempfile.mkdtemp(prefix='fabcheck_')
            try:
                d = os.path.join(tmp, b.name)
                os.makedirs(d)
                for f in os.listdir(b.dir):
                    src = os.path.join(b.dir, f)
                    if os.path.isfile(src) and not f.endswith('.lck'):
                        shutil.copyfile(src, os.path.join(d, f))
                copy = Board(d)
                apply(p, copy, force=True)
                add_canary(copy)
                types, fired = drc_errors(cli, copy.pcb, os.path.join(tmp, 'drc.json'))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            row['fabs'][p.id] = {'applies': True, 'errors': sum(types.values()), 'types': types,
                                 'rules_loaded': fired}
    unloaded = [(n, pid) for n, r in results.items() for pid, e in r['fabs'].items()
                if e['applies'] and not e['rules_loaded']]
    if a.json:
        print(json.dumps(results, indent=2))
        return 1 if unloaded else 0
    ids = list(profiles)

    def cell(r, pid):
        e = r['fabs'][pid]
        if not e['applies']:
            s = 'n/a (%s)' % n_layers(r['copper_layers'])
        elif not e['rules_loaded']:
            s = 'RULES NOT LOADED'
        else:
            s = 'ok' if not e['errors'] else '%d: %s' % (e['errors'], ', '.join(
                '%s %d' % kv for kv in sorted(e['types'].items(), key=lambda kv: -kv[1])))
        return s + (' *' if r['current'] == pid else '')

    if a.markdown:
        print('### Fab check\n')
        print('KiCad DRC errors with each fab profile; `*` = the board\'s current fab; n/a = the fab does not make '
              'boards with that many copper layers. Errors that show under every fab are design errors, not fab '
              'limits. Board thickness, copper weight and stackup are not checked.\n')
        print('| board | ' + ' | '.join(ids) + ' |')
        print('|---|' + '---|' * len(ids))
        for name, r in results.items():
            print('| %s | %s |' % (name, ' | '.join(cell(r, i) for i in ids)))
    else:
        print('KiCad DRC errors with each fab profile (* = current fab; n/a = not made with that many copper '
              'layers; errors under every fab are design errors):')
        w = max(len(x) for x in ids)
        for name, r in results.items():
            print('%s (%s)' % (name, n_layers(r['copper_layers'])))
            for i in ids:
                print('  %-*s %s' % (w, i, cell(r, i)))
    for name, pid in unloaded:
        print('%s with %s: KiCad did not load the rules, so DRC ran without them. Look for a mistake in %s or in '
              'the board rules below the "%s" line (KiCad gives no message).'
              % (name, pid, os.path.relpath(profiles[pid].path), BOARD_MARK), file=sys.stderr)
    return 1 if unloaded else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--fabs', help='the fab profiles folder (default: fabs/ next to this script)')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('list', help='profiles and each board\'s fab')
    s.add_argument('boards', nargs='*')
    s.set_defaults(func=cmd_list)
    s = sub.add_parser('set', help='switch boards to a fab profile')
    s.add_argument('profile')
    s.add_argument('boards', nargs='*')
    s.add_argument('--all', action='store_true', help='every board next to this script')
    s.add_argument('--force', action='store_true', help='write even if KiCad has the board open')
    s.set_defaults(func=cmd_set)
    s = sub.add_parser('verify', help='exit 1 if a board no longer matches its profile')
    s.add_argument('boards', nargs='*')
    s.add_argument('--all', action='store_true')
    s.set_defaults(func=cmd_verify)
    s = sub.add_parser('check', help='DRC each board against every profile')
    s.add_argument('boards', nargs='*')
    s.add_argument('--all', action='store_true')
    g = s.add_mutually_exclusive_group()
    g.add_argument('--markdown', action='store_true')
    g.add_argument('--json', action='store_true')
    s.set_defaults(func=cmd_check)
    a = p.parse_args(argv)
    try:
        return a.func(a)
    except FabError as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
