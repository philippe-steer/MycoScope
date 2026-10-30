"""Encodage des facteurs environnementaux dans les tuiles RGBA (WebP sans perte).

Chaque pixel (≈ 27 m au sol à 46°N, grille Web-Mercator z12) porte :

    R  classe de peuplement (FOREST)              0 = pas de donnée
    G  géologie (5 bits forts) | classe de pH (3 bits faibles)
    B  TWI (4 bits forts)      | exposition (4 bits faibles)
    A  altitude : (A - 1) × 20 m, A = 0 → pas de donnée

L'appli (Encoding.kt) décode exactement ce format ; toute modification doit être faite
des deux côtés et le champ FORMAT_VERSION incrémenté.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np

FORMAT_VERSION = 1
TILE_ZOOM = 12          # zoom natif des données
MIN_ZOOM = 5            # zoom le plus bas de la pyramide
TILE_SIZE = 256

# ----------------------------------------------------------------- peuplements
FOREST = {
    "nodata": 0, "open": 1, "lande": 2, "herbace": 3, "peupleraie": 4,
    "chene": 10, "chene_vert": 11, "hetre": 12, "chataignier": 13, "robinier": 14,
    "feuillus_autres": 15, "feuillus_melange": 16,
    "pin_maritime": 20, "pin_sylvestre": 21, "pin_noir": 22, "pin_alep": 23, "pin_montagne": 24,
    "pins_autres": 25, "sapin_epicea": 26, "meleze": 27, "douglas": 28, "coniferes_autres": 29,
    "mixte_feuillus": 30, "mixte_coniferes": 31,
    "ouverte_feuillus": 40, "ouverte_coniferes": 41, "ouverte_mixte": 42, "coupe": 43,
}
BROADLEAF = [10, 11, 12, 13, 14, 15, 16]
CONIFER = [20, 21, 22, 23, 24, 25, 26, 27, 28, 29]

# ----------------------------------------------------------------- géologie
LITHO = {
    "nodata": 0, "calcaire": 1, "marne": 2, "argile_limon": 3, "sable_gres": 4, "granite": 5,
    "gneiss_micaschiste": 6, "schiste_pelite": 7, "volcanique_basique": 8, "volcanique_acide": 9,
    "alluvions": 10, "tourbe": 11, "ultrabasique": 12, "conglomerat_molasse": 13, "evaporite": 14,
    "moraine": 15, "autre": 16,
}

# pH (eau, 0-5 cm) → classe 1..7 ; bornes supérieures
PH_BOUNDS = [4.5, 5.0, 5.5, 6.0, 6.5, 7.2]          # classe 7 au-delà de 7.2
PH_CENTERS = [0.0, 4.2, 4.75, 5.25, 5.75, 6.25, 6.85, 7.7]  # valeur représentative par classe

# TWI → classe 1..15 (TWI 2..16, pas de 1)
TWI_MIN, TWI_MAX = 2.0, 16.0
# Exposition : 0 plat (< 3°), 1 N, 2 NE, 3 E, 4 SE, 5 S, 6 SO, 7 O, 8 NO
FLAT_SLOPE_DEG = 3.0
ELEV_STEP = 20.0


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower().replace("’", "'")).strip()


# ----------------------------------------------------------------- BD Forêt V2
# Règles appliquées dans l'ordre sur le libellé TFV (et ESSENCE en secours).
_FOREST_RULES: list[tuple[str, str]] = [
    (r"peupleraie|peuplier", "peupleraie"),
    (r"lande", "lande"),
    (r"formation herbacee", "herbace"),
    (r"sans couvert arbore|coupe", "coupe"),
    (r"foret ouverte.*conifere.*pur|foret ouverte de conifere", "ouverte_coniferes"),
    (r"foret ouverte.*feuillu.*pur|foret ouverte de feuillu", "ouverte_feuillus"),
    (r"foret ouverte", "ouverte_mixte"),
    (r"melange de conifere(s)? preponderants et feuillus|coniferes preponderants", "mixte_coniferes"),
    (r"melange de feuillus preponderants et coniferes|feuillus preponderants|mixte", "mixte_feuillus"),
    (r"chenes? sempervirent|chene vert|chene-liege|chene liege|yeuse", "chene_vert"),
    (r"chenes? decidu|chene", "chene"),
    (r"hetre", "hetre"),
    (r"chataignier", "chataignier"),
    (r"robinier", "robinier"),
    (r"pin maritime", "pin_maritime"),
    (r"pin sylvestre", "pin_sylvestre"),
    (r"pin laricio|pin noir", "pin_noir"),
    (r"pin d'alep", "pin_alep"),
    (r"pin a crochets|pin cembro|pin de montagne", "pin_montagne"),
    (r"melange de pins|autre pin|pins melanges|\bpins?\b", "pins_autres"),
    (r"sapin|epicea", "sapin_epicea"),
    (r"meleze", "meleze"),
    (r"douglas", "douglas"),
    (r"conifere", "coniferes_autres"),
    (r"melange de feuillus|feuillus melanges", "feuillus_melange"),
    (r"feuillu", "feuillus_autres"),
    (r"foret", "feuillus_melange"),
]


def forest_class(tfv: str | None, essence: str | None = None) -> int:
    for txt in (tfv, essence):
        if not txt:
            continue
        t = _norm(txt)
        for pat, name in _FOREST_RULES:
            if re.search(pat, t):
                return FOREST[name]
    return FOREST["feuillus_melange"] if (tfv or essence) else FOREST["open"]


# ----------------------------------------------------------------- BD Charm-50
# Mots-clés → classe ; la lithologie retenue est celle du mot-clé apparaissant le plus
# tôt dans le libellé (la première roche citée est la roche dominante).
_LITHO_KEYS: list[tuple[str, str]] = [
    (r"tourbe", "tourbe"),
    (r"gypse|anhydrite|sel gemme|evaporit", "evaporite"),
    (r"serpentin|peridotit|ultrabasique|ophiolit", "ultrabasique"),
    (r"moraine|glaciaire|fluvio-glaciaire|tillite", "moraine"),
    (r"alluvion|colluvion|limon(s)? de (fond|vallee)|depots? de pente|eboulis", "alluvions"),
    (r"basalt|andesit|dolerit|gabbro|diabase|spilite|cinerit|scorie|pouzzolan", "volcanique_basique"),
    (r"rhyolit|trachyt|phonolit|dacit|ignimbrit|tufs? volcanique", "volcanique_acide"),
    (r"granit|granodiorit|tonalit|monzonit|syenit|diorit|leucogranit|aplit|pegmatit|migmatit|anatexit", "granite"),
    (r"gneiss|micaschist|amphibolit|quartzit|leptynit|eclogit", "gneiss_micaschiste"),
    (r"schiste|pelite|ardoise|phyllade|siltite|argilite|lydienne|flysch", "schiste_pelite"),
    (r"conglomerat|poudingue|molasse|breche", "conglomerat_molasse"),
    (r"marno-calcaire|calcaires? marneu|marne", "marne"),
    (r"calcaire|craie|dolomi|calcarenite|travertin|tuffeau|lumachelle", "calcaire"),
    (r"gres|sable|arkose|quartz", "sable_gres"),
    (r"argile|limon|loess|lehm|glaise", "argile_limon"),
]


def litho_class(*texts: str | None) -> int:
    """Classe géologique d'après un ou plusieurs libellés (LITHOLOGIE d'abord, puis DESCR...)."""
    for txt in texts:
        if not txt:
            continue
        t = _norm(txt)
        best, pos = None, 10 ** 9
        for pat, name in _LITHO_KEYS:
            m = re.search(pat, t)
            if m and m.start() < pos:
                best, pos = name, m.start()
        if best:
            return LITHO[best]
    return LITHO["autre"]


# ----------------------------------------------------------------- quantification
def ph_class(ph: np.ndarray) -> np.ndarray:
    """pH (float, NaN = inconnu) → classe 0..7."""
    c = np.digitize(ph, PH_BOUNDS) + 1
    return np.where(np.isfinite(ph), c, 0).astype(np.uint8)


def twi_class(twi: np.ndarray) -> np.ndarray:
    c = np.clip(np.floor(twi - TWI_MIN) + 1, 1, 15)
    return np.where(np.isfinite(twi), c, 0).astype(np.uint8)


def aspect_class(aspect_deg: np.ndarray, slope_deg: np.ndarray) -> np.ndarray:
    """aspect : direction de la pente (0 = N, sens horaire)."""
    a = (np.floor(((aspect_deg % 360) + 22.5) / 45.0) % 8 + 1).astype(np.uint8)
    a = np.where(slope_deg < FLAT_SLOPE_DEG, 0, a)
    return np.where(np.isfinite(aspect_deg), a, 0).astype(np.uint8)


def elev_code(elev: np.ndarray) -> np.ndarray:
    c = np.clip(np.round(np.maximum(elev, 0) / ELEV_STEP) + 1, 1, 255)
    return np.where(np.isfinite(elev), c, 0).astype(np.uint8)


def pack(forest: np.ndarray, litho: np.ndarray, phc: np.ndarray, twic: np.ndarray,
         aspc: np.ndarray, elevc: np.ndarray) -> np.ndarray:
    """→ tableau (h, w, 4) uint8. Un pixel sans peuplement connu est entièrement à 0."""
    r = forest.astype(np.uint8)
    g = ((litho.astype(np.uint8) & 0x1F) << 3) | (phc.astype(np.uint8) & 0x07)
    b = ((twic.astype(np.uint8) & 0x0F) << 4) | (aspc.astype(np.uint8) & 0x0F)
    a = elevc.astype(np.uint8)
    out = np.stack([r, g, b, a], axis=-1)
    out[(r == 0) | (a == 0)] = 0
    return out


def unpack(rgba: np.ndarray) -> dict[str, np.ndarray]:
    r, g, b, a = (rgba[..., i].astype(np.int32) for i in range(4))
    return {
        "forest": r, "litho": g >> 3, "phc": g & 7, "twic": b >> 4, "aspc": b & 15,
        "elev": np.where(a > 0, (a - 1) * ELEV_STEP, np.nan),
        "valid": (r > 0) & (a > 0),
    }
