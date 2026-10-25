# kicad-project-template

**A KiCad 10 starting point for boards built with
[kicad-part-importer](https://github.com/aqsnyder/kicad-part-importer) and
[kicad-fab-package](https://github.com/aqsnyder/kicad-fab-package).**

It is unbranded on purpose. Each project copies it once and brands its own copy; nothing links the
projects together afterwards. The parts that must stay the same everywhere live in the two tools, which every
repository pins to a release.

- [What is in it](#what-is-in-it)
- [Set up a repository](#set-up-a-repository)
- [Add a board](#add-a-board)
- [Make it yours](#make-it-yours)
- [Fab rules](#fab-rules)
- [Parts](#parts)
- [Fab packages](#fab-packages)
- [CI](#ci)
- [Known gaps](#known-gaps)

## What is in it

| Path | What |
|---|---|
| `templates/starter-board/` | The KiCad project template: project, schematic, board, fab rules, drawing sheet, library tables |
| `rules/` | Fab design rules: JLCPCB 1-2 layer, JLCPCB 4/6 layer, PCBWay standard |
| `repo-files/` | Repository-level files: `kicad-fab.toml`, pinned tool requirements, the `hardware` workflow, a `.gitignore` block |
| `scripts/kicad_template.py` | `init-repo` and `new-board`, so a person or an agent can do the setup from a terminal |
| `.github/workflows/self-test.yml` | Builds a demo repository from the template and runs KiCad 10 and both tools on it |

What the starter board is set up with:

- **Text variables** `BOARD_NAME`, `COMPANY`, `DESIGNER`, `REVISION` and `RELEASE_DATE` (*Schematic Setup > Text
  Variables*). The title blocks show them, and `REVISION` is the one kicad-fab-package names its outputs after. The
  board file carries them too.
- **Symbol field templates** `MPN`, `Manufacturer`, `LCSC`, `Voltage`, `Tolerance`, `Type` and `TempCo`.
  kicad-macrofab-bom needs `MPN` and `Manufacturer` on every fitted part; `LCSC` is for JLCPCB assembly; the other
  four are kicad-bom-check's grouped BOM fields.
- **Plot settings** that kicad-fab-export checks: absolute origin, no X2 or netlist attributes, no Protel
  extensions, all copper plus mask, paste, silkscreen and Edge.Cuts.
- **Fab rules** for JLCPCB 1-2 layer in `<project>.kicad_dru`.
- **Net classes** Default (0.2 mm track and clearance, 0.6/0.3 mm via) and Power (0.4 mm; nets `+*`, `GND*`,
  `VBAT*`, `VBUS*`, `VIN*`). Via sizes 0.45/0.2 and 0.6/0.3 mm.
- **Board setup minimums** kept low, so the `.kicad_dru` file decides what the fab can make.
- **Silkscreen defaults** of 1.0 mm text with 0.15 mm strokes.
- **A cover sheet** with overview, sheet list, revision history and ordering notes, and a 50 x 50 mm outline.
- **A drawing sheet** (`drawing-sheet.kicad_wks`) with a logo cell, company, designer, title, size, date, revision,
  sheet number and file name.

## Set up a repository

The layout it sets up:

```text
kicad-fab.toml                     kicad-fab-package settings
.github/workflows/hardware.yml     library check, ERC and DRC on every push; fab packages on tags
hw/
  requirements-tools.txt           both tools, pinned to a release
  drawing-sheet.kicad_wks          the repository's drawing sheet: brand it once
  rules/                           the fab rules files
  lib/                             part library (kicad-part-importer), reached as ${KIPRJMOD}/../lib
  <board>/                         one KiCad project per board
```

From the repository's top folder:

```bash
git clone https://github.com/aqsnyder/kicad-project-template ~/src/kicad-project-template
pip install -r ~/src/kicad-project-template/repo-files/requirements-tools.txt
python3 ~/src/kicad-project-template/scripts/kicad_template.py init-repo . --prefix acme_
```

`--prefix` names the part library's category libraries (`acme_passives`, `acme_sensors`, ...). `init-repo` keeps any file
that already exists (`--force` replaces them) and adds the `.gitignore` block once. Without kicad-part-importer
installed it prints the `--init` command to run instead of creating `hw/lib`.

## Add a board

```bash
python3 ~/src/kicad-project-template/scripts/kicad_template.py new-board hw/main-board \
    --title "Main board" --company "Acme" --revision 0.1
```

The folder name becomes the project name (`hw/main-board/main-board.kicad_pro`), so kicad-fab-package names the
outputs `main-board_v0.1`. `new-board` sets `RELEASE_DATE` to today, `DESIGNER` to your `git config user.name` unless you pass
`--designer`, copies `hw/drawing-sheet.kicad_wks` into the board, and lists every category library of `hw/lib` in the
board's `sym-lib-table` and `fp-lib-table`. `--rules pcbway-standard` starts the board with another rules file.

**From KiCad instead:** set `KICAD_USER_TEMPLATE_DIR` to this repository's `templates` folder (*Preferences >
Configure Paths*), then *File > New Project from Template > User Templates > Starter board*, and create the project
in `hw/<board>/`. This route leaves the text variables at the template's values and the library tables empty. Set the
variables in *Schematic Setup > Text Variables*, copy `hw/drawing-sheet.kicad_wks` over the board's copy, and add the
libraries with:

```bash
kicad-part-importer --library hw/lib --project-dir hw/<board> --add-to-project
```

## Make it yours

**Brand the drawing sheet once per repository.** Open `hw/drawing-sheet.kicad_wks` in KiCad's Drawing Sheet Editor,
delete the `LOGO` rectangle and text, add your logo with the editor's bitmap tool, and save. New boards copy this file. To
update boards that already exist:

```bash
for pro in hw/*/*.kicad_pro; do cp hw/drawing-sheet.kicad_wks "$(dirname "$pro")/"; done
```

**Set the company** with `--company` on `new-board`, or change `COMPANY` in an existing board's text variables.

**For an organization with many repositories,** make a branded copy of this repository (GitHub's *Use this
template*, or a plain copy): put the logo in `templates/starter-board/drawing-sheet.kicad_wks`, set `COMPANY` in
`templates/starter-board/starter-board.kicad_pro` (and the matching `COMPANY` property in the `.kicad_pcb`), and
change the default `starter-board.kicad_dru` if your boards go elsewhere. The self-test keeps working in the copy.

## Fab rules

| File | For | Notes |
|---|---|---|
| `jlcpcb-2layer.kicad_dru` | JLCPCB 1-2 layer, 1 oz | Template default. Vias 0.2/0.45 mm and up (no surcharge) |
| `jlcpcb-multilayer.kicad_dru` | JLCPCB 4 and 6 layer, 1 oz | 0.09 mm track and space; inner-layer hole clearance |
| `pcbway-standard.kicad_dru` | PCBWay standard service | Holes 0.2 mm and up (no surcharge); 0.25 mm edge clearance |

KiCad reads only `<project>.kicad_dru` beside the `.kicad_pro`, so switching is a copy:

```bash
cp hw/rules/pcbway-standard.kicad_dru hw/main-board/main-board.kicad_dru
```

Each file names its source page and the date the numbers were checked (2026-10-25). Fab houses change their limits;
check the page before a tight design.

## Parts

Add parts from inside the library, exactly as the
[kicad-part-importer docs](https://github.com/aqsnyder/kicad-part-importer/blob/main/docs/getting-started.md)
describe:

```bash
cd hw/lib
kicad-part-importer ~/Downloads/LIB_PART.zip --category sensors --link-3d --dry-run
kicad-part-importer ~/Downloads/LIB_PART.zip --category sensors --link-3d --yes
kicad-part-importer --check-3d
```

Model paths come out as `${KIPRJMOD}/../lib/3d_models/<file>`, which resolves from every `hw/<board>/` folder.
`init-repo` puts a `.gitkeep` in each empty category folder, because git does not keep empty folders and KiCad
expects every listed `.pretty` folder to exist.

## Fab packages

Each board has its own folder, so name it with `--project-dir`:

```bash
kicad-macrofab-bom HEAD --project-dir hw/main-board --out ../fab/main-board/bom
kicad-fab-export   HEAD --project-dir hw/main-board --out ../fab/main-board
```

The `hardware` workflow does this for every board when you push a tag, and attaches the packages to the run.
kicad-fab-package's BOM, placement file and upload zip are in MacroFab's format. The Gerbers and drill files in
`fab/` suit any board house, so a bare-board order at JLCPCB or PCBWay works from them today; their assembly BOM and
placement files do not exist yet (see [Known gaps](#known-gaps)).

## CI

`hardware.yml` (in each adopting repository):

- **library**: `kicad-part-importer --check-3d` on `hw/lib`. No KiCad needed.
- **boards**: KiCad 10 from the KiCad PPA, then ERC and DRC (with schematic parity) on every `hw/*/` project. Errors
  fail the run; warnings are printed. On a tag, also the fab package of every board, uploaded as an artifact.

`self-test.yml` (this repository): makes a demo repository with `init-repo` and `new-board`, then runs the library
check, ERC, DRC, kicad-macrofab-bom and kicad-fab-export on it with KiCad 10, renders the schematic and checks that
the drawing sheet loads and the text variables resolve. It also warns when KiCad would rewrite the template files,
which means they should be re-saved in the current KiCad.

## Known gaps

All four are in kicad-fab-package 0.1.0 and show up in the self-test:

- **Drawing sheet in the fab package.** The tool's project copy takes `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`,
  `.kicad_dru` and the library tables, not `.kicad_wks`. The package's schematic PDF therefore uses KiCad's default
  title block (the text variables still fill it in).
- **Library 3D models in the STEP.** The tool adds a library only when it is a git submodule inside the board
  folder (`library_dir`). `hw/lib` is a plain folder beside the boards, so the package's STEP has no bodies for
  library parts. The Gerbers, drills, BOM and placement files are not affected.
- **An empty board fails one check** ("XYRS vs KiCad pos: same frame on the 0 parts ..."). It passes once the board
  has a placed part. The self-test allows exactly this failure on the starter board.
- **No JLCPCB or PCBWay assembly files.** Their BOM (`Comment, Designator, Footprint, LCSC Part #`) and placement
  file (`Designator, Mid X, Mid Y, Layer, Rotation`, in mm) are not produced.

## License

MIT; see [LICENSE](LICENSE).
