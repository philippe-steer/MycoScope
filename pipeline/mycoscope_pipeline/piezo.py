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
            "format": "json", "size": 5000, "page": page})
        r.raise_for_status()
        d = r.json()
        if page == 1 and d.get("data"):
            ex = d["data"][0]
            print(f"::notice title=Hub'Eau stations::{d.get('count')} stations ; champs {sorted(ex)[:40]}")
        for s in d.get("data", []):
            s["x"] = s.get("x") or s.get("longitude")
            s["y"] = s.get("y") or s.get("latitude")
            out.append(s)
        if not d.get("next"):
            break
        page += 1
    return [s for s in out if s.get("x") and s.get("y") and (s.get("date_fin_mesure") or "") >= since
            and (s.get("nb_mesures_piezo") or 0) > 365 * MIN_YEARS]


def monthly_quantiles(code: str, keep: bool = False):
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
    q = [[round(float(np.percentile(m, q)), 2) for q in (10, 50, 90)] for m in by_month]
    if not keep:
        return q
    d0 = dt.date(2000, 1, 1)
    ser = [((dt.date.fromisoformat(d["date_mesure"][:10]) - d0).days, d["niveau_nappe_eau"])
           for d in data if d.get("niveau_nappe_eau") is not None]
    return q, ser


def main():
    out = Path(sys.argv[1])
    hist = Path(sys.argv[2]) if len(sys.argv) > 2 else None   # historique complet (calage)
    st = stations()
    print(f"{len(st)} stations candidates")
    res = {}
    series = {}
    with ThreadPoolExecutor(6) as ex:
        for s, r in zip(st, ex.map(lambda s: monthly_quantiles(s["code_bss"], keep=hist is not None), st)):
            if not r:
                continue
            q, ser = r if hist is not None else (r, None)
            res[s["code_bss"]] = {"lat": round(s["y"], 5), "lon": round(s["x"], 5), "q": q}
            if ser:
                series[s["code_bss"]] = ser
    out.write_text(json.dumps({"built": dt.date.today().isoformat(), "stations": res},
                              separators=(",", ":")), encoding="utf-8")
    print(f"{len(res)} stations écrites dans {out}")
    if hist is not None:
        codes = sorted(series)
        days = [np.array([d for d, _ in series[c]], np.int32) for c in codes]
        vals = [np.array([v for _, v in series[c]], np.float32) for c in codes]
        np.savez_compressed(hist, codes=np.array(codes), lat=np.array([res[c]["lat"] for c in codes]),
                            lon=np.array([res[c]["lon"] for c in codes]),
                            q=np.array([res[c]["q"] for c in codes], np.float32),
                            offsets=np.cumsum([0] + [len(d) for d in days]),
                            days=np.concatenate(days), values=np.concatenate(vals))
        print(f"::notice title=Nappes::historique de {len(codes)} stations ({sum(map(len, days))} mesures)")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:  # noqa: BLE001
        tb = " | ".join(traceback.format_exc().strip().splitlines()[-6:])
        print(f"::error title=Nappes::{type(e).__name__}: {tb}"[:1800])
        raise
