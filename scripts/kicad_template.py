#!/usr/bin/env python3
"""Set up a repository for KiCad boards, and add boards to it, from this template.

usage:
  kicad_template.py init-repo REPO [--prefix PREFIX] [--no-library] [--force]
  kicad_template.py new-board BOARD_DIR [--title TEXT] [--company TEXT] [--designer TEXT]
                              [--revision REV] [--rules NAME] [--no-library-tables]

init-repo  adds the repository-level files: kicad-fab.toml, hw/requirements-tools.txt,
           hw/rules/, hw/drawing-sheet.kicad_wks (the repository's master copy, to brand
           once), .github/workflows/hardware.yml and a KiCad block in .gitignore. It
           creates the part library in hw/lib with kicad-part-importer --init (mount
           ${KIPRJMOD}/../lib), when the tool is installed. Existing files are kept unless
           --force is given; the .gitignore block is added once.
new-board  copies templates/starter-board to BOARD_DIR (normally REPO/hw/<board>), names
           the project after the folder, fills the text variables, takes the drawing
           sheet from hw/drawing-sheet.kicad_wks when there is one, and lists every
           category library of hw/lib in the board's library tables. Text variables not
           given keep the template's values (edit those in a branded copy of the template).

Standard library only; Python 3.9 or newer.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(ROOT, 'templates', 'starter-board')
TEMPLATE_NAME = 'starter-board'
REPO_FILES = os.path.join(ROOT, 'repo-files')
RULES = os.path.join(ROOT, 'rules')
MOUNT = '${KIPRJMOD}/../lib'
GITIGNORE_MARK = '# KiCad (from kicad-project-template)'
SHEET = 'drawing-sheet.kicad_wks'
TEXT_VARS = ('BOARD_NAME', 'COMPANY', 'DESIGNER', 'RELEASE_DATE', 'REVISION')


def say(msg):
    print(msg, flush=True)


def copy_file(src, dst, force, written, skipped):
    if os.path.exists(dst) and not force:
        skipped.append(dst)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    written.append(dst)


def add_gitkeeps(top):
    """git drops empty folders; an empty .pretty or 3d_models folder must survive a clone."""
    n = 0
    for d, subdirs, files in os.walk(top):
        if '.git' in subdirs:
            subdirs.remove('.git')
        if not subdirs and not files:
            open(os.path.join(d, '.gitkeep'), 'w').close()
            n += 1
    return n


def init_repo(a):
    repo = os.path.abspath(a.repo)
    if not os.path.isdir(repo):
        sys.exit('ERROR: %s is not a folder' % repo)
    written, skipped = [], []
    copy_file(os.path.join(REPO_FILES, 'kicad-fab.toml'), os.path.join(repo, 'kicad-fab.toml'), a.force,
              written, skipped)
    copy_file(os.path.join(REPO_FILES, 'requirements-tools.txt'),
              os.path.join(repo, 'hw', 'requirements-tools.txt'), a.force, written, skipped)
    copy_file(os.path.join(REPO_FILES, 'hardware.yml'),
              os.path.join(repo, '.github', 'workflows', 'hardware.yml'), a.force, written, skipped)
    for f in sorted(os.listdir(RULES)):
        if f.endswith('.kicad_dru'):
            copy_file(os.path.join(RULES, f), os.path.join(repo, 'hw', 'rules', f), a.force, written, skipped)
    copy_file(os.path.join(TEMPLATE, SHEET), os.path.join(repo, 'hw', SHEET), a.force, written, skipped)

    gi = os.path.join(repo, '.gitignore')
    have = open(gi, encoding='utf-8').read() if os.path.exists(gi) else ''
    if GITIGNORE_MARK in have:
        skipped.append(gi)
    else:
        block = open(os.path.join(REPO_FILES, 'gitignore-kicad'), encoding='utf-8').read()
        with open(gi, 'a', encoding='utf-8', newline='\n') as f:
            if have and not have.endswith('\n'):
                f.write('\n')
            f.write(('\n' if have else '') + block)
        written.append(gi)

    lib = os.path.join(repo, 'hw', 'lib')
    if a.no_library:
        say('library: skipped (--no-library)')
    elif os.path.exists(os.path.join(lib, 'kicad-part-importer.toml')):
        say('library: hw/lib already has a kicad-part-importer.toml, left as it is')
    else:
        cmd = ['kicad-part-importer', '--init', '--library', lib, '--library-prefix', a.prefix,
               '--library-mount', MOUNT, '--config-format', 'toml']
        if shutil.which('kicad-part-importer') is None:
            say('library: kicad-part-importer is not installed. Install it (pip install -r hw/requirements-tools.txt)'
                ' and run:\n  ' + ' '.join("'%s'" % c if '$' in c else c for c in cmd))
        else:
            os.makedirs(lib, exist_ok=True)
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit('ERROR: kicad-part-importer --init failed:\n' + r.stdout + r.stderr)
            say('library: hw/lib created (prefix %s, mount %s), %d empty folders kept with .gitkeep'
                % (a.prefix, MOUNT, add_gitkeeps(lib)))

    for p in written:
        say('wrote   ' + os.path.relpath(p, repo))
    for p in skipped:
        say('kept    ' + os.path.relpath(p, repo) + ' (exists; --force to replace)')
    say('Next: python3 %s new-board %s' % (sys.argv[0], os.path.join(a.repo, 'hw', '<board>')))


def git_user_name():
    try:
        r = subprocess.run(['git', 'config', 'user.name'], capture_output=True, text=True)
        return r.stdout.strip()
    except OSError:
        return ''


def library_categories(lib):
    """(name, description, kind) for every category library in hw/lib, in config order when readable."""
    out = []
    descr = {}
    cfg = os.path.join(lib, 'kicad-part-importer.toml')
    prefix = 'lib_'
    sym_dir, fp_dir = 'lib_sym', 'lib_fp'
    try:
        import tomllib  # Python 3.11+
        with open(cfg, 'rb') as f:
            c = tomllib.load(f)
        prefix = c.get('library_prefix', prefix)
        sym_dir = c.get('symbol_dir', sym_dir)
        fp_dir = c.get('footprint_dir', fp_dir)
        for cat in c.get('categories', []):
            descr[cat.get('name') or prefix + cat['key']] = cat.get('description', '')
    except (ImportError, OSError, KeyError, ValueError):
        pass
    order = list(descr)
    sd, fd = os.path.join(lib, sym_dir), os.path.join(lib, fp_dir)
    syms = sorted(f[:-len('.kicad_sym')] for f in os.listdir(sd) if f.endswith('.kicad_sym')) \
        if os.path.isdir(sd) else []
    fps = sorted(f[:-len('.pretty')] for f in os.listdir(fd) if f.endswith('.pretty')) if os.path.isdir(fd) else []
    rank = lambda n: (order.index(n) if n in order else len(order), n)  # noqa: E731
    for n in sorted(syms, key=rank):
        out.append((n, descr.get(n, ''), 'sym', '%s/%s/%s.kicad_sym' % (MOUNT, sym_dir, n)))
    for n in sorted(fps, key=rank):
        out.append((n, descr.get(n, ''), 'fp', '%s/%s/%s.pretty' % (MOUNT, fp_dir, n)))
    return out


def write_lib_table(path, kind, entries):
    head = 'sym_lib_table' if kind == 'sym' else 'fp_lib_table'
    lines = ['(%s' % head, '  (version 7)']
    for name, descr, k, uri in entries:
        if k == kind:
            lines.append('  (lib (name "%s")(type "KiCad")(uri "%s")(options "")(descr "%s"))'
                         % (name, uri, descr.replace('"', "'")))
    lines.append(')')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def new_board(a):
    dest = os.path.abspath(a.board_dir)
    name = os.path.basename(dest.rstrip('/\\'))
    if not re.match(r'^[A-Za-z0-9_.-]+$', name):
        sys.exit('ERROR: board folder name %r: use letters, digits, _ . and - (it becomes the project name)' % name)
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit('ERROR: %s exists and is not empty' % dest)
    os.makedirs(dest, exist_ok=True)
    master_sheet = os.path.join(os.path.dirname(dest), SHEET)
    for f in sorted(os.listdir(TEMPLATE)):
        src = os.path.join(TEMPLATE, f)
        if os.path.isdir(src):          # meta/ is for KiCad's template chooser only
            continue
        if f == SHEET and os.path.exists(master_sheet):
            src = master_sheet          # the repository's branded drawing sheet
        out = name + f[len(TEMPLATE_NAME):] if f.startswith(TEMPLATE_NAME + '.') else f
        shutil.copyfile(src, os.path.join(dest, out))

    pro = os.path.join(dest, name + '.kicad_pro')
    with open(pro, encoding='utf-8') as f:
        data = json.load(f)
    old = data.get('text_variables', {})
    values = {
        'BOARD_NAME': a.title or name,
        'COMPANY': a.company if a.company is not None else old.get('COMPANY', ''),
        'DESIGNER': a.designer if a.designer is not None else (old.get('DESIGNER') or git_user_name()),
        'RELEASE_DATE': datetime.date.today().isoformat(),
        'REVISION': a.revision,
    }
    data.setdefault('meta', {})['filename'] = name + '.kicad_pro'
    data.setdefault('text_variables', {}).update(values)
    with open(pro, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

    pcb = os.path.join(dest, name + '.kicad_pcb')
    with open(pcb, encoding='utf-8') as f:
        t = f.read()
    for k, v in values.items():
        t, n = re.subn(r'(\(property "%s" ")[^"]*(")' % k, lambda m: m.group(1) + v.replace('"', "'") + m.group(2), t)
        if n != 1:
            sys.exit('ERROR: %s: expected one (property "%s" ...) line, found %d' % (pcb, k, n))
    with open(pcb, 'w', encoding='utf-8', newline='\n') as f:
        f.write(t)

    if a.rules:
        src = os.path.join(RULES, a.rules if a.rules.endswith('.kicad_dru') else a.rules + '.kicad_dru')
        if not os.path.exists(src):
            sys.exit('ERROR: no rules file %s; choose from %s' % (src, ', '.join(
                f[:-10] for f in sorted(os.listdir(RULES)) if f.endswith('.kicad_dru'))))
        shutil.copyfile(src, os.path.join(dest, name + '.kicad_dru'))

    lib = os.path.join(os.path.dirname(dest), 'lib')
    note = 'library tables left empty'
    if not a.no_library_tables and os.path.isdir(lib):
        entries = library_categories(lib)
        if entries:
            write_lib_table(os.path.join(dest, 'sym-lib-table'), 'sym', entries)
            write_lib_table(os.path.join(dest, 'fp-lib-table'), 'fp', entries)
            note = 'library tables list %d symbol and %d footprint libraries of %s' % (
                sum(1 for e in entries if e[2] == 'sym'), sum(1 for e in entries if e[2] == 'fp'),
                os.path.relpath(lib, os.path.dirname(os.path.dirname(dest))))
    sheet = 'drawing sheet from %s' % (os.path.relpath(master_sheet) if os.path.exists(master_sheet)
                                       else 'the template')
    say('Created %s: project %s, %s; %s; fab rules %s' % (
        os.path.relpath(dest), name, note, sheet, a.rules or 'from the template'))
    say('Text variables: ' + ', '.join('%s=%s' % kv for kv in values.items()))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('init-repo', help='add the repository-level files and the part library')
    r.add_argument('repo')
    r.add_argument('--prefix', default='lib_', help='part library prefix, e.g. acme_ (default lib_)')
    r.add_argument('--no-library', action='store_true', help='do not create hw/lib')
    r.add_argument('--force', action='store_true', help='replace repository files that exist')
    r.set_defaults(func=init_repo)
    b = sub.add_parser('new-board', help='copy the starter board into a new folder')
    b.add_argument('board_dir')
    b.add_argument('--title', help='BOARD_NAME (default: the folder name)')
    b.add_argument('--company', help='COMPANY')
    b.add_argument('--designer', help='DESIGNER (default: git config user.name)')
    b.add_argument('--revision', default='0.1', help='REVISION (default 0.1)')
    b.add_argument('--rules', help='a rules/ file instead of jlcpcb-2layer, e.g. pcbway-standard')
    b.add_argument('--no-library-tables', action='store_true', help='leave sym-lib-table and fp-lib-table empty')
    b.set_defaults(func=new_board)
    a = p.parse_args(argv)
    a.func(a)


if __name__ == '__main__':
    main()
