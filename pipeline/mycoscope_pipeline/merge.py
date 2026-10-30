"""Fusionne les tuiles de tous les départements, construit la pyramide et écrit le PMTiles.

python -m mycoscope_pipeline.merge tiles_dir1 tiles_dir2 ... -o france.pmtiles
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

from . import encoding as enc
from .grid import R, tile_bounds_merc

ATTRIBUTION = ("Forêts : IGN BD Forêt® V2 · Géologie : BRGM BD Charm-50 · Sols : ISRIC SoilGrids (CC-BY 4.0) · "
               "Relief : Copernicus DEM GLO-30 © DLR/Airbus, ESA")


def decode(b: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(b)).convert("RGBA"))


def encode(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").save(buf, "WEBP", lossless=True, quality=100, method=6, exact=True)
    return buf.getvalue()


def combine(tiles: list[np.ndarray]) -> np.ndarray:
    """Pixels valides (R ≠ 0) du premier département qui en a, puis des suivants."""
    out = tiles[0].copy()
    for t in tiles[1:]:
        m = (out[..., 0] == 0) & (t[..., 0] != 0)
        out[m] = t[m]
    return out


def downsample(children: dict[tuple[int, int], np.ndarray]) -> np.ndarray:
    """4 tuiles enfants → 1 tuile : par bloc 2×2, premier pixel valide (classes catégorielles)."""
    big = np.zeros((512, 512, 4), np.uint8)
    for (dx, dy), a in children.items():
        big[dy * 256:(dy + 1) * 256, dx * 256:(dx + 1) * 256] = a
    out = big[0::2, 0::2].copy()
    for oy, ox in ((1, 1), (0, 1), (1, 0)):
        cand = big[oy::2, ox::2]
        m = (out[..., 0] == 0) & (cand[..., 0] != 0)
        out[m] = cand[m]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    a = ap.parse_args()
    z = enc.TILE_ZOOM
    sources = defaultdict(list)
    for d in a.dirs:
        for p in (d / str(z)).glob("*/*.webp"):
            sources[(int(p.parent.name), int(p.stem))].append(p)
    print(f"{len(sources)} tuiles z{z}")
    BLOCK_Z = 6
    shift = z - BLOCK_Z
    blocks = defaultdict(list)
    for k in sources:
        blocks[(k[0] >> shift, k[1] >> shift)].append(k)
    f = open(a.out, "wb")
    wr = Writer(f)
    count = 0

    def emit(zz, x, y, data):
        nonlocal count
        wr.write_tile(zxy_to_tileid(zz, x, y), data)
        count += 1

    top: dict[tuple[int, int], np.ndarray] = {}
    for bi, (bk, keys) in enumerate(sorted(blocks.items())):
        current: dict[tuple[int, int], np.ndarray] = {}
        for (x, y) in keys:
            paths = sources[(x, y)]
            if len(paths) == 1:
                data = paths[0].read_bytes()
                arr = decode(data)
            else:
                arr = combine([decode(p.read_bytes()) for p in paths])
                data = encode(arr)
            emit(z, x, y, data)
            current[(x, y)] = arr
        for zz in range(z - 1, BLOCK_Z - 1, -1):
            parents = defaultdict(dict)
            for (x, y), arr in current.items():
                parents[(x // 2, y // 2)][(x % 2, y % 2)] = arr
            current = {k: downsample(ch) for k, ch in parents.items()}
            for (x, y), arr in current.items():
                emit(zz, x, y, encode(arr))
        top.update(current)
        print(f"bloc {bi+1}/{len(blocks)} ({count} tuiles)")
    current = top
    for zz in range(BLOCK_Z - 1, enc.MIN_ZOOM - 1, -1):
        parents = defaultdict(dict)
        for (x, y), arr in current.items():
            parents[(x // 2, y // 2)][(x % 2, y % 2)] = arr
        current = {k: downsample(ch) for k, ch in parents.items()}
        for (x, y), arr in current.items():
            emit(zz, x, y, encode(arr))
    xs = [k[0] for k in sources]
    ys = [k[1] for k in sources]
    w, _, _, n = tile_bounds_merc(z, min(xs), min(ys))
    _, s, e, _ = tile_bounds_merc(z, max(xs), max(ys))
    import math
    lon = lambda mx: mx / R * 180 / math.pi
    lat = lambda my: math.degrees(math.atan(math.sinh(my / R)))
    wr.finalize(
        {"tile_type": TileType.WEBP, "tile_compression": Compression.NONE,
         "min_lon_e7": int(lon(w) * 1e7), "min_lat_e7": int(lat(s) * 1e7),
         "max_lon_e7": int(lon(e) * 1e7), "max_lat_e7": int(lat(n) * 1e7),
         "center_zoom": 6},
        {"name": "MycoScope environment", "format_version": enc.FORMAT_VERSION,
         "attribution": ATTRIBUTION, "built": dt.date.today().isoformat(),
         "forest_classes": enc.FOREST, "litho_classes": enc.LITHO},
    )
    f.close()
    print(f"écrit {a.out} ({a.out.stat().st_size/1e6:.0f} Mo, {count} tuiles)")


if __name__ == "__main__":
    main()
