"""Récupération de paramètres : observations simulées avec des paramètres connus."""
import numpy as np

from mycoscope_pipeline.calib.fastmodel import PNAMES, fruiting_one, params_from_species
from mycoscope_pipeline.calib.fit import CASE, OFFSETS, WINDOW, PhenoData, fit_phenology, score
from mycoscope_pipeline.model import load_species


def simulate(p_true, n_sites=400, years=6, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sites):
        z = rng.uniform(50, 900)
        for y in range(years):
            nd = 365
            doy = np.arange(1, nd + 1)
            tm = 11 - 8 * np.cos(2 * np.pi * (doy - 20) / 365) + rng.normal(0, 2.0, nd)
            tm = np.convolve(tm, np.ones(3) / 3, mode="same")
            P = np.where(rng.random(nd) < 0.33, rng.gamma(1.2, 7, nd), 0.0)
            E = np.clip(1.8 - 1.5 * np.cos(2 * np.pi * (doy - 20) / 365), 0.2, None)
            TN = tm - 5
            F = fruiting_one(p_true, P, tm, TN, E, doy, z, z, 0.0)
            weekend = (doy % 7 >= 5) * 2.0 + 1.0                   # effort : week-ends ×3
            prob = F * weekend * 0.004
            for d in np.nonzero(rng.random(nd) < prob)[0]:
                if CASE <= d <= nd - 22:
                    sl = slice(d - CASE, d - CASE + WINDOW)
                    rows.append((P[sl], tm[sl], TN[sl], E[sl], doy[sl], z))
    P, T, TN, E, D, Z = map(np.array, zip(*rows))
    return PhenoData(P, T, TN, E, D, Z, Z.copy(), np.zeros(len(Z)))


def test_recover_lag_and_rain():
    sp = {s["id"]: s for s in load_species()}["cepe_bordeaux"]
    p_true = params_from_species(sp)
    p_true[PNAMES.index("lag_days")] = 14.0
    p_true[PNAMES.index("rain_ref_mm")] = 45.0
    data = simulate(p_true)
    p0 = params_from_species(sp)                                # a priori : lag 10, R0 30
    p_hat = fit_phenology(p0, data, lam=0.002, maxiter=40)
    print(len(data), "obs ; lag", p_hat[6], "R0", p_hat[8], "score prior", score(p0, data),
          "fit", score(p_hat, data), "vrai", score(p_true, data))
    assert abs(p_hat[PNAMES.index("lag_days")] - 14) < 2.0
    assert score(p_hat, data) >= score(p0, data)
