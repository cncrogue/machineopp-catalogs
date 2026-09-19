#!/usr/bin/env python3
"""Build the M.A. Ford MILLING speeds/feeds catalog (series_speeds format) from
speeds_feeds.csv (end_mill rows only) — feeds the resolver's milling-published
layer (v4.24.0), the milling counterpart to the OSG/Dormer holemaking catalogs.

Only end_mill rows go here: M.A. Ford drills already ship embedded per-tool in
the MA Ford Drills tool catalog and via OSG/Dormer holemaking, and M.A. Ford's
feed_unit is not uniform across families (IPT end mills vs IPR drills), which the
holemaking build's hoist requires. Uniform-per-file fields are hoisted to the
catalog object (source_file/notes set to one catalog-level value — they vary by
series in the CSV but are not used by the resolver). Blanks -> JSON null.

Output: speeds/ma_ford_milling.json (+ updates speeds/index.json)
Usage:  python build_maford_milling_speeds.py <path-to-Catalogs-folder>
"""
import csv, json, os, sys

VERSION = 1
OUT_FILE = 'ma_ford_milling.json'
NOTE = ('Technical data provided should be considered advisory only as '
        'variations may be necessary.')


def num(v):
    v = (v or '').strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def s(v):
    v = (v or '').strip()
    return v if v else None


def main():
    catalogs_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    out_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(catalogs_dir, 'speeds_feeds.csv'),
              newline='', encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f)
                if r.get('brand', '').strip() == 'M.A. Ford'
                and r.get('tool_family', '').strip() == 'end_mill']
    if not rows:
        raise SystemExit('no M.A. Ford end_mill rows found')

    # feed_unit must be uniform (it is: IPT) so we can hoist it.
    units = {s(r.get('feed_unit')) for r in rows}
    assert units == {'IPT'}, f'end-mill feed_unit not uniform IPT: {units}'

    series = [{
        'series': s(r.get('series')),
        'tool_family': 'end_mill',
        'operation': s(r.get('operation')),
        'iso_group': s(r.get('iso_group')),
        'wmg_code': s(r.get('wmg_code')),      # null for milling
        'material': s(r.get('material')),
        'hardness': s(r.get('hardness')),
        'dia_in': num(r.get('dia_in')),
        'dia_mm': num(r.get('dia_mm')),
        'sfm_min': num(r.get('sfm_min')),
        'sfm_max': num(r.get('sfm_max')),
        'rpm': num(r.get('rpm')),
        'feed_min': num(r.get('feed_min')),
        'feed_max': num(r.get('feed_max')),
        'feed_alpha': None,                     # null for milling (self-contained)
    } for r in rows]

    detail = {
        'catalog': 'M.A. Ford Milling S&F',
        'brand': 'M.A. Ford',
        'source_catalog': 'Vol 105 (2024)',
        'source_year': '2024',
        'feed_unit': 'IPT',
        'confidence': 'parsed-verified',
        'source_file': 'MA Ford Vol 105 (2024) speeds & feeds',
        'notes': NOTE,
        'series': series,
    }
    path = os.path.join(out_dir, OUT_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(detail, f, separators=(',', ':'), ensure_ascii=False)
    sz = os.path.getsize(path)
    print(f'M.A. Ford milling: {len(series)} rows -> {OUT_FILE} ({sz/1024:.0f} KB)')

    # Merge into index.json (append/replace our entry, keep the others).
    idx_path = os.path.join(out_dir, 'index.json')
    with open(idx_path, encoding='utf-8') as f:
        idx = json.load(f)
    entry = {
        'name': 'M.A. Ford Milling S&F',
        'description': ('M.A. Ford end-mill speeds & feeds: published SFM + '
                        f'per-tooth feed (IPT) by material and diameter '
                        f'({len(series)} rows). Auto-applies to solid carbide '
                        f'end mills.'),
        'file': OUT_FILE,
        'version': VERSION,
        'series_count': len(series),
    }
    idx['catalogs'] = [c for c in idx['catalogs'] if c.get('file') != OUT_FILE]
    idx['catalogs'].append(entry)
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(idx, f, indent=1, ensure_ascii=False)
    print('index.json updated:', [c['file'] for c in idx['catalogs']])


if __name__ == '__main__':
    main()
