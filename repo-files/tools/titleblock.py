#!/usr/bin/env python3
"""titleblock: draw hw/drawing-sheet.kicad_wks and copy it into every board folder.

usage: python3 hw/tools/titleblock.py [HW | SHEET.kicad_wks] [--logo PNG] [--logo-width MM] [--check]

  HW            the hw folder (default: the folder above this script's). HW/drawing-sheet.kicad_wks is the
                master; every board folder HW/<board>/ gets a copy
  SHEET.kicad_wks  one drawing sheet to write instead, with no copies
  --logo PNG    embed this image as the logo (as it is: scale it to about 800 px wide first). Without it the
                logo already in the drawing sheet is kept. A sheet that has none gets a placeholder: a box
                that says LOGO.
  --logo-width  printed width of the logo in mm (default 36; the logo box is 42 x 42)
  --check       write nothing; exit 1 if a file on disk differs from what would be written

The title block is 187 x 42 mm at the bottom right of the frame, in four rows:

    +-----------+-----------+--------------------------+----------------+
    |           | Comments  | Company                  | Variant        |
    |   logo    |           +--------------------------+----------------+
    |           |           | Board Name               | Project Name   |
    |           +-----------+------------+-------------+--------+-------+
    |           | Sheet     | File Name  | Designer    | Date   | Rev.  |
    |           | Title     |            |             |        |       |
    |           +-----------+------------+-------------+-----+--+-------+
    |           | Sheet Path             | Reviewer    |Size | Sheet    |
    +-----------+------------------------+-------------+-----+----------+

Board Name, Project Name, Company, Variant, Designer and Reviewer are project text variables (BOARD_NAME,
PROJECT_NAME, COMPANY, VARIANT, DESIGNER, REVIEWER; frontpages.py adds the missing ones to a project). Sheet
Title, Date, Revision and Comments come from each sheet's title block; the rest is KiCad's own. Each board folder
carries a copy because a project names its drawing sheet by a path beside it. schdraw.TITLE_BLOCK keeps the
corner clear on a redrawn sheet. Standard library only.
"""
import base64
import glob
import io
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- the layout, mm from the bottom right corner
X = (2.0, 43.5, 78.0, 112.5, 147.0, 189.0)        # cell edges, right to left; 147 to 189 is the logo box
Y = (2.0, 12.5, 23.0, 33.5, 44.0)                 # row edges, bottom to top
LABEL = '(font (face "Arial") (color 0 0 255 1))'                    # the name of a field, 1.5 mm
VALUE = '(font (face "Times New Roman") (color 0 0 127 1))'          # what is in it, 1.5 mm
BIG = '(font (face "Times New Roman") (size 2.5 2.5) bold (color 0 0 127 1))'
PPI = 300.0                                       # KiCad's resolution for an image that names none

HEAD = '''(kicad_wks (version 20231118) (generator "pl_editor") (generator_version "8.0")
  (setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
  (left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
  (rect (name "") (start 0 0 ltcorner) (end 0 0) (repeat 2) (incrx 2) (incry 2))
  (line (name "") (start 50 2 ltcorner) (end 50 0 ltcorner) (repeat 30) (incrx 50))
  (tbtext "1" (name "") (pos 25 1 ltcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))
  (line (name "") (start 50 2 lbcorner) (end 50 0 lbcorner) (repeat 30) (incrx 50))
  (tbtext "1" (name "") (pos 25 1 lbcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))
  (line (name "") (start 0 50 ltcorner) (end 2 50 ltcorner) (repeat 30) (incry 50))
  (tbtext "A" (name "") (pos 1 25 ltcorner) (font (size 1.3 1.3)) (justify center) (repeat 100) (incrlabel 1) (incry 50))
  (line (name "") (start 0 50 rtcorner) (end 2 50 rtcorner) (repeat 30) (incry 50))
  (tbtext "A" (name "") (pos 1 25 rtcorner) (font (size 1.3 1.3)) (justify center) (repeat 100) (incrlabel 1) (incry 50))
'''


def num(v):
    s = ('%.4f' % v).rstrip('0').rstrip('.')
    return s or '0'


def line(x0, y0, x1, y1, comment=None):
    return '  (line (name "") (start %s %s) (end %s %s)%s)\n' % (
        num(x0), num(y0), num(x1), num(y1), ' (comment "%s")' % comment if comment else '')


def text(s, x, y, font, maxlen=None):
    return '  (tbtext "%s" (name "") (pos %s %s) %s%s)\n' % (
        s, num(x), num(y), font, ' (maxlen %s)' % num(maxlen) if maxlen else '')


def field(label, value, col, row, font=VALUE, x1=None, dy=4.5):
    """A cell's label at its top left and its value under it. col, row: index of the cell's left and top edge."""
    left, top = X[col], Y[row]
    width = left - (x1 if x1 is not None else X[col - 1])
    out = text(label, left - 1.5, top - 2.0, LABEL)
    if value:
        out += text(value, left - 1.5, top - 2.0 - dy, font, maxlen=width - 2.5)
    return out


def body(bitmap):
    out = HEAD
    out += '  (rect (name "") (start %s %s) (end %s %s) (comment "Title block outline"))\n' % (
        num(X[5]), num(Y[4]), num(X[0]), num(Y[0]))
    out += line(X[4], Y[0], X[4], Y[4], 'Logo box, left of the fields')
    out += line(X[0], Y[1], X[4], Y[1])
    out += line(X[0], Y[2], X[4], Y[2])
    out += line(X[0], Y[3], X[3], Y[3])
    out += line(X[3], Y[1], X[3], Y[4])
    out += line(X[2], Y[0], X[2], Y[2])
    out += line(X[1], Y[0], X[1], Y[4])
    out += line(27.5, Y[0], 27.5, Y[1])
    out += line(19.5, Y[1], 19.5, Y[2])
    # top row: comments (two rows high), company, variant
    out += field('Comments:', '${COMMENT1}', 4, 4)
    for i, y in enumerate((34.0, 30.5, 27.0)):
        out += text('${COMMENT%d}' % (i + 2), X[4] - 1.5, y, VALUE, maxlen=X[4] - X[3] - 2.5)
    # The logo stands in the file just before the Company value.
    company = field('Company:', '${COMPANY}', 3, 4, '(font (face "Times New Roman") bold (color 0 0 127 1))',
                    x1=X[1])
    at = company.index('  (tbtext "${COMPANY}"')
    out += company[:at] + bitmap + company[at:]
    out += field('Variant:', '${VARIANT}', 1, 4)
    # second row: the two names
    out += field('Board Name:', '${BOARD_NAME}', 3, 3, BIG, x1=X[1])
    out += field('Project Name:', '${PROJECT_NAME}', 1, 3, BIG)
    # third row
    out += field('Sheet Title:', '${TITLE}', 4, 2)
    out += field('File Name:', '${FILENAME}', 3, 2)
    out += field('Designer:', '${DESIGNER}', 2, 2)
    out += field('Date:', '${ISSUE_DATE}', 1, 2, x1=19.5)
    out += text('Revision:', 18.0, Y[2] - 2.0, LABEL)
    out += text('${REVISION}', 18.0, Y[2] - 6.5, VALUE, maxlen=15.0)
    # bottom row
    out += field('Sheet Path:', '${SHEETPATH}', 4, 1, x1=X[2])
    out += field('Reviewer:', '${REVIEWER}', 2, 1)
    out += text('Size:', 42.0, Y[1] - 2.0, LABEL)
    out += text('${PAPER}', 41.0, 6.0, BIG)
    out += text('Sheet:', 26.0, Y[1] - 2.0, LABEL)
    out += text('${#}', 25.6, 6.0, BIG)
    out += text('of', 17.5, 5.5, LABEL)
    out += text('${##}', 14.0, 6.0, BIG)
    out += text('${KICAD_VERSION}', X[5] - 1.5, 3.4, '(font (size 1 1))', maxlen=X[5] - X[4] - 3.0)
    return out + ')\n'


# ---------------------------------------------------------------- the logo
def png_width(data):
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'the logo is not a PNG'
    return struct.unpack('>I', data[16:20])[0]


def bitmap_item(lines, width_px, width_mm, comment):
    """A drawing-sheet bitmap centred in the logo box. lines: the base64 text, 76 characters a line."""
    scale = width_mm / (width_px / PPI * 25.4)
    return ('  (bitmap (name "") (pos %s %s) (scale %.4f)\n    (comment "%s")\n    (data\n%s\n    )\n  )\n' % (
        num((X[4] + X[5]) / 2), num((Y[0] + Y[4]) / 2), scale, comment,
        '\n'.join('      "%s"' % ln for ln in lines)))


def placeholder():
    """What stands in the logo box until a logo is given: an outline and the word LOGO."""
    inset = 4.0
    return ('  (rect (name "") (start %s %s) (end %s %s) (comment "Placeholder logo: titleblock.py --logo PNG '
            'puts yours here"))\n' % (num(X[5] - inset), num(Y[4] - inset), num(X[4] + inset), num(Y[0] + inset))
            + '  (tbtext "LOGO" (name "") (pos %s %s) (font (size 2.5 2.5) bold) (justify center))\n'
            % (num((X[4] + X[5]) / 2), num((Y[0] + Y[4]) / 2)))


def logo_from_sheet(path, width_mm):
    """The bitmap that is in a drawing sheet already: its data as it stands, placed in the logo box. A sheet
    without one (or no sheet yet) gets the placeholder."""
    text_ = io.open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    m = re.search(r'\(bitmap \(name ""\).*?\(comment "([^"]*)"\)\s*\(data\s*(.*?)\s*\)\s*\)', text_, re.S)
    if not m:
        return placeholder()
    lines = re.findall(r'"([A-Za-z0-9+/=]+)"', m.group(2))
    width_px = png_width(base64.b64decode(''.join(lines)))
    return bitmap_item(lines, width_px, width_mm, m.group(1))


def logo_from_png(path, width_mm):
    data = open(path, 'rb').read()
    b64 = base64.b64encode(data).decode('ascii')
    lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    return bitmap_item(lines, png_width(data), width_mm, 'Logo: %s (titleblock.py)' % os.path.basename(path))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    check = '--check' in args
    if check:
        args.remove('--check')
    opts = {}
    for key in ('--logo', '--logo-width'):
        if key in args:
            i = args.index(key)
            opts[key] = args[i + 1]
            del args[i:i + 2]
    one = bool(args) and args[0].endswith('.kicad_wks')      # a single sheet: no master, no copies
    hw = os.path.dirname(os.path.abspath(args[0])) if one else \
        os.path.abspath(args[0]) if args else os.path.dirname(HERE)
    master = os.path.abspath(args[0]) if one else os.path.join(hw, 'drawing-sheet.kicad_wks')
    width_mm = float(opts.get('--logo-width', 36.0))
    bitmap = logo_from_png(opts['--logo'], width_mm) if '--logo' in opts else logo_from_sheet(master, width_mm)
    new = body(bitmap)
    paths = [master] + ([] if one else sorted(os.path.join(os.path.dirname(p), 'drawing-sheet.kicad_wks')
                                              for p in glob.glob(os.path.join(hw, '*', '*.kicad_pro'))))
    stale = 0
    for p in paths:
        old = io.open(p, encoding='utf-8', newline='').read() if os.path.exists(p) else None
        if old is not None and old.replace('\r\n', '\n') == new:     # a CR LF checkout is no difference
            print('unchanged  %s' % os.path.relpath(p, os.path.dirname(hw)))
            continue
        stale += 1
        if check:
            print('differs    %s' % os.path.relpath(p, os.path.dirname(hw)))
            continue
        with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new)
        print('written    %s' % os.path.relpath(p, os.path.dirname(hw)))
    return 1 if check and stale else 0


if __name__ == '__main__':
    sys.exit(main())
