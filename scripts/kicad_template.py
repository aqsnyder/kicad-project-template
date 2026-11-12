#!/usr/bin/env python3
"""Set up a repository for KiCad boards, and add boards to it, from this template.

usage:
  kicad_template.py init-repo REPO [--prefix PREFIX] [--no-library] [--force]
  kicad_template.py update-repo REPO [--check] [--force]
  kicad_template.py new-board BOARD_DIR [--title TEXT] [--project TEXT] [--company TEXT] [--designer TEXT]
                              [--reviewer TEXT] [--revision REV] [--fab PROFILE] [--no-library-tables]

init-repo  adds the repository-level files: kicad-fab.toml, hw/requirements-tools.txt,
           hw/fab.py and the fab profiles in hw/fabs/, hw/theme.py and the colour themes
           in hw/themes/, the front-page scripts in hw/tools/, hw/drawing-sheet.kicad_wks (the
           repository's master copy, to brand once), .github/workflows/hardware.yml and a
           KiCad block in .gitignore. It
           creates the part library in hw/lib with kicad-part-importer --init (mount
           ${KIPRJMOD}/../lib), when the tool is installed. Existing files are kept unless
           --force is given; the .gitignore block is added once.
update-repo  copies the files that have one source, this template, into a repository again:
           hw/fab.py, hw/theme.py, the template's fab profiles in hw/fabs/ and the scripts in
           hw/tools/. It writes hw/template-files.json, the list that the repository's
           hw/tools/check_copies.py checks them against. A copy that was edited in the
           repository stops the run before anything is written; --force replaces it too.
           --check writes nothing and exits 1 if a copy is missing or differs. Themes that
           are missing are added. Everything else in the repository is left alone.
new-board  copies templates/starter-board to BOARD_DIR (normally REPO/hw/<board>), names
           the project after the folder, fills the text variables, takes the drawing
           sheet from hw/drawing-sheet.kicad_wks when there is one, sets the fab
           (hw/fab.py set; default pcbway-standard), lists every category library of hw/lib in
           the board's library tables, and draws the schematic's front pages for the new
           name (hw/tools/frontpages.py; the board views need kicad-cli). Text variables
           not given keep the template's values (edit those in a branded copy of the
           template).

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
FABS = os.path.join(ROOT, 'fabs')
THEMES = os.path.join(ROOT, 'themes')
TOOLS = os.path.join(REPO_FILES, 'tools')
DEFAULT_FAB = 'pcbway-standard'
sys.path.insert(0, REPO_FILES)
sys.dont_write_bytecode = True
import fab  # noqa: E402  (repo-files/fab.py, copied into each repository as hw/fab.py)
sys.path.insert(0, TOOLS)
import check_copies  # noqa: E402  (repo-files/tools/check_copies.py: the list of copied files, and its check)
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


def managed():
    """[(file in this template, its path under REPO/hw)]: the files that have one source, the template. A
    repository does not edit its copies (hw/tools/check_copies.py checks them); update-repo copies them again."""
    out = [(os.path.join(REPO_FILES, 'fab.py'), 'fab.py'), (os.path.join(REPO_FILES, 'theme.py'), 'theme.py')]
    out += [(os.path.join(FABS, f), 'fabs/' + f) for f in sorted(os.listdir(FABS)) if f.endswith('.kicad_dru')]
    out += [(os.path.join(TOOLS, f), 'tools/' + f) for f in sorted(os.listdir(TOOLS)) if f.endswith('.py')]
    return out


def template_version():
    """What a repository's list calls this copy of the template: git describe, or "unknown"."""
    try:
        r = subprocess.run(['git', '-C', ROOT, 'describe', '--tags', '--always', '--dirty'],
                           capture_output=True, text=True)
        return r.stdout.strip() or 'unknown'
    except OSError:
        return 'unknown'


def write_list(repo):
    """hw/template-files.json: the copied files, each with the sha256 of the template's. Returns True if it was
    written. A list that names the same files with the same digits is left as it is, so another commit of the
    template alone does not change a repository."""
    hw = os.path.join(repo, 'hw')
    files = {rel: check_copies.digest(src) for src, rel in managed()}
    if check_copies.read_list(hw)[1] == files:
        return False
    data = {'comment': 'Files copied from kicad-project-template, each with the sha256 of its text. Do not edit '
                       'them here: change the template and run its kicad_template.py update-repo on this '
                       'repository. hw/tools/check_copies.py checks them against this list.',
            'template': template_version(), 'files': files}
    with open(os.path.join(hw, check_copies.LIST), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    return True


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
    for src, rel in managed():
        copy_file(src, os.path.join(repo, 'hw', *rel.split('/')), a.force, written, skipped)
    for f in sorted(os.listdir(THEMES)):
        if f.endswith('.json'):
            copy_file(os.path.join(THEMES, f), os.path.join(repo, 'hw', 'themes', f), a.force, written, skipped)
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

    if write_list(repo):
        written.append(os.path.join(repo, 'hw', check_copies.LIST))
    for p in written:
        say('wrote   ' + os.path.relpath(p, repo))
    for p in skipped:
        say('kept    ' + os.path.relpath(p, repo) + ' (exists; --force to replace)')
    stale = check_copies.changed(os.path.join(repo, 'hw'))
    if stale:
        say('note: %d kept files are not the template\'s (%s): %s update-repo %s brings them up to date'
            % (len(stale), ', '.join(rel for rel, _ in stale), sys.argv[0], a.repo))
    say('Next: python3 %s new-board %s' % (sys.argv[0], os.path.join(a.repo, 'hw', '<board>')))
    say('Colours: python3 %s install, once per machine, then choose the theme in KiCad\'s preferences'
        % os.path.join(a.repo, 'hw', 'theme.py'))


def update_repo(a):
    """Copy the template's own files into a repository again and write its list of them (see the module's text)."""
    repo = os.path.abspath(a.repo)
    hw = os.path.join(repo, 'hw')
    if not os.path.isdir(hw):
        sys.exit('ERROR: %s has no hw folder: run init-repo on it first' % repo)
    listed = check_copies.read_list(hw)[1]
    todo, edited = [], []                   # (src, rel, why) to copy; and those of them that were edited here
    for src, rel in managed():
        dst = os.path.join(hw, *rel.split('/'))
        if not os.path.exists(dst):
            todo.append((src, rel, 'missing'))
        elif check_copies.digest(dst) != check_copies.digest(src):
            # An older copy reads as the list says. Anything else was edited here, or copied before there was a list.
            mine = (listed or {}).get(rel) != check_copies.digest(dst)
            todo.append((src, rel, 'older than the template\'s' if not mine else
                         'edited here' if listed is not None else 'differs (no list yet)'))
            if mine:
                edited.append(rel)
    themes = [f for f in sorted(os.listdir(THEMES))
              if f.endswith('.json') and not os.path.exists(os.path.join(hw, 'themes', f))]
    gone = sorted(set(listed or {}) - {rel for _, rel in managed()})
    stale_list = listed != {rel: check_copies.digest(src) for src, rel in managed()}
    others = []                             # the repository's own to keep or merge: only said, never copied
    for name, dst in (('hardware.yml', os.path.join('.github', 'workflows', 'hardware.yml')),
                      ('kicad-fab.toml', 'kicad-fab.toml'),
                      ('requirements-tools.txt', os.path.join('hw', 'requirements-tools.txt'))):
        src, path = os.path.join(REPO_FILES, name), os.path.join(repo, dst)
        if not os.path.exists(path) or check_copies.digest(path) != check_copies.digest(src):
            others.append(dst)

    for _, rel, why in todo:
        say('%-28s hw/%s' % (why, rel))
    for f in themes:
        say('%-28s hw/themes/%s' % ('missing', f))
    if a.check:
        if listed is None:
            say('hw/%s is missing' % check_copies.LIST)
        say('%s: %d of %d copied files would change' % (a.repo, len(todo), len(managed())))
        return 1 if todo or themes or stale_list else 0
    if edited and not a.force:
        say('Nothing was written. Edited in this repository, or copied before it kept a list: %d. Compare each '
            'with the template\'s (%s and %s), move what should stay into the template, then run update-repo '
            '--force, which replaces them.' % (len(edited), os.path.relpath(REPO_FILES), os.path.relpath(FABS)))
        return 1
    for src, rel, _ in todo:
        dst = os.path.join(hw, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    for f in themes:
        os.makedirs(os.path.join(hw, 'themes'), exist_ok=True)
        shutil.copyfile(os.path.join(THEMES, f), os.path.join(hw, 'themes', f))
    wrote = write_list(repo)
    say('%s: %d files copied%s; hw/%s %s' % (a.repo, len(todo) + len(themes),
                                             ' (%d of them had been edited here)' % len(edited) if edited else '',
                                             check_copies.LIST, 'written' if wrote else 'unchanged'))
    for rel in gone:
        say('note: hw/%s was copied from an earlier template, which no longer has it: delete it if nothing uses it'
            % rel)
    if any(rel.startswith('fabs/') for _, rel, _ in todo):
        say('note: a fab profile changed. Run python3 hw/fab.py verify --all, then python3 hw/fab.py set <profile> '
            '<board> for each board it names.')
    if others:
        say('note: not copied, and different from the template\'s (yours to keep or to merge by hand): '
            + ', '.join(o.replace(os.sep, '/') for o in others))
    return 0


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


def front_pages(dest):
    """Draw the cover, Architecture, Mechanical and Revision History pages of the board in dest for its own name,
    with the repository's hw/tools/frontpages.py when it has one, else the template's. Returns a note."""
    repo_tools = os.path.join(os.path.dirname(dest), 'tools')
    sys.path.insert(0, repo_tools if os.path.exists(os.path.join(repo_tools, 'frontpages.py')) else TOOLS)
    import frontpages
    try:
        frontpages.kicad_cli()
        render = True
    except RuntimeError:
        render = False                  # the cover then says how to get the two board views
    try:
        frontpages.build(dest, render_views=render, quiet=True)
    except (RuntimeError, AssertionError) as e:
        sys.exit('ERROR: front pages of %s: %s' % (dest, e))
    return 'front pages drawn' if render else \
        'front pages drawn without the board views (no kicad-cli: run frontpages.py on the board later)'


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
        if f.endswith(('.kicad_prl', '.lck')):      # what KiCad or kicad-cli leaves beside a project it opened
            continue
        if f == SHEET and os.path.exists(master_sheet):
            src = master_sheet          # the repository's branded drawing sheet
        out = name + f[len(TEMPLATE_NAME):] if f.startswith(TEMPLATE_NAME + '.') else f
        shutil.copyfile(src, os.path.join(dest, out))
        if out.endswith('.kicad_sch'):      # a sheet symbol names its project: the copy is its own project
            with open(os.path.join(dest, out), encoding='utf-8', newline='') as fh:
                t = fh.read()
            with open(os.path.join(dest, out), 'w', encoding='utf-8', newline='') as fh:
                fh.write(t.replace('(project "%s"' % TEMPLATE_NAME, '(project "%s"' % name))

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
    for key, given in (('PROJECT_NAME', a.project), ('REVIEWER', a.reviewer)):     # in the project file only
        if given is not None:
            data['text_variables'][key] = given
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

    # The repository's own profiles (hw/fabs) when it has them, else the template's.
    repo_fabs = os.path.join(os.path.dirname(dest), 'fabs')
    try:
        profiles = fab.load_profiles(repo_fabs if os.path.isdir(repo_fabs) else FABS)
        profile = profiles.get(a.fab)
        if profile is None:
            raise fab.FabError('no fab profile %r; choose from %s' % (a.fab, ', '.join(profiles)))
        os.remove(os.path.join(dest, name + '.kicad_dru'))     # start from the profile alone
        fab.apply(profile, fab.Board(dest))
    except fab.FabError as e:
        sys.exit('ERROR: %s' % e)

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
    pages = front_pages(dest)
    say('Created %s: project %s, %s; %s; fab %s (%s); %s' % (
        os.path.relpath(dest), name, note, sheet, profile.id, os.path.relpath(profile.path), pages))
    say('Text variables: ' + ', '.join('%s=%s' % kv for kv in values.items()) + ', FAB=' + profile.name)


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
    b.add_argument('--project', help='PROJECT_NAME: the product the board belongs to')
    b.add_argument('--company', help='COMPANY')
    b.add_argument('--designer', help='DESIGNER (default: git config user.name)')
    b.add_argument('--reviewer', help='REVIEWER')
    b.add_argument('--revision', default='0.1', help='REVISION (default 0.1)')
    b.add_argument('--fab', default=DEFAULT_FAB, help='fab profile (default %s); see fabs/' % DEFAULT_FAB)
    b.add_argument('--no-library-tables', action='store_true', help='leave sym-lib-table and fp-lib-table empty')
    b.set_defaults(func=new_board)
    u = sub.add_parser('update-repo', help='copy the template\'s own files into a repository again')
    u.add_argument('repo')
    u.add_argument('--check', action='store_true', help='write nothing; exit 1 if a copy is missing or differs')
    u.add_argument('--force', action='store_true', help='also replace copies that were edited in the repository')
    u.set_defaults(func=update_repo)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == '__main__':
    sys.exit(main())
