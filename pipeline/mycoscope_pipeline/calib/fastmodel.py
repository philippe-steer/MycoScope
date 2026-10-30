"""Version numba du modèle de fructification (identique à model.fruiting) pour le calage.

Paramètres d'une espèce sous forme de vecteur (PNAMES) ; les séries météo de N occurrences
sont des tableaux (N, T). Testé contre model.fruiting dans tests/test_calib.py.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit, prange

from ..model import (BUCKET_MM, BUCKET_START, FROST_RECOVERY, LAPSE, SEASON_RAMP, SOIL_TAU)

PNAMES = ["season_start", "season_end", "t0", "t1", "t2", "t3", "lag_days", "lag_sd", "rain_ref_mm",
          "m0", "m1", "m2", "m3", "frost_c", "cold_shock", "persistence_days"]


def params_from_species(sp: dict) -> np.ndarray:
    f = sp["fruiting"]
    return np.array([*f["season"], *f["tsoil"], f["lag_days"], f["lag_sd"], f["rain_ref_mm"],
                     *f["moisture"], f["frost_c"], f["cold_shock"], f["persistence_days"]], float)


def params_to_fruiting(p: np.ndarray, base: dict) -> dict:
    f = dict(base)
    r = lambda x, k=1: round(float(x), k)  # noqa: E731
    f.update(season=[r(p[0], 0), r(p[1], 0)], tsoil=[r(v) for v in p[2:6]], lag_days=r(p[6]),
             lag_sd=r(p[7]), rain_ref_mm=r(p[8]), moisture=[r(v, 2) for v in p[9:13]],
             frost_c=r(p[13]), cold_shock=r(p[14], 2), persistence_days=r(p[15]))
    return f


@njit(cache=True, inline="always")
def _trap(x, a, b, c, d):
    if b > a:
        up = (x - a) / max(b - a, 1e-9)
    else:
        up = 1.0 if x >= a else 0.0
    if d > c:
        down = (d - x) / max(d - c, 1e-9)
    else:
        down = 1.0 if x <= d else 0.0
    v = min(min(up, down), 1.0)
    return min(max(v, 0.0), 1.0)


@njit(cache=True)
def _pyround(x):
    # arrondi au pair le plus proche, comme round() de Python
    return int(np.rint(x))


@njit(cache=True)
def fruiting_one(p, P, T, TN, E, doy, z_grid, elev, dm):
    n = P.shape[0]
    lag, sd = p[6], p[7]
    # déclenchement par la pluie
    tmax = int(math.ceil(lag + 3 * sd))
    k = np.empty(tmax + 1)
    for t in range(tmax + 1):
        k[t] = math.exp(-0.5 * ((t - lag) / sd) ** 2)
    trig = np.zeros(n)
    for i in range(n):
        s = 0.0
        for tau in range(min(tmax, i) + 1):
            v = P[i - tau]
            s += (v if np.isfinite(v) else 0.0) * k[tau]
        trig[i] = s
    # coup de froid (sur T de la maille, comme le modèle de référence)
    t0 = np.empty(n)
    for i in range(n):
        t0[i] = T[i] if np.isfinite(T[i]) else 0.0
    drop = np.full(n, -99.0)
    for j in range(3, n - 2):
        drop[j] = (t0[j - 3] + t0[j - 2] + t0[j - 1]) / 3.0 - (t0[j] + t0[j + 1] + t0[j + 2]) / 3.0
    lo = _pyround(max(0.0, lag - sd))
    hi = _pyround(lag + sd)
    shock = np.zeros(n)
    for i in range(n):
        b = 0.0
        for tau in range(lo, hi + 1):
            if i - tau >= 0:
                b = max(b, drop[i - tau])
        shock[i] = b
    # réservoir
    moist = np.empty(n)
    s = BUCKET_START * BUCKET_MM
    for i in range(n):
        pp = P[i] if np.isfinite(P[i]) else 0.0
        ee = E[i] if np.isfinite(E[i]) else 0.0
        stress = min(1.0, s / (0.5 * BUCKET_MM))
        s = min(BUCKET_MM, max(0.0, s + pp - ee * stress))
        moist[i] = s / BUCKET_MM
    # température du sol
    dt = LAPSE * (elev - z_grid)
    cnt = 0
    tot = 0.0
    for i in range(n):
        if np.isfinite(T[i]):
            tot += T[i] + dt
            cnt += 1
    mean = tot / cnt if cnt > 0 else 0.0
    a = 1 - math.exp(-1 / SOIL_TAU)
    ta = np.empty(n)
    for i in range(n):
        ta[i] = T[i] + dt if np.isfinite(T[i]) else mean
    m7 = min(7, n)
    ts = 0.0
    for i in range(m7):
        ts += ta[i]
    ts /= m7
    win = _pyround(lag)
    decay = math.exp(-1 / p[15])
    out = np.zeros(n)
    prev = 0.0
    last_frost = -1000000
    cum = np.zeros(n + 1)
    for i in range(n):
        cum[i + 1] = cum[i] + moist[i]
    st, en = p[0], p[1]
    for i in range(n):
        ts += a * (ta[i] - ts)
        tn = TN[i] + dt
        if np.isfinite(tn) and tn < p[13]:
            last_frost = i
            prev = 0.0
        phi = 1 - math.exp(-(i - last_frost) / FROST_RECOVERY) if last_frost > -1000000 else 1.0
        i0 = max(0, i - win)
        mbar = (cum[i + 1] - cum[i0]) / (i + 1 - i0)
        theta = _trap(ts, p[2], p[3], p[4], p[5])
        rho = 1 - math.exp(-trig[i] / p[8])
        mu = _trap(min(max(mbar + dm, 0.0), 1.0), p[9], p[10], p[11], p[12])
        bonus = 1 + p[14] * min(max((shock[i] - 2.0) / 4.0, 0.0), 1.0)
        d = float(doy[i])
        e = en
        if en < st:
            if d < st - SEASON_RAMP:
                d += 365
            e = en + 365
        sea = _trap(d, st - SEASON_RAMP, st, e, e + SEASON_RAMP)
        raw = min(1.0, sea * theta * rho * mu * bonus) * phi
        prev = max(raw, prev * decay)
        out[i] = prev
    return out


@njit(cache=True, parallel=True)
def fruiting_batch(p, P, T, TN, E, DOY, ZG, ELEV, DM, idx):
    """F aux jours idx[i, :] de chaque occurrence i (cas en colonne 0, témoins ensuite)."""
    n, m = idx.shape
    out = np.empty((n, m))
    for i in prange(n):
        f = fruiting_one(p, P[i], T[i], TN[i], E[i], DOY[i], ZG[i], ELEV[i], DM[i])
        for j in range(m):
            out[i, j] = f[idx[i, j]]
    return out


EPS = 0.02


def case_control_loglik(F: np.ndarray, W: np.ndarray | None = None) -> np.ndarray:
    """log P(cas) avec P ∝ (F + ε)·effort parmi {cas, témoins} ; F[:, 0] = cas.
    W : effort d'observation relatif de chaque jour (1 = uniforme)."""
    w = F + EPS
    if W is not None:
        w = w * W
    return np.log(w[:, 0] / w.sum(axis=1))
