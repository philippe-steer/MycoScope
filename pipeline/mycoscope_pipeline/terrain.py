"""Relief : MNT Copernicus GLO-30, pente, exposition et indice topographique d'humidité (TWI).

TWI = ln(a / tan β), a = aire drainée spécifique (D8, après comblement des dépressions par
priority-flood), β = pente locale. Le calcul se fait sur la grille du département avec une
marge : les très grands bassins sont tronqués au bord, mais le TWI y est de toute façon
saturé (borné à 16), ce qui n'affecte que les grands fonds de vallée.
"""
from __future__ import annotations

import heapq
import math

import numpy as np
from numba import njit

DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")


def dem_urls(west, south, east, north):
    for lat in range(math.floor(south), math.floor(north) + 1):
        for lon in range(math.floor(west), math.floor(east) + 1):
            yield DEM_URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat),
                                 ew="E" if lon >= 0 else "W", lon=abs(lon))


def load_dem(grid) -> np.ndarray:
    """MNT rééchantillonné (bilinéaire) sur la grille ; NaN en mer."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    out = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    w, s, e, n = grid.lonlat_bounds()
    for url in dem_urls(w, s, e, n):
        try:
            src = rasterio.open(url)
        except Exception:
            continue  # tuile absente (mer)
        with src, WarpedVRT(src, crs="EPSG:3857", transform=grid.transform, width=grid.width,
                            height=grid.height, resampling=Resampling.bilinear,
                            src_nodata=src.nodata, nodata=np.nan, dtype="float32") as vrt:
            a = vrt.read(1)
        m = np.isfinite(a) & np.isnan(out)
        out[m] = a[m]
    return out


@njit(cache=True)
def _priority_flood(dem, nodata_mask):
    """Comblement des dépressions (Barnes et al. 2014, variante epsilon)."""
    h, w = dem.shape
    filled = dem.copy()
    closed = np.zeros((h, w), dtype=np.bool_)
    heap = [(0.0, 0, 0)]
    heap.pop()
    for i in range(h):
        for j in range(w):
            if nodata_mask[i, j]:
                closed[i, j] = True
            elif i == 0 or j == 0 or i == h - 1 or j == w - 1 or _touches_nodata(nodata_mask, i, j):
                heapq.heappush(heap, (filled[i, j], i, j))
                closed[i, j] = True
    eps = 1e-4
    while len(heap) > 0:
        z, i, j = heapq.heappop(heap)
        for di in range(-1, 2):
            for dj in range(-1, 2):
                if di == 0 and dj == 0:
                    continue
                ni, nj = i + di, j + dj
                if ni < 0 or nj < 0 or ni >= h or nj >= w or closed[ni, nj]:
                    continue
                closed[ni, nj] = True
                if filled[ni, nj] <= z:
                    filled[ni, nj] = z + eps
                heapq.heappush(heap, (filled[ni, nj], ni, nj))
    return filled


@njit(cache=True)
def _touches_nodata(mask, i, j):
    h, w = mask.shape
    for di in range(-1, 2):
        for dj in range(-1, 2):
            ni, nj = i + di, j + dj
            if 0 <= ni < h and 0 <= nj < w and mask[ni, nj]:
                return True
    return False


@njit(cache=True)
def _d8_accumulation(filled, nodata_mask, order):
    """Nombre de cellules drainées (D8), en parcourant les cellules de la plus haute à la plus basse."""
    h, w = filled.shape
    acc = np.ones((h, w), dtype=np.float64)
    for k in range(order.size - 1, -1, -1):
        idx = order[k]
        i, j = idx // w, idx % w
        if nodata_mask[i, j]:
            continue
        best, bi, bj = 0.0, -1, -1
        z = filled[i, j]
        for di in range(-1, 2):
            for dj in range(-1, 2):
                if di == 0 and dj == 0:
                    continue
                ni, nj = i + di, j + dj
                if ni < 0 or nj < 0 or ni >= h or nj >= w or nodata_mask[ni, nj]:
                    continue
                d = 1.4142135623730951 if di != 0 and dj != 0 else 1.0
                s = (z - filled[ni, nj]) / d
                if s > best:
                    best, bi, bj = s, ni, nj
        if bi >= 0:
            acc[bi, bj] += acc[i, j]
    return acc


def slope_aspect(dem: np.ndarray, cell: float):
    """Pente (°) et exposition (° depuis le nord, sens horaire, direction de descente)."""
    gy, gx = np.gradient(dem, cell)          # gy : vers le sud (lignes croissantes)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    # descente vers -grad ; nord = -lignes → composante nord de la descente = +gy
    aspect = (np.degrees(np.arctan2(-gx, gy)) + 360.0) % 360.0
    return slope, aspect


def twi(dem: np.ndarray, cell: float) -> np.ndarray:
    nod = ~np.isfinite(dem)
    d = np.where(nod, 0.0, dem).astype(np.float64)
    filled = _priority_flood(d, nod)
    order = np.argsort(filled, axis=None, kind="stable")
    acc = _d8_accumulation(filled, nod, order)
    slope, _ = slope_aspect(np.where(nod, np.nan, dem), cell)
    tanb = np.tan(np.radians(np.maximum(np.nan_to_num(slope, nan=0.0), 0.5)))
    t = np.log(acc * cell / tanb)
    t[nod] = np.nan
    return t.astype(np.float32)
