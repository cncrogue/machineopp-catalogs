#!/usr/bin/env python3
"""Convert Craig's holemaking speeds/feeds CSVs into MachineOpp downloadable
`speeds/` catalog JSON, one file per brand + a manifest.

Source (not in this repo): <Tool Finder>/Catalogs/speeds_feeds.csv (8,258 rows)
and feed_alpha_codes.csv (335 rows). See MACHINEOPP_DATA_HANDOFF.md.

Rules (from the data brief):
  * A blank cell means the manufacturer published nothing there. Emit JSON null,
    never 0 or "". Never interpolate.
  * Keep the OSG (self-contained dia+sfm+feed) and Dormer (point sfm + feed_alpha
    letter) two-shape distinction verbatim. Do NOT pre-resolve the Dormer feed.
  * The Dormer feed_alpha lookup table is embedded in the Dormer file so one
    download imports atomically.

Output: speeds/index.json, speeds/osg.json, speeds/dormer_pramet.json
Usage:  python build_speeds_catalogs.py <path-to-Catalogs-folder>
"""
import csv, json, os, sys

# Series-row columns, in model order. Numeric columns become float|null.
# Per-row columns kept in each series entry (the ones that vary row-to-row).
# Uniform-per-file fields (brand, source_catalog, source_year, feed_unit,
# confidence, source_file, notes) are hoisted to the catalog object to keep the
# download small; the importer merges them back onto every row.
STR_COLS = ['series', 'tool_family', 'operation', 'iso_group', 'wmg_code',
            'material', 'hardness', 'feed_alpha']
NUM_COLS = ['dia_in', 'dia_mm', 'sfm_min', 'sfm_max', 'rpm',
            'feed_min', 'feed_max']
ALL_COLS = ['series', 'tool_family', 'operation', 'iso_group', 'wmg_code',
            'material', 'hardness', 'dia_in', 'dia_mm', 'sfm_min', 'sfm_max',
            'rpm', 'feed_min', 'feed_max', 'feed_alpha']
# Uniform-per-file, hoisted to the catalog object.
HOIST_COLS = ['source_catalog', 'source_year', 'feed_unit', 'confidence',
              'source_file', 'notes']

VERSION = 1


def clean_str(v):
    v = (v or '').strip()
    return v if v else None


def clean_num(v):
    v = (v or '').strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def row_to_obj(r):
    o = {}
    for c in STR_COLS:
        o[c] = clean_str(r.get(c))
    for c in NUM_COLS:
        o[c] = clean_num(r.get(c))
    return {c: o[c] for c in ALL_COLS}  # stable key order


def main():
    catalogs_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    out_dir = os.path.dirname(os.path.abspath(__file__))
    sf_path = os.path.join(catalogs_dir, 'speeds_feeds.csv')
    fa_path = os.path.join(catalogs_dir, 'feed_alpha_codes.csv')

    with open(sf_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    with open(fa_path, newline='', encoding='utf-8-sig') as f:
        fa_rows = list(csv.DictReader(f))

    # Group series rows by brand.
    by_brand = {}
    for r in rows:
        by_brand.setdefault(r['brand'].strip(), []).append(row_to_obj(r))

    # Feed-alpha table (Dormer only) — brand, feed_alpha, dia_mm, dia_in, feed_ipr.
    feed_alpha = [{
        'brand': clean_str(r.get('brand')),
        'feed_alpha': clean_str(r.get('feed_alpha')),
        'dia_mm': clean_num(r.get('dia_mm')),
        'dia_in': clean_num(r.get('dia_in')),
        'feed_ipr': clean_num(r.get('feed_ipr')),
    } for r in fa_rows]

    # Sanity: the 16 known feed-alpha diameters.
    fa_dias = sorted({c['dia_mm'] for c in feed_alpha if c['dia_mm'] is not None})
    expected = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20, 25, 30, 40, 50]
    assert fa_dias == [float(x) for x in expected], \
        f'feed_alpha diameters unexpected: {fa_dias}'

    # Raw rows grouped again to read the hoistable fields (uniform per file).
    raw_by_brand = {}
    for r in rows:
        raw_by_brand.setdefault(r['brand'].strip(), []).append(r)

    file_map = {'OSG': 'osg.json', 'Dormer Pramet': 'dormer_pramet.json'}
    manifest = []
    for brand, series in sorted(by_brand.items()):
        fname = file_map.get(brand)
        if not fname:
            raise SystemExit(f'Unmapped brand: {brand!r}')
        shapes = {'osg' if s['dia_in'] is not None else 'dormer' for s in series}
        detail = {'catalog': f'{brand} Holemaking S&F', 'brand': brand,
                  'series': series}
        # Hoist uniform-per-file fields onto the catalog object (must be uniform).
        raw = raw_by_brand[brand]
        for c in HOIST_COLS:
            vals = {clean_str(r.get(c)) for r in raw}
            if len(vals) != 1:
                raise SystemExit(
                    f'{brand}: column {c!r} not uniform ({len(vals)} values) — '
                    f'cannot hoist')
            detail[c] = next(iter(vals))
        # Embed the Dormer feed-alpha lookup only in the Dormer file.
        if brand == 'Dormer Pramet':
            detail['feed_alpha'] = feed_alpha
        with open(os.path.join(out_dir, fname), 'w', encoding='utf-8') as f:
            json.dump(detail, f, separators=(',', ':'), ensure_ascii=False)
        manifest.append({
            'name': f'{brand} Holemaking S&F',
            'description': f'{brand} holemaking speeds & feeds: '
                           f'published SFM + IPR by tool family, material and '
                           f'diameter ({len(series)} rows).',
            'file': fname,
            'version': VERSION,
            'series_count': len(series),
        })
        print(f'{brand}: {len(series)} rows -> {fname} (shapes: {sorted(shapes)})')

    with open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'catalogs': manifest}, f, indent=1, ensure_ascii=False)
    print(f'feed_alpha: {len(feed_alpha)} codes, dias={[int(d) for d in fa_dias]}')
    print('Wrote index.json + per-brand files.')


if __name__ == '__main__':
    main()
