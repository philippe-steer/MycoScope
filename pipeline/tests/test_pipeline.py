"""Test de bout en bout sur données synthétiques (pas de réseau) : python -m pytest pipeline/tests"""
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import zxy_to_tileid
from shapely.geometry import box

from mycoscope_pipeline import encoding as enc
from mycoscope_pipeline.build_dept import build_arrays, write_tiles
from mycoscope_pipeline.grid import TileGrid, lonlat_to_tile
from mycoscope_pipeline.merge import decode


def fake_dept(w, s, e, n, out: Path):
    geom = box(w, s, e, n)
    grid = TileGrid.from_lonlat_bounds(w, s, e, n, enc.TILE_ZOOM, pad_m=2000)
    forest = gpd.GeoDataFrame({"cls": [enc.FOREST["hetre"], enc.FOREST["sapin_epicea"]]},
                              geometry=[box(w, s, (w + e) / 2, n), box((w + e) / 2, s, e, (s + n) / 2)],
                              crs="EPSG:4326")
    litho = gpd.GeoDataFrame({"cls": [enc.LITHO["calcaire"]]}, geometry=[geom], crs="EPSG:4326")
    yy, xx = np.mgrid[0:grid.height, 0:grid.width]
    dem = (300 + 0.5 * np.abs(xx - grid.width / 2) + 0.1 * yy).astype(np.float32)
    ph = np.full(dem.shape, 6.8, np.float32)
    rgba = build_arrays(grid, geom, forest, litho, dem, ph)
    return write_tiles(rgba, grid, out), rgba


def test_end_to_end(tmp_path):
    n1, rgba = fake_dept(-1.70, 48.00, -1.55, 48.10, tmp_path / "a")
    n2, _ = fake_dept(-1.55, 48.00, -1.40, 48.10, tmp_path / "b")
    assert n1 > 0 and n2 > 0
    u = enc.unpack(rgba)
    v = u["valid"]
    assert set(np.unique(u["forest"][v])) <= {enc.FOREST["hetre"], enc.FOREST["sapin_epicea"], enc.FOREST["open"]}
    assert (u["litho"][v] == enc.LITHO["calcaire"]).all()
    assert (u["phc"][v] == 6).all()
    assert np.nanmin(u["elev"][v]) >= 280
    out = tmp_path / "fr.pmtiles"
    subprocess.check_call([sys.executable, "-m", "mycoscope_pipeline.merge", str(tmp_path / "a"),
                           str(tmp_path / "b"), "-o", str(out)], cwd=Path(__file__).parents[1])
    with open(out, "rb") as f:
        r = Reader(MmapSource(f))
        h = r.header()
        assert h["min_zoom"] == enc.MIN_ZOOM and h["max_zoom"] == enc.TILE_ZOOM
        # tuile à la frontière des deux départements : doit contenir les deux côtés
        x, y = lonlat_to_tile(-1.55, 48.05, enc.TILE_ZOOM)
        a = decode(r.get(enc.TILE_ZOOM, x, y))
        assert (a[..., 0] != 0).mean() > 0.5
        x5, y5 = lonlat_to_tile(-1.55, 48.05, 5)
        assert r.get(5, x5, y5) is not None
        meta = r.metadata()
        assert meta["format_version"] == enc.FORMAT_VERSION
