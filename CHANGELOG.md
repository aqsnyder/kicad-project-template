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

Upgrading a repository made from 0.2.0: copy `repo-files/hardware.yml` to `.github/workflows/`, `repo-files/fab.py`
to `hw/`, and `fabs/*.kicad_dru` to `hw/fabs/`, then run `python3 hw/fab.py set <profile> <board>` for each board so
its rules match the profile again. A profile of your own needs a `# copper-layers:` line, or `fab.py` refuses it.

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
