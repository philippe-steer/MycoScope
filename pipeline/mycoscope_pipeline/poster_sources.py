"""Sources des posters régionaux (exécuté dans GitHub Actions) : MNT Copernicus 30 m sur la
grille Web-Mercator z12 de chaque région, contours des départements, forêts publiques ONF.

python -m mycoscope_pipeline.poster_sources out_dir
"""
import json
import sys
from pathlib import Path

import numpy as np
import requests

from .grid import TileGrid
from .terrain import load_dem

REGIONS = {
    "bretagne": (-5.25, 47.20, -0.95, 48.95),
    "rhone_alpes": (3.65, 44.08, 7.25, 46.58),
}
GEO = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/"
UA = {"User-Agent": "MycoScope-poster (+https://github.com/philippe-steer/MycoScope)"}


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for f in ("departements-version-simplifiee.geojson", "regions-version-simplifiee.geojson", "departements.geojson"):
        r = requests.get(GEO + f, headers=UA, timeout=300)
        r.raise_for_status()
        (out / f).write_bytes(r.content)
    for name, (w, s, e, n) in REGIONS.items():
        g = TileGrid.from_lonlat_bounds(w, s, e, n, 12, pad_m=0)
        dem = load_dem(g)
        np.savez_compressed(out / f"dem_{name}.npz", dem=np.where(np.isfinite(dem), np.round(dem), -9999).astype(np.int16),
                            x0=g.x0, y0=g.y0, x1=g.x1, y1=g.y1, z=12)
        print(f"::notice title=MNT {name}::{g.width}×{g.height}")
        # forêts publiques ONF (WFS Géoplateforme), facultatif
        try:
            cap = requests.get("https://data.geopf.fr/wfs/ows?SERVICE=WFS&REQUEST=GetCapabilities", headers=UA, timeout=300).text
            import re
            names = sorted(set(re.findall(r"<Name>([^<]*(?:FORET|foret)[^<]*PUBLI[^<]*)</Name>", cap, re.I)))
            print(f"::notice title=WFS forêts::{names[:10]}")
            feats = []
            for tn in names[:1]:
                start = 0
                while True:
                    r = requests.get("https://data.geopf.fr/wfs/ows", headers=UA, timeout=300, params={
                        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": tn,
                        "BBOX": f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326", "OUTPUTFORMAT": "application/json",
                        "SRSNAME": "EPSG:4326", "COUNT": 2000, "STARTINDEX": start})
                    r.raise_for_status()
                    d = r.json()
                    feats += d.get("features", [])
                    if len(d.get("features", [])) < 2000:
                        break
                    start += 2000
            (out / f"forets_publiques_{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
            print(f"::notice title=Forêts publiques {name}::{len(feats)} entités")
        except Exception as ex:  # noqa: BLE001
            print(f"::warning title=Forêts publiques {name}::{type(ex).__name__} {ex}"[:500])


if __name__ == "__main__":
    main()
