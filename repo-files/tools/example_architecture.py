"""An architecture drawing to start from: copy this file to hw/<board>/architecture/<board>_architecture.py, name it
in the board's frontpages.json ("architecture": "architecture/<board>_architecture.py") and run

    python3 hw/tools/frontpages.py hw/<board>

The drawing then takes the board's Architecture page at 1:1. archdiagram.py beside this file explains regions,
blocks, lines, the legend and the footnotes, and checks the layout on every run.

Canvas: 380 x 252 mm, its top left corner at (20, 32) mm of the A3 page. The title block covers the bottom right of
it, so nothing is drawn right of x 200 and below y 204 (KEEPOUT), and the picture is cut in two there (SPLIT).
"""
import os

from archdiagram import Diagram

W, H = 380.0, 252.0
SPLIT = (200.0, 204.0)
KEEPOUT = (SPLIT[0], SPLIT[1], W, H)
NAME = os.path.splitext(os.path.basename(__file__))[0]      # also the name of the SVG beside this file


def build():
    d = Diagram(NAME, 'Architecture', W, H, keepout=KEEPOUT)
    d.split = SPLIT
    # a region is a schematic sheet; a block is a part or a group of parts, with a reference and one fact
    d.region(40, 20, 120, 70, 'POWER')
    j1 = d.block('J1', 48, 40, 38, 'Supply input', ['J1 screw terminal', '5 V, 1 A'], note=1)
    u1 = d.block('U1', 112, 40, 40, 'Regulator', ['U1 LDO', '3.3 V, 300 mA'])
    d.line('power', [j1.R(), u1.L()], label={'s': 'VIN', 'at': 'above'})
    d.region(200, 20, 140, 70, 'MCU')
    u2 = d.block('U2', 230, 40, 46, 'Controller', ['U2 microcontroller', 'SWD on J2'])
    d.line('power', [u1.R(), u2.L()], label={'s': '+3V3', 'at': 'above'})
    d.legend(40, 110, 60)
    d.footnotes(40, 210, 150, {1: 'The supply input is not protected against reverse polarity.'})
    return d
