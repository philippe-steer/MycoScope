"""Calage du modèle : phénologie (cas-témoins temporel), habitat (présence / groupe cible)
et humidité locale (TWI, nappes).

Phénologie — pour chaque observation datée, on compare l'indice F du jour d'observation à
celui du même jour de la semaine 1, 2 et 3 semaines avant et après, au même endroit.
L'effort d'observation (week-ends, saison, accès) est ainsi en grande partie contrôlé.
Vraisemblance : P(cas) = (F_cas + ε) / Σ (F + ε). Une pénalité quadratique retient les
paramètres près des a priori (données bruitées, présence seule).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import differential_evolution, minimize

from .fastmodel import PNAMES, case_control_loglik, fruiting_batch

SPINUP = 60
OFFSETS = np.array([0, -7, -14, -21, 7, 14, 21])          # cas puis témoins
CASE = SPINUP + 21                                          # index du jour d'observation
WINDOW = CASE + 22                                          # longueur des séries (103 j)

FREE = ["t0", "t1", "t2", "t3", "lag_days", "lag_sd", "rain_ref_mm", "m0", "m1", "cold_shock", "persistence_days"]
SCALE = {"t0": 2.0, "t1": 2.0, "t2": 2.0, "t3": 2.0, "lag_days": 3.0, "lag_sd": 1.5, "rain_ref_mm": 10.0,
         "m0": 0.1, "m1": 0.1, "cold_shock": 0.2, "persistence_days": 3.0}


def bounds_for(p0: np.ndarray):
    b = {
        "t0": (p0[2] - 6, p0[2] + 6), "t1": (p0[3] - 6, p0[3] + 6), "t2": (p0[4] - 6, p0[4] + 6),
        "t3": (p0[5] - 6, p0[5] + 6), "lag_days": (3, 35), "lag_sd": (1, 10), "rain_ref_mm": (5, 80),
        "m0": (0.0, 0.6), "m1": (0.1, 0.85), "cold_shock": (0.0, 0.8), "persistence_days": (2, 25),
    }
    return [b[k] for k in FREE]


class PhenoData:
    """Séries (N, WINDOW) centrées sur les observations."""

    def __init__(self, P, T, TN, E, DOY, ZG, ELEV, DM):
        self.P, self.T, self.TN, self.E, self.DOY = P, T, TN, E, DOY
        self.ZG, self.ELEV, self.DM = ZG, ELEV, DM
        self.idx = np.tile(CASE + OFFSETS, (len(P), 1)).astype(np.int64)

    def __len__(self):
        return len(self.P)

    def subset(self, m):
        return PhenoData(*(a[m] for a in (self.P, self.T, self.TN, self.E, self.DOY, self.ZG, self.ELEV, self.DM)))

    def F(self, p, dm=None):
        return fruiting_batch(p, self.P, self.T, self.TN, self.E, self.DOY, self.ZG, self.ELEV,
                              self.DM if dm is None else dm, self.idx)


def _full(theta, p0):
    p = p0.copy()
    for k, v in zip(FREE, theta):
        p[PNAMES.index(k)] = v
    p[2:6] = np.sort(p[2:6])
    p[9:11] = np.sort(p[9:11])
    p[10] = min(p[10], p[11])
    return p


def score(p, data: PhenoData) -> float:
    """Gain moyen de log-vraisemblance par rapport au hasard (log 7), en nats."""
    return float(case_control_loglik(data.F(p)).mean() + np.log(len(OFFSETS)))


def fit_phenology(p0: np.ndarray, data: PhenoData, lam: float = 0.002, seed: int = 0, maxiter: int = 80):
    theta0 = np.array([p0[PNAMES.index(k)] for k in FREE])
    sc = np.array([SCALE[k] for k in FREE])

    def obj(theta):
        p = _full(theta, p0)
        ll = case_control_loglik(data.F(p)).mean()
        return -ll + lam * np.sum(((theta - theta0) / sc) ** 2)

    res = differential_evolution(obj, bounds_for(p0), seed=seed, maxiter=maxiter, popsize=15, tol=1e-7, mutation=(0.5, 1.0),
                                 polish=False, init="sobol", x0=np.clip(theta0, *np.array(bounds_for(p0)).T))
    res2 = minimize(obj, res.x, method="Nelder-Mead", options={"maxiter": 400, "xatol": 1e-3, "fatol": 1e-6})
    best = res2.x if res2.fun < res.fun else res.x
    return _full(best, p0)


def bootstrap(p0, p_hat, data: PhenoData, n=8, seed=1, **kw):
    """Intervalles par rééchantillonnage des observations (parcimonieux : n petit)."""
    rng = np.random.default_rng(seed)
    out = []
    for b in range(n):
        m = rng.integers(0, len(data), len(data))
        out.append(fit_phenology(p_hat, data.subset(m), seed=seed + b, maxiter=25, **kw))
    return np.array(out)


# ======================================================================= humidité locale
def fit_moisture_gains(species_runs, twi, gw_w):
    """Calage commun de (TWI_GAIN, GW_GAIN) sur toutes les espèces, paramètres par espèce fixés.

    species_runs : liste de (p, PhenoData, sel) ; twi, gw_w : tableaux alignés sur chaque
    PhenoData (TWI du pixel, anomalie de nappe × poids des fonds humides)."""
    def obj(g):
        tot, n = 0.0, 0
        for (p, data), t, w in zip(species_runs, twi, gw_w):
            dm = np.clip(g[0] * (t - 7.0) + g[1] * w, -0.25, 0.25)
            ll = case_control_loglik(data.F(p, dm))
            tot += ll.sum()
            n += len(ll)
        return -tot / n
    grid = [(a, b) for a in np.linspace(0, 0.06, 7) for b in np.linspace(0, 0.4, 9)]
    vals = [obj(np.array(g)) for g in grid]
    g0 = np.array(grid[int(np.argmin(vals))])
    res = minimize(obj, g0, method="Nelder-Mead", options={"xatol": 1e-3})
    return res.x, (grid, vals)


# ======================================================================= habitat
def fit_habitat(prior_log: dict, X: dict, y: np.ndarray, lam: float = 1.0):
    """Régression logistique log-linéaire présence / fond groupe cible.

    X[name] : codes entiers (n,), prior_log[name] : log des poids a priori par code (tableau).
    Les coefficients sont rétrécis vers les a priori (pénalité lam). Renvoie des poids
    multiplicatifs (max = 1) par facteur."""
    names = list(X)
    sizes = [len(prior_log[k]) for k in names]
    offs = np.cumsum([0] + sizes)

    def unpack(v):
        return {k: v[offs[i]:offs[i + 1]] for i, k in enumerate(names)}

    v0 = np.concatenate([prior_log[k] for k in names] + [[0.0]])
    counts = {k: np.bincount(X[k], minlength=sizes[i]) for i, k in enumerate(names)}

    def obj(v):
        c = unpack(v[:-1])
        eta = v[-1] + sum(c[k][X[k]] for k in names)
        pr = 1 / (1 + np.exp(-eta))
        ll = np.sum(y * np.log(pr + 1e-12) + (1 - y) * np.log(1 - pr + 1e-12))
        pen = sum(np.sum((c[k] - prior_log[k]) ** 2 * (counts[k] > 0)) for k in names)
        g_eta = y - pr
        grad = np.concatenate([np.bincount(X[k], weights=g_eta, minlength=sizes[i]) - 2 * lam * (c[k] - prior_log[k])
                               * (counts[k] > 0) for i, k in enumerate(names)] + [[g_eta.sum()]])
        return -(ll - lam * pen) / len(y), -grad / len(y)

    res = minimize(obj, v0, jac=True, method="L-BFGS-B")
    c = unpack(res.x[:-1])
    out = {}
    for k in names:
        w = np.exp(c[k] - c[k][counts[k] > 0].max()) if (counts[k] > 0).any() else np.exp(c[k])
        w[counts[k] == 0] = np.exp(prior_log[k][counts[k] == 0])
        out[k] = np.clip(w, 0, 1)
    return out


def auc(score_pos, score_neg) -> float:
    s = np.concatenate([score_pos, score_neg])
    r = s.argsort().argsort().astype(float) + 1
    n1, n0 = len(score_pos), len(score_neg)
    return float((r[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")
