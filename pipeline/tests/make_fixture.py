"""Génère app/src/test/resources/model_fixture.json : entrées + sorties attendues du modèle de
référence Python, relues par le test unitaire Kotlin (ModelParityTest)."""
import json
from pathlib import Path

import numpy as np

from mycoscope_pipeline import encoding as enc
from mycoscope_pipeline.model import Weather, fruiting, habitat, load_species

ROOT = Path(__file__).resolve().parents[2]


def weather():
    rng = np.random.default_rng(42)
    n = 68
    doy = np.arange(230, 230 + n)
    precip = np.round(np.where(rng.random(n) < 0.3, rng.gamma(1.5, 8, n), 0.0), 1)
    tmean = np.round(19 - 0.12 * np.arange(n) + rng.normal(0, 1.5, n), 1)
    tmin = np.round(tmean - 5 - rng.random(n) * 3, 1)
    tmin[60] = -4.0
    et0 = np.round(np.clip(3.5 - 0.04 * np.arange(n), 0.5, None), 2)
    return Weather(doy, precip, tmean, tmin, et0, 250.0)


def main():
    sp = load_species()
    w = weather()
    cases = []
    for s in sp:
        for elev, dm in ((250.0, 0.0), (900.0, -0.125), (50.0, 0.25)):
            cases.append({"species": s["id"], "elev": elev, "dm": dm,
                          "f": [round(float(v), 6) for v in fruiting(s, w, elev, dm)]})
    hab = []
    rng = np.random.default_rng(1)
    for s in sp:
        for _ in range(20):
            fo = int(rng.choice(list(enc.FOREST.values())))
            li, ph = int(rng.integers(0, 17)), int(rng.integers(0, 8))
            el = float(rng.integers(0, 120) * 20)
            hab.append({"species": s["id"], "forest": fo, "litho": li, "phc": ph, "elev": el,
                        "h": round(float(habitat(s, np.array([fo]), np.array([li]), np.array([ph]),
                                                 np.array([el]))[0]), 6)})
    fx = {"weather": {"doy": w.doy.tolist(), "precip": w.precip.tolist(), "tmean": w.tmean.tolist(),
                      "tmin": w.tmin.tolist(), "et0": w.et0.tolist(), "elevation": w.elevation},
          "fruiting": cases, "habitat": hab}
    p = ROOT / "app/src/test/resources/model_fixture.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fx), encoding="utf-8")
    print(p, len(cases), len(hab))


if __name__ == "__main__":
    main()


def sample_pmtiles():
    """Petit PMTiles synthétique + quelques tuiles attendues, pour tester le lecteur Kotlin."""
    import hashlib
    import subprocess
    import sys
    import tempfile
    sys.path.insert(0, str(Path(__file__).parent))
    from test_pipeline import fake_dept
    from pmtiles.reader import MmapSource
    res = ROOT / "app/src/test/resources"
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        fake_dept(-1.70, 48.00, -1.55, 48.06, t / "a")
        out = res / "sample.pmtiles"
        subprocess.check_call([sys.executable, "-m", "mycoscope_pipeline.merge", str(t / "a"), "-o", str(out)],
                              cwd=ROOT / "pipeline")
    exp = []
    with open(out, "rb") as f:
        from pmtiles.reader import all_tiles
        for (z, x, y), data in list(all_tiles(MmapSource(f)))[::3]:
            exp.append({"z": z, "x": x, "y": y, "sha1": hashlib.sha1(data).hexdigest()})
    (res / "sample_tiles.json").write_text(json.dumps(exp))
    print(out, out.stat().st_size, len(exp))


if __name__ == "__main__":
    sample_pmtiles()
