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

## 2026-10-30 (soir) — correction du biais d'effort, phénologie de 8 espèces de plus

Rapport : [report-2026-10-30-effort.md](report-2026-10-30-effort.md), figures : `figures-2026-10-30-effort/`.

Les observateurs sortent juste après la pluie : sans correction, le délai pluie → poussée
s'effondre (girolle 4 j au premier calage ; test synthétique : 3 j estimés pour 12 j vrais).
Les jours témoins sont désormais pondérés par les observations de **polypores pérennes**
(amadouvier, ganoderme, tramète…, 14 560 observations), visibles toute l'année et donc
traceurs des sorties. Après correction, le score a priori devient positif pour 10 espèces sur 12.

Adopté (phénologie, gain VC ≥ 0,02) :

| Espèce | délai | R₀ | gain VC | remarque |
|---|---|---|---|---|
| Bolet bai | 9 → 8,5 j | 25 → 40 mm | +0,11 | |
| Lactaire délicieux / sanguin | 10 → 14,5 j | 30 → 41 mm | +0,08 | |
| Chanterelle jaunissante | 12 → 6,4 j | 30 → 45 mm | +0,07 | 177 obs. |
| Trompette de la mort | 14 → 23,2 j | 35 → 46 mm | +0,07 | poussée lente |
| Pied de mouton | 12 → 13,5 j | 25 → 19 mm | +0,04 | |
| Cèpe des pins | 10 → 12 j | 30 → 41 mm | +0,04 | 130 obs., incertain |
| Girolle | 8 → 5,5 j | 20 → 30 mm | +0,03 | délai court, à surveiller |
| Chanterelle en tube | 12 → 9,5 j | 30 → 33 mm | +0,03 | |

Inchangé : cèpes de Bordeaux et d'été, coulemelle (déjà calés, gain nul) ; morille (score
toujours négatif) ; habitat ; nappes (gain estimé nul). Tendance générale : R₀ plus élevé
(≈ 40 mm) que les a priori. Les intervalles bootstrap du rapport ne sont pas fiables
(ré-ajustements trop courts) : à refaire avant toute publication.
