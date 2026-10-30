"""Téléchargement et lecture des données sources (exécuté dans GitHub Actions).

- Contours des départements : france-geojson (G. David, données IGN Admin Express)
- BD Forêt® V2 (IGN, Licence Ouverte) : API de téléchargement de la Géoplateforme
- BD Charm-50 (BRGM) : cartes géologiques harmonisées 1/50 000 (miroir data.cquest.org)
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
# Miroir de C. Quest (le BRGM ne sert plus ces archives et filtre les accès automatiques)
CHARM_URL = "https://data.cquest.org/brgm/bd_charm_50/2019/GEO050K_HARM_{code}.zip"
IDF = "075_077_078_091_092_093_094_095"
CHARM_ALIASES = {"59": "059_062", "62": "059_062", "2A": "02A", "2B": "02B",
                 **{d: IDF for d in ("75", "77", "78", "91", "92", "93", "94", "95")}}
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
CHARM_RELEASE = "sources-charm"   # release du dépôt contenant les GEO050K_HARM_XXX.zip


def _fetch_charm(code: str, d: Path) -> bool:
    """Archive départementale BD Charm-50, par ordre de préférence :
    1. dossier local $MYCO_CHARM_DIR ; 2. release « sources-charm » du dépôt (gh, dans Actions) ;
    3. miroir data.cquest.org des archives 2019 du BRGM."""
    import os
    import subprocess
    name = f"GEO050K_HARM_{code}.zip"
    local = os.environ.get("MYCO_CHARM_DIR")
    if local and (Path(local) / name).exists():
        zipfile.ZipFile(Path(local) / name).extractall(d)
        return True
    if os.environ.get("GH_TOKEN") and os.environ.get("GITHUB_REPOSITORY"):
        r = subprocess.run(["gh", "release", "download", CHARM_RELEASE, "-R", os.environ["GITHUB_REPOSITORY"],
                            "-p", name, "-D", str(d), "--clobber"], capture_output=True, text=True)
        if r.returncode == 0 and (d / name).exists():
            zipfile.ZipFile(d / name).extractall(d)
            (d / name).unlink()
            return True
    try:
        data = _get(CHARM_URL.format(code=code))
        zipfile.ZipFile(io.BytesIO(data)).extractall(d)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"::warning title=BD Charm {code}::{type(e).__name__} {e}"[:600])
    return False


def load_charm(dep: str, work: Path):
    import geopandas as gpd
    from .encoding import litho_class
    d = work / f"charm_{dep}"
    if not d.exists():
        d.mkdir(parents=True)
        codes = [CHARM_ALIASES[dep]] if dep in CHARM_ALIASES else [dep.zfill(3)]
        for c in codes:
            if _fetch_charm(c, d):
                break
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
    """pH SoilGrids ; si le serveur ISRIC est indisponible, pH inconnu (classe 0, facteur neutre)."""
    import time
    for attempt in range(4):
        try:
            return _load_ph(grid)
        except Exception as e:  # noqa: BLE001
            print(f"::warning title=SoilGrids::tentative {attempt + 1} : {type(e).__name__} {e}"[:400])
            time.sleep(60 * (attempt + 1))
    print("::warning title=SoilGrids::pH indisponible pour ce département (repli : pH inconnu)")
    return np.full((grid.height, grid.width), np.nan, np.float32)


def _load_ph(grid) -> np.ndarray:
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
