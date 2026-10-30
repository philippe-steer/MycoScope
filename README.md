# MycoScope

Météo des champignons comestibles pour Android : une carte par espèce (cèpes, girolles,
trompettes, chanterelles, pieds de mouton, lactaires, morilles…) qui croise
**l'habitat** (essences forestières, géologie, pH du sol, relief) et **la météo des
semaines passées et à venir** (pluie décalée, température du sol, humidité, gel, nappes).

Sans publicité, sans compte, sans serveur : données ouvertes uniquement.

> MycoScope n'identifie aucun champignon. Ne consommez jamais un champignon sans
> certitude absolue (pharmacien, société mycologique). Respectez la réglementation locale et
> la propriété des forêts.

## Utilisation

- **Changer** : choisir l'espèce.
- **Conditions du jour / Habitat seul** : indice complet, ou potentiel d'habitat seul.
- **Curseur** : de J-14 à J+7 (prévisions).
- **Toucher la carte** : fiche du point (essence, géologie, pH, altitude, exposition, TWI,
  courbe de fructification, pluie récente, confusions dangereuses).
- **⚙** : fond OpenTopoMap/OSM, source des couches (URL ou fichier local).

## Construire

| Étape | Où | Comment |
|---|---|---|
| APK | GitHub Actions « Build APK » | à chaque push sur `main` ; APK dans la branche `apk` et en artefact |
| Couches France | Actions « Data – couches France » | lancement manuel (≈ 96 jobs) → release `data-v1/france.pmtiles` |
| Nappes | Actions « Data – statistiques des nappes » | manuel ou tous les 3 mois → `assets/piezo_stats.json` |

Pipeline en local :

```bash
pip install -r pipeline/requirements.txt
cd pipeline
python -m mycoscope_pipeline.build_dept 35 out/35         # un département
python -m mycoscope_pipeline.merge out/* -o france.pmtiles
python -m pytest tests                                    # tests hors réseau
PYTHONPATH=. python tests/make_fixture.py                 # après toute modif. du modèle
```

Le modèle et ses hypothèses sont décrits dans [DESIGN.md](DESIGN.md) ; les paramètres des
espèces sont dans [`species.json`](app/src/main/assets/species.json).

## Sources de données

IGN BD Forêt® V2 (Licence Ouverte) · BRGM BD Charm-50 · ISRIC SoilGrids 2.0 (CC-BY 4.0) ·
Copernicus DEM GLO-30 (© DLR/Airbus, ESA) · Open-Meteo (CC-BY 4.0) · Hub'Eau / ADES ·
contours france-geojson · fonds © OpenStreetMap, OpenTopoMap.

Licence : GPL-3.0.
