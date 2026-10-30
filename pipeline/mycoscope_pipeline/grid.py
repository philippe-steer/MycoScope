"""Grille Web-Mercator alignée sur les tuiles (EPSG:3857)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from affine import Affine

from .encoding import TILE_SIZE

R = 6378137.0
ORIGIN = math.pi * R  # 20037508.34


def res(z: int) -> float:
    return 2 * ORIGIN / (TILE_SIZE * 2 ** z)


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat = max(min(lat, 85.0511), -85.0511)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_bounds_merc(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    s = 2 * ORIGIN / 2 ** z
    return (-ORIGIN + x * s, ORIGIN - (y + 1) * s, -ORIGIN + (x + 1) * s, ORIGIN - y * s)


@dataclass
class TileGrid:
    """Raster couvrant les tuiles [x0..x1]×[y0..y1] au zoom z, plus une marge de `pad` pixels."""
    z: int
    x0: int
    y0: int
    x1: int
    y1: int
    pad: int

    @classmethod
    def from_lonlat_bounds(cls, west, south, east, north, z, pad_m=6000.0):
        x0, y0 = lonlat_to_tile(west, north, z)
        x1, y1 = lonlat_to_tile(east, south, z)
        return cls(z, x0, y0, x1, y1, int(math.ceil(pad_m / res(z))))

    @property
    def width(self) -> int:
        return (self.x1 - self.x0 + 1) * TILE_SIZE + 2 * self.pad

    @property
    def height(self) -> int:
        return (self.y1 - self.y0 + 1) * TILE_SIZE + 2 * self.pad

    @property
    def transform(self) -> Affine:
        r = res(self.z)
        left, _, _, top = tile_bounds_merc(self.z, self.x0, self.y0)
        return Affine(r, 0, left - self.pad * r, 0, -r, top + self.pad * r)

    def bounds(self) -> tuple[float, float, float, float]:
        t = self.transform
        return (t.c, t.f - self.height * res(self.z), t.c + self.width * res(self.z), t.f)

    def lonlat_bounds(self) -> tuple[float, float, float, float]:
        l, b, r, t = self.bounds()
        lon = lambda mx: mx / R * 180 / math.pi
        lat = lambda my: math.degrees(math.atan(math.sinh(my / R)))
        return lon(l), lat(b), lon(r), lat(t)

    def tiles(self):
        for y in range(self.y0, self.y1 + 1):
            for x in range(self.x0, self.x1 + 1):
                r0 = self.pad + (y - self.y0) * TILE_SIZE
                c0 = self.pad + (x - self.x0) * TILE_SIZE
                yield x, y, (slice(r0, r0 + TILE_SIZE), slice(c0, c0 + TILE_SIZE))

    def ground_cell(self) -> float:
        """Taille au sol d'un pixel au centre de la grille (m)."""
        _, b, _, t = self.lonlat_bounds()
        return res(self.z) * math.cos(math.radians((b + t) / 2))
