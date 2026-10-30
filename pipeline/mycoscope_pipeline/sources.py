"""Téléchargement et lecture des données sources (exécuté dans GitHub Actions).

- Contours des départements : france-geojson (G. David, données IGN Admin Express)
- BD Forêt® V2 (IGN, Licence Ouverte) : API de téléchargement de la Géoplateforme
- BD Charm-50 (BRGM) : cartes géologiques harmonisées 1/50 000
- SoilGrids 2.0 (ISRIC, CC-BY 4.0) : pH eau 0-5 cm, 250 m
"""
from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path

import numpy as np
import requests

UA = {"User-Agent": "MycoScope-pipeline (+https://github.com/philippe-steer/MycoScope)"}
DEPTS_URL = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson"
GEOPF = "https://data.geopf.fr/telechargement"
CHARM_URL = "http://infoterre.brgm.fr/telechargements/BDCharm50/GEO050K_HARM_{code}.zip"
CHARM_ALIASES = {"75": "075", "92": "075", "93": "075", "94": "075", "2A": "020", "2B": "020"}
SOILGRIDS_PH = "https://files.isric.org/soilgrids/latest/data/phh2o/phh2o_0-5cm_mean.vrt"


def _get(url: str, dest: Path | None = None, timeout=600) -> bytes | Path:
    r = requests.get(url, headers=UA, timeout=timeout, stream=dest is not None)
    r.raise_for_status()
    if dest is None:
        return r.content
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return dest


# ------------------------------------------------------------------ départements
def departments(cache: Path):
    import geopandas as gpd
    p = cache / "departements.geojson"
    if not p.exists():
        _get(DEPTS_URL, p)
    return gpd.read_file(p).set_index("code")


# ------------------------------------------------------------------ BD Forêt V2
def bdforet_files(dep: str) -> list[str]:
    """URLs des archives BD Forêt V2 les plus récentes pour un département (ex. '35', '2A')."""
    zone = f"D{dep.zfill(3)}"
    txt = _get(f"{GEOPF}/resource/BDFORET?zone={zone}&limit=50").decode()
    subs = sorted(set(re.findall(r"BDFORET_2-0__SHP_[A-Z0-9]+_" + zone + r"_\d{4}-\d{2}-\d{2}", txt)))
    if not subs:
        raise RuntimeError(f"BD Forêt V2 introuvable pour {zone}")
    sub = max(subs, key=lambda s: s[-10:])
    listing = _get(f"{GEOPF}/resource/BDFORET/{sub}?limit=50").decode()
    files = sorted(set(re.findall(re.escape(sub) + r"[^\"<>\s/]*\.7z(?:\.\d{3})?", listing)))
    files = [f for f in files if f != sub]
    if not files:
        files = [sub + ".7z"]
    return [f"{GEOPF}/download/BDFORET/{sub}/{f}" for f in files]


def load_bdforet(dep: str, work: Path):
    import geopandas as gpd
    import py7zr
    d = work / f"bdforet_{dep}"
    if not d.exists():
        d.mkdir(parents=True)
        parts = [_get(u, d / u.rsplit("/", 1)[1]) for u in bdforet_files(dep)]
        archive = d / "all.7z"
        with open(archive, "wb") as out:          # archives multi-volumes : simple concaténation
            for p in sorted(parts):
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out)
        with py7zr.SevenZipFile(archive) as z:
            z.extractall(d / "x")
        for p in parts + [archive]:
            p.unlink()
    shp = [p for p in (d / "x").rglob("*.shp") if "FORMATION_VEGETALE" in p.name.upper()]
    if not shp:
        raise RuntimeError(f"FORMATION_VEGETALE.shp absent ({dep})")
    gdf = gpd.read_file(shp[0])
    cols = {c.upper(): c for c in gdf.columns}
    tfv = gdf[cols["TFV"]] if "TFV" in cols else None
    ess = gdf[cols["ESSENCE"]] if "ESSENCE" in cols else None
    from .encoding import forest_class
    gdf["cls"] = [forest_class(tfv.iloc[i] if tfv is not None else None,
                               ess.iloc[i] if ess is not None else None) for i in range(len(gdf))]
    return gdf[["cls", "geometry"]]


# ------------------------------------------------------------------ BD Charm-50
def load_charm(dep: str, work: Path):
    import geopandas as gpd
    from .encoding import litho_class
    d = work / f"charm_{dep}"
    if not d.exists():
        d.mkdir(parents=True)
        codes = [dep.zfill(3)] + ([CHARM_ALIASES[dep]] if dep in CHARM_ALIASES else [])
        for c in codes:
            try:
                data = _get(CHARM_URL.format(code=c))
                zipfile.ZipFile(io.BytesIO(data)).extractall(d)
                break
            except Exception as e:  # noqa: BLE001
                print(f"::warning title=BD Charm {dep}::{c}: {type(e).__name__} {e}"[:900])
    shp = [p for p in d.rglob("*.shp") if "S_FGEOL" in p.name.upper()]
    if not shp:
        names = [p.name for p in d.rglob("*")][:15]
        print(f"::warning title=BD Charm {dep}::pas de couche S_FGEOL ; fichiers : {names}")
        return None
    gdf = gpd.read_file(shp[0])
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:2154")
    cols = list(gdf.columns)
    prio = [c for c in cols if c.upper().startswith("LITHO")] + \
           [c for c in cols if c.upper() in ("DESCR", "DESCRIPTIO", "LEGENDE", "LIBELLE")]
    gdf["cls"] = [litho_class(*[str(row[c]) for c in prio if row[c] is not None])
                  for _, row in gdf.iterrows()]
    from collections import Counter
    top = Counter(gdf["cls"]).most_common(6)
    print(f"::notice title=BD Charm {dep}::{len(gdf)} polygones, colonnes {prio}, classes {top}")
    return gdf[["cls", "geometry"]]


# ------------------------------------------------------------------ SoilGrids pH
def load_ph(grid) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    with rasterio.open("/vsicurl/" + SOILGRIDS_PH) as src, \
            WarpedVRT(src, crs="EPSG:3857", transform=grid.transform, width=grid.width,
                      height=grid.height, resampling=Resampling.bilinear,
                      src_nodata=-32768, nodata=np.nan, dtype="float32") as vrt:
        a = vrt.read(1)
    a = a / 10.0
    a[(a <= 0) | (a > 14)] = np.nan
    return a
