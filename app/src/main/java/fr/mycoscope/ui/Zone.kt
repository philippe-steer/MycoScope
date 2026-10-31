package fr.mycoscope.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fr.mycoscope.data.DailyWeatherAt
import fr.mycoscope.data.PmTiles
import fr.mycoscope.data.WeatherGrid
import fr.mycoscope.map.MushroomOverlay
import fr.mycoscope.map.Ramp
import fr.mycoscope.map.TileMath
import fr.mycoscope.model.Enc
import fr.mycoscope.model.Model
import fr.mycoscope.model.Species
import kotlin.math.cos
import kotlin.math.floor

/** Bilan d'un secteur (~8 km autour d'un point) : milieu et espèces à chercher. */
class ZoneReport(
    val lat: Double, val lon: Double,
    val forestShare: Double,
    val essences: List<Pair<String, Double>>,
    val geology: List<Pair<String, Double>>,
    val elevRange: Pair<Double, Double>,
    val rows: List<Row>,
    val weatherOk: Boolean,
) {
    class Row(
        val sp: Species,
        val habitatTop: Double,      // 90e centile de l'habitat dans le secteur
        val favorableShare: Double,  // part du secteur avec habitat > 0,5
        val today: Double,           // fructification aujourd'hui (altitude typique)
        val week: Double,            // maximum sur les 7 prochains jours
        val inSeason: Boolean,
    ) {
        val score get() = habitatTop * today
        val scoreWeek get() = habitatTop * week
    }
}

object Zone {
    const val RADIUS_KM = 8.0

    /** Calcul hors du fil principal ; `weather` = séries au point (null si indisponibles). */
    fun compute(pm: PmTiles, overlay: MushroomOverlay, species: List<Species>, lat: Double, lon: Double,
                weather: DailyWeatherAt?): ZoneReport {
        val z = 11
        val kx = 111.0 * cos(Math.toRadians(lat))
        val dLat = RADIUS_KM / 111.0
        val dLon = RADIUS_KM / kx
        val x0 = floor(TileMath.tx(lon - dLon, z)).toInt()
        val x1 = floor(TileMath.tx(lon + dLon, z)).toInt()
        val y0 = floor(TileMath.ty(lat + dLat, z)).toInt()
        val y1 = floor(TileMath.ty(lat - dLat, z)).toInt()
        val pix = ArrayList<Int>()
        for (y in y0..y1) for (x in x0..x1) {
            val px = runCatching { overlay.pixels(pm, z, x, y) }.getOrNull() ?: continue
            for (j in 0 until 256) {
                val la = TileMath.lat(y + (j + 0.5) / 256.0, z)
                for (i in 0 until 256) {
                    val lo = TileMath.lon(x + (i + 0.5) / 256.0, z)
                    val dx = (lo - lon) * kx
                    val dy = (la - lat) * 111.0
                    if (dx * dx + dy * dy > RADIUS_KM * RADIUS_KM) continue
                    val c = px[j * 256 + i]
                    if (Enc.valid(c)) pix += c
                }
            }
        }
        val n = pix.size.coerceAtLeast(1)
        val forest = pix.filter { Enc.forest(it) >= 10 }
        val ess = forest.groupingBy { Enc.FOREST_LABEL[Enc.forest(it)] ?: "?" }.eachCount()
            .entries.sortedByDescending { it.value }.take(5).map { it.key to it.value.toDouble() / forest.size.coerceAtLeast(1) }
        val geo = pix.groupingBy { Enc.LITHO_LABEL[Enc.litho(it)] ?: "?" }.eachCount()
            .entries.sortedByDescending { it.value }.take(4).map { it.key to it.value.toDouble() / n }
        val elevs = (if (forest.isNotEmpty()) forest else pix).map { Enc.elev(it) }.filter { it.isFinite() }.sorted()
        val zMed = if (elevs.isEmpty()) 200.0 else elevs[elevs.size / 2]
        val range = if (elevs.isEmpty()) 0.0 to 0.0 else elevs[(elevs.size * 0.05).toInt()] to elevs[(elevs.size * 0.95).toInt().coerceAtMost(elevs.size - 1)]

        val t = WeatherGrid.TODAY
        val rows = species.map { sp ->
            val h = pix.map { sp.habitatPixel(it) }.sorted()
            val top = if (h.isEmpty()) 0.0 else h[(h.size * 0.9).toInt().coerceAtMost(h.size - 1)]
            val fav = h.count { it > 0.5 }.toDouble() / n
            var today = 0.0
            var week = 0.0
            if (weather != null && weather.w.n > t) {
                val f = Model.fruiting(sp, weather.w, zMed, 0.0)
                today = f[t]
                for (k in t until minOf(f.size, t + 8)) week = maxOf(week, f[k])
            }
            val doy = java.time.LocalDate.now().dayOfYear
            ZoneReport.Row(sp, top, fav, today, week, Model.season(doy, sp.season[0], sp.season[1]) > 0.0)
        }.sortedWith(compareByDescending<ZoneReport.Row> { it.scoreWeek }.thenByDescending { it.habitatTop })
        return ZoneReport(lat, lon, forest.size.toDouble() / n, ess, geo, range, rows, weather != null)
    }
}

@Composable
fun ZoneCard(r: ZoneReport?, loading: Boolean, modifier: Modifier, onPick: (Species) -> Unit, onClose: () -> Unit) {
    Card(modifier.fillMaxWidth().heightIn(max = 560.dp)) {
        Column(Modifier.padding(14.dp).verticalScroll(rememberScrollState())) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Que trouver dans ce secteur ?", fontWeight = FontWeight.Bold, fontSize = 17.sp, modifier = Modifier.weight(1f))
                TextButton(onClick = onClose) { Text("Fermer") }
            }
            if (r == null) {
                Text(if (loading) "Analyse du secteur (rayon ${Zone.RADIUS_KM.toInt()} km)…" else "Pas de données ici.", fontSize = 13.sp)
                return@Column
            }
            Text("Rayon ${Zone.RADIUS_KM.toInt()} km · forêt ${(r.forestShare * 100).toInt()} % · altitude " +
                "${r.elevRange.first.toInt()}–${r.elevRange.second.toInt()} m", fontSize = 12.sp)
            if (r.essences.isNotEmpty()) Text("Peuplements : " + r.essences.joinToString { "${it.first} ${(it.second * 100).toInt()} %" }, fontSize = 12.sp)
            Text("Géologie : " + r.geology.joinToString { "${it.first} ${(it.second * 100).toInt()} %" }, fontSize = 12.sp)
            Spacer(Modifier.height(8.dp))
            Row {
                Text("Espèce", Modifier.weight(1.3f), fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Text("Habitat", Modifier.weight(1f), fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Text(if (r.weatherOk) "Auj. / 7 j" else "Météo ?", Modifier.weight(1f), fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
            }
            r.rows.forEach { row ->
                Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1.3f)) {
                        TextButton(onClick = { onPick(row.sp) }, contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                            Box(Modifier.size(10.dp).background(Color(row.sp.color), RoundedCornerShape(5.dp)))
                            Spacer(Modifier.width(6.dp))
                            Text(row.sp.nameFr, fontSize = 13.sp, maxLines = 1)
                        }
                        if (!row.inSeason) Text("hors saison", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Bar(row.habitatTop, Modifier.weight(1f))
                    Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        Bar(row.score, Modifier.weight(1f))
                        Bar(row.scoreWeek, Modifier.weight(1f))
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
            Text("Habitat : meilleurs coins du secteur (90e centile). Auj. / 7 j : habitat × conditions de " +
                "fructification aujourd'hui et au mieux dans la semaine. Toucher une espèce pour l'afficher.",
                fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun Bar(v: Double, modifier: Modifier = Modifier) {
    Box(modifier.height(12.dp).padding(end = 4.dp).background(Color(0x22888888), RoundedCornerShape(3.dp))) {
        Box(Modifier.fillMaxWidth(v.toFloat().coerceIn(0.02f, 1f)).height(12.dp)
            .background(Color(Ramp.color(maxOf(v.toFloat(), 0.06f)) or (0xFF shl 24)), RoundedCornerShape(3.dp)))
    }
}
