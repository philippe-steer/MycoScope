"""Implémentation de référence du modèle MycoScope (habitat statique × fructification).

L'appli Android (Model.kt) reproduit exactement ces calculs ; tests/test_model.py fige
quelques valeurs pour détecter toute divergence. Unités : °C, mm, humidité relative du
réservoir 0-1, altitudes en m.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .encoding import BROADLEAF, CONIFER, FOREST, LITHO, PH_CENTERS, TWI_MIN

LAPSE = -0.0065            # °C / m
SOIL_TAU = 4.0             # jours : inertie de la température du sol (~10 cm)
BUCKET_MM = 120.0          # réserve utile d'un sol forestier moyen
BUCKET_START = 0.5         # remplissage initial (60 jours avant : peu d'influence)
SEASON_RAMP = 20.0         # jours de transition en début/fin de saison
FROST_RECOVERY = 5.0       # jours
TWI_REF = 7.0
TWI_GAIN = 0.03            # humidité relative par unité de TWI
DM_MAX = 0.25
GW_GAIN = 0.15             # effet d'une nappe haute/basse dans les fonds humides
ELEV_BANDS = np.arange(0.0, 3001.0, 100.0)
DM_LEVELS = np.array([-0.25, -0.125, 0.0, 0.125, 0.25])
# décalage d'altitude effective par exposition (versant sud plus chaud → « plus bas »)
ASPECT_DZ = [0.0, 120.0, 80.0, 0.0, -80.0, -120.0, -80.0, 0.0, 80.0]

SPECIES_FILE = Path(__file__).resolve().parents[2] / "app/src/main/assets/species.json"


def load_species(path: Path = SPECIES_FILE) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["species"]


def trap(x, a, b, c, d):
    """Trapèze 0→1→1→0 sur [a, b, c, d] (accepte a == b ou c == d)."""
    x = np.asarray(x, dtype=float)
    up = np.where(b > a, (x - a) / max(b - a, 1e-9), (x >= a).astype(float))
    down = np.where(d > c, (d - x) / max(d - c, 1e-9), (x <= d).astype(float))
    return np.clip(np.minimum(np.minimum(up, down), 1.0), 0.0, 1.0)


# ===================================================================== habitat
def host_table(sp: dict) -> np.ndarray:
    """Affinité 0-1 pour chacune des 256 valeurs du canal R."""
    h = sp["habitat"]["hosts"]
    t = np.zeros(256)
    for name, code in FOREST.items():
        if name in h:
            t[code] = h[name]
    mb = max([t[c] for c in BROADLEAF] + [0.0])
    mc = max([t[c] for c in CONIFER] + [0.0])
    fallback = {
        "feuillus_melange": 0.9 * mb,
        "mixte_feuillus": max(0.9 * mb, 0.7 * mc),
        "mixte_coniferes": max(0.7 * mb, 0.9 * mc),
        "ouverte_feuillus": 0.6 * mb,
        "ouverte_coniferes": 0.6 * mc,
        "ouverte_mixte": 0.6 * max(mb, mc),
        "coupe": 0.1 * max(mb, mc),
    }
    for name, v in fallback.items():
        if name not in h:
            t[FOREST[name]] = v
    t[0] = 0.0
    return t


def litho_table(sp: dict) -> np.ndarray:
    hab = sp["habitat"]
    t = np.full(32, hab.get("litho_default", 0.7))
    for name, code in LITHO.items():
        if name in hab["litho"]:
            t[code] = hab["litho"][name]
    return t


def ph_table(sp: dict) -> np.ndarray:
    hab = sp["habitat"]
    fl = hab.get("ph_floor", 0.4)
    t = np.array([fl + (1 - fl) * float(trap(PH_CENTERS[c], *hab["ph"])) for c in range(8)])
    t[0] = (1 + fl) / 2  # pH inconnu : neutre
    return t


def habitat(sp: dict, forest, litho, phc, elev) -> np.ndarray:
    """Indice d'habitat 0-1 (tableaux décodés de la tuile)."""
    e = np.nan_to_num(np.asarray(elev, float), nan=-9999.0)
    return (host_table(sp)[forest] * litho_table(sp)[litho] * ph_table(sp)[phc]
            * trap(e, *sp["habitat"]["elev"]))


def moisture_offset(twic, gw_anomaly=0.0):
    """Décalage d'humidité locale : TWI (classe 1-15) + anomalie de nappe régionale (-1..1)."""
    twic = np.asarray(twic)
    twi = np.where(twic > 0, TWI_MIN + twic - 0.5, TWI_REF)
    dm = TWI_GAIN * (twi - TWI_REF)
    w = np.clip((twi - 8.0) / 5.0, 0.0, 1.0)
    return np.clip(dm + GW_GAIN * np.asarray(gw_anomaly) * w, -DM_MAX, DM_MAX)


def effective_elev(elev, aspc):
    return np.asarray(elev, float) + np.asarray(ASPECT_DZ)[np.asarray(aspc)]


# ===================================================================== météo → fructification
@dataclass
class Weather:
    """Séries journalières en un point de grille (jours consécutifs)."""
    doy: np.ndarray        # jour de l'année (1-366)
    precip: np.ndarray     # mm/j
    tmean: np.ndarray      # °C
    tmin: np.ndarray       # °C
    et0: np.ndarray        # mm/j (FAO)
    elevation: float       # altitude du point de grille (m)


def bucket(w: Weather) -> np.ndarray:
    """Réservoir sol simple : humidité relative 0-1, évapotranspiration réduite sous stress."""
    n = len(w.precip)
    m = np.empty(n)
    s = BUCKET_START * BUCKET_MM
    for i in range(n):
        p = w.precip[i] if np.isfinite(w.precip[i]) else 0.0
        e = w.et0[i] if np.isfinite(w.et0[i]) else 0.0
        stress = min(1.0, s / (0.5 * BUCKET_MM))
        s = min(BUCKET_MM, max(0.0, s + p - e * stress))
        m[i] = s / BUCKET_MM
    return m


def rain_trigger(precip: np.ndarray, lag: float, sd: float) -> np.ndarray:
    """Pluie « au bon délai » : Σ P(t-τ)·exp(-½((τ-L)/σ)²)."""
    n = len(precip)
    tmax = int(math.ceil(lag + 3 * sd))
    k = np.exp(-0.5 * ((np.arange(tmax + 1) - lag) / sd) ** 2)
    p = np.nan_to_num(precip)
    out = np.zeros(n)
    for i in range(n):
        for tau in range(min(tmax, i) + 1):
            out[i] += p[i - tau] * k[tau]
    return out


def cold_shock(tmean: np.ndarray, lag: float, sd: float) -> np.ndarray:
    """Baisse de température (moyenne 3 j avant − 3 j après) autour du délai de fructification."""
    n = len(tmean)
    t = np.nan_to_num(tmean)
    drop = np.full(n, -99.0)
    for j in range(3, n - 2):
        drop[j] = t[j - 3:j].mean() - t[j:j + 3].mean()
    out = np.zeros(n)
    lo, hi = int(max(0, round(lag - sd))), int(round(lag + sd))
    for i in range(n):
        best = 0.0
        for tau in range(lo, hi + 1):
            if i - tau >= 0:
                best = max(best, drop[i - tau])
        out[i] = best
    return out


def season(doy: np.ndarray, start: float, end: float) -> np.ndarray:
    d = np.asarray(doy, float)
    if end < start:  # saison à cheval sur le 1er janvier
        d = np.where(d < start - SEASON_RAMP, d + 365, d)
        end = end + 365
    return trap(d, start - SEASON_RAMP, start, end, end + SEASON_RAMP)


def soil_temp(tair: np.ndarray) -> np.ndarray:
    a = 1 - math.exp(-1 / SOIL_TAU)
    t = np.nan_to_num(tair, nan=float(np.nanmean(tair)))
    out = np.empty_like(t)
    s = t[:7].mean()
    for i, v in enumerate(t):
        s += a * (v - s)
        out[i] = s
    return out


def fruiting(sp: dict, w: Weather, elev: float, dm: float,
             trig: np.ndarray | None = None, shock: np.ndarray | None = None,
             moist: np.ndarray | None = None) -> np.ndarray:
    """Indice de fructification 0-1, jour par jour, pour une altitude et un décalage d'humidité."""
    f = sp["fruiting"]
    L, sd = f["lag_days"], f["lag_sd"]
    dt = LAPSE * (elev - w.elevation)
    tair = w.tmean + dt
    tmin = w.tmin + dt
    if trig is None:
        trig = rain_trigger(w.precip, L, sd)
    if shock is None:
        shock = cold_shock(w.tmean, L, sd)
    if moist is None:
        moist = bucket(w)
    n = len(tair)
    ts = soil_temp(tair)
    theta = trap(ts, *f["tsoil"])
    rho = 1 - np.exp(-trig / f["rain_ref_mm"])
    win = int(round(L))
    mbar = np.array([moist[max(0, i - win):i + 1].mean() for i in range(n)])
    mu = trap(np.clip(mbar + dm, 0, 1), *f["moisture"])
    bonus = 1 + f["cold_shock"] * np.clip((shock - 2.0) / 4.0, 0, 1)
    s = season(w.doy, *f["season"])
    decay = math.exp(-1 / f["persistence_days"])
    out = np.zeros(n)
    prev = 0.0
    last_frost = -10 ** 6
    for i in range(n):
        if np.isfinite(tmin[i]) and tmin[i] < f["frost_c"]:
            last_frost = i
            prev = 0.0
        phi = 1 - math.exp(-(i - last_frost) / FROST_RECOVERY) if last_frost > -10 ** 6 else 1.0
        raw = min(1.0, s[i] * theta[i] * rho[i] * mu[i] * bonus[i]) * phi
        prev = max(raw, prev * decay)
        out[i] = prev
    return out


def fruiting_lattice(sp: dict, w: Weather) -> np.ndarray:
    """Tableau [bande d'altitude, niveau d'humidité, jour] utilisé par l'appli pour interpoler."""
    f = sp["fruiting"]
    trig = rain_trigger(w.precip, f["lag_days"], f["lag_sd"])
    shock = cold_shock(w.tmean, f["lag_days"], f["lag_sd"])
    moist = bucket(w)
    return np.array([[fruiting(sp, w, z, dm, trig, shock, moist) for dm in DM_LEVELS] for z in ELEV_BANDS])
