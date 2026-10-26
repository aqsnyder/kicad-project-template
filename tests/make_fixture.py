"""Add known fab-limit violations to a board made from the template, for the self-test.

usage: python3 tests/make_fixture.py BOARD_DIR      (a python that imports pcbnew, i.e. KiCad's)

The board keeps the template's net classes (Default clearance 0.2 mm). Added:
  A/B   two 0.2 mm tracks 0.17 mm apart        -> net class clearance error under every fab
  C     a 0.12 mm track                        -> below PCBWay's 0.15 mm, fine for JLCPCB
  D     a track 0.22 mm from the board edge    -> below PCBWay's 0.25 mm, fine for JLCPCB
  E     a 0.15 mm via, 0.45 mm across          -> hole below every profile's 0.2 mm; diameter below PCBWay's 0.5 mm
  FIX1  a plated pad, 0.8 mm hole, 1.1 mm      -> 0.15 mm ring: below JLCPCB 1-2 layer's 0.18 mm only
        a 0.4 mm NPTH hole                     -> below JLCPCB's 0.5 mm NPTH minimum only
"""
import glob
import os
import sys

import pcbnew


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def call(obj, method, value):
    """KiCad 9+ padstack setters take a layer first; older ones do not."""
    f = getattr(obj, method)
    try:
        return f(value)
    except TypeError:
        return f(pcbnew.F_Cu, value)


def main():
    d = sys.argv[1]
    pcb = glob.glob(os.path.join(d, '*.kicad_pcb'))[0]
    b = pcbnew.LoadBoard(pcb)
    nets = {}
    for name in 'ABCDE':
        n = pcbnew.NETINFO_ITEM(b, name)
        b.Add(n)
        nets[name] = n

    def track(net, x1, y1, x2, y2, w):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pt(x1, y1))
        t.SetEnd(pt(x2, y2))
        t.SetWidth(mm(w))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(nets[net])
        b.Add(t)

    track('A', 110, 120, 130, 120, 0.2)
    track('B', 110, 120.37, 130, 120.37, 0.2)
    track('C', 110, 130, 130, 130, 0.12)
    track('D', 100.32, 105, 100.32, 115, 0.2)

    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pt(140, 110))
    call(v, 'SetWidth', mm(0.45))
    v.SetDrill(mm(0.15))
    v.SetNet(nets['E'])
    b.Add(v)

    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference('FIX1')
    fp.SetValue('fixture')
    fp.SetPosition(pt(140, 130))
    b.Add(fp)

    pth = pcbnew.PAD(fp)
    pth.SetNumber('1')
    pth.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    call(pth, 'SetShape', pcbnew.PAD_SHAPE_CIRCLE)
    call(pth, 'SetSize', pcbnew.VECTOR2I(mm(1.1), mm(1.1)))
    pth.SetDrillSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
    pth.SetLayerSet(pcbnew.PAD.PTHMask())
    fp.Add(pth)
    pth.SetPosition(pt(140, 125))

    npth = pcbnew.PAD(fp)
    npth.SetNumber('')
    npth.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    call(npth, 'SetShape', pcbnew.PAD_SHAPE_CIRCLE)
    call(npth, 'SetSize', pcbnew.VECTOR2I(mm(0.4), mm(0.4)))
    npth.SetDrillSize(pcbnew.VECTOR2I(mm(0.4), mm(0.4)))
    npth.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
    fp.Add(npth)
    npth.SetPosition(pt(140, 140))

    pcbnew.SaveBoard(pcb, b)
    print('fixture written to %s' % pcb)


if __name__ == '__main__':
    main()
