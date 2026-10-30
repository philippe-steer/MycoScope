"""Météo quotidienne SAFRAN-SIM2 (Météo-France, maille 8 km) aux mailles des observations.

python -m mycoscope_pipeline.calib.sim2 occurrences.csv sim2.npz --work work/
Sortie : mailles (x, y en hm Lambert II étendu, lat, lon), jours depuis 1999-01-01, et
tableau [maille, jour, variable] avec P = PRENEI + PRELIQ, T_Q, TINF_H_Q, ETP_Q.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

DATASET = "https://www.data.gouv.fr/api/1/datasets/donnees-changement-climatique-sim-quotidienne/"
UA = {"User-Agent": "MycoScope-calibration (+https://github.com/philippe-steer/MycoScope)"}
DAY0 = dt.date(1999, 1, 1)
START = dt.date(1999, 9, 1)
VARS = ["P", "T", "TN", "ETP"]
TO_L2E = Transformer.from_crs("EPSG:4326", "EPSG:27572", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:27572", "EPSG:4326", always_xy=True)


def resources():
    d = requests.get(DATASET, headers=UA, timeout=120).json()
    out = []
    this_year = dt.date.today().year
    for r in d.get("resources", []):
        name = (r.get("title") or "") + " " + (r.get("url") or "")
        if "QUOT_SIM2" not in name.upper() or not re.search(r"csv", name, re.I):
            continue
        m = re.search(r"QUOT_SIM2_(\d{4})(?:-(\d{4}))?", name, re.I)
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        elif re.search(r"latest|previous", name, re.I):
            a, b = this_year - 2, this_year
        else:
            continue
        if b >= START.year:
            out.append((a, b, r["url"]))
    print(f"::notice title=SIM2::{len(out)} fichiers : {[u.rsplit('/', 1)[-1] for _, _, u in out]}")
    return out


def stream(url, work: Path):
    p = work / url.rsplit("/", 1)[-1]
    if not p.exists():
        with requests.get(url, headers=UA, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                for c in r.iter_content(1 << 22):
                    f.write(c)
    op = gzip.open if p.suffix == ".gz" else open
    return op(p, "rt"), p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("occ")
    ap.add_argument("out")
    ap.add_argument("--work", type=Path, default=Path("work"))
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    occ = pd.read_csv(a.occ)
    res = sorted(resources())
    end = dt.date.today()
    nd = (end - DAY0).days + 1
    grid = None
    sel = None
    data = None
    for (_, _, url) in res:
        fh, path = stream(url, a.work)
        with fh:
            for chunk in pd.read_csv(fh, sep=";", chunksize=2_000_000, low_memory=False):
                chunk.columns = [c.strip().upper() for c in chunk.columns]
                if grid is None:
                    # grille régulière de 8 km (80 hm) : on recale les observations dessus
                    x0 = float(chunk.LAMBX.iloc[0]) % 80
                    y0 = float(chunk.LAMBY.iloc[0]) % 80
                    ox, oy = TO_L2E.transform(occ.lon.to_numpy(), occ.lat.to_numpy())
                    gx = x0 + 80 * np.round((ox / 100 - x0) / 80)
                    gy = y0 + 80 * np.round((oy / 100 - y0) / 80)
                    grid = np.unique(np.c_[gx, gy], axis=0)
                    sel = np.arange(len(grid))
                    cell_index = {(float(x), float(y)): k for k, (x, y) in enumerate(grid)}
                    data = np.full((len(grid), nd, len(VARS)), np.nan, np.float32)
                    print(f"::notice title=SIM2 grille::{len(grid)} mailles utiles (origine {x0}, {y0} hm)")
                keys = list(zip(chunk.LAMBX.to_numpy(float), chunk.LAMBY.to_numpy(float)))
                rows = np.array([cell_index.get(k, -1) for k in keys])
                m = rows >= 0
                if not m.any():
                    continue
                c = chunk[m]
                dates = pd.to_datetime(c.DATE.astype(str), format="%Y%m%d").dt.date
                di = np.array([(d - DAY0).days for d in dates])
                ok = (di >= (START - DAY0).days) & (di < nd)
                r, di = rows[m][ok], di[ok]
                c = c[ok]
                data[r, di, 0] = (c.PRENEI_Q.to_numpy(float) + c.PRELIQ_Q.to_numpy(float))
                data[r, di, 1] = c.T_Q.to_numpy(float)
                data[r, di, 2] = c.TINF_H_Q.to_numpy(float)
                data[r, di, 3] = c.ETP_Q.to_numpy(float)
        path.unlink()
        print(f"::notice title=SIM2 lu::{path.name} ; jours couverts {(np.isfinite(data[:, :, 1]).any(0)).sum()}")
    xy = grid[sel] * 100
    lon, lat = TO_WGS.transform(xy[:, 0], xy[:, 1])
    np.savez_compressed(a.out, x=xy[:, 0], y=xy[:, 1], lat=lat, lon=lon, day0=str(DAY0), data=data, vars=VARS)


if __name__ == "__main__":
    main()
