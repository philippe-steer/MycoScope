"""Statistiques mensuelles des piézomètres (Hub'Eau / ADES) → app/src/main/assets/piezo_stats.json

Pour chaque station active : position et quantiles 10/50/90 % du niveau (m NGF) par mois sur
les 15 dernières années. L'appli compare le dernier niveau mesuré à ces quantiles pour obtenir
une anomalie de nappe entre -1 (très basse) et +1 (très haute).

python -m mycoscope_pipeline.piezo app/src/main/assets/piezo_stats.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

API = "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes"
UA = {"User-Agent": "MycoScope-pipeline (+https://github.com/philippe-steer/MycoScope)"}
YEARS = 15
MIN_YEARS = 5


def stations() -> list[dict]:
    out, page = [], 1
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    while True:
        r = requests.get(f"{API}/stations", headers=UA, timeout=120, params={
            "format": "json", "size": 5000, "page": page,
            "fields": "code_bss,x,y,date_fin_mesure,nb_mesures_piezo"})
        r.raise_for_status()
        d = r.json()
        out += d.get("data", [])
        if not d.get("next"):
            break
        page += 1
    return [s for s in out if s.get("x") and s.get("y") and (s.get("date_fin_mesure") or "") >= since
            and (s.get("nb_mesures_piezo") or 0) > 365 * MIN_YEARS]


def monthly_quantiles(code: str):
    start = (dt.date.today() - dt.timedelta(days=365 * YEARS)).isoformat()
    for attempt in range(3):
        try:
            r = requests.get(f"{API}/chroniques", headers=UA, timeout=120, params={
                "code_bss": code, "date_debut_mesure": start, "size": 20000,
                "fields": "date_mesure,niveau_nappe_eau"})
            r.raise_for_status()
            data = r.json().get("data", [])
            break
        except Exception:  # noqa: BLE001
            time.sleep(5 * (attempt + 1))
    else:
        return None
    by_month = [[] for _ in range(12)]
    for d in data:
        v = d.get("niveau_nappe_eau")
        if v is None:
            continue
        by_month[int(d["date_mesure"][5:7]) - 1].append(v)
    if min(len(m) for m in by_month) < 10 * MIN_YEARS / 5:
        return None
    return [[round(float(np.percentile(m, q)), 2) for q in (10, 50, 90)] for m in by_month]


def main():
    out = Path(sys.argv[1])
    st = stations()
    print(f"{len(st)} stations candidates")
    res = {}
    with ThreadPoolExecutor(6) as ex:
        for s, q in zip(st, ex.map(lambda s: monthly_quantiles(s["code_bss"]), st)):
            if q:
                res[s["code_bss"]] = {"lat": round(s["y"], 5), "lon": round(s["x"], 5), "q": q}
    out.write_text(json.dumps({"built": dt.date.today().isoformat(), "stations": res},
                              separators=(",", ":")), encoding="utf-8")
    print(f"{len(res)} stations écrites dans {out}")


if __name__ == "__main__":
    main()
