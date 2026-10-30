"""Calage complet → rapport + species.json calé.

python -m mycoscope_pipeline.calib.run --occ occurrences.csv --sim2 sim2.npz \
    [--pmtiles france.pmtiles] [--piezo piezo_history.npz] --out calibration/
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

from .. import encoding as enc
from ..model import (GW_GAIN, TWI_GAIN, TWI_MIN, habitat, host_table, litho_table, load_species, ph_table)
from . import fit as F
from .fastmodel import PNAMES, fruiting_one, params_from_species, params_to_fruiting

MIN_OBS = 80
MAX_OBS = 2500   # sous-échantillon par espèce (temps de calcul)
TO_L2E = Transformer.from_crs("EPSG:4326", "EPSG:27572", always_xy=True)


# ----------------------------------------------------------------------------- données
def load_occurrences(path) -> pd.DataFrame:
    o = pd.read_csv(path)
    o["date"] = pd.to_datetime(o["date"], errors="coerce").dt.date
    o = o.dropna(subset=["date", "lat", "lon"])
    o = o[[d.year >= 2000 and not (d.month == 1 and d.day == 1) for d in o.date]]
    o["k"] = o.lat.round(3).astype(str) + o.lon.round(3).astype(str)
    o = o.drop_duplicates(["species", "date", "k"]).drop(columns="k")
    o["uncert_m"] = pd.to_numeric(o["uncert_m"], errors="coerce")
    return o.reset_index(drop=True)


class Sim2:
    def __init__(self, path):
        d = np.load(path, allow_pickle=False)
        self.x, self.y, self.lat, self.lon = d["x"], d["y"], d["lat"], d["lon"]
        self.day0 = dt.date.fromisoformat(str(d["day0"]))
        self.data = d["data"]
        self.tree = cKDTree(np.c_[self.x, self.y])

    def cell(self, lat, lon):
        ox, oy = TO_L2E.transform(lon, lat)
        dist, ci = self.tree.query(np.c_[ox, oy])
        return np.where(dist < 6000, ci, -1)


def phenology_arrays(occ: pd.DataFrame, sim: Sim2, elev: np.ndarray, zcell: np.ndarray, dm: np.ndarray):
    """Fenêtres météo autour de chaque observation ; renvoie (PhenoData, masque des lignes gardées)."""
    cells = sim.cell(occ.lat.to_numpy(), occ.lon.to_numpy())
    keep, rows = [], []
    for i, (c, d) in enumerate(zip(cells, occ.date)):
        if c < 0 or not np.isfinite(elev[i]) or not np.isfinite(zcell[c]):
            continue
        di = (d - sim.day0).days
        a, b = di - F.CASE, di - F.CASE + F.WINDOW
        if a < 0 or b > sim.data.shape[1]:
            continue
        w = sim.data[c, a:b]
        if not np.isfinite(w[:, 1]).all():
            continue
        doy = np.array([(sim.day0 + dt.timedelta(days=int(k))).timetuple().tm_yday for k in range(a, b)])
        rows.append((w[:, 0], w[:, 1], w[:, 2], w[:, 3], doy, zcell[c], elev[i], dm[i]))
        keep.append(i)
    if not rows:
        return None, np.array([], int)
    P, T, TN, E, D, ZG, EL, DM = (np.array(v, dtype=float if j != 4 else np.int64) for j, v in enumerate(zip(*rows)))
    return F.PhenoData(P, T, TN, E, D, ZG, EL, DM), np.array(keep)


def twi_from_pixel(px: np.ndarray) -> np.ndarray:
    c = px[:, 2] >> 4
    return np.where(c > 0, TWI_MIN + c - 0.5, 7.0)


def aspect_dz(px):
    from ..model import ASPECT_DZ
    return np.array(ASPECT_DZ)[px[:, 2] & 15]


def effort_weights(cases_lat, cases_lon, cases_day, tr_lat, tr_lon, tr_day,
                   radius_km: float = 100.0, half: int = 2, pseudo: float = 1.0):
    """Effort relatif des jours cas/témoins : 1 + nombre de traceurs observés à moins de
    radius_km et à ±half jours. Lignes sans aucun traceur → effort uniforme (1)."""
    from collections import defaultdict
    by_day = defaultdict(list)
    for la, lo, d in zip(tr_lat, tr_lon, tr_day):
        by_day[int(d)].append((la, lo))
    by_day = {d: np.array(v) for d, v in by_day.items()}
    W = np.ones((len(cases_day), len(F.OFFSETS)))
    informative = np.zeros(len(cases_day), bool)
    for i, (la, lo, d0) in enumerate(zip(cases_lat, cases_lon, cases_day)):
        c = np.zeros(len(F.OFFSETS))
        kx = 111.0 * np.cos(np.radians(la))
        for j, off in enumerate(F.OFFSETS):
            for dd in range(int(d0) + int(off) - half, int(d0) + int(off) + half + 1):
                pts = by_day.get(dd)
                if pts is None:
                    continue
                dist2 = ((pts[:, 0] - la) * 111.0) ** 2 + ((pts[:, 1] - lo) * kx) ** 2
                c[j] += np.count_nonzero(dist2 < radius_km ** 2)
        if c.sum() > 0:
            W[i] = c + pseudo
            informative[i] = True
    return W, informative


# ----------------------------------------------------------------------------- calage phéno
def cv_scores(p0, data: F.PhenoData, years: np.ndarray, lam: float, k: int = 4):
    """Validation croisée par blocs d'années : score hors échantillon a priori vs calé."""
    folds = years % k
    s0, s1, n = 0.0, 0.0, 0
    for f in range(k):
        te = folds == f
        if te.sum() < 10 or (~te).sum() < 40:
            continue
        p = F.fit_phenology(p0, data.subset(~te), lam=lam, maxiter=25)
        s0 += F.score(p0, data.subset(te)) * te.sum()
        s1 += F.score(p, data.subset(te)) * te.sum()
        n += te.sum()
    return (s0 / n, s1 / n) if n else (float("nan"), float("nan"))


def response_curve(p, data: F.PhenoData, n=400):
    """Indice moyen de J-21 à J+21 autour des observations (diagnostic)."""
    m = min(n, len(data))
    curves = np.array([fruiting_one(p, data.P[i], data.T[i], data.TN[i], data.E[i], data.DOY[i], data.ZG[i],
                                    data.ELEV[i], data.DM[i])[F.CASE - 21:F.CASE + 22] for i in range(m)])
    return curves.mean(0)


# ----------------------------------------------------------------------------- calage habitat
def habitat_fit(sp, px_pos, px_bg, blocks_pos, blocks_bg):
    """Poids hôte / géologie / pH, présences vs groupe cible, restreint aux pixels forestiers."""
    def dec(px):
        return {"forest": px[:, 0].astype(int), "litho": (px[:, 1] >> 3).astype(int), "phc": (px[:, 1] & 7).astype(int)}

    pos, bg = dec(px_pos), dec(px_bg)
    X = {k: np.concatenate([pos[k], bg[k]]) for k in pos}
    y = np.r_[np.ones(len(px_pos)), np.zeros(len(px_bg))]
    blocks = np.r_[blocks_pos, blocks_bg]
    prior = {"forest": np.log(np.clip(host_table(sp), 0.02, 1)), "litho": np.log(np.clip(litho_table(sp), 0.02, 1)),
             "phc": np.log(np.clip(ph_table(sp), 0.02, 1))}

    def H(tabs, X):
        return tabs["forest"][X["forest"]] * tabs["litho"][X["litho"]] * tabs["phc"][X["phc"]]

    prior_tabs = {k: np.exp(v) for k, v in prior.items()}
    a0, a1 = [], []
    for f in range(5):
        te = (blocks % 5) == f
        if y[te].sum() < 5 or (y[te] == 0).sum() < 5:
            continue
        tabs = F.fit_habitat(prior, {k: X[k][~te] for k in X}, y[~te])
        Xt = {k: X[k][te] for k in X}
        a0.append(F.auc(H(prior_tabs, Xt)[y[te] == 1], H(prior_tabs, Xt)[y[te] == 0]))
        a1.append(F.auc(H(tabs, Xt)[y[te] == 1], H(tabs, Xt)[y[te] == 0]))
    tabs = F.fit_habitat(prior, X, y)
    return tabs, (float(np.nanmean(a0)) if a0 else float("nan"), float(np.nanmean(a1)) if a1 else float("nan"))


def tables_to_habitat(sp, tabs):
    h = copy.deepcopy(sp["habitat"])
    inv_f = {c: n for n, c in enc.FOREST.items()}
    inv_l = {c: n for n, c in enc.LITHO.items()}
    for code, w in enumerate(tabs["forest"]):
        name = inv_f.get(code)
        if name and code >= 10 and (name in h["hosts"] or w > 0.05):
            h["hosts"][name] = round(float(w), 2)
    for code, w in enumerate(tabs["litho"]):
        name = inv_l.get(code)
        if name and code > 0:
            h["litho"][name] = round(float(w), 2)
    return h


# ----------------------------------------------------------------------------- figures
def figure(sid, name, curve0, curve1, doy_obs, out: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    t = np.arange(-21, 22)
    ax[0].plot(t, curve0, color="0.5", label="a priori")
    ax[0].plot(t, curve1, color="#C4452F", label="calé")
    ax[0].axvline(0, color="k", lw=0.8)
    ax[0].set_xlabel("jours autour de l'observation")
    ax[0].set_ylabel("indice de fructification moyen")
    ax[0].legend(frameon=False)
    ax[1].hist(doy_obs, bins=np.arange(0, 367, 7), color="#E8873A")
    ax[1].set_xlabel("jour de l'année des observations")
    fig.suptitle(name)
    fig.tight_layout()
    fig.savefig(out / f"{sid}.png", dpi=110)
    plt.close(fig)


# ----------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--occ", required=True)
    ap.add_argument("--sim2", required=True)
    ap.add_argument("--pmtiles")
    ap.add_argument("--piezo")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lam", type=float, default=0.002)
    ap.add_argument("--species", default="")
    ap.add_argument("--no-effort", action="store_true", help="ne pas pondérer par l'effort (traceurs)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    from .sample import GroundWater, dem_box_means, dem_points, habitat_pixels

    species = load_species()
    occ_all = load_occurrences(a.occ)
    tracers = occ_all[occ_all.species.astype(str).str.startswith("_")]
    occ = occ_all[~occ_all.species.astype(str).str.startswith("_")].reset_index(drop=True)
    print(f"::notice title=Effort::{len(tracers)} observations de traceurs (polypores pérennes)")
    tr_day = np.array([(d - dt.date(1999, 1, 1)).days for d in tracers.date])
    print(f"::notice title=Calage::{len(occ)} observations après nettoyage")
    sim = Sim2(a.sim2)
    elev = dem_points(occ.lat.to_numpy(), occ.lon.to_numpy())
    zcell = dem_box_means(sim.lat, sim.lon)
    px = habitat_pixels(a.pmtiles, occ.lat.to_numpy(), occ.lon.to_numpy()) if a.pmtiles else np.zeros((len(occ), 4), np.uint8)
    twi = twi_from_pixel(px)
    elev_eff = elev + aspect_dz(px)
    gw = np.zeros(len(occ))
    if a.piezo and Path(a.piezo).exists():
        g = GroundWater(a.piezo)
        gw = np.array([g.anomaly(la, lo, d) for la, lo, d in zip(occ.lat, occ.lon, occ.date)])
        print(f"::notice title=Nappes::anomalie connue pour {(gw != 0).mean():.0%} des observations")
    gw_w = gw * np.clip((twi - 8.0) / 5.0, 0, 1)
    dm0 = np.clip(TWI_GAIN * (twi - 7.0) + GW_GAIN * gw_w, -0.25, 0.25)

    pheno_ok = occ.uncert_m.isna() | (occ.uncert_m <= 5000)
    results, runs, run_twi, run_gw = [], [], [], []
    new_species = []
    out_figs = a.out / "figures"
    out_figs.mkdir(exist_ok=True)
    only = set(filter(None, a.species.split(",")))
    for sp in species:
        sid = sp["id"]
        sp_new = copy.deepcopy(sp)
        row = {"id": sid, "nom": sp["name"]["fr"]}
        m = (occ.species == sid).to_numpy() & pheno_ok.to_numpy()
        sub = np.nonzero(m)[0]
        if len(sub) > MAX_OBS:
            sub = np.sort(np.random.default_rng(0).choice(sub, MAX_OBS, replace=False))
        data, keep = phenology_arrays(occ.iloc[sub], sim, elev_eff[sub], zcell, dm0[sub]) if len(sub) else (None, [])
        row["n_obs"] = int((occ.species == sid).sum())
        row["n_pheno"] = 0 if data is None else len(data)
        if data is not None and len(tracers) and not a.no_effort:
            ok = occ.iloc[sub[keep]]
            cday = np.array([(d - dt.date(1999, 1, 1)).days for d in ok.date])
            data.W, inf = effort_weights(ok.lat.to_numpy(), ok.lon.to_numpy(), cday,
                                         tracers.lat.to_numpy(), tracers.lon.to_numpy(), tr_day)
            row["effort_info"] = float(inf.mean())
        if data is not None and len(data) >= MIN_OBS and (not only or sid in only):
            p0 = params_from_species(sp)
            years = np.array([occ.date.iloc[sub[k]].year for k in keep])
            p1 = F.fit_phenology(p0, data, lam=a.lam)
            cv0, cv1 = cv_scores(p0, data, years, a.lam)
            boot = F.bootstrap(p0, p1, data, n=4, lam=a.lam)
            row.update(score_prior=F.score(p0, data), score_fit=F.score(p1, data), cv_prior=cv0, cv_fit=cv1,
                       lag=(p0[6], p1[6], *np.percentile(boot[:, 6], [10, 90])),
                       rain=(p0[8], p1[8], *np.percentile(boot[:, 8], [10, 90])),
                       tsoil=(list(p0[2:6]), list(np.round(p1[2:6], 1))))
            if cv1 > cv0:
                sp_new["fruiting"] = params_to_fruiting(p1, sp["fruiting"])
                runs.append((p1, data))
            else:
                runs.append((p0, data))
            run_twi.append(twi[sub][keep])
            run_gw.append(gw_w[sub][keep])
            doy = [occ.date.iloc[sub[k]].timetuple().tm_yday for k in keep]
            figure(sid, sp["name"]["fr"], response_curve(p0, data), response_curve(p1, data), doy, out_figs)
        # habitat
        if a.pmtiles:
            valid = (px[:, 0] >= 10) & (px[:, 3] > 0) & (occ.uncert_m.fillna(1e9) <= 1000).to_numpy()
            pos = valid & (occ.species == sid).to_numpy()
            bg = valid & (occ.species != sid).to_numpy()
            row["n_habitat"] = int(pos.sum())
            if pos.sum() >= MIN_OBS and bg.sum() >= MIN_OBS:
                blocks = (np.floor(occ.lat * 2) * 1000 + np.floor(occ.lon * 2)).astype(int).to_numpy()
                tabs, (auc0, auc1) = habitat_fit(sp, px[pos], px[bg], blocks[pos], blocks[bg])
                row.update(auc_prior=auc0, auc_fit=auc1)
                if auc1 > auc0 + 0.005:
                    sp_new["habitat"] = tables_to_habitat(sp, tabs)
                e = elev[pos]
                row["elev_obs"] = tuple(np.nanpercentile(e, [2, 50, 98]).round(0)) if np.isfinite(e).any() else None
        sp_new.setdefault("calibration", {}).update({
            "date": dt.date.today().isoformat(), "n_obs": row["n_obs"],
            "pheno_cv_gain": round(row.get("cv_fit", np.nan) - row.get("cv_prior", np.nan), 4) if "cv_fit" in row else None,
            "habitat_auc": round(row.get("auc_fit", np.nan), 3) if "auc_fit" in row else None})
        new_species.append(sp_new)
        results.append(row)
        print(f"::notice title=Calage {sid}::" + json.dumps(row, default=lambda x: round(float(x), 3))[:900])

    gains = None
    if runs:
        g, _ = F.fit_moisture_gains(runs, run_twi, run_gw)
        gains = {"twi_gain": round(float(g[0]), 4), "gw_gain": round(float(g[1]), 3)}
        print(f"::notice title=Humidité locale::{gains}")

    doc = json.loads(Path(__file__).resolve().parents[3].joinpath("app/src/main/assets/species.json").read_text())
    doc["species"] = [{k: v for k, v in s.items()} for s in new_species]
    if gains:
        doc["moisture_gains"] = gains
    (a.out / "species_calibrated.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    report(results, gains, len(occ), a.out)


def _f(x, k=3):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{k}f}"


def report(results, gains, n, out: Path):
    L = [f"# Calage MycoScope — {dt.date.today().isoformat()}", "",
         f"{n} observations GBIF datées (France, 2000–2025, après nettoyage). Météo : SAFRAN-SIM2.", "",
         "**Phénologie** : cas-témoins (même lieu, même jour de semaine, ±1–3 semaines). Score = gain de "
         "log-vraisemblance par observation par rapport au hasard (0 = aucun pouvoir, log 7 ≈ 1,95 = parfait). "
         "« VC » = validation croisée par blocs d'années : seul ce score décide de l'adoption des paramètres.", "",
         "**Habitat** : présences vs observations des autres espèces (groupe cible), pixels forestiers, "
         "AUC en validation croisée spatiale (blocs de 0,5°).", "",
         "**Effort** : jours témoins pondérés par les observations de polypores pérennes (traceurs des sorties) "
         "à moins de 100 km et ±2 jours ; « effort » = part des observations où ce poids est informatif.", "",
         "| Espèce | obs. | phéno | effort | VC a priori | VC calé | délai (a priori → calé [IC 80 %]) | R₀ mm | habitat | AUC a priori | AUC calé |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lag = r.get("lag")
        rain = r.get("rain")
        L.append(f"| {r['nom']} | {r['n_obs']} | {r['n_pheno']} | {_f(r.get('effort_info'), 2)} | {_f(r.get('cv_prior'))} | {_f(r.get('cv_fit'))} | "
                 + (f"{lag[0]:.0f} → {lag[1]:.1f} [{lag[2]:.1f}–{lag[3]:.1f}]" if lag else "–") + " | "
                 + (f"{rain[0]:.0f} → {rain[1]:.0f} [{rain[2]:.0f}–{rain[3]:.0f}]" if rain else "–")
                 + f" | {r.get('n_habitat', '–')} | {_f(r.get('auc_prior'))} | {_f(r.get('auc_fit'))} |")
    if gains:
        L += ["", f"**Humidité locale** (toutes espèces) : TWI_GAIN = {gains['twi_gain']} (a priori 0,03), "
                  f"GW_GAIN = {gains['gw_gain']} (a priori 0,15)."]
    L += ["", "Paramètres adoptés seulement si la validation croisée s'améliore. Figures : `figures/`.",
          "Limites : données de présence seule, dates parfois de saisie, coordonnées approximatives, "
          "observateurs concentrés près des villes ; l'AUC mesure la préférence relative entre espèces."]
    (out / "report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"::error title=Calage::{type(e).__name__}: " + " | ".join(traceback.format_exc().splitlines()[-6:])[:1700])
        sys.exit(1)
