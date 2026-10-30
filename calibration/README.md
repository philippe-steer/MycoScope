# Calages

## 2026-10-30 — adopté : phénologie de 3 espèces

Rapport complet : [report-2026-10-30.md](report-2026-10-30.md), figures : `figures-2026-10-30/`.

Adopté dans `species.json` (paramètres de fructification seulement) :

| Espèce | délai pluie → poussée | R₀ | gain VC (nats/obs.) |
|---|---|---|---|
| Cèpe de Bordeaux | 10 → 14,5 j | 30 → 39 mm | +0,13 |
| Cèpe d'été / tête de nègre | 9 → 15,6 j | 25 → 33 mm | +0,15 |
| Coulemelle | 8 → 13,5 j | 20 → 33 mm | +0,18 |

Non adopté :
- **Phénologie des 9 autres espèces** : score encore inférieur au hasard après calage, délais peu crédibles
  (4 j pour la girolle). Probable biais d'effort : les observateurs sortent juste après la pluie.
  À refaire avec des témoins pondérés par l'effort (observations des autres champignons).
- **Habitat** : gains d'AUC faibles et poids marqués par l'accessibilité (alluvions en tête pour le cèpe,
  hêtre en baisse) ; on garde les a priori.
- **Nappes** : gain estimé nul (observations rarement en fond humide) ; on garde l'a priori 0,15.
  TWI confirmé (0,026 contre 0,03).
