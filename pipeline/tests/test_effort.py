"""Biais « sortie après la pluie » : les observateurs sortent juste après les pluies.
Sans correction, le délai estimé est tiré vers le bas ; la pondération par les traceurs
d'effort (polypores pérennes) doit le corriger."""
import numpy as np

from mycoscope_pipeline.calib.fastmodel import PNAMES, fruiting_one, params_from_species
from mycoscope_pipeline.calib.fit import CASE, OFFSETS, WINDOW, PhenoData, fit_phenology
from mycoscope_pipeline.model import load_species


def simulate(p_true, n_sites=500, years=6, seed=0):
    rng = np.random.default_rng(seed)
    rows, eff_rows = [], []
    for s in range(n_sites):
        z = rng.uniform(50, 900)
        for y in range(years):
            nd = 365
            doy = np.arange(1, nd + 1)
            tm = 11 - 8 * np.cos(2 * np.pi * (doy - 20) / 365) + rng.normal(0, 2.0, nd)
            P = np.where(rng.random(nd) < 0.33, rng.gamma(1.2, 7, nd), 0.0)
            E = np.clip(1.8 - 1.5 * np.cos(2 * np.pi * (doy - 20) / 365), 0.2, None)
            F = fruiting_one(p_true, P, tm, tm - 5, E, doy, z, z, 0.0)
            recent = np.convolve(P, np.ones(4), mode="full")[:nd]           # pluie des 4 derniers jours
            effort = (1 + 10.0 * (recent > 10)) * ((doy % 7 >= 5) * 2.0 + 1.0)
            tracer = rng.poisson(effort * 0.15)                              # traceurs observés ∝ effort
            for d in np.nonzero(rng.random(nd) < F * effort * 0.0015)[0]:
                if CASE <= d <= nd - 22:
                    sl = slice(d - CASE, d - CASE + WINDOW)
                    rows.append((P[sl], tm[sl], tm[sl] - 5, E[sl], doy[sl], z))
                    eff_rows.append(np.array([tracer[d + o - 2:d + o + 3].sum() for o in OFFSETS], float) + 1.0)
    P, T, TN, E, D, Z = map(np.array, zip(*rows))
    return PhenoData(P, T, TN, E, D, Z, Z.copy(), np.zeros(len(Z))), np.array(eff_rows)


def test_effort_correction():
    sp = {s["id"]: s for s in load_species()}["girolle"]
    p_true = params_from_species(sp)
    p_true[PNAMES.index("lag_days")] = 12.0
    data, W = simulate(p_true)
    p0 = params_from_species(sp)
    naive = fit_phenology(p0, data, maxiter=40)[PNAMES.index("lag_days")]
    data.W = W
    corrected = fit_phenology(p0, data, maxiter=40)[PNAMES.index("lag_days")]
    print(f"\n{len(W)} obs ; vrai 12 j ; naïf {naive:.1f} j ; corrigé {corrected:.1f} j")
    assert naive < 8            # le biais tire le délai vers 0 (comme la girolle réelle : 4 j)
    assert abs(corrected - 12) < 2
