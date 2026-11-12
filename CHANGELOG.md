# Changelog

## Unreleased

- **Fix: fab packages on tags.** The `hardware` workflow's boards job runs as root, but the checkout belongs to the
  runner user, so git refused it ("dubious ownership") and kicad-macrofab-bom and kicad-fab-export failed on every
  tag. The job now adds the checkout to git's `safe.directory`. The self-test runs both tools in its own checkout to
  cover this; before, it ran git only in a demo repository that root owns.
- **Fab packages only on `hw-v*` tags,** not every tag: path filters do not apply to tags, so a repository that also
  tags firmware built packages for those too, and a tag with `/` in it broke the artifact name. The fab package loop
  now keeps going past a failing board, and the packages that were made are uploaded either way.
- **Fab profiles give their copper layer counts** (`# copper-layers: 1-6` for PCBWay standard, `1-2` for JLCPCB 1-2
  layer, `4-6` for JLCPCB 4-6 layer). `fab.py check` shows `n/a (N layers)` for a fab outside its range instead of
  the `ok` a 4-layer board used to get under `jlcpcb-2layer`, and `set` prints a note. `check` covers DRC geometry
  and layer count, not thickness or stackup. The self-test adds a 4-layer fixture board.
- **README:** the known gaps now give PCBWay's real BOM and centroid formats (the ones listed were JLCPCB's), say that
  a placed part with a model in `hw/lib` fails kicad-fab-export, and add that an outline drawn as one `gr_circle`
  fails the STEP origin check.
- **Altium-style colour theme.** `themes/Altium_Theme.json` is a KiCad colour theme for the schematic and board
  editors. KiCad reads themes from the user's settings folder only, so `hw/theme.py` (copied into each repository,
  with the theme in `hw/themes/`) installs it: `list` shows whether a machine has it, and `install` copies it,
  leaving alone a theme the user has edited unless `--force` is given. kicad-cli takes it as `--theme Altium_Theme`.
- **Coloured net classes.** The starter board's classes now carry schematic and board colours, and wires in a class
  are drawn 10 mil wide. New classes `RF_50R`, `Debug`, `UART`, `Bus`, `Clock`, `Analog` and `USB` only colour
  their nets: they set no rules, so those nets keep the `Default` class's widths and clearances. `GND*` nets move
  from `Power` to a new `GND` class with the same rules, so that ground is green and supply rails are red. The
  project file states each class's priority (net settings version 5), with the classes that set rules first.
- **`Bus` has a lighter blue on the board** (`rgb(70, 130, 255)`): navy does not show on the board editor's dark
  background, where KiCad draws ratsnest lines in the class colour.
- **Front pages.** A schematic now opens with a cover (contents table, two views of the board, notes, the key to
  boxed notes) and an Architecture page, and closes with Mechanical and Revision History pages; every other sheet
  gets a "[page] Title" heading. `hw/tools/frontpages.py` draws them from the board and from
  `hw/<board>/frontpages.json`, and `new-board` runs it. The net colour key is on the Architecture page, drawn
  from the project's net classes. `hw/tools/archdiagram.py` draws an architecture diagram from a description.
- **New title block,** 187 x 42 mm, drawn by `hw/tools/titleblock.py`: it adds Comments, Variant, Project Name,
  Sheet Path and Reviewer, and `--logo PNG` replaces the `LOGO` box. New text variables `PROJECT_NAME`, `REVIEWER`
  and `VARIANT`; `new-board` takes `--project` and `--reviewer`.
- **One source for the copied scripts.** `hw/fab.py`, `hw/theme.py`, the template's fab profiles and the scripts
  in `hw/tools/` are copies that a repository does not edit. `kicad_template.py update-repo REPO` copies the
  template's into a repository again and writes `hw/template-files.json`, a list with a checksum each;
  `hw/tools/check_copies.py` fails when a copy was edited in place, and the `hardware` workflow runs it.
  `update-repo` stops at a copy that was edited in the repository unless `--force` is given.
- **Fix: `fab.py` picks the newest KiCad on Windows.** With KiCad 9 and 10 both installed and no `kicad-cli` on
  the path it took KiCad 9, which cannot load a KiCad 10 board.
- **Self-test:** `tests/check_netclasses.py` checks the class table, the colour key, and that KiCad 10 resolves
  and plots some forty sample net names as the table says, with the theme installed by `theme.py`. The front
  pages are checked on the starter board and on a board made by `new-board`, also after KiCad saves each sheet.
  `update-repo` and `check_copies.py` are run on a repository with an edited copy and with an older one.

Upgrading a repository made from 0.2.0: run `kicad_template.py update-repo <repository> --check` to see what
differs. If the repository changed `hw/fab.py` or a profile itself, move that into the template first. Then run
`update-repo <repository> --force`, which brings `hw/fab.py`, `hw/theme.py`, the fab profiles, the theme and
`hw/tools/`, and copy `repo-files/hardware.yml` to `.github/workflows/` (or merge it into yours). Run
`python3 hw/fab.py set <profile> <board>` for each board so its rules match the profile again, and
`python3 hw/theme.py install` on each machine. A profile of your own needs a `# copper-layers:` line, or `fab.py`
refuses it.

A board that exists keeps its own net classes. To give it the coloured ones, close it in KiCad and copy the
`net_settings` object from `templates/starter-board/starter-board.kicad_pro` into its `.kicad_pro`, keeping any
classes and patterns of the board's own; a custom rule that tests `A.NetClass == 'Power'` no longer matches `GND*`
nets after that.

To give an existing board the front pages, close it in KiCad, copy
`templates/starter-board/frontpages.json` into its folder, move the words of its cover's Overview, Ordering notes
and Revision history boxes into that file, and run `python3 hw/tools/titleblock.py hw` and then
`python3 hw/tools/frontpages.py hw/<board>`. The run replaces the 0.2.0 cover, adds the three pages and the text
variables, and moves a design sheet's drawing down where the heading needs the room. The title block is wider
and higher than before (it was 120 x 40 mm): move what a sheet has in its bottom right corner.

## 0.2.0 - 2026-10-26

- **Switchable fab profiles.** `fabs/*.kicad_dru` replaces `rules/`, and each board's fab is now one command away:
  `hw/fab.py` (copied into each repository) with `list`, `set`, `verify` and `check`. `set` keeps the board's own
  rules and sets the new `FAB` text variable, which the cover sheet shows. `new-board --fab` replaces `--rules`.
- **PCBWay standard is the default.** Its track and space are now 0.15 mm (6 mil), PCBWay's no-extra-cost tier, not
  the 0.1 mm manufacturing minimum. Plated hole to track is 0.35 mm, and component hole to hole is 16 mil.
- **Fix: fab rules no longer override net class clearances.** In KiCad 10 an unconditioned `clearance` rule replaces
  the net class clearance. General fab limits now go into Board Setup minimums, which act as floors. `fab.py` refuses
  profiles with `clearance` rules.
- **`fab.py check` reports rules KiCad did not load.** KiCad 10 silently ignores a rules file with a mistake in it.
- **CI:** the `hardware` workflow adds `fab.py verify` (warning) and `fab.py check` (table in the run summary). The
  self-test proves each profile finds its own limits on a fixture board. Both now run in KiCad's official Docker
  image (`kicad/kicad:10.0-full`) instead of installing from the KiCad PPA, which stalled for over 20 minutes.
- **Via presets** are 0.5/0.2 and 0.6/0.3 mm, which every profile accepts.

## 0.1.0 - 2026-10-25

First version.

- Starter board template for KiCad 10: text variables, BOM field templates, plot settings for kicad-fab-package,
  net classes, JLCPCB 1-2 layer rules, cover sheet and a drawing sheet with a logo cell.
- Fab rules for JLCPCB 1-2 layer, JLCPCB 4/6 layer and PCBWay standard.
- `scripts/kicad_template.py` with `init-repo` and `new-board`.
- `hardware` workflow for adopting repositories, pinned to kicad-part-importer and kicad-fab-package v0.1.0.
- Self-test on KiCad 10.0.7.
