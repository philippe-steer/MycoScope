"""Exécution complète du calage sur données synthétiques (sans réseau)."""
import datetime as dt
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer

from mycoscope_pipeline.calib import run as R
from mycoscope_pipeline.calib import sample
from mycoscope_pipeline.calib.fastmodel import fruiting_one, params_from_species
from mycoscope_pipeline.model import load_species


def test_run_synthetic(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    sp = {s["id"]: s for s in load_species()}
    tr = Transformer.from_crs("EPSG:4326", "EPSG:27572", always_xy=True)
    back = Transformer.from_crs("EPSG:27572", "EPSG:4326", always_xy=True)
    day0 = dt.date(1999, 1, 1)
    nd = (dt.date(2010, 12, 31) - day0).days + 1
    lat_c, lon_c = rng.uniform(46, 48, 40), rng.uniform(-1, 3, 40)
    x, y = tr.transform(lon_c, lat_c)
    x, y = np.round(x / 8000) * 8000 + 600 % 80 * 100, np.round(y / 8000) * 8000
    lon_c, lat_c = back.transform(x, y)
    doy = np.array([(day0 + dt.timedelta(days=k)).timetuple().tm_yday for k in range(nd)])
    data = np.zeros((40, nd, 4), np.float32)
    rows = []
    for c in range(40):
        tm = 11 - 8 * np.cos(2 * np.pi * (doy - 20) / 365) + rng.normal(0, 2, nd)
        P = np.where(rng.random(nd) < 0.33, rng.gamma(1.2, 7, nd), 0.0)
        E = np.clip(1.8 - 1.5 * np.cos(2 * np.pi * (doy - 20) / 365), 0.2, None)
        data[c, :, 0], data[c, :, 1], data[c, :, 2], data[c, :, 3] = P, tm, tm - 5, E
        for sid in ("cepe_bordeaux", "girolle"):
            Fz = fruiting_one(params_from_species(sp[sid]), P, tm, tm - 5, E, doy, 200.0, 200.0, 0.0)
            for d in np.nonzero(rng.random(nd) < Fz * 0.01)[0]:
                if 200 < d < nd - 30:
                    rows.append([sid, "x", 0, str(day0 + dt.timedelta(days=int(d))), lat_c[c] + 0.01, lon_c[c] + 0.01,
                                 100, "ds", "HUMAN_OBSERVATION"])
    pd.DataFrame(rows, columns=["species", "taxon", "gbif_id", "date", "lat", "lon", "uncert_m", "dataset", "basis"]
                 ).to_csv(tmp_path / "occ.csv", index=False)
    np.savez_compressed(tmp_path / "sim2.npz", x=x, y=y, lat=lat_c, lon=lon_c, day0=str(day0), data=data,
                        vars=["P", "T", "TN", "ETP"])
    monkeypatch.setattr(sample, "dem_points", lambda la, lo: np.full(len(la), 200.0))
    monkeypatch.setattr(sample, "dem_box_means", lambda la, lo: np.full(len(la), 200.0))

    def fake_px(path, la, lo):
        px = np.zeros((len(la), 4), np.uint8)
        px[:, 0] = rng.choice([10, 12, 21, 26], len(la))
        px[:, 1] = (rng.choice([1, 5, 7], len(la)) << 3) | 4
        px[:, 2] = (7 << 4) | 3
        px[:, 3] = 12
        return px
    monkeypatch.setattr(sample, "habitat_pixels", fake_px)
    (tmp_path / "f.pmtiles").write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", ["run", "--occ", str(tmp_path / "occ.csv"), "--sim2", str(tmp_path / "sim2.npz"),
                                      "--pmtiles", str(tmp_path / "f.pmtiles"), "--out", str(tmp_path / "out"),
                                      "--species", "cepe_bordeaux,girolle"])
    monkeypatch.setattr(R, "MIN_OBS", 30)
    R.main()
    rep = (tmp_path / "out/report.md").read_text()
    print(rep)
    assert "Cèpe de Bordeaux" in rep
    assert (tmp_path / "out/figures/cepe_bordeaux.png").exists()
    assert (tmp_path / "out/species_calibrated.json").exists()
