#!/usr/bin/env python3
"""Build M.A. Ford downloadable tool catalogs (CatalogTool + embedded speeds[])
from maford_tools.csv + speeds_feeds.csv.

One catalog JSON per tool family. Each tool carries embedded speeds[] joined by
series + nearest published diameter, one CatalogSpeed per ISO material letter.

Rules honored:
  - Never interpolate a blank. Missing dim/speed => omitted (null), never invented.
  - mm->inch is a unit conversion of a PUBLISHED value (exact), not interpolation:
    catalogs are all-inch for uniformity (dimension_unit='inch').
  - Feed: end mills feed_unit IPT -> feed_per_tooth direct; drills/reamers/
    countersinks feed_unit IPR -> feed_per_tooth = IPR / num_flutes (matches the
    existing ma_ford_305 catalog; app reconstitutes IPR via fpt x flutes x rpm).
"""
import csv, json, os, re, sys
from collections import defaultdict

ROOT = r"C:\Users\cw003\OneDrive\Documents\Projects\Tool Finder\Tool Finder\Catalogs"
TOOLS_CSV = os.path.join(ROOT, "maford_tools.csv")
SF_CSV = os.path.join(ROOT, "speeds_feeds.csv")
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "out")
os.makedirs(OUTDIR, exist_ok=True)

# family -> (app tool_type, catalog display label, filename stem)
FAMILY = {
    'end_mill':    ('End Mill',    'End Mills',    'ma_ford_end_mills'),
    'drill':       ('Drill',       'Drills',       'ma_ford_drills'),
    'reamer':      ('Reamer',      'Reamers',      'ma_ford_reamers'),
    'countersink': ('Countersink', 'Countersinks', 'ma_ford_countersinks'),
    'chamfer_mill':('Chamfer Mill','Chamfer Mills','ma_ford_chamfer_mills'),
    # bur, router deferred (no app tool type)
}
FAMILY_DEFAULT_FLUTES = {'drill': 2}  # fallback only when nof blank

# Families split into ONE catalog PER SERIES (founder: import just the series you
# run). The rest stay a single family catalog. Per-series files live under maford/.
SPLIT_FAMILIES = {'end_mill', 'drill'}
SPLIT_SUBDIR = 'maford'

def sanitize(series):
    return re.sub(r'[^a-z0-9]+', '_', (series or '').lower()).strip('_') or 'x'

FRAC = re.compile(r'^\s*(\d+)?\s*[- ]?\s*(\d+)\s*/\s*(\d+)\s*$')

def to_decimal(v):
    """Parse a value that may be a decimal ('.1250') or a fraction ('1-1/2',
    '5/32', '1/8') into a float. Blank -> None. Never guesses."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = FRAC.match(s)
    if m:
        whole = int(m.group(1)) if m.group(1) else 0
        return whole + int(m.group(2)) / int(m.group(3))
    try:
        return float(s)
    except ValueError:
        return None

def dim_inch(row, base):
    """Return a dimension in inches. Prefer the inch column (may be fraction or
    decimal); else convert the mm column. None if both blank."""
    iv = to_decimal(row.get(base + '_in'))
    if base == 'dc':  # dc has a decimal column too
        iv = iv if iv is not None else to_decimal(row.get('dc_decimal'))
    if iv is not None:
        return round(iv, 4)
    mv = to_decimal(row.get(base + '_mm'))
    if mv is not None:
        return round(mv / 25.4, 4)
    return None

def dia_display(row):
    """Human diameter for the tool name: fraction if printed, else decimal in,
    else mm."""
    f = row.get('dc_in', '').strip()
    if f and '/' in f:
        return f'{f}"'
    d = to_decimal(row.get('dc_decimal')) or to_decimal(row.get('dc_in'))
    if d is not None:
        return '{0}"'.format(('%.4f' % d).rstrip('0').rstrip('.'))
    mm = to_decimal(row.get('dc_mm'))
    if mm is not None:
        return '{0}mm'.format(('%.3f' % mm).rstrip('0').rstrip('.'))
    return '?'

feed_unit_warnings = []

# ---- load S&F, index by (series, iso_group) -> list of (dia_in, row) ----
sf_by_series_iso = defaultdict(list)
sf_series = set()
with open(SF_CSV, encoding='utf-8') as fh:
    for r in csv.DictReader(fh):
        if r.get('brand') != 'M.A. Ford':
            continue
        dia = to_decimal(r.get('dia_in')) or (
            (to_decimal(r.get('dia_mm')) or 0) / 25.4 or None)
        iso = (r.get('iso_group') or '').strip()
        if not iso or dia is None:
            continue
        sf_series.add(r['series'])
        sf_by_series_iso[(r['series'], iso)].append((round(dia, 4), r))

def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0

def speeds_for(series, tool_dia, family):
    """Build embedded CatalogSpeed[] for one tool: one row per ISO letter,
    snapping to the nearest published diameter, then collapsing the letter's
    sub-material rows (e.g. P = low-carbon/medium-carbon/alloy/tool-steel) to a
    MEDIAN band — tool_speeds is keyed by single ISO letter, so one band per
    letter. Profile Milling preferred over Slotting when both exist.

    Feed is stored DIRECTLY (no unit conversion): the app consumes
    feed_per_tooth in the tool's OWN calc mode — milling (end mill, chamfer) as
    fpt x flutes x rpm (source IPT), holemaking (drill/reamer/countersink) as
    feed x rpm, IPR-direct (Operation.calcModeForToolType). Source unit already
    matches the mode; a mismatch is flagged, not silently converted."""
    milling = family in ('end_mill', 'chamfer_mill')
    expected_unit = 'IPT' if milling else 'IPR'
    out = []
    isos = sorted({iso for (s, iso) in sf_by_series_iso if s == series})
    for iso in isos:
        cand = sf_by_series_iso[(series, iso)]
        if tool_dia is None:
            target = min(d for d, _ in cand)
        else:
            target = min((d for d, _ in cand), key=lambda d: abs(d - tool_dia))
        atdia = [row for d, row in cand if abs(d - target) < 1e-6]
        # prefer Profile Milling when the sheet tags operations
        ops = {(r.get('operation') or '') for r in atdia}
        if 'Profile Milling' in ops:
            atdia = [r for r in atdia if (r.get('operation') or '') == 'Profile Milling']
        lows = [to_decimal(r.get('sfm_min')) for r in atdia]
        highs = [to_decimal(r.get('sfm_max')) for r in atdia]
        smin = _median(lows)
        smax = _median(highs)
        if smin is None and smax is None:
            continue
        smin = smin if smin is not None else smax
        smax = smax if smax is not None else smin
        feeds = []
        bad_unit = False
        for r in atdia:
            fmin = to_decimal(r.get('feed_min'))
            fmax = to_decimal(r.get('feed_max'))
            if fmin is None and fmax is None:
                continue
            unit = (r.get('feed_unit') or '').strip().upper()
            if unit and unit != expected_unit:
                bad_unit = True
                continue
            feeds.append(((fmin or fmax) + (fmax or fmin)) / 2.0)
        fval = _median(feeds)
        if bad_unit and fval is None:
            feed_unit_warnings.append(
                f'{series} {iso}: family {family} expected {expected_unit} feed '
                f'but source unit differs — feed dropped')
        sp = {'material': iso, 'sfm_low': round(smin, 1), 'sfm_high': round(smax, 1)}
        if fval is not None:
            sp['feed_per_tooth'] = round(fval, 5)
        out.append(sp)
    return out

# ---- pre-pass: per-series uniform flute count (milling families only) ----
# Many end-mill rows leave nof blank though the series header states one flute
# count. Backfill a blank nof ONLY when every non-blank row in that series agrees
# (uniform) — the printed flute count, never a guess across mixed-flute series.
series_nof = defaultdict(set)
with open(TOOLS_CSV, encoding='utf-8') as fh:
    for r in csv.DictReader(fh):
        if r.get('tool_family') in ('end_mill', 'chamfer_mill'):
            v = r.get('nof', '').strip()
            if v:
                try:
                    series_nof[r['series']].add(int(float(v)))
                except ValueError:
                    pass
uniform_nof = {s: next(iter(v)) for s, v in series_nof.items() if len(v) == 1}
nof_backfilled = 0

# ---- build tools per family ----
catalogs = defaultdict(list)
counts = defaultdict(int)
skipped_family = defaultdict(int)
seen_pn = defaultdict(set)  # per-family part-number dedup
dup_pn_dropped = defaultdict(int)
with open(TOOLS_CSV, encoding='utf-8') as fh:
    for r in csv.DictReader(fh):
        fam = r.get('tool_family', '').strip()
        if fam not in FAMILY:
            skipped_family[fam] += 1
            continue
        tool_type, label, _ = FAMILY[fam]
        # per-family part-number dedup (same part printed on sibling pages, e.g.
        # 179/179L — identical rows; importCatalog would skip the 2nd anyway).
        pn_key = r.get('tool_no', '').strip()
        if pn_key and pn_key in seen_pn[fam]:
            dup_pn_dropped[fam] += 1
            continue
        if pn_key:
            seen_pn[fam].add(pn_key)
        dia = dim_inch(r, 'dc')
        nof = None
        try:
            nof = int(float(r['nof'])) if r.get('nof', '').strip() else None
        except ValueError:
            nof = None
        if nof is None and fam in ('end_mill', 'chamfer_mill') \
                and r['series'] in uniform_nof:
            nof = uniform_nof[r['series']]
            nof_backfilled += 1
        weldon = (r.get('weldon_flat', '').strip().lower() == 'true')
        flute_len = dim_inch(r, 'apmx') if fam in ('end_mill', 'chamfer_mill') \
            else dim_inch(r, 'lf')
        if flute_len is None:  # fall back to whichever the family didn't use
            flute_len = dim_inch(r, 'lf') if fam in ('end_mill', 'chamfer_mill') \
                else dim_inch(r, 'apmx')
        tool = {
            'tool_type': tool_type,
            'tool_name': '{0} {1}MA Ford {2} {3}'.format(
                dia_display(r),
                (str(nof) + 'FL ') if nof else '',
                r['series'],
                ('Weldon ' if weldon else '') + label[:-1]),  # singular
            'diameter': dia,
            'num_flutes': nof,
            'flute_length': flute_len,
            'overall_length': dim_inch(r, 'oal'),
            'corner_radius': dim_inch(r, 're'),
            'coating': (r.get('coating') or '').strip() or None,
            'substrate': (r.get('substrate') or '').strip() or 'Carbide',
            'shank_type': 'Weldon' if weldon else 'Straight',
            'part_number': r.get('tool_no', '').strip() or None,
            'edp': (r.get('edp') or '').strip() or None,
            'parts_per_tool': 1,
            'speeds': speeds_for(r['series'], dia, fam) if r['series'] in sf_series else [],
        }
        # drop null keys to keep files lean
        tool = {k: v for k, v in tool.items() if v is not None and v != []}
        if 'speeds' not in tool:
            tool['speeds'] = []
        # Split families get one catalog per series; others one per family.
        key = (fam, r['series'].strip()) if fam in SPLIT_FAMILIES else (fam, None)
        catalogs[key].append(tool)
        counts[fam] += 1

# ---- uniqueness guard on tool_name within each catalog file ----
for key, tools in catalogs.items():
    seen = {}
    for t in tools:
        nm = t['tool_name']
        if nm in seen:
            t['tool_name'] = '{0} ({1})'.format(nm, t.get('part_number', 'v'))
        seen[t['tool_name']] = True

# ---- emit: one JSON per (family, series) bucket ----
os.makedirs(os.path.join(OUTDIR, SPLIT_SUBDIR), exist_ok=True)
index_entries = []
for (fam, series), tools in sorted(catalogs.items(),
                                   key=lambda kv: (kv[0][0], kv[0][1] or '')):
    tool_type, label, stem = FAMILY[fam]
    with_sf = sum(1 for t in tools if t.get('speeds'))
    if series is None:  # single family catalog (reamers/countersinks/chamfer)
        name = 'MA Ford ' + label
        rel = stem + '.json'
        desc = (f'M.A. Ford {label.lower()} — full 2024 Vol 105 library, '
                f'part numbers + dimensions')
    else:  # per-series catalog (end mills / drills)
        singular = label[:-1]  # "End Mills" -> "End Mill"
        name = f'MA Ford {series} {label}'
        rel = f'{SPLIT_SUBDIR}/ma_ford_{sanitize(series)}_{stem.replace("ma_ford_", "")}.json'
        desc = (f'M.A. Ford {series} series {singular.lower()}s — part numbers + '
                f'dimensions')
    if with_sf:
        desc += f'; published speeds & feeds on {with_sf} tools'
    detail = {'catalog': name, 'manufacturer': 'MA Ford', 'tools': tools}
    path = os.path.join(OUTDIR, rel)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(detail, fh, separators=(',', ':'), ensure_ascii=False)
    index_entries.append({
        'name': name,
        'category': 'manufacturer',
        'description': desc,
        'file': rel.replace('\\', '/'),
        'version': 1,
        'tool_count': len(tools),
    })
print(f'emitted {len(index_entries)} catalog files '
      f'({sum(1 for e in index_entries if "/" in e["file"])} per-series under {SPLIT_SUBDIR}/)')

if feed_unit_warnings:
    print('\nFEED-UNIT WARNINGS ({0}):'.format(len(feed_unit_warnings)))
    for w in feed_unit_warnings[:10]:
        print('  ', w)
print('\nnof backfilled (series-uniform, milling):', nof_backfilled)
print('duplicate part-numbers dropped:', dict(dup_pn_dropped))
print('skipped families (no app type):', dict(skipped_family))
with open(os.path.join(OUTDIR, '_index_entries.json'), 'w', encoding='utf-8') as fh:
    json.dump(index_entries, fh, indent=2)
print('index entries written to _index_entries.json')
