# Calage MycoScope — 2026-10-30

13739 observations GBIF datées (France, 2000–2025, après nettoyage). Météo : SAFRAN-SIM2.

**Phénologie** : cas-témoins (même lieu, même jour de semaine, ±1–3 semaines). Score = gain de log-vraisemblance par observation par rapport au hasard (0 = aucun pouvoir, log 7 ≈ 1,95 = parfait). « VC » = validation croisée par blocs d'années : seul ce score décide de l'adoption des paramètres.

**Habitat** : présences vs observations des autres espèces (groupe cible), pixels forestiers, AUC en validation croisée spatiale (blocs de 0,5°).

**Effort** : jours témoins pondérés par les observations de polypores pérennes (traceurs des sorties) à moins de 100 km et ±2 jours ; « effort » = part des observations où ce poids est informatif.

| Espèce | obs. | phéno | effort | VC a priori | VC calé | délai (a priori → calé [IC 80 %]) | R₀ mm | habitat | AUC a priori | AUC calé |
|---|---|---|---|---|---|---|---|---|---|---|
| Cèpe de Bordeaux | 1859 | 1495 | 0.96 | 0.188 | 0.193 | 14 → 14.5 [13.4–14.2] | 39 → 45 [49–50] | 293 | 0.542 | 0.603 |
| Cèpe d'été / tête de nègre | 1186 | 980 | 0.89 | 0.226 | 0.211 | 16 → 16.0 [15.6–16.3] | 32 → 38 [41–43] | 166 | 0.622 | 0.644 |
| Cèpe des pins | 233 | 130 | 0.94 | 0.109 | 0.150 | 10 → 12.0 [15.6–24.6] | 30 → 41 [43–51] | 17 | – | – |
| Bolet bai | 1365 | 1203 | 0.97 | 0.015 | 0.125 | 9 → 8.5 [6.8–11.8] | 25 → 40 [50–53] | 229 | 0.665 | 0.647 |
| Girolle | 1620 | 1328 | 0.93 | 0.046 | 0.080 | 8 → 5.5 [4.0–4.5] | 20 → 30 [38–39] | 221 | 0.556 | 0.542 |
| Trompette de la mort | 773 | 614 | 0.93 | -0.011 | 0.056 | 14 → 23.2 [22.0–23.2] | 35 → 46 [53–56] | 130 | 0.635 | 0.639 |
| Chanterelle en tube | 1105 | 889 | 0.97 | 0.179 | 0.212 | 12 → 9.5 [3.2–7.2] | 30 → 33 [36–38] | 159 | 0.625 | 0.632 |
| Chanterelle jaunissante | 257 | 177 | 0.89 | 0.032 | 0.102 | 12 → 6.4 [3.4–6.1] | 30 → 45 [50–59] | 38 | – | – |
| Pied de mouton | 1797 | 1514 | 0.95 | 0.101 | 0.142 | 12 → 13.5 [13.6–15.2] | 25 → 19 [14–18] | 183 | 0.571 | 0.539 |
| Lactaire délicieux / sanguin | 1215 | 1000 | 0.95 | 0.023 | 0.102 | 10 → 14.5 [15.3–21.0] | 30 → 41 [50–53] | 164 | 0.710 | 0.716 |
| Morille | 485 | 394 | 0.81 | -0.144 | -0.036 | 7 → 6.7 [6.2–8.6] | 15 → 23 [27–34] | 75 | – | – |
| Coulemelle | 1844 | 1568 | 0.93 | 0.156 | 0.165 | 14 → 14.5 [14.1–14.5] | 33 → 42 [47–49] | 403 | 0.498 | 0.600 |

**Humidité locale** (toutes espèces) : TWI_GAIN = 0.025 (a priori 0,03), GW_GAIN = -0.001 (a priori 0,15).

Paramètres adoptés seulement si la validation croisée s'améliore. Figures : `figures/`.
Limites : données de présence seule, dates parfois de saisie, coordonnées approximatives, observateurs concentrés près des villes ; l'AUC mesure la préférence relative entre espèces.