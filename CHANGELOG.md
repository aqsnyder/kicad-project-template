# Changelog

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
