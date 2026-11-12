#!/usr/bin/env python3
"""check_copies: are the files this repository copied from kicad-project-template still as the template wrote them?

usage: python3 hw/tools/check_copies.py [HW]

  HW   the hw folder (default: the folder above this script's)

hw/template-files.json lists the copied files, each with a sha256 of its text (line ends do not count), and the
template they came from. This script prints every listed file that is missing or reads differently and exits 1 if
there is one, else 0. It needs no KiCad and no network, so the hardware workflow runs it on every push.

These files have one source, the template: hw/fab.py, hw/theme.py, the template's fab profiles in hw/fabs/ and the
scripts in hw/tools/. Do not edit them here. To change one, change it in kicad-project-template (repo-files/ and
fabs/ there), then copy the template's files into this repository again:

    python3 <kicad-project-template>/scripts/kicad_template.py update-repo <this repository>

That writes hw/template-files.json anew. Files this repository adds to hw/fabs/ or hw/tools/ are its own: they are
not in the list and nothing checks them. Standard library only; Python 3.9 or newer.
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = 'template-files.json'


def digest(path):
    """sha256 of a text file with its line ends as LF, so a CR LF checkout gives the same digits."""
    with io.open(path, 'rb') as f:
        return hashlib.sha256(f.read().replace(b'\r\n', b'\n')).hexdigest()


def read_list(hw):
    """(template, {path under hw: sha256}) from hw/template-files.json, or (None, None) if there is no list."""
    path = os.path.join(hw, LIST)
    if not os.path.exists(path):
        return None, None
    with io.open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('template', ''), data.get('files', {})


def changed(hw):
    """[(path under hw, 'missing' or 'edited')] of the listed files that are not as the list says."""
    _, files = read_list(hw)
    out = []
    for rel, want in sorted((files or {}).items()):
        path = os.path.join(hw, *rel.split('/'))
        if not os.path.exists(path):
            out.append((rel, 'missing'))
        elif digest(path) != want:
            out.append((rel, 'edited'))
    return out


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    hw = os.path.abspath(args[0]) if args else os.path.dirname(HERE)
    template, files = read_list(hw)
    if files is None:
        print('ERROR: %s has no %s. Run kicad_template.py update-repo from kicad-project-template on this '
              'repository: it copies the template\'s files and writes the list.' % (hw, LIST), file=sys.stderr)
        return 2
    bad = changed(hw)
    for rel, what in bad:
        print('%-8s %s' % (what, os.path.join(os.path.basename(hw), *rel.split('/'))))
    if bad:
        print('Not as the template wrote them: %d of the %d files copied from kicad-project-template (%s). Do not '
              'edit them here: make the change in the template, then run its kicad_template.py update-repo on this '
              'repository. update-repo --force also puts back what was edited or is missing.'
              % (len(bad), len(files), template or 'version not recorded'))
        return 1
    print('%d files copied from kicad-project-template (%s): all as the template wrote them'
          % (len(files), template or 'version not recorded'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
