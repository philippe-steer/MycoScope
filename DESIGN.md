# MycoScope — conception

Indice « champignon » = **habitat statique** (où l'espèce peut pousser) × **fructification**
(quand les conditions météo récentes la déclenchent). Les deux sont des a priori experts,
paramétrés espèce par espèce dans `app/src/main/assets/species.json`, fichier unique lu à la
fois par le pipeline Python et par l'appli.

## 1. Architecture (hybride, sans serveur)

```
GitHub Actions (une fois, ~96 jobs)                 Téléphone
───────────────────────────────────                 ─────────────────────────────────────
BD Forêt V2 ─┐                                      france.pmtiles (requêtes Range, cache disque)
BD Charm-50 ─┤  rasterisation z12 (≈27 m)               │ tuile RGBA décodée
SoilGrids pH ┼─ + TWI, exposition, altitude ──► PMTiles ─┤
Copernicus  ─┘    (encodage RGBA, §2)                    ▼
DEM 30 m                                            habitat(espèce, pixel)
                                                         ×
Hub'Eau (tous les 3 mois) → piezo_stats.json        fructification(treillis Open-Meteo, altitude,
                                                    exposition, TWI, nappes, jour J-14…J+7)
```

- **Statique** : `pipeline/` construit une tuile z12 par département (`build_dept.py`), puis
  `merge.py` fusionne, construit la pyramide z5–z11 et écrit `france.pmtiles`
  (release `data-v1`). Le fichier contient des **facteurs environnementaux**, pas des cartes
  par espèce : changer les paramètres d'une espèce ou en ajouter une ne demande aucun recalcul.
- **Dynamique** : l'appli télécharge pour la zone visible un treillis de points Open-Meteo
  (pas de 0,125° à 1° selon le zoom) avec 60 jours passés + 8 jours de prévision
  (pluie, T moyenne, T min, ET0), mis en cache pour la journée.

## 2. Encodage des tuiles (format v1)

| Canal | Contenu |
|---|---|
| R | classe de peuplement (BD Forêt V2, 28 classes, 0 = pas de donnée, 1 = hors forêt) |
| G | géologie (5 bits, 16 classes BD Charm-50) \| pH eau 0–5 cm (3 bits, 7 classes SoilGrids) |
| B | TWI (4 bits, 2–16) \| exposition (4 bits : plat, N … NO) |
| A | altitude = (A − 1) × 20 m |

WebP sans perte. Côté Android, décoder avec `inPremultiplied = false` (sinon l'alpha corrompt
RGB). Les tables de classes sont dans `encoding.py` et `Model.kt` (`Enc`), à garder identiques.

Classification : regex sur les libellés TFV/ESSENCE (BD Forêt) et LITHOLOGIE/DESCR
(BD Charm-50 ; la roche citée en premier l'emporte). Pyramide : par bloc 2×2, premier pixel
valide (données catégorielles, pas de moyenne).

## 3. Habitat

`H = hôte[peuplement] × géologie[classe] × f_pH(classe) × trapèze(altitude)`

- **Hôte** (ectomycorhizes) : affinité 0–1 par essence. Classes déduites si absentes :
  mélange de feuillus = 0,9 × max(feuillus), mixtes = combinaisons 0,9/0,7, forêts ouvertes
  = 0,6 × max, coupes = 0,1 × max.
- **pH** : trapèze avec plancher (`ph_floor`) : le pH SoilGrids à 250 m est indicatif.
- **Altitude** : bornes dures ; l'effet thermique de l'altitude passe surtout par la météo.

## 4. Fructification (pas de temps journalier)

Au point de treillis, la température est ramenée à l'altitude effective du pixel
(gradient −6,5 °C/km ; versant sud = −120 m, nord = +120 m).

| Terme | Formule |
|---|---|
| Température du sol | moyenne exponentielle de T air (τ = 4 j) → trapèze `tsoil` |
| Déclenchement par la pluie | R(t) = Σ P(t−τ)·exp(−½((τ−L)/σ)²) ; ρ = 1 − exp(−R/R₀) |
| Humidité du sol | réservoir 120 mm, ET0 réduite sous stress ; moyenne sur L jours, + décalage local → trapèze `moisture` |
| Décalage local d'humidité | 0,03 × (TWI − 7) + 0,15 × anomalie de nappe × poids(TWI > 8), borné à ±0,25 |
| Coup de froid | bonus jusqu'à +`cold_shock` si T chute de 2 à 6 °C autour du délai L |
| Saison | trapèze sur le jour de l'année, rampes de 20 j |
| Gel | T min < `frost_c` : poussées détruites, reprise en ~5 j |
| Persistance | F(t) = max(brut, F(t−1)·exp(−1/persistance)) |

L'appli précalcule F pour 31 bandes d'altitude (0–3000 m) × 5 niveaux d'humidité × 22 jours
par point, puis interpole par pixel (bilinéaire en espace, linéaire en altitude et humidité).

**Nappes** : `piezo_stats.json` contient les quantiles mensuels 10/50/90 % de chaque
piézomètre actif (15 ans). L'appli télécharge les dernières mesures Hub'Eau et calcule une
anomalie −1…+1, moyennée (inverse distance) sur 25 km. Effet limité aux fonds humides.

## 5. Parité Python ↔ Kotlin

`pipeline/mycoscope_pipeline/model.py` est la référence. `tests/make_fixture.py` produit
`app/src/test/resources/model_fixture.json` (36 séries, 240 cas d'habitat) et un petit
PMTiles ; `ModelParityTest` vérifie que Kotlin reproduit tout à 1e-5. **Après toute
modification du modèle ou de species.json : relancer `PYTHONPATH=. python tests/make_fixture.py`.**

## 6. Limites connues et pistes

- Paramètres = connaissances naturalistes, **non calibrés**. Piste prioritaire : calage et
  validation avec les occurrences GBIF / INPN (datées et localisées) contre la météo ERA5-Land
  de la même date (AUC pour l'habitat, délai pluie → récolte pour la phénologie).
- BD Forêt : essence dominante seulement (pas de bouleau, charme, frêne distincts),
  millésimes 2007–2018. Les espèces de prairie (coulemelle) et la morille sont mal servies
  par une carte forestière : marquées « expérimental ». Piste : OCS GE / Copernicus HRL Grassland.
- pH SoilGrids : 250 m, modélisé. Géologie 1/50 000 : formations superficielles parfois absentes.
- TWI sur MNT 30 m, bassins tronqués aux bords (marge 6 km) : sans effet sauf grandes vallées.
- Météo : maille Open-Meteo (≈2–11 km selon modèles), pluie très locale en été mal captée.
- Hors France : remplacer BD Forêt par Copernicus HRL Forest Type + cartes d'essences
  (Bonannella et al. 2022, 30 m), BD Charm par GLiM ; Hub'Eau → anomalie ERA5-Land profonde.
  Le format de tuile et l'appli n'ont pas à changer.
