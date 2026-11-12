#!/usr/bin/env python3
"""Install this repository's KiCad colour themes on this machine.

usage:
  python3 hw/theme.py list
  python3 hw/theme.py install [THEME...] [--force] [--create]

KiCad reads colour themes from the user's settings folder only, never from a project, so a theme kept in the
repository (hw/themes/<name>.json) has to be copied there once per machine and per KiCad version:

  Windows  %APPDATA%\\kicad\\10.0\\colors
  Linux    ~/.config/kicad/10.0/colors      ($XDG_CONFIG_HOME/kicad/10.0/colors when that is set)
  macOS    ~/Library/Preferences/kicad/10.0/colors

list     shows each theme in hw/themes and whether this machine has it.
install  copies the themes (all of them, or the ones named). A theme that is already installed with other
         colours is left alone and the command exits 1; --force replaces it and keeps the old file beside it as
         <name>.json.bak. When KiCad has not made its settings folder yet, open KiCad once first, or pass
         --create (meant for CI) to make the folder.

Then restart KiCad and choose the theme in Preferences > Preferences > Schematic Editor > Colors, and again under
PCB Editor > Colors. kicad-cli takes a theme by name on its export commands:
  kicad-cli sch export pdf --theme Altium_Theme -o board.pdf hw/<board>/<board>.kicad_sch
kicad-cli does not complain about a theme it cannot find: it plots with KiCad's default colours instead.

--kicad-version picks another settings version (default 10.0). KICAD_CONFIG_HOME replaces the folder that holds the
version folder, as it does in KiCad itself. --config-dir names the folder that holds "colors" directly, for a
Flatpak or portable KiCad. Standard library only; Python 3.9 or newer.
"""
import argparse
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_VERSION = '10.0'


class ThemeError(Exception):
    pass


def themes_dir(arg=None):
    if arg:
        return os.path.abspath(arg)
    for d in (os.path.join(HERE, 'themes'), os.path.join(os.path.dirname(HERE), 'themes')):
        if os.path.isdir(d):
            return d
    raise ThemeError('no themes folder next to %s; pass --themes' % HERE)


def read_theme(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ThemeError('%s: cannot read it as JSON (%s)' % (path, e))
    if not isinstance(data, dict) or not isinstance(data.get('meta'), dict) or not data['meta'].get('name'):
        raise ThemeError('%s: not a KiCad colour theme (no meta.name)' % path)
    return data


def load_themes(d):
    """{name: (path, data)}. The name is the file name: KiCad and kicad-cli --theme look themes up by it."""
    paths = sorted(glob.glob(os.path.join(d, '*.json')))
    if not paths:
        raise ThemeError('no *.json themes in %s' % d)
    return {os.path.basename(p)[:-len('.json')]: (p, read_theme(p)) for p in paths}


def settings_dir(version, config_dir=None):
    """The KiCad settings folder for this version: the one that holds colors/."""
    if config_dir:
        return os.path.abspath(config_dir)
    env = os.environ.get('KICAD_CONFIG_HOME')
    if env:
        base = env
    elif sys.platform == 'win32':
        appdata = os.environ.get('APPDATA')
        if not appdata:
            raise ThemeError('APPDATA is not set; pass --config-dir')
        base = os.path.join(appdata, 'kicad')
    elif sys.platform == 'darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Preferences', 'kicad')
    else:
        base = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config'),
                            'kicad')
    return os.path.join(os.path.abspath(base), version)


def flatten(data, prefix=''):
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out.update(flatten(v, prefix + k + '.'))
        else:
            out[prefix + k] = v
    return out


def differences(ours, theirs):
    """Keys of our theme that the installed file lacks or has with another value. KiCad adds keys of its own when
    it saves a theme, and lengthens the colour lists, so extra keys and list entries in the installed file do not
    count."""
    a, b = flatten(ours), flatten(theirs)

    def same(x, y):
        if isinstance(x, list) and isinstance(y, list):
            return y[:len(x)] == x
        return x == y

    return sorted(k for k in a if k not in b or not same(a[k], b[k]))


def state(name, data, colors):
    """('missing' | 'same' | 'differs' | 'unreadable', [differing keys])."""
    dst = os.path.join(colors, name + '.json')
    if not os.path.exists(dst):
        return 'missing', []
    try:
        diffs = differences(data, read_theme(dst))
    except ThemeError:
        return 'unreadable', []
    return ('differs', diffs) if diffs else ('same', [])


def shown(path):
    """The path as the user would type it: relative when it is under the current folder."""
    rel = os.path.relpath(path)
    return path if rel.startswith('..') else rel


def some(keys, n=4):
    return ', '.join(keys[:n]) + (' and %d more' % (len(keys) - n) if len(keys) > n else '')


def cmd_list(a):
    d = themes_dir(a.themes)
    themes = load_themes(d)
    colors = os.path.join(settings_dir(a.kicad_version, a.config_dir), 'colors')
    print('Themes in %s; KiCad reads them from %s:' % (shown(d), colors))
    for name, (path, data) in themes.items():
        st, diffs = state(name, data, colors)
        note = {'missing': 'not installed',
                'same': 'installed',
                'differs': 'installed with other colours (%s); install --force replaces it' % some(diffs),
                'unreadable': 'installed, but KiCad\'s copy is not readable; install --force replaces it'}[st]
        print('  %-22s %s' % (name, note))
        if data['meta']['name'] != name:
            print('  %-22s note: KiCad\'s menus show it as "%s" (meta.name)' % ('', data['meta']['name']))
    return 0


def cmd_install(a):
    d = themes_dir(a.themes)
    themes = load_themes(d)
    unknown = [n for n in a.names if n not in themes]
    if unknown:
        raise ThemeError('no theme %s in %s; choose from %s' % (', '.join(unknown), d, ', '.join(themes)))
    settings = settings_dir(a.kicad_version, a.config_dir)
    colors = os.path.join(settings, 'colors')
    if not os.path.isdir(settings):
        if not a.create:
            raise ThemeError(
                'KiCad %s has no settings folder here yet (%s). Open KiCad %s once so it can set itself up, then run '
                'this again. Other KiCad version: --kicad-version. Flatpak or portable KiCad: --config-dir. On a CI '
                'machine: --create makes the folder' % (a.kicad_version, settings, a.kicad_version))
        os.makedirs(settings)
        print('made %s' % settings)
    os.makedirs(colors, exist_ok=True)
    left = done = 0
    for name in a.names or list(themes):
        path, data = themes[name]
        dst = os.path.join(colors, name + '.json')
        st, diffs = state(name, data, colors)
        if st == 'same':
            print('%s: already installed' % name)
            continue
        if st in ('differs', 'unreadable'):
            why = 'other colours (%s)' % some(diffs) if st == 'differs' else 'a file that is not readable'
            if not a.force:
                left += 1
                print('%s: left alone. %s has %s. --force replaces it and keeps the old file as %s.json.bak'
                      % (name, dst, why, name))
                continue
            shutil.copyfile(dst, dst + '.bak')
            print('%s: kept the old file as %s.bak' % (name, dst))
        shutil.copyfile(path, dst)
        done += 1
        print('%s: installed to %s' % (name, dst))
    if done:
        print('Restart KiCad if it is open, then choose the theme in Preferences > Preferences > Schematic Editor > '
              'Colors and PCB Editor > Colors. kicad-cli: --theme <name> on the export commands.')
    return 1 if left else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--themes', help='the themes folder (default: themes/ next to this script)')
    p.add_argument('--kicad-version', default=KICAD_VERSION,
                   help='KiCad settings version, the folder name under kicad/ (default %s)' % KICAD_VERSION)
    p.add_argument('--config-dir', help='the KiCad settings folder that holds colors/, when it is not the usual one')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('list', help='the themes, and whether this machine has them')
    s.set_defaults(func=cmd_list)
    s = sub.add_parser('install', help='copy the themes into KiCad\'s settings folder')
    s.add_argument('names', nargs='*', metavar='THEME', help='theme names (default: all)')
    s.add_argument('--force', action='store_true', help='replace an installed theme that has other colours')
    s.add_argument('--create', action='store_true', help='make the KiCad settings folder when it does not exist')
    s.set_defaults(func=cmd_install)
    a = p.parse_args(argv)
    try:
        return a.func(a)
    except ThemeError as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
