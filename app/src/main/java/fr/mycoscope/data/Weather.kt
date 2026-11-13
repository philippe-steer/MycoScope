package fr.mycoscope.data

import fr.mycoscope.BuildConfig
import fr.mycoscope.model.DailyWeather
import fr.mycoscope.model.Model
import fr.mycoscope.model.Species
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.Locale
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.min

object Http {
    val UA = "MycoScope/" + BuildConfig.VERSION_NAME + " (+https://github.com/philippe-steer/MycoScope)"

    suspend fun getBytes(url: String): ByteArray = withContext(Dispatchers.IO) {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 60_000
        conn.setRequestProperty("User-Agent", UA)
        try {
            if (conn.responseCode !in 200..299) throw IOException("HTTP ${conn.responseCode}")
            conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    suspend fun getText(url: String): String = withContext(Dispatchers.IO) {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 60_000
        conn.setRequestProperty("User-Agent", UA)
        try {
            val code = conn.responseCode
            if (code !in 200..299) {
                val err = conn.errorStream?.use { String(it.readBytes()) } ?: ""
                throw IOException("HTTP $code ${err.take(200)}")
            }
            conn.inputStream.use { String(it.readBytes(), Charsets.UTF_8) }
        } finally {
            conn.disconnect()
        }
    }
}

fun Double.f3(): String = String.format(Locale.US, "%.3f", this)

/**
 * Météo journalière sur un treillis régulier de points (pas `s` en degrés), 60 jours passés
 * + 8 jours de prévision (Open-Meteo, gratuit sans clé). Chaque point est mis en cache sur
 * disque pour la journée : la carte reste utilisable hors réseau le jour même.
 */
object WeatherGrid {
    const val PAST = 60
    const val FUTURE = 8
    const val N_DAYS = PAST + FUTURE
    /** Fenêtre affichée : J-14 … J+7 (index dans les séries : PAST + offset). */
    const val SHOW_FROM = -14
    const val SHOW_TO = 7
    const val TODAY = PAST
    private val SPACINGS = doubleArrayOf(0.125, 0.25, 0.5, 1.0)
    private const val VARS = "precipitation_sum,temperature_2m_mean,temperature_2m_min,et0_fao_evapotranspiration"
    // Open-Meteo gratuit : 600 appels/min, 5 000/h, 10 000/j ; 68 jours ≈ 5 appels par point.
    private const val PER_REQUEST = 20
    private const val PAUSE_MS = 2_500L
    /** Durée de validité d'un point : Open-Meteo recalcule ses prévisions plusieurs fois par jour. */
    const val TTL_MS = 3 * 3600_000L

    lateinit var cacheRoot: File
    @Volatile private var cooldownUntil = 0L
    @Volatile private var cooldownReason = ""
    private val mem = HashMap<String, Pair<Long, DailyWeather>>()

    /** Oublie le cache mémoire (les fichiers restent comme secours hors réseau). */
    fun invalidate() = synchronized(mem) { mem.clear() }

    fun spacingFor(latSpan: Double, lonSpan: Double): Double {
        val target = min(latSpan, lonSpan) / 3.0
        return SPACINGS.firstOrNull { it >= target } ?: SPACINGS.last()
    }

    fun today(): LocalDate = LocalDate.now(ZoneOffset.UTC)

    private fun file(s: Double, i: Int, j: Int) = File(cacheRoot, "wx/${today()}/${s}_${i}_$j.json")

    /** Valeurs manquantes écrites `null` : org.json refuse NaN (toString() renverrait null). */
    private fun ja(a: DoubleArray) = JSONArray().also { j -> a.forEach { j.put(if (it.isFinite()) it else JSONObject.NULL) } }

    private fun toJson(w: DailyWeather) = JSONObject()
        .put("doy", JSONArray(w.doy.toList())).put("p", ja(w.precip))
        .put("t", ja(w.tmean)).put("tn", ja(w.tmin))
        .put("e", ja(w.et0)).put("z", if (w.elevation.isFinite()) w.elevation else 0.0)

    private fun arr(o: JSONObject, k: String): DoubleArray {
        val a = o.getJSONArray(k)
        return DoubleArray(a.length()) { if (a.isNull(it)) Double.NaN else a.optDouble(it, Double.NaN) }
    }

    private fun fromJson(o: JSONObject) = DailyWeather(
        arr(o, "doy").map { it.toInt() }.toIntArray(), arr(o, "p"), arr(o, "t"), arr(o, "tn"), arr(o, "e"), o.getDouble("z"),
    )

    /** Points du treillis couvrant la boîte (+ marge d'un pas), téléchargés si besoin. */
    suspend fun field(south: Double, north: Double, west: Double, east: Double, s: Double, force: Boolean = false): WxField {
        val i0 = floor(west / s).toInt() - 1
        val i1 = ceil(east / s).toInt() + 1
        val j0 = floor(south / s).toInt() - 1
        val j1 = ceil(north / s).toInt() + 1
        val nx = i1 - i0 + 1
        val ny = j1 - j0 + 1
        if (nx * ny > 900) throw IOException("zone trop grande")
        val pts = arrayOfNulls<DailyWeather>(nx * ny)
        val stamps = LongArray(nx * ny)
        val fallback = arrayOfNulls<DailyWeather>(nx * ny)
        val missing = ArrayList<Triple<Int, Int, Int>>()
        val now0 = System.currentTimeMillis()
        val day = today()
        withContext(Dispatchers.IO) {
            for (j in j0..j1) for (i in i0..i1) {
                val k = "$day|$s|$i|$j"
                val idx = (j - j0) * nx + (i - i0)
                val m = synchronized(mem) { mem[k] }
                if (m != null && !force && now0 - m.first < TTL_MS) { pts[idx] = m.second; stamps[idx] = m.first; continue }
                val f = file(s, i, j)
                val w = if (f.exists()) runCatching { fromJson(JSONObject(f.readText())) }.getOrNull() else null
                if (w != null && !force && now0 - f.lastModified() < TTL_MS) {
                    pts[idx] = w; stamps[idx] = f.lastModified()
                    synchronized(mem) { mem[k] = f.lastModified() to w }
                } else {
                    fallback[idx] = w ?: m?.second  // version plus ancienne du jour, si le réseau manque
                    stamps[idx] = if (w != null) f.lastModified() else (m?.first ?: 0L)
                    missing += Triple(i, j, idx)
                }
            }
        }
        var limited: String? = null
        var retryIn = 0L
        for ((ci, chunk) in missing.chunked(PER_REQUEST).withIndex()) {
            val now = android.os.SystemClock.elapsedRealtime()
            if (now < cooldownUntil) {
                limited = cooldownReason
                retryIn = (cooldownUntil - now) / 1000 + 1
                break
            }
            if (ci > 0) kotlinx.coroutines.delay(PAUSE_MS)
            val lats = chunk.joinToString(",") { (it.second * s).f3() }
            val lons = chunk.joinToString(",") { (it.first * s).f3() }
            val url = "https://api.open-meteo.com/v1/forecast?latitude=$lats&longitude=$lons&daily=$VARS" +
                "&past_days=$PAST&forecast_days=$FUTURE&timezone=GMT"
            val txt = try {
                Http.getText(url)
            } catch (e: IOException) {
                val msg = e.message ?: ""
                if (!msg.startsWith("HTTP 429")) {
                    if (fallback.any { it != null }) { limited = "réseau indisponible"; retryIn = 120; break }
                    throw e
                }
                val (secs, why) = when {
                    msg.contains("Daily", true) -> 3600L * 3 to "limite journalière"
                    msg.contains("Hourly", true) -> 900L to "limite horaire"
                    else -> 65L to "limite par minute"
                }
                cooldownUntil = android.os.SystemClock.elapsedRealtime() + secs * 1000
                cooldownReason = why
                limited = why
                retryIn = secs
                break
            }
            val t = txt.trimStart()
            val objs = if (t.startsWith("[")) JSONArray(t).let { a -> List(a.length()) { a.getJSONObject(it) } } else listOf(JSONObject(t))
            if (objs.size != chunk.size) throw IOException("réponse météo inattendue")
            withContext(Dispatchers.IO) {
                chunk.forEachIndexed { c, (i, j, idx) ->
                    val o = objs[c]
                    val d = o.getJSONObject("daily")
                    val times = d.getJSONArray("time")
                    val doy = IntArray(times.length()) { LocalDate.parse(times.getString(it)).dayOfYear }
                    val w = DailyWeather(
                        doy, arr(d, "precipitation_sum"), arr(d, "temperature_2m_mean"), arr(d, "temperature_2m_min"),
                        arr(d, "et0_fao_evapotranspiration"), o.optDouble("elevation", 0.0),
                    )
                    pts[idx] = w
                    val t = System.currentTimeMillis()
                    stamps[idx] = t
                    synchronized(mem) { mem["$day|$s|$i|$j"] = t to w }
                    val f = file(s, i, j)
                    f.parentFile?.mkdirs()
                    toJson(w).toString()?.let { f.writeText(it) }
                }
            }
        }
        // points non rafraîchis : on garde la version antérieure du jour plutôt qu'un trou
        var usedOld = false
        for (k in pts.indices) if (pts[k] == null && fallback[k] != null) { pts[k] = fallback[k]; usedOld = true }
        cleanOld()
        if (pts.all { it == null }) throw IOException("Open-Meteo : $limited, nouvel essai dans $retryIn s")
        val oldest = stamps.filterIndexed { k, t -> pts[k] != null && t > 0 }.minOrNull() ?: now0
        return WxField(s, i0, j0, nx, ny, pts,
            limited?.let { if (it == "réseau indisponible") it else "$it Open-Meteo" }, retryIn,
            day = day, fetchedAt = oldest, usedOld = usedOld)
    }

    private fun cleanOld() {
        val keep = today().toString()
        File(cacheRoot, "wx").listFiles()?.filter { it.name != keep }?.forEach { it.deleteRecursively() }
    }
}

/** Séries météo au point de treillis le plus proche d'un lieu. */
class DailyWeatherAt(val w: DailyWeather)

/** Météo au lieu : depuis le champ courant s'il le couvre, sinon petite requête (1 à 4 points). */
suspend fun weatherAt(lat: Double, lon: Double, field: WxField?): DailyWeatherAt? {
    field?.let { f ->
        val i = Math.round(lon / f.s).toInt() - f.i0
        val j = Math.round(lat / f.s).toInt() - f.j0
        if (i in 0 until f.nx && j in 0 until f.ny) f.pts[j * f.nx + i]?.let { return DailyWeatherAt(it) }
    }
    return runCatching {
        val f = WeatherGrid.field(lat - 0.01, lat + 0.01, lon - 0.01, lon + 0.01, 0.125)
        val i = Math.round(lon / f.s).toInt() - f.i0
        val j = Math.round(lat / f.s).toInt() - f.j0
        f.pts[j * f.nx + i]?.let { DailyWeatherAt(it) }
    }.getOrNull()
}

/** Treillis de séries météo ; `pts[(j - j0) * nx + (i - i0)]`, point (lon = i·s, lat = j·s). */
class WxField(
    val s: Double, val i0: Int, val j0: Int, val nx: Int, val ny: Int, val pts: Array<DailyWeather?>,
    /** non nul si le téléchargement a été interrompu par une limite Open-Meteo */
    val partial: String? = null,
    val retryIn: Long = 0,
    /** jour (UTC) des séries : l'indice PAST y correspond à « aujourd'hui » */
    val day: LocalDate = WeatherGrid.today(),
    /** heure de la donnée la plus ancienne du champ (ms) */
    val fetchedAt: Long = System.currentTimeMillis(),
    /** vrai si une partie des points vient d'un téléchargement antérieur (réseau ou quota) */
    val usedOld: Boolean = false,
) {
    /** À recharger : changement de jour ou prévisions de plus de 3 h. */
    fun stale(now: Long = System.currentTimeMillis()) =
        day != WeatherGrid.today() || now - fetchedAt > WeatherGrid.TTL_MS

    fun covers(south: Double, north: Double, west: Double, east: Double) = partial == null &&
        west >= (i0 + 1) * s && east <= (i0 + nx - 2) * s && south >= (j0 + 1) * s && north <= (j0 + ny - 2) * s
}

/**
 * Indice de fructification d'une espèce sur le treillis, pour les jours affichés
 * (J-14 … J+7) : par point, valeurs [bande d'altitude][humidité][jour].
 */
class FruitField(val sp: Species, val wx: WxField, val gw: DoubleArray) {
    val d0 = WeatherGrid.PAST + WeatherGrid.SHOW_FROM
    val nd = WeatherGrid.SHOW_TO - WeatherGrid.SHOW_FROM + 1
    private val lat: Array<FloatArray?> = Array(wx.pts.size) { k ->
        wx.pts[k]?.takeIf { it.n >= d0 + nd }?.let { Model.lattice(sp, it, d0, d0 + nd) }
    }

    /** Indice 0-1 au point (lat, lon), jour `day` (0 = J-14), altitude effective et TWI du pixel. */
    fun sample(latDeg: Double, lonDeg: Double, day: Int, elevEff: Double, twic: Int): Float {
        val gx = lonDeg / wx.s - wx.i0
        val gy = latDeg / wx.s - wx.j0
        val ix = floor(gx).toInt().coerceIn(0, wx.nx - 2)
        val iy = floor(gy).toInt().coerceIn(0, wx.ny - 2)
        val fx = (gx - ix).coerceIn(0.0, 1.0)
        val fy = (gy - iy).coerceIn(0.0, 1.0)
        var sum = 0.0
        var wsum = 0.0
        for (dy in 0..1) for (dx in 0..1) {
            val k = (iy + dy) * wx.nx + ix + dx
            val l = lat[k] ?: continue
            val w = (if (dx == 1) fx else 1 - fx) * (if (dy == 1) fy else 1 - fy)
            if (w <= 0.0) continue
            val dm = Model.moistureOffset(twic, gw[k])
            sum += w * Model.sampleLattice(l, nd, day, elevEff, dm)
            wsum += w
        }
        return if (wsum > 0) (sum / wsum).toFloat() else 0f
    }

    /** Série J-14 … J+7 en un point (pour la fiche). */
    fun series(latDeg: Double, lonDeg: Double, elevEff: Double, twic: Int) =
        FloatArray(nd) { sample(latDeg, lonDeg, it, elevEff, twic) }

    /** Moyennes météo au point le plus proche (pour la fiche). */
    fun nearestWeather(latDeg: Double, lonDeg: Double): DailyWeather? {
        val i = Math.round(lonDeg / wx.s).toInt() - wx.i0
        val j = Math.round(latDeg / wx.s).toInt() - wx.j0
        if (i !in 0 until wx.nx || j !in 0 until wx.ny) return null
        return wx.pts[j * wx.nx + i]
    }
}
