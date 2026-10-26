"""Compare `fab.py check --json` on the fixture board with what each profile must find.

usage: python3 tests/check_fixture.py CHECK_JSON
Exits 1 on any difference. Hole-size violations are reported by KiCad as drill_out_of_range (or hole_size); both
count as "hole" here.
"""
import json
import sys

EXPECTED = {
    'jlcpcb-2layer': {'clearance': 1, 'hole': 2, 'annular_width': 1},
    'jlcpcb-multilayer': {'clearance': 1, 'hole': 2},
    'pcbway-standard': {'clearance': 1, 'track_width': 1, 'copper_edge_clearance': 1, 'hole': 1,
                        'via_diameter': 1},
}
HOLE = ('drill_out_of_range', 'hole_size', 'drill_size')


def main():
    data = json.load(open(sys.argv[1]))
    (board, row), = data.items()
    bad = 0
    for pid, want in EXPECTED.items():
        got = {}
        for t, n in row['fabs'][pid]['types'].items():
            k = 'hole' if t in HOLE else t
            got[k] = got.get(k, 0) + n
        loaded = row['fabs'][pid]['rules_loaded']
        ok = got == want and loaded
        bad += not ok
        print('%-4s %-18s want %s\n     %-18s got  %s%s' % (
            'ok' if ok else 'FAIL', pid, want, '', got, '' if loaded else '  (RULES NOT LOADED)'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
