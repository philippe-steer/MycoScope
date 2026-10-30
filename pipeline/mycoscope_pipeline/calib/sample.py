"""Valeurs aux points d'observation : altitude (Copernicus DEM), pixel d'habitat (PMTiles),
anomalie de nappe à la date (historique Hub'Eau)."""
from __future__ import annotations

import datetime as dt
import io
import math
from collections import defaultdict

import numpy as np

from ..terrain import DEM_URL


def _dem_url(lat, lon):
    la, lo = math.floor(lat), math.floor(lon)
    return DEM_URL.format(ns="N" if la >= 0 else "S", lat=abs(la), ew="E" if lo >= 0 else "W", lon=abs(lo))


def dem_points(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    import rasterio
    out = np.full(len(lat), np.nan)
    groups = defaultdict(list)
    for i, (a, b) in enumerate(zip(lat, lon)):
        groups[_dem_url(a, b)].append(i)
    for url, ids in groups.items():
        try:
            with rasterio.open(url) as src:
                vals = [v[0] for v in src.sample([(lon[i], lat[i]) for i in ids])]
                for i, v in zip(ids, vals):
                    out[i] = v if v > -1000 else np.nan
        except Exception:  # noqa: BLE001 (tuile en mer)
            pass
    return out


def dem_box_means(lat: np.ndarray, lon: np.ndarray, half_m: float = 4000.0) -> np.ndarray:
    """Altitude moyenne d'un carré de 8 km centré sur chaque point (maille SAFRAN)."""
    import rasterio
    from rasterio.windows import from_bounds
    out = np.full(len(lat), np.nan)
    groups = defaultdict(list)
    for i, (a, b) in enumerate(zip(lat, lon)):
        groups[_dem_url(a, b)].append(i)
    for url, ids in groups.items():
        try:
            with rasterio.open(url) as src:
                for i in ids:
                    dlat = half_m / 111_000
                    dlon = half_m / (111_000 * math.cos(math.radians(lat[i])))
                    w = from_bounds(lon[i] - dlon, lat[i] - dlat, lon[i] + dlon, lat[i] + dlat, src.transform)
                    a = src.read(1, window=w, out_shape=(16, 16), boundless=True, fill_value=-32767).astype(float)
                    a[a < -1000] = np.nan
                    out[i] = np.nanmean(a) if np.isfinite(a).any() else np.nan
        except Exception:  # noqa: BLE001
            pass
    return out


def habitat_pixels(pmtiles_path: str, lat: np.ndarray, lon: np.ndarray, z: int = 12) -> np.ndarray:
    """Pixel RGBA (n, 4) de la tuile z12 sous chaque point (0 si absent)."""
    from PIL import Image
    from pmtiles.reader import MmapSource, Reader
    out = np.zeros((len(lat), 4), np.uint8)
    n = 2 ** z
    fx = (lon + 180) / 360 * n
    fy = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n
    tx, ty = fx.astype(int), fy.astype(int)
    groups = defaultdict(list)
    for i in range(len(lat)):
        groups[(tx[i], ty[i])].append(i)
    with open(pmtiles_path, "rb") as f:
        r = Reader(MmapSource(f))
        for (x, y), ids in groups.items():
            b = r.get(z, x, y)
            if not b:
                continue
            a = np.array(Image.open(io.BytesIO(b)).convert("RGBA"))
            for i in ids:
                px = min(int((fx[i] - x) * 256), 255)
                py = min(int((fy[i] - y) * 256), 255)
                out[i] = a[py, px]
    return out


class GroundWater:
    """Anomalie de nappe (-1..1) à une date et un lieu, comme dans l'appli (IDW 25 km)."""

    def __init__(self, path: str):
        d = np.load(path, allow_pickle=False)
        self.lat, self.lon, self.q = d["lat"], d["lon"], d["q"]
        self.off, self.days, self.values = d["offsets"], d["days"], d["values"]
        self.d0 = dt.date(2000, 1, 1)

    def _station(self, k: int, day: int, month: int):
        a, b = self.off[k], self.off[k + 1]
        days = self.days[a:b]
        j = np.searchsorted(days, day, side="right") - 1
        if j < 0 or day - days[j] > 30:
            return None
        v = self.values[a + j]
        p10, p50, p90 = self.q[k, month - 1]
        return float(np.clip((v - p50) / max(p90 - p50, 0.05) if v >= p50 else (v - p50) / max(p50 - p10, 0.05), -1, 1))

    def anomaly(self, lat: float, lon: float, date: dt.date) -> float:
        dx = (self.lon - lon) * 111 * math.cos(math.radians(lat))
        dy = (self.lat - lat) * 111
        dist = np.hypot(dx, dy)
        day = (date - self.d0).days
        sw = sa = 0.0
        for k in np.nonzero(dist < 25)[0]:
            a = self._station(int(k), day, date.month)
            if a is None:
                continue
            w = 1 / (2 + dist[k])
            sw += w
            sa += w * a
        return sa / sw if sw > 0 else 0.0
