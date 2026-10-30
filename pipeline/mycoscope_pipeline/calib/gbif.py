"""Observations datées GBIF (France métropolitaine) des espèces de MycoScope.

GBIF agrège l'INPN / OpenObs, les sociétés mycologiques et les plateformes participatives.
python -m mycoscope_pipeline.calib.gbif occurrences.csv
"""
from __future__ import annotations

import csv
import sys
import time

import requests

API = "https://api.gbif.org/v1"
UA = {"User-Agent": "MycoScope-calibration (+https://github.com/philippe-steer/MycoScope)"}
YEARS = range(2000, 2026)

TAXA = {
    "cepe_bordeaux": ["Boletus edulis"],
    "cepe_thermophile": ["Boletus reticulatus", "Boletus aereus"],
    "cepe_pins": ["Boletus pinophilus"],
    "bolet_bai": ["Imleria badia"],
    "girolle": ["Cantharellus cibarius", "Cantharellus pallens"],
    "trompette": ["Craterellus cornucopioides"],
    "chanterelle_tube": ["Craterellus tubaeformis"],
    "chanterelle_jaunissante": ["Craterellus lutescens"],
    "pied_mouton": ["Hydnum repandum", "Hydnum rufescens"],
    "lactaire_delicieux": ["Lactarius deliciosus", "Lactarius sanguifluus", "Lactarius deterrimus"],
    "morille": ["Morchella"],
    "coulemelle": ["Macrolepiota procera"],
}


def get(url, params=None):
    for i in range(6):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=120)
            if r.status_code == 429:
                time.sleep(30 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"GBIF inaccessible : {url} {params}")


def taxon_key(name: str) -> int:
    d = get(f"{API}/species/match", {"name": name, "kingdom": "Fungi", "strict": "false"})
    k = d.get("acceptedUsageKey") or d.get("usageKey")
    if not k:
        raise RuntimeError(f"taxon introuvable : {name}")
    print(f"::notice title=GBIF taxon::{name} → {k} ({d.get('scientificName')}, {d.get('rank')}, {d.get('matchType')})")
    return int(k)


def occurrences(key: int, year: int):
    off = 0
    while True:
        d = get(f"{API}/occurrence/search", {
            "taxonKey": key, "country": "FR", "year": year, "hasCoordinate": "true",
            "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT", "limit": 300, "offset": off})
        for o in d.get("results", []):
            yield o
        off += 300
        if d.get("endOfRecords", True) or off >= 99_900:
            break


def main():
    out = sys.argv[1]
    n = 0
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["species", "taxon", "gbif_id", "date", "lat", "lon", "uncert_m", "dataset", "basis"])
        for sid, names in TAXA.items():
            ns = 0
            for name in names:
                key = taxon_key(name)
                for y in YEARS:
                    for o in occurrences(key, y):
                        ev = o.get("eventDate") or ""
                        if len(ev) < 10 or not ev[:10].replace("-", "").isdigit():
                            continue
                        if "/" in ev and ev.split("/")[0][:10] != ev.split("/")[-1][:10]:
                            continue  # intervalle de dates
                        lat, lon = o.get("decimalLatitude"), o.get("decimalLongitude")
                        if lat is None or not (41 < lat < 51.5 and -5.5 < lon < 10):
                            continue
                        w.writerow([sid, name, o.get("key"), ev[:10], round(lat, 5), round(lon, 5),
                                    o.get("coordinateUncertaintyInMeters") or "", o.get("datasetKey"),
                                    o.get("basisOfRecord")])
                        ns += 1
            print(f"::notice title=GBIF {sid}::{ns} observations datées")
            n += ns
    print(f"{n} observations écrites dans {out}")


if __name__ == "__main__":
    main()
