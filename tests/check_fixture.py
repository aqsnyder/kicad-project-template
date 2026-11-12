"""Compare `fab.py check --all --json` on the fixture boards with what each profile must find.

usage: python3 tests/check_fixture.py CHECK_JSON
The JSON must hold one 2-layer and one 4-layer fixture board. Exits 1 on any difference. Hole-size violations are
reported by KiCad as drill_out_of_range (or hole_size); both count as "hole" here. None means the profile does not
cover that many copper layers, so check must show it as n/a and run no DRC.
"""
import json
import sys

PCBWAY = {'clearance': 1, 'track_width': 1, 'copper_edge_clearance': 1, 'hole': 1, 'via_diameter': 1}
EXPECTED = {
    2: {
        'jlcpcb-2layer': {'clearance': 1, 'hole': 2, 'annular_width': 1},
        'jlcpcb-multilayer': None,
        'pcbway-standard': PCBWAY,
    },
    4: {
        'jlcpcb-2layer': None,
        'jlcpcb-multilayer': {'clearance': 1, 'hole': 2},
        'pcbway-standard': PCBWAY,
    },
}
HOLE = ('drill_out_of_range', 'hole_size', 'drill_size')


def main():
    data = json.load(open(sys.argv[1]))
    by_layers = {row['copper_layers']: (board, row) for board, row in data.items()}
    if len(data) != len(EXPECTED) or sorted(by_layers) != sorted(EXPECTED):
        print('FAIL want one fixture board each with %s copper layers, got %s'
              % (sorted(EXPECTED), {b: r['copper_layers'] for b, r in data.items()}))
        sys.exit(1)
    bad = 0
    for layers, expected in sorted(EXPECTED.items()):
        board, row = by_layers[layers]
        print('%s (%d copper layers)' % (board, layers))
        for pid, want in expected.items():
            e = row['fabs'][pid]
            if want is None:
                want, loaded = 'n/a', True
                got = 'n/a' if not e['applies'] else e['types']
                ok = not e['applies'] and e['errors'] is None and e['rules_loaded'] is None
            else:
                got = {}
                for t, n in e['types'].items():
                    k = 'hole' if t in HOLE else t
                    got[k] = got.get(k, 0) + n
                loaded = e['rules_loaded']
                ok = e['applies'] and got == want and loaded
            bad += not ok
            print('  %-4s %-18s want %s\n       %-18s got  %s%s' % (
                'ok' if ok else 'FAIL', pid, want, '', got, '' if loaded else '  (RULES NOT LOADED)'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
