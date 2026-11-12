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
- [Colours](#colours)
- [Front pages](#front-pages)
- [Fabs](#fabs)
- [Parts](#parts)
- [Fab packages](#fab-packages)
- [CI](#ci)
- [Known gaps](#known-gaps)

## What is in it

| Path | What |
|---|---|
| `templates/starter-board/` | The KiCad project template: project, schematic with its front pages, board, fab rules, drawing sheet, library tables |
| `fabs/` | Fab profiles: PCBWay standard, JLCPCB 1-2 layer, JLCPCB 4-6 layer |
| `themes/` | KiCad colour themes: `Altium_Theme`, an Altium-style look for the schematic and board editors |
| `repo-files/` | Repository-level files: `fab.py`, `theme.py`, the front-page scripts in `tools/`, `kicad-fab.toml`, pinned tool requirements, the `hardware` workflow, a `.gitignore` block |
| `scripts/kicad_template.py` | `init-repo` and `new-board`, so a person or an agent can do the setup from a terminal |
| `tests/` | The self-test's fab fixture: 2- and 4-layer boards with known violations, and what each fab must find. Also the net class check |
| `.github/workflows/self-test.yml` | Builds demo repositories from the template and runs KiCad 10, both tools and `fab.py` on them |

What the starter board is set up with:

- **Text variables** `BOARD_NAME`, `PROJECT_NAME`, `COMPANY`, `DESIGNER`, `REVIEWER`, `REVISION`, `RELEASE_DATE`
  and `FAB` (*Schematic Setup > Text Variables*). The title blocks and the front pages show them, and `REVISION`
  is the one kicad-fab-package names its outputs after. The board file carries all but `PROJECT_NAME` and
  `REVIEWER` too.
- **Symbol field templates** `MPN`, `Manufacturer`, `LCSC`, `Voltage`, `Tolerance`, `Type` and `TempCo`.
  kicad-macrofab-bom needs `MPN` and `Manufacturer` on every fitted part; `LCSC` is for JLCPCB assembly; the other
  four are kicad-bom-check's grouped BOM fields.
- **Plot settings** that kicad-fab-export checks: absolute origin, no X2 or netlist attributes, no Protel
  extensions, all copper plus mask, paste, silkscreen and Edge.Cuts.
- **The PCBWay standard fab profile** (see [Fabs](#fabs)).
- **Net classes** Default (0.2 mm track and clearance, 0.6/0.3 mm via), Power (0.4 mm; nets `+*`, `VBAT*`, `VBUS*`,
  `VIN*`) and GND (0.4 mm; nets `GND*`), plus seven classes that only colour their nets (see [Colours](#colours)).
  Via sizes 0.5/0.2 and 0.6/0.3 mm, which every profile accepts.
- **Silkscreen defaults** of 1.0 mm text with 0.15 mm strokes.
- **Four front pages** drawn by a script (see [Front pages](#front-pages)): a cover with a contents table and two
  views of the board, Architecture, Mechanical and Revision History. The board is a 50 x 50 mm outline.
- **A drawing sheet** (`drawing-sheet.kicad_wks`) with a title block of 187 x 42 mm: a logo box, comments,
  company, variant, board and project name, sheet title, file name, designer, date, revision, sheet path,
  reviewer, size and sheet number.

## Set up a repository

The layout it sets up:

```text
kicad-fab.toml                     kicad-fab-package settings
.github/workflows/hardware.yml     library check, ERC, DRC and the fab check on every push; fab packages on hw-v* tags
hw/
  requirements-tools.txt           both tools, pinned to a release
  drawing-sheet.kicad_wks          the repository's drawing sheet: brand it once
  fab.py                           switches a board's fab, and checks which fabs can make it
  fabs/                            fab profiles, one .kicad_dru file per fab
  theme.py                         installs the colour themes into KiCad's settings folder
  themes/                          colour themes, one .json file per theme
  tools/                           frontpages.py and titleblock.py, which draw the front pages and the title block
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
    --title "Main board" --project "Acme sensor" --company "Acme" --revision 0.1
```

The folder name becomes the project name (`hw/main-board/main-board.kicad_pro`), so kicad-fab-package names the
outputs `main-board_v0.1`. `new-board` sets `RELEASE_DATE` to today, `DESIGNER` to your `git config user.name` unless you pass
`--designer`, copies `hw/drawing-sheet.kicad_wks` into the board, and lists every category library of `hw/lib` in the
board's `sym-lib-table` and `fp-lib-table`. The board starts on PCBWay; `--fab jlcpcb-2layer` starts it on another
fab. It also draws the schematic's [front pages](#front-pages) for the new board. The two board views on the
cover need KiCad's `kicad-cli`; without it the cover says how to get them later.

**From KiCad instead:** set `KICAD_USER_TEMPLATE_DIR` to this repository's `templates` folder (*Preferences >
Configure Paths*), then *File > New Project from Template > User Templates > Starter board*, and create the project
in `hw/<board>/`. This route leaves the text variables at the template's values and the library tables empty. Set the
variables in *Schematic Setup > Text Variables*, copy `hw/drawing-sheet.kicad_wks` over the board's copy, close the
project, and add the libraries, the fab and the front pages under the new name with:

```bash
kicad-part-importer --library hw/lib --project-dir hw/<board> --add-to-project
python3 hw/fab.py set pcbway-standard <board>
python3 hw/tools/frontpages.py hw/<board>
```

## Make it yours

**Brand the title block once per repository.** Give the script your logo as a PNG, about 800 px wide:

```bash
python3 hw/tools/titleblock.py hw --logo logo.png
```

It puts the logo into `hw/drawing-sheet.kicad_wks` in place of the `LOGO` box and copies the sheet into every
board folder; new boards copy that file. Later runs keep the logo, so `--logo` is needed once. The script draws
the whole sheet: to change the title block, change `titleblock.py`, not the sheet in the Drawing Sheet Editor.

**Set the company** with `--company` on `new-board`, or change `COMPANY` in an existing board's text variables.

**For an organization with many repositories,** make a branded copy of this repository (GitHub's *Use this
template*, or a plain copy): put the logo in the template's drawing sheet
(`python3 repo-files/tools/titleblock.py templates/starter-board/drawing-sheet.kicad_wks --logo logo.png`), set
`COMPANY` and `PROJECT_NAME` in `templates/starter-board/starter-board.kicad_pro` (and the matching `COMPANY`
property in the `.kicad_pcb`), and change `DEFAULT_FAB` in `scripts/kicad_template.py` if your boards usually go
elsewhere (then run `python3 repo-files/fab.py set <profile> templates/starter-board`). The self-test keeps working
in the copy.

## Colours

The Altium-style look has two parts. The **net class colours** are in each board's project file, so everyone who
opens the board sees them. The **colour theme** is a KiCad preference, so each machine installs it once.

### The theme

`hw/themes/Altium_Theme.json` is KiCad's default theme with the schematic editor's colours changed: wires, pins,
junctions, sheet symbols and the drawing sheet are black, references and values blue, and local labels dark red.
Symbols keep their dark red outlines on pale yellow bodies, the sheet stays cream, and the board editor keeps
KiCad's default colours. KiCad reads themes from the user's settings folder only, never from a project, so copy it
there:

```bash
python3 hw/theme.py install
```

Then restart KiCad and choose **Altium_Theme** under *Preferences > Preferences > Schematic Editor > Colors*, and
again under *PCB Editor > Colors*.

| System | Where `install` puts it |
|---|---|
| Windows | `%APPDATA%\kicad\10.0\colors` |
| Linux | `~/.config/kicad/10.0/colors` (`$XDG_CONFIG_HOME/kicad/10.0/colors` when that is set) |
| macOS | `~/Library/Preferences/kicad/10.0/colors` |

- **`python3 hw/theme.py list`** shows whether this machine has the theme.
- **Your own edits are kept.** When the installed copy has other colours, `install` leaves it alone and exits with
  status 1. `install --force` replaces it and keeps the old file beside it as `Altium_Theme.json.bak`.
- **Other setups:** `--kicad-version 11.0` for another KiCad version, `--config-dir DIR` for a Flatpak or portable
  KiCad (the folder that holds `colors`). `KICAD_CONFIG_HOME` is honoured as KiCad honours it.
- **Without an adopting repository** (a project made with *New Project from Template*): run
  `python3 repo-files/theme.py install` in a clone of this repository.
- **To add or change a theme,** put its `.json` file in `hw/themes/`. The file name is the theme's name.

**kicad-cli takes the theme by name** on its export commands:

```bash
kicad-cli sch export pdf --theme Altium_Theme -o main-board.pdf hw/main-board/main-board.kicad_sch
```

`sch export svg`, `pcb export pdf` and `pcb export svg` take `--theme` the same way. kicad-cli does not report a
theme it cannot find: it plots in KiCad's default colours. On a CI machine, install the theme first with
`python3 hw/theme.py install --create`, which also makes the settings folder when KiCad has not run there yet.

kicad-fab-package 0.1.0 always plots its schematic PDF in KiCad's built-in default theme. That PDF shows the net
class colours, which come from the project, but not the theme.

### Net classes

Wires and labels take their net class's colour and are drawn 10 mil wide; nets in no class stay at 6 mil in the
theme's wire colour. The Architecture page has the key, NET COLOURS.

| Class | Colour | Nets, by name | Sets |
|---|---|---|---|
| `Power` | red, `rgb(194, 0, 0)` | `+*`, `VBAT*`, `VBUS*`, `VIN*` | 0.4 mm track, 0.2 mm clearance, 0.6/0.3 mm via |
| `RF_50R` | magenta, `rgb(194, 0, 194)` | names with `RF_50R` | colour only, until you give it your stackup's 50 Ω width |
| `GND` | green, `rgb(0, 132, 0)` | `GND*` | the same rules as `Power` |
| `Debug` | olive, `rgb(132, 132, 0)` | names with `SWD`, `SWCLK`, `JTAG` or `NRST`, or ending in `SWO` | colour only |
| `UART` | purple, `rgb(132, 0, 132)` | names with `UART` or `USART` | colour only |
| `Bus` | navy, `rgb(0, 0, 132)`; on the board `rgb(70, 130, 255)` | names with `I2C`, `SCL`, `SDA`, `SPI`, `MOSI`, `MISO` or `GPIO` | colour only |
| `Clock` | grey, `rgb(132, 132, 132)` | names with `CLK`, `XTAL` or `OSC` | colour only |
| `Analog` | orange, `rgb(204, 102, 0)` | names with `ADC`, `VREF` or `SENSE` | colour only |
| `USB` | cyan, `rgb(0, 194, 194)` | names with `USB` | colour only |

**A net gets its class from its name.** The patterns are in *File > Schematic Setup > Net Classes* (the board
editor's *Board Setup > Net Classes* shows the same list). To put other nets in a class, add a pattern there,
right-click a wire and choose *Assign Netclass*, or place a net class directive on the wire. A pattern is matched
against the whole net name and is case sensitive. A local label's net name starts with its sheet path
(`/MCU/I2C_SCL`), which is why the colour patterns begin with `*`; a sheet called `USB` therefore colours all of
its local nets cyan. `AGND` and `PGND` are not in `GND`: add `AGND*` there if they should be.

**The colour classes cannot change a net's rules.** They set no track width, clearance or via size, so their nets
keep the `Default` class's values and follow them when you change `Default`. KiCad names such a net's class
"Bus and Default"; a custom rule with `A.NetClass == 'Bus'` still matches it.

**A net that matches several classes** takes each property from the class highest in the table that sets it (the
lowest `priority` number in the project file; the order of the list in *Schematic Setup*). `Power`, `RF_50R` and
`GND` come first, so a class with rules also gives the colour: `VBAT_SENSE` is `Power` in rules and colour. Below
them the more specific names win: `USB_UART_TX` is `UART`, `SPI_CLK` is `Bus`, `ADC_CLK` is `Clock`.

**On the board,** KiCad draws ratsnest lines in the net class colour by default. *Appearance > Nets > Net Display
Options > Net colors* switches between *All* (tracks, pads and zones too), *Ratsnest* and *None* (layer colours
only). A class has the same colour on the board as on the schematic, except `Bus`: navy does not show on the
board editor's dark background, so its board colour is a lighter blue.

**When you change the classes,** run `python3 hw/tools/frontpages.py hw/<board>`: the NET COLOURS key on the
Architecture page is drawn from the project file. What a class is for comes from `"net_colours"` in the board's
`frontpages.json` (`{"Bus": "I2C, SPI and GPIO"}`); a class without words there shows its name patterns.
`tests/check_netclasses.py` holds this repository's copy together: the table above, the key, and what KiCad
itself makes of some forty sample net names, in the project settings and in a plot made with the theme.

## Front pages

Every schematic opens and closes the same way. `hw/tools/frontpages.py` draws these pages and the heading of every
other sheet; nobody draws them by hand.

| Page | Paper | What is on it |
|---|---|---|
| Cover | A3 | The board's name, variant, today's date and the revision; a contents table of 40 rows filled from the sheets, each row a link; TOP VIEW and BOTTOM VIEW, rendered from the board; NOTES with the status key (DRAFT, PRELIMINARY, CHECKED, RELEASED) and the release date; DESIGN CONSIDERATIONS, the key to the five colours of boxed notes |
| Architecture | A3 | The architecture drawing at 1:1. Until a board has one: a frame that says so, the sheets (drawn and planned), the net colour key and the overview |
| The design sheets | A3 or A4 | A "[page] Title" heading at the top centre; the drawing starts below it |
| Mechanical | A4 | The outline at scale with its overall dimensions, mounting holes and connectors read from the board file; the ordering notes; the stackup; a table of positions |
| Revision History | A4 | A table, oldest first; the overview under it once a drawing has the Architecture page |

What the pages say is in `hw/<board>/frontpages.json`: the cover's comment and status, the overview, the sheets
that are planned, the ordering notes and the revisions. `frontpages.py`'s own text lists every key. Edit the file,
close the project in KiCad, then run:

```bash
python3 hw/tools/frontpages.py hw/main-board
```

Run it again after the board changes (the views and the Mechanical page are read from it), after a sheet is added
or reordered (pages, contents table and headings follow), and after `frontpages.json` or the net classes change.

- **`--check`** writes nothing and exits 1 if a run would change a file. **`--no-render`** leaves the board views
  as they are and needs no KiCad. Before a commit or in CI use both, naming the board folders:
  `python3 hw/tools/frontpages.py hw/main-board --check --no-render`. Without `--no-render` the check renders the
  two views and compares the pictures byte for byte, which holds on one machine but need not between two.
- **What you add stays.** The script removes and redraws only what it drew itself (its items carry a uuid that
  starts with `f407a9e5`), so a text or picture added to one of these pages in KiCad is kept. Saving a sheet in
  KiCad does not make `--check` fail.
- **Adding a design sheet.** Add a hierarchical sheet on the cover in KiCad, draw on it, and run the script. It
  parks the sheet symbols left of the page frame, numbers the pages, sets each sheet's title to its name and adds
  the heading. It changes no symbol, wire or label. Start a sheet's drawing below the heading (y 27.94 mm on A4,
  35.56 mm on A3) and keep out of the title block's 189 x 44 mm at the bottom right.
- **Boxed notes.** The cover's DESIGN CONSIDERATIONS row is the key: grey for information, orange for bring-up,
  yellow for caution, red for critical, blue for layout. To box a note of a design sheet, name it in
  `frontpages.json` by the sheet's name and the note's first words: `"callouts": {"Power": {"J1: external
  supply": "critical"}}`. The next run draws a box of that kind around the note, where it stands.
- **Text variables.** The pages and the title block show `BOARD_NAME`, `PROJECT_NAME`, `COMPANY`, `DESIGNER`,
  `REVIEWER`, `REVISION`, `RELEASE_DATE` and `FAB` (*File > Schematic Setup > Text Variables*). `VARIANT` is a
  variable of KiCad 10's own, which wins over the project's: the cover and the title block show it empty.
- **Fonts.** The pages name Times New Roman and Arial. A machine without them substitutes its own.

**The title block** (`hw/drawing-sheet.kicad_wks`, and a copy in each board folder) is drawn by
`hw/tools/titleblock.py`: Comments, Company, Variant, Board Name, Project Name, Sheet Title, File Name, Designer,
Date, Revision, Sheet Path, Reviewer, Size and Sheet, with the logo in a box on the left
([Make it yours](#make-it-yours)).

**An architecture drawing** is a block diagram generated from a description, a Python file in
`hw/<board>/architecture/`: regions, blocks and lines placed in millimetres. `hw/tools/archdiagram.py` measures
the text, draws arrowheads, labels and the legend in the net class colours, and checks the layout.
`hw/tools/example_architecture.py` is a drawing to start from; its first lines say how. `frontpages.py` renders the
description and embeds the picture again whenever it changes. That step turns the SVG into PNGs with headless Edge
or Chrome, and the text is measured with Arial Narrow or Liberation Sans Narrow; nothing else needs either. The
starter board has no drawing.

The self-test checks that the starter board's pages and title block are what the scripts draw, that `new-board`
draws them for a new board with its two views, and that KiCad's own save of every sheet leaves them unchanged.

## Fabs

Each board has a fab, and switching it is one command. Close the board in KiCad first, because KiCad rewrites the
project file when it saves:

```bash
python3 hw/fab.py list                              # profiles, and each board's fab
python3 hw/fab.py set jlcpcb-2layer main-board      # one board (a name in hw/, or a folder)
python3 hw/fab.py set pcbway-standard --all         # every board
python3 hw/fab.py check --all                       # which fabs can make each board (needs KiCad 10)
```

| Profile | Fab | Copper layers | Main limits (no extra charge) |
|---|---|---|---|
| `pcbway-standard` | PCBWay standard | 1-6 | Template default. 0.15 mm track and space; 0.2 mm holes, 0.5 mm vias; 0.25 mm to the edge |
| `jlcpcb-2layer` | JLCPCB 1-2 layer | 1-2 | 0.1 mm track and space; 0.2 mm holes, 0.45 mm vias; 0.18 mm pad rings; 0.5 mm NPTH |
| `jlcpcb-multilayer` | JLCPCB 4-6 layer | 4-6 | 0.09 mm track and space; 0.2 mm holes, 0.45 mm vias; 0.3 mm inner hole clearance |

**What `set` does:**

- **Writes the profile's minimums into Board Setup > Constraints.** These are floors: net classes above them still
  apply.
- **Writes the profile's rules into `<project>.kicad_dru`,** above a `# ==== Board rules ====` line. Anything you
  put below that line, in a text editor or in KiCad's *Board Setup > Custom Rules*, belongs to the board: it is kept
  on every switch, and it wins over the fab rules when both match.
- **Sets the `FAB` text variable,** which the cover sheet shows.

**What `check` shows:** `check` runs KiCad's DRC on a temporary copy of each board once per profile, without
touching the board, and lists the errors under each fab. Errors that show under every fab are design errors, not fab
limits. A fab whose `copper-layers` range leaves out the board's copper layer count shows `n/a (4 layers)` and gets
no DRC. `check` covers DRC geometry and layer count only: `ok` says nothing about the board's thickness, copper
weight or stackup, so compare those with the fab's page. `set` prints a note when the new fab does not cover the
board's layer count. The `hardware` workflow puts this table in every run's summary and warns when a board's fab
settings drift from its profile (`fab.py verify`).

**A mistake in a rules file turns off all of its rules, silently.** KiCad 10 skips a `.kicad_dru` it cannot read,
including the fab rules above the board rules, and its DRC still passes. `check` guards against this: it adds a
canary rule and item to each scratch copy, prints `RULES NOT LOADED` when the canary does not fire, and exits 1, so
the `hardware` workflow fails. `fab.py` also checks parentheses and quotes when it loads a profile or sets a fab.

**Adding a fab** means adding one file. Copy a profile in `hw/fabs/`, rename it (the name is the profile id), and edit
it:

```text
(version 1)
# fab-profile: acme-proto                  <- must match the file name
# fab-name: Acme Proto 2-layer             <- what FAB and the cover sheet show
# copper-layers: 1-2                       <- copper layer counts it makes (required); check shows n/a outside it
# board-setup: min_clearance 0.127         <- Board Setup > Constraints, in mm
# board-setup: min_track_width 0.127
# ...
(rule "Acme: NPTH hole size"               <- KiCad custom rules for everything else
	(constraint hole_size (min 0.5mm))
	(condition "A.Pad_Type == 'NPTH, mechanical'"))
```

The keys `board-setup` accepts are the Board Setup names in the `.kicad_pro`: `min_clearance`, `min_track_width`,
`min_connection`, `min_via_diameter`, `min_via_annular_width`, `min_through_hole_diameter`, `min_hole_clearance`,
`min_hole_to_hole`, `min_copper_edge_clearance`, `min_microvia_diameter`, `min_microvia_drill`, `min_silk_clearance`,
`min_text_height` and `min_text_thickness`.

**Why general clearance is not a custom rule.** In KiCad 10 a matching `clearance` rule in `.kicad_dru` *replaces*
the net class clearance instead of adding to it. A fab rule of 0.1 mm would let a 0.2 mm net class route at 0.1 mm,
and DRC would not complain. Board Setup minimums are floors instead, so profiles put fab clearances there. `fab.py`
refuses a profile with a `clearance` rule, and the self-test proves the net class still holds under every profile.

Each profile lists its sources and the date its numbers were checked (2026-10-26). Fabs change their limits, so check
their pages before a tight design.

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

The `hardware` workflow does this for every board when you push a hardware tag (`hw-v0.1`, `hw-v1.0-rc1`, ...), and
attaches the packages to the run as `fab-<tag>`. To use other tag names, change `tags: ["hw-v*"]` in `hardware.yml`.
Path filters do not apply to tags, so `**` would build packages for every tag, firmware and software tags included.
Keep `/` out of hardware tags: artifact names cannot contain one.

kicad-fab-package's BOM, placement file and upload zip are in MacroFab's format. The Gerbers and drill files in
`fab/` suit any board house, so a bare-board order at JLCPCB or PCBWay works from them today; their assembly BOM and
placement files do not exist yet (see [Known gaps](#known-gaps)).

## CI

`hardware.yml` (in each adopting repository):

- **library**: `kicad-part-importer --check-3d` on `hw/lib`. No KiCad needed.
- **boards**: runs in KiCad's official Docker image (`kicad/kicad:10.0-full`), then ERC and DRC (with schematic parity) on every `hw/*/` project, each
  with its own fab's rules. Errors fail the run; warnings are printed. Then `fab.py verify` (a warning on drift) and
  `fab.py check` (the table of fabs, in the run summary). On a `hw-v*` tag, also the fab package of every board,
  uploaded as an artifact. A board whose package fails does not stop the others: the step fails at the end, and the
  packages that were made are still uploaded. The job runs as root while the checkout belongs to the runner user, so
  it marks the checkout as a git `safe.directory`; without that, git refuses the checkout and both fab tools fail.

`self-test.yml` (this repository): makes a demo repository with `init-repo` and `new-board`, then runs the library
check, ERC, DRC, kicad-macrofab-bom and kicad-fab-export on it with KiCad 10, renders the schematic and checks that
the drawing sheet loads and the text variables resolve. It runs both fab tools in its own checkout as well, which, as
in an adopting repository, belongs to the runner user rather than root, so the `safe.directory` line is tested. It
also builds 2- and 4-layer fixture boards with known violations (`tests/make_fixture.py`), switches one between fabs
and back with a board rule in place, and checks that each profile finds exactly its own limits plus the net class
error, and shows `n/a` on the layer count it does not cover (`tests/check_fixture.py`). It runs in the same KiCad
image as the `hardware` workflow, and warns when KiCad would rewrite the template files, which means they should be
re-saved in the current KiCad.

## Known gaps

All five are in kicad-fab-package 0.1.0. The self-test shows the drawing sheet and the empty board; the others need
a board with library parts, a round outline or an assembly order.

- **Drawing sheet in the fab package.** The tool's project copy takes `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`,
  `.kicad_dru` and the library tables, not `.kicad_wks`. The package's schematic PDF therefore uses KiCad's default
  title block (the text variables still fill it in).
- **Library 3D models fail the package.** The tool adds a library only when it is a git submodule inside the board
  folder (`library_dir`). `hw/lib` is a plain folder beside the boards, so the package's STEP has no bodies for
  library parts. Once a board has a placed part whose model is in `hw/lib`, kicad-fab-export fails its error-level
  check "STEP: every placed part with a model entry gets a model": it still writes the package but exits 1, so the
  `hardware` workflow's fab package step fails on every hardware tag (the other boards still package, and the
  upload still runs). The Gerbers, drills, BOM and placement files themselves are not affected.
- **A round outline fails a check.** A board outline drawn as one `gr_circle` on Edge.Cuts fails "STEP: origin =
  XYRS corner". Draw the circle as four quarter arcs instead.
- **An empty board fails one check** ("XYRS vs KiCad pos: same frame on the 0 parts ..."). It passes once the board
  has a placed part. The self-test allows exactly this failure on the starter board.
- **No JLCPCB or PCBWay assembly files.** The tool writes MacroFab's BOM and placement formats only. JLCPCB's BOM
  has `Comment, Designator, Footprint, LCSC Part #` and its placement file `Designator, Mid X, Mid Y, Layer,
  Rotation`, in mm. PCBWay's [BOM template](https://www.pcbway.com/img/images/pcbway/Sample_BOM_PCBWay.xlsx) has
  `Item #, *Designator, *Qty, Manufacturer, *Mfg Part #, Description / Value, *Package/Footprint, Type, Your
  Instructions / Notes`, and its centroid file is one per side, in mm, with the origin at the board's lower-left
  corner seen from the top.

## License

MIT; see [LICENSE](LICENSE).
