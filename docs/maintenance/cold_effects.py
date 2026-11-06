"""Give CWP's state regions the base game's seasonal cold (Victoria 3 1.15+).

1.15 added a cold system: every state region, land or sea, has min_cold_effect / max_cold_effect, and the
engine moves each region's cold between the two over the year (NSeasons in the defines). A sea region with
moderate or severe cold slows fleets, cuts the world market access of trade centers whose hub uses it and
makes overseas supply routes through it need more supply ships; world market hubs prefer ice-free ports.
CWP replaces map_data/state_regions with its own map, so without these values nothing would ever freeze.

Both province maps share the base game's 8192x3616 projection, so each CWP region takes the pixel-weighted
average of the base-game regions it covers (regions the base game leaves without cold count as 0). Regions
that end up without cold get no fields, as in the base game. The fields go at the end of each block, where
the base game puts them; existing ones are replaced, so the script can be re-run.

Usage: python docs/maintenance/cold_effects.py [--game "<Victoria 3>/game"] [--check]
Re-run it after editing CWP's state regions or when the base game changes its cold values.
"""

import argparse
import os
import re
import sys

import numpy as np
from PIL import Image

MOD = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DEFAULT_GAME = r'C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\game'
COLD_LINE = re.compile(r'^[ \t]*(?:min|max)_cold_effect\s*=.*(?:\r?\n|$)', re.M)


def blocks(text):
    """Yield (key, start, open_brace, close_brace) for each top-level 'KEY = { ... }' block."""
    i, n, depth, key_start, key, open_at = 0, len(text), 0, None, None, None
    while i < n:
        c = text[i]
        if c == '#':
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '"':
            j = text.find('"', i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == '{':
            if depth == 0:
                m = re.search(r'([A-Za-z0-9_]+)\s*=\s*$', text[max(0, i - 200):i])
                key = m.group(1) if m else None
                key_start = i - (len(text[max(0, i - 200):i]) - m.start()) if m else i
                open_at = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and key:
                yield key, key_start, open_at, i
                key = None
        i += 1


def read_regions(folder):
    regions = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.txt'):
            continue
        text = open(os.path.join(folder, name), encoding='utf-8-sig').read()
        for key, _, open_at, close_at in blocks(text):
            body = text[open_at + 1:close_at]
            m = re.search(r'provinces\s*=\s*\{([^}]*)\}', body)
            provs = [p.upper() for p in re.findall(r'x[0-9A-Fa-f]{6}', m.group(1))] if m else []
            lo = re.search(r'min_cold_effect\s*=\s*([\d.]+)', body)
            hi = re.search(r'max_cold_effect\s*=\s*([\d.]+)', body)
            regions[key] = (provs, float(lo.group(1)) if lo else 0.0, float(hi.group(1)) if hi else 0.0, name)
    return regions


def pixel_regions(png, regions, order):
    index = {key: i for i, key in enumerate(order)}
    colour_to_region = {}
    for key in order:
        for p in regions[key][0]:
            colour_to_region[int(p[1:], 16)] = index[key]
    rgb = np.asarray(Image.open(png).convert('RGB'), dtype=np.uint32)
    codes = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    unique, inverse = np.unique(codes.ravel(), return_inverse=True)
    lookup = np.array([colour_to_region.get(int(c), -1) for c in unique], dtype=np.int64)
    return lookup[inverse]


def project(game):
    base = read_regions(os.path.join(game, 'map_data', 'state_regions'))
    cwp = read_regions(os.path.join(MOD, 'map_data', 'state_regions'))
    base_order, cwp_order = sorted(base), sorted(cwp)
    base_pix = pixel_regions(os.path.join(game, 'map_data', 'provinces.png'), base, base_order)
    cwp_pix = pixel_regions(os.path.join(MOD, 'map_data', 'provinces.png'), cwp, cwp_order)
    both = (base_pix >= 0) & (cwp_pix >= 0)
    lo = np.array([base[k][1] for k in base_order])
    hi = np.array([base[k][2] for k in base_order])
    target, source = cwp_pix[both], base_pix[both]
    count = np.bincount(target, minlength=len(cwp_order))
    sum_lo = np.bincount(target, weights=lo[source], minlength=len(cwp_order))
    sum_hi = np.bincount(target, weights=hi[source], minlength=len(cwp_order))
    values, unmatched = {}, []
    for i, key in enumerate(cwp_order):
        if count[i] == 0:
            unmatched.append(key)
            continue
        low, high = round(sum_lo[i] / count[i], 2), round(sum_hi[i] / count[i], 2)
        if high >= 0.01:
            values[key] = (low, high)
    return cwp, values, unmatched


def write(cwp, values, check):
    folder = os.path.join(MOD, 'map_data', 'state_regions')
    changed_files, changed_regions = [], 0
    for name in sorted({v[3] for v in cwp.values()}):
        path = os.path.join(folder, name)
        raw = open(path, 'rb').read()
        bom = raw.startswith(b'\xef\xbb\xbf')
        text = raw.decode('utf-8-sig')
        nl = '\r\n' if '\r\n' in text else '\n'
        out, last = [], 0
        for key, _, open_at, close_at in blocks(text):
            body = text[open_at + 1:close_at]
            new_body = COLD_LINE.sub('', body)
            if key in values:
                low, high = values[key]
                fields = f'    min_cold_effect = {low:.2f}{nl}    max_cold_effect = {high:.2f}{nl}'
                line_start = new_body.rfind('\n') + 1
                if new_body[line_start:].strip():
                    new_body += nl + fields
                else:
                    new_body = new_body[:line_start] + fields + new_body[line_start:]
            if new_body != body:
                changed_regions += 1
            out.append(text[last:open_at + 1])
            out.append(new_body)
            last = close_at
        out.append(text[last:])
        new_text = ''.join(out)
        if new_text != text:
            changed_files.append(name)
            if not check:
                with open(path, 'wb') as f:
                    f.write((b'\xef\xbb\xbf' if bom else b'') + new_text.encode('utf-8'))
    return changed_files, changed_regions


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--game', default=DEFAULT_GAME, help='Victoria 3 game folder')
    parser.add_argument('--check', action='store_true', help='report what would change without writing')
    args = parser.parse_args()
    cwp, values, unmatched = project(args.game)
    files, regions = write(cwp, values, args.check)
    seas = sorted((k for k in values if cwp[k][3] == '99_seas.txt'), key=lambda k: -values[k][1])
    print(f'{len(values)} of {len(cwp)} CWP regions have cold ({len(seas)} seas); '
          f'{regions} regions in {len(files)} files {"would change" if args.check else "changed"}')
    for key in seas:
        print(f'  {key}: {values[key][0]:.2f}-{values[key][1]:.2f}')
    if unmatched:
        print('No overlap with any base-game region (left without cold): ' + ' '.join(unmatched))
    return 1 if args.check and files else 0


if __name__ == '__main__':
    sys.exit(main())
