"""Construit les tuiles z12 d'un département : python -m mycoscope_pipeline.build_dept 35 out/"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio import features

from . import encoding as enc
from .grid import TileGrid
from .terrain import load_dem, slope_aspect, twi


def rasterize(gdf, grid, fill=0) -> np.ndarray:
    g = gdf.to_crs("EPSG:3857")
    shapes = ((geom, int(c)) for geom, c in zip(g.geometry, g["cls"]) if geom is not None)
    return features.rasterize(shapes, out_shape=(grid.height, grid.width), transform=grid.transform,
                              fill=fill, dtype="uint8")


def build_arrays(grid, dept_geom, forest_gdf, litho_gdf, dem, ph):
    """Assemble le tableau RGBA (h, w, 4) — séparé des téléchargements pour les tests."""
    import geopandas as gpd
    inside = features.rasterize([(gpd.GeoSeries([dept_geom], crs="EPSG:4326").to_crs("EPSG:3857")[0], 1)],
                                out_shape=(grid.height, grid.width), transform=grid.transform,
                                fill=0, dtype="uint8").astype(bool)
    forest = rasterize(forest_gdf, grid, fill=enc.FOREST["open"])
    forest[~inside] = 0
    litho = rasterize(litho_gdf, grid, fill=0) if litho_gdf is not None else np.zeros_like(forest)
    cell = grid.ground_cell()
    slope, aspect = slope_aspect(dem, cell)
    t = twi(dem, cell)
    return enc.pack(forest, litho, enc.ph_class(ph), enc.twi_class(t),
                    enc.aspect_class(aspect, slope), enc.elev_code(dem))


def write_tiles(rgba: np.ndarray, grid, out: Path) -> int:
    n = 0
    for x, y, sl in grid.tiles():
        tile = rgba[sl]
        if not tile[..., 0].any():
            continue
        p = out / str(grid.z) / str(x) / f"{y}.webp"
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(tile, "RGBA").save(p, "WEBP", lossless=True, quality=100, method=6, exact=True)
        n += 1
    return n


def main():
    from . import sources
    ap = argparse.ArgumentParser()
    ap.add_argument("dept")
    ap.add_argument("out", type=Path)
    ap.add_argument("--work", type=Path, default=Path("work"))
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    depts = sources.departments(a.work)
    geom = depts.loc[a.dept].geometry
    w, s, e, n = geom.bounds
    grid = TileGrid.from_lonlat_bounds(w, s, e, n, enc.TILE_ZOOM)
    print(f"{a.dept}: grille {grid.width}×{grid.height}")
    forest = sources.load_bdforet(a.dept, a.work)
    print(f"  BD Forêt : {len(forest)} polygones ({time.time()-t0:.0f}s)")
    litho = sources.load_charm(a.dept, a.work)
    print(f"  BD Charm : {0 if litho is None else len(litho)} polygones ({time.time()-t0:.0f}s)")
    dem = load_dem(grid)
    print(f"  MNT ok ({time.time()-t0:.0f}s)")
    ph = sources.load_ph(grid)
    print(f"  pH ok ({time.time()-t0:.0f}s)")
    rgba = build_arrays(grid, geom, forest, litho, dem, ph)
    k = write_tiles(rgba, grid, a.out)
    print(f"  {k} tuiles écrites ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
