package fr.mycoscope.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fr.mycoscope.model.Enc
import fr.mycoscope.model.Model
import fr.mycoscope.model.Species
import fr.mycoscope.model.trap
import kotlin.math.exp

/** Onglet « Comprendre » : comment l'indice est calculé, avec les paramètres de l'espèce choisie. */
@Composable
fun ExplainScreen(species: List<Species>, current: Species, onPick: (String) -> Unit) {
    val sp = current
    val accent = Color(sp.color)
    Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(12.dp)) {
        Text("Comment MycoScope estime les champignons", fontWeight = FontWeight.Bold, fontSize = 20.sp)
        Spacer(Modifier.height(6.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            species.forEach { s -> FilterChip(selected = s.id == sp.id, onClick = { onPick(s.id) }, label = { Text(s.nameFr) }) }
        }
        Spacer(Modifier.height(8.dp))

        Section("1. Le principe") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Pill("OÙ ?\nHabitat", "essence × géologie × pH × altitude", Color(0xFF5B7F3A), Modifier.weight(1f))
                Text("×", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Pill("QUAND ?\nFructification", "pluie décalée × T° du sol × humidité × saison", Color(0xFF2F6FA8), Modifier.weight(1f))
                Text("=", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Pill("Indice", "0 à 100 %", accent, Modifier.weight(0.7f))
            }
            Note("Chaque facteur vaut entre 0 et 1 ; ils se multiplient. Il suffit donc qu'un seul soit défavorable " +
                "(mauvais arbre, sol trop sec, gel…) pour que l'indice s'effondre.")
        }

        Section("2. Où ? Les arbres hôtes de : ${sp.nameFr}") {
            val hosts = Enc.FOREST.filter { it.value >= 10 }.map { (k, code) -> (Enc.FOREST_LABEL[code] ?: k) to sp.hostT[code] }
                .filter { it.second > 0.01 }.sortedByDescending { it.second }
            hosts.forEach { (l, v) -> WeightRow(l, v, accent) }
            Note("Les champignons recherchés sont surtout mycorhiziens : ils vivent en association avec les racines " +
                "de certains arbres. Peuplements : IGN BD Forêt V2 (essence dominante, parcelles ≥ 0,5 ha).")
        }

        Section("3. Où ? Géologie et pH du sol") {
            Enc.LITHO.filter { it.value in 1..15 }.map { (k, code) -> (Enc.LITHO_LABEL[code] ?: k) to sp.lithoT[code] }
                .sortedByDescending { it.second }.forEach { (l, v) -> WeightRow(l, v, Color(0xFF8C7A5B)) }
            Spacer(Modifier.height(8.dp))
            val ph = sp.phRange
            Curve("pH du sol (SoilGrids)", 3.5, 8.5, "pH", accent) { x -> sp.phFloor + (1 - sp.phFloor) * trap(x, ph[0], ph[1], ph[2], ph[3]) }
            val e = sp.elevR
            Curve("Altitude", 0.0, 2500.0, "m", accent) { x -> trap(x, e[0], e[1], e[2], e[3]) }
            Note("Roche-mère : BRGM BD Charm-50 (1/50 000). Le pH module l'habitat sans l'annuler (plancher " +
                "${(sp.phFloor * 100).toInt()} %), car il est estimé à 250 m de résolution.")
        }

        Section("4. Quand ? Le délai après la pluie") {
            val lag = sp.lag
            val sd = sp.lagSd
            Curve("Poids d'une pluie selon son ancienneté", 0.0, 45.0, "jours avant", Color(0xFF2F6FA8),
                marks = listOf(lag to "pic ${lag.toInt()} j")) { x -> exp(-0.5 * ((x - lag) / sd) * ((x - lag) / sd)) }
            Note("Une pluie tombée il y a environ ${lag.toInt()} jours (± ${sd.toInt()}) compte le plus : c'est le temps " +
                "que le mycélium forme des primordia puis des fructifications.")
            Curve("Effet de la quantité de pluie (au bon délai)", 0.0, 100.0, "mm", Color(0xFF2F6FA8),
                marks = listOf(sp.rainRef to "${sp.rainRef.toInt()} mm → 63 %")) { x -> 1 - exp(-x / sp.rainRef) }
        }

        Section("5. Quand ? Température, humidité, saison") {
            val t = sp.tsoil
            Curve("Température du sol (moyenne glissante de l'air, ~10 cm)", -2.0, 30.0, "°C", Color(0xFFC4452F)) { x -> trap(x, t[0], t[1], t[2], t[3]) }
            val m = sp.moisture
            Curve("Humidité du sol (réserve de 120 mm)", 0.0, 1.0, "fraction", Color(0xFF2F8FA8)) { x -> trap(x, m[0], m[1], m[2], m[3]) }
            SeasonBar(sp, accent)
            Note("Gel : une minimale sous ${sp.frostC.toInt()} °C détruit les fructifications (reprise en ~5 jours). " +
                "Une poussée reste visible environ ${sp.persistence.toInt()} jours." +
                (if (sp.coldShock > 0.01) " Un coup de froid de 2 à 6 °C au bon moment augmente l'indice (jusqu'à +${(sp.coldShock * 100).toInt()} %)." else ""))
        }

        Section("6. Corrections locales, au pixel près (≈ 27 m)") {
            Note("• Altitude : la température est corrigée de −0,65 °C par 100 m.\n" +
                "• Exposition : un versant sud compte comme 120 m plus bas (plus chaud), un versant nord 120 m plus haut.\n" +
                "• Topographie (TWI, indice d'humidité) : les fonds de vallon gardent l'eau, les crêtes sèchent " +
                "(±0,03 d'humidité par unité de TWI, confirmé par le calage : 0,025).\n" +
                "• Nappes (Hub'Eau, 2 604 piézomètres) : dans les fonds humides, une nappe haute ajoute de l'humidité, " +
                "une nappe basse en retire.")
        }

        Section("7. Fiabilité et incertitude") {
            if (sp.calibrated) {
                Note("✔ Phénologie calée sur ${sp.nObs} observations datées (GBIF / INPN), confrontées à la météo " +
                    "SAFRAN du jour même, avec correction des sorties des observateurs. Gain de prédiction en " +
                    "validation croisée : +${"%.2f".format(sp.cvGain)} (nats par observation).")
            } else {
                Note("Paramètres a priori (connaissances naturalistes), non encore validés par des observations" +
                    (if (sp.experimental) " ; espèce marquée expérimentale : sa carte est peu fiable." else "."))
            }
            Note("La fiche d'un point affiche une fourchette : on recalcule l'indice en faisant varier le délai " +
                "(±3 j), le seuil de pluie (×0,75 à ×1,33), la température optimale (±1,5 °C) et, pour les jours à venir, " +
                "la pluie prévue (×0,5 à ×1,6). Plus la fourchette est large, moins l'estimation est sûre. " +
                "Ne sont pas comptées : les erreurs de carte (essence, roche), la météo très locale (orages) " +
                "et la pression de cueillette.")
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
        Column(Modifier.padding(12.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            Spacer(Modifier.height(6.dp))
            content()
        }
    }
}

@Composable
private fun Note(t: String) {
    Text(t, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
}

@Composable
private fun Pill(title: String, sub: String, color: Color, modifier: Modifier) {
    Column(modifier.background(color.copy(alpha = 0.15f), RoundedCornerShape(10.dp))
        .border(1.dp, color, RoundedCornerShape(10.dp)).padding(6.dp)) {
        Text(title, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = color)
        Text(sub, fontSize = 10.sp)
    }
}

@Composable
private fun WeightRow(label: String, v: Double, color: Color) {
    Row(Modifier.fillMaxWidth().padding(vertical = 1.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, fontSize = 12.sp, modifier = Modifier.weight(1.2f), maxLines = 1)
        Box(Modifier.weight(1f).height(10.dp).background(Color(0x22888888), RoundedCornerShape(3.dp))) {
            Box(Modifier.fillMaxWidth(v.toFloat().coerceIn(0.01f, 1f)).height(10.dp).background(color, RoundedCornerShape(3.dp)))
        }
        Text("${(v * 100).toInt()} %", fontSize = 11.sp, modifier = Modifier.width(42.dp).padding(start = 4.dp))
    }
}

@Composable
private fun Curve(title: String, x0: Double, x1: Double, unit: String, color: Color,
                  marks: List<Pair<Double, String>> = emptyList(), f: (Double) -> Double) {
    val axis = MaterialTheme.colorScheme.onSurfaceVariant
    Text(title, fontSize = 12.sp, fontWeight = FontWeight.Medium)
    Canvas(Modifier.fillMaxWidth().height(70.dp).padding(vertical = 4.dp)) {
        val n = 120
        val p = Path()
        for (k in 0..n) {
            val x = x0 + (x1 - x0) * k / n
            val y = f(x).coerceIn(0.0, 1.0)
            val px = size.width * k / n
            val py = size.height * (1 - y.toFloat())
            if (k == 0) p.moveTo(px, py) else p.lineTo(px, py)
        }
        val fill = Path().apply { addPath(p); lineTo(size.width, size.height); lineTo(0f, size.height); close() }
        drawPath(fill, color.copy(alpha = 0.18f))
        drawPath(p, color, style = Stroke(2.5f))
        drawLine(axis, Offset(0f, size.height), Offset(size.width, size.height), 1f)
        marks.forEach { (mx, _) ->
            val px = (size.width * ((mx - x0) / (x1 - x0))).toFloat()
            drawLine(axis, Offset(px, 0f), Offset(px, size.height), 1.5f)
        }
    }
    Row(Modifier.fillMaxWidth()) {
        Text(fmt(x0), fontSize = 10.sp, color = axis)
        Spacer(Modifier.weight(1f))
        Text((marks.joinToString("  ") { it.second }).ifBlank { unit }, fontSize = 10.sp, color = axis)
        Spacer(Modifier.weight(1f))
        Text("${fmt(x1)} $unit", fontSize = 10.sp, color = axis)
    }
}

private fun fmt(x: Double) = if (x == x.toLong().toDouble()) x.toLong().toString() else "%.1f".format(x)

@Composable
private fun SeasonBar(sp: Species, color: Color) {
    val axis = MaterialTheme.colorScheme.onSurfaceVariant
    Text("Saison de fructification", fontSize = 12.sp, fontWeight = FontWeight.Medium)
    Canvas(Modifier.fillMaxWidth().height(26.dp).padding(vertical = 4.dp)) {
        for (d in 1..365) {
            val v = Model.season(d, sp.season[0], sp.season[1]).toFloat()
            if (v > 0f) drawRect(color.copy(alpha = 0.25f + 0.75f * v), Offset(size.width * (d - 1) / 365f, 0f),
                Size(size.width / 365f + 0.5f, size.height))
        }
        for (m in 0..12) {
            val x = size.width * m / 12f
            drawLine(axis, Offset(x, size.height * 0.6f), Offset(x, size.height), 1f)
        }
        val today = java.time.LocalDate.now().dayOfYear
        drawLine(Color.Black, Offset(size.width * today / 365f, 0f), Offset(size.width * today / 365f, size.height), 2.5f)
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        "JFMAMJJASOND".forEach { Text(it.toString(), fontSize = 10.sp, color = axis) }
    }
}

@Suppress("unused")
@Composable
private fun Dot(c: Color) = Box(Modifier.size(8.dp).background(c, RoundedCornerShape(4.dp)))
