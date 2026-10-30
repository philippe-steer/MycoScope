package fr.mycoscope.data

import android.content.Context
import org.json.JSONObject
import java.time.LocalDate
import kotlin.math.cos
import kotlin.math.sqrt

/**
 * Anomalie des nappes (-1 très basses … +1 très hautes) à partir des piézomètres Hub'Eau
 * (France). Les quantiles mensuels de chaque station sont précalculés par le pipeline
 * (assets/piezo_stats.json) ; l'appli ne télécharge que les dernières mesures.
 */
object Piezo {
    private class Station(val code: String, val lat: Double, val lon: Double, val q: Array<DoubleArray>)

    private var stations: List<Station> = emptyList()
    private val latest = HashMap<String, Pair<String, Double>>() // code → (date, niveau)
    private val anomalyCache = HashMap<String, Double>()

    fun load(ctx: Context) {
        if (stations.isNotEmpty()) return
        runCatching {
            val o = JSONObject(ctx.assets.open("piezo_stats.json").bufferedReader().readText()).getJSONObject("stations")
            val out = ArrayList<Station>()
            for (code in o.keys()) {
                val s = o.getJSONObject(code)
                val q = s.getJSONArray("q")
                out += Station(code, s.getDouble("lat"), s.getDouble("lon"),
                    Array(12) { m -> q.getJSONArray(m).let { a -> DoubleArray(3) { a.getDouble(it) } } })
            }
            stations = out
        }
    }

    private fun near(lat: Double, lon: Double, km: Double) = stations.filter {
        val dx = (it.lon - lon) * 111.0 * cos(Math.toRadians(lat))
        val dy = (it.lat - lat) * 111.0
        dx * dx + dy * dy < km * km
    }

    /** Télécharge les derniers niveaux des stations de la zone (silencieux en cas d'échec). */
    suspend fun refresh(south: Double, north: Double, west: Double, east: Double) {
        val todo = stations.filter {
            it.lat in (south - 0.3)..(north + 0.3) && it.lon in (west - 0.4)..(east + 0.4) &&
                synchronized(latest) { latest[it.code] } == null
        }
        val since = LocalDate.now().minusDays(30).toString()
        for (chunk in todo.chunked(100)) {
            runCatching {
                val url = "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/chroniques?code_bss=" +
                    chunk.joinToString(",") { java.net.URLEncoder.encode(it.code, "UTF-8") } +
                    "&date_debut_mesure=$since&size=5000&fields=code_bss,date_mesure,niveau_nappe_eau"
                val data = JSONObject(Http.getText(url)).getJSONArray("data")
                synchronized(latest) {
                    for (k in 0 until data.length()) {
                        val d = data.getJSONObject(k)
                        if (d.isNull("niveau_nappe_eau")) continue
                        val code = d.getString("code_bss")
                        val date = d.getString("date_mesure")
                        val prev = latest[code]
                        if (prev == null || prev.first < date) latest[code] = date to d.getDouble("niveau_nappe_eau")
                    }
                    anomalyCache.clear()
                }
            }
        }
    }

    private fun stationAnomaly(s: Station): Double? {
        val (date, v) = synchronized(latest) { latest[s.code] } ?: return null
        val q = s.q[date.substring(5, 7).toInt() - 1]
        val (p10, p50, p90) = Triple(q[0], q[1], q[2])
        val a = if (v >= p50) (v - p50) / (p90 - p50).coerceAtLeast(0.05) else (v - p50) / (p50 - p10).coerceAtLeast(0.05)
        return a.coerceIn(-1.0, 1.0)
    }

    /** Moyenne pondérée (inverse distance) des stations à moins de 25 km ; 0 si aucune. */
    fun anomaly(lat: Double, lon: Double): Double {
        val key = "%.2f,%.2f".format(lat, lon)
        synchronized(latest) { anomalyCache[key] }?.let { return it }
        var sw = 0.0
        var sa = 0.0
        for (s in near(lat, lon, 25.0)) {
            val a = stationAnomaly(s) ?: continue
            val dx = (s.lon - lon) * 111.0 * cos(Math.toRadians(lat))
            val dy = (s.lat - lat) * 111.0
            val w = 1.0 / (2.0 + sqrt(dx * dx + dy * dy))
            sw += w
            sa += w * a
        }
        val r = if (sw > 0) sa / sw else 0.0
        synchronized(latest) { anomalyCache[key] = r }
        return r
    }

    fun field(wx: WxField) = DoubleArray(wx.pts.size) { k ->
        val i = k % wx.nx + wx.i0
        val j = k / wx.nx + wx.j0
        anomaly(j * wx.s, i * wx.s)
    }
}
