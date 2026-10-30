package fr.mycoscope.model

import org.json.JSONObject
import kotlin.math.ceil
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Port exact de pipeline/mycoscope_pipeline/model.py (vérifié par ModelParityTest).
 * Toute modification doit être faite des deux côtés.
 */
object Enc {
    const val FORMAT_VERSION = 1
    const val DATA_ZOOM = 12
    const val MIN_ZOOM = 5
    const val ELEV_STEP = 20.0
    const val TWI_MIN = 2.0

    val FOREST = linkedMapOf(
        "nodata" to 0, "open" to 1, "lande" to 2, "herbace" to 3, "peupleraie" to 4,
        "chene" to 10, "chene_vert" to 11, "hetre" to 12, "chataignier" to 13, "robinier" to 14,
        "feuillus_autres" to 15, "feuillus_melange" to 16,
        "pin_maritime" to 20, "pin_sylvestre" to 21, "pin_noir" to 22, "pin_alep" to 23, "pin_montagne" to 24,
        "pins_autres" to 25, "sapin_epicea" to 26, "meleze" to 27, "douglas" to 28, "coniferes_autres" to 29,
        "mixte_feuillus" to 30, "mixte_coniferes" to 31,
        "ouverte_feuillus" to 40, "ouverte_coniferes" to 41, "ouverte_mixte" to 42, "coupe" to 43,
    )
    val BROADLEAF = intArrayOf(10, 11, 12, 13, 14, 15, 16)
    val CONIFER = intArrayOf(20, 21, 22, 23, 24, 25, 26, 27, 28, 29)

    val LITHO = linkedMapOf(
        "nodata" to 0, "calcaire" to 1, "marne" to 2, "argile_limon" to 3, "sable_gres" to 4, "granite" to 5,
        "gneiss_micaschiste" to 6, "schiste_pelite" to 7, "volcanique_basique" to 8, "volcanique_acide" to 9,
        "alluvions" to 10, "tourbe" to 11, "ultrabasique" to 12, "conglomerat_molasse" to 13, "evaporite" to 14,
        "moraine" to 15, "autre" to 16,
    )
    val PH_CENTERS = doubleArrayOf(0.0, 4.2, 4.75, 5.25, 5.75, 6.25, 6.85, 7.7)

    val FOREST_LABEL = mapOf(
        0 to "—", 1 to "Hors forêt", 2 to "Lande", 3 to "Pelouse / prairie naturelle", 4 to "Peupleraie",
        10 to "Chênes décidus", 11 to "Chênes verts / liège", 12 to "Hêtre", 13 to "Châtaignier",
        14 to "Robinier", 15 to "Autres feuillus", 16 to "Mélange de feuillus",
        20 to "Pin maritime", 21 to "Pin sylvestre", 22 to "Pin laricio / noir", 23 to "Pin d'Alep",
        24 to "Pin à crochets / cembro", 25 to "Autres pins", 26 to "Sapin / épicéa", 27 to "Mélèze",
        28 to "Douglas", 29 to "Autres conifères", 30 to "Mixte (feuillus dominants)",
        31 to "Mixte (conifères dominants)", 40 to "Forêt ouverte de feuillus", 41 to "Forêt ouverte de conifères",
        42 to "Forêt ouverte mixte", 43 to "Coupe / sans couvert",
    )
    val LITHO_LABEL = mapOf(
        0 to "Inconnue", 1 to "Calcaire, craie, dolomie", 2 to "Marnes, marno-calcaires", 3 to "Argiles, limons, lœss",
        4 to "Sables, grès", 5 to "Granites", 6 to "Gneiss, micaschistes", 7 to "Schistes, pélites",
        8 to "Volcanique basique (basalte…)", 9 to "Volcanique acide (rhyolite…)", 10 to "Alluvions, colluvions",
        11 to "Tourbe", 12 to "Roches ultrabasiques", 13 to "Conglomérats, molasses", 14 to "Gypse, évaporites",
        15 to "Moraines", 16 to "Autre",
    )
    val PH_LABEL = arrayOf("inconnu", "< 4,5", "4,5–5", "5–5,5", "5,5–6", "6–6,5", "6,5–7,2", "> 7,2")
    val ASPECT_LABEL = arrayOf("plat", "N", "NE", "E", "SE", "S", "SO", "O", "NO")

    /** Décodage d'un pixel ARGB (non prémultiplié). */
    fun forest(c: Int) = (c shr 16) and 0xFF
    fun litho(c: Int) = ((c shr 8) and 0xFF) shr 3
    fun phc(c: Int) = (c shr 8) and 0x07
    fun twic(c: Int) = (c and 0xFF) shr 4
    fun aspc(c: Int) = c and 0x0F
    fun elevCode(c: Int) = (c ushr 24) and 0xFF
    fun elev(c: Int): Double { val a = elevCode(c); return if (a > 0) (a - 1) * ELEV_STEP else Double.NaN }
    fun valid(c: Int) = forest(c) != 0 && elevCode(c) != 0
}

fun trap(x: Double, a: Double, b: Double, c: Double, d: Double): Double {
    val up = if (b > a) (x - a) / max(b - a, 1e-9) else if (x >= a) 1.0 else 0.0
    val down = if (d > c) (d - x) / max(d - c, 1e-9) else if (x <= d) 1.0 else 0.0
    return min(min(up, down), 1.0).coerceIn(0.0, 1.0)
}

private fun DoubleArray.t(x: Double) = trap(x, this[0], this[1], this[2], this[3])

class Species(o: JSONObject) {
    val id: String = o.getString("id")
    val nameFr: String = o.getJSONObject("name").getString("fr")
    val latin: String = o.optString("latin")
    val color: Int = (0xFF000000L or o.optString("color", "#8B5A2B").removePrefix("#").toLong(16)).toInt()
    val experimental: Boolean = o.optBoolean("experimental", false)
    val lookalikes: String = o.optJSONObject("lookalikes")?.optString("fr") ?: ""

    val hostT = DoubleArray(256)
    val lithoT = DoubleArray(32)
    val phT = DoubleArray(8)
    val elevR: DoubleArray

    val season: DoubleArray
    val tsoil: DoubleArray
    val lag: Double
    val lagSd: Double
    val rainRef: Double
    val moisture: DoubleArray
    val frostC: Double
    val coldShock: Double
    val persistence: Double

    init {
        val hab = o.getJSONObject("habitat")
        val hosts = hab.getJSONObject("hosts")
        for ((name, code) in Enc.FOREST) if (hosts.has(name)) hostT[code] = hosts.getDouble(name)
        val mb = Enc.BROADLEAF.maxOf { hostT[it] }.coerceAtLeast(0.0)
        val mc = Enc.CONIFER.maxOf { hostT[it] }.coerceAtLeast(0.0)
        val fallback = mapOf(
            "feuillus_melange" to 0.9 * mb,
            "mixte_feuillus" to max(0.9 * mb, 0.7 * mc),
            "mixte_coniferes" to max(0.7 * mb, 0.9 * mc),
            "ouverte_feuillus" to 0.6 * mb,
            "ouverte_coniferes" to 0.6 * mc,
            "ouverte_mixte" to 0.6 * max(mb, mc),
            "coupe" to 0.1 * max(mb, mc),
        )
        for ((name, v) in fallback) if (!hosts.has(name)) hostT[Enc.FOREST.getValue(name)] = v
        hostT[0] = 0.0

        lithoT.fill(hab.optDouble("litho_default", 0.7))
        val li = hab.getJSONObject("litho")
        for ((name, code) in Enc.LITHO) if (li.has(name)) lithoT[code] = li.getDouble(name)

        val fl = hab.optDouble("ph_floor", 0.4)
        val ph = arr(hab, "ph")
        for (c in 0 until 8) phT[c] = fl + (1 - fl) * ph.t(Enc.PH_CENTERS[c])
        phT[0] = (1 + fl) / 2
        elevR = arr(hab, "elev")

        val f = o.getJSONObject("fruiting")
        season = arr(f, "season")
        tsoil = arr(f, "tsoil")
        lag = f.getDouble("lag_days")
        lagSd = f.getDouble("lag_sd")
        rainRef = f.getDouble("rain_ref_mm")
        moisture = arr(f, "moisture")
        frostC = f.getDouble("frost_c")
        coldShock = f.getDouble("cold_shock")
        persistence = f.getDouble("persistence_days")
    }

    private fun arr(o: JSONObject, k: String): DoubleArray {
        val a = o.getJSONArray(k)
        return DoubleArray(a.length()) { a.getDouble(it) }
    }

    /** Habitat 0-1 d'un pixel décodé. */
    fun habitat(forest: Int, litho: Int, phc: Int, elev: Double): Double {
        val e = if (elev.isNaN()) -9999.0 else elev
        return hostT[forest] * lithoT[litho and 31] * phT[phc and 7] * elevR.t(e)
    }

    fun habitatPixel(c: Int): Double =
        if (!Enc.valid(c)) 0.0 else habitat(Enc.forest(c), Enc.litho(c), Enc.phc(c), Enc.elev(c))

    companion object {
        fun parseAll(json: String): List<Species> {
            val a = JSONObject(json).getJSONArray("species")
            return List(a.length()) { Species(a.getJSONObject(it)) }
        }
    }
}

/** Séries journalières en un point de grille. */
class DailyWeather(
    val doy: IntArray,
    val precip: DoubleArray,
    val tmean: DoubleArray,
    val tmin: DoubleArray,
    val et0: DoubleArray,
    val elevation: Double,
) {
    val n get() = precip.size
}

object Model {
    const val LAPSE = -0.0065
    const val SOIL_TAU = 4.0
    const val BUCKET_MM = 120.0
    const val BUCKET_START = 0.5
    const val SEASON_RAMP = 20.0
    const val FROST_RECOVERY = 5.0
    const val TWI_REF = 7.0
    const val TWI_GAIN = 0.03
    const val DM_MAX = 0.25
    const val GW_GAIN = 0.15
    val ELEV_BANDS = DoubleArray(31) { it * 100.0 }
    val DM_LEVELS = doubleArrayOf(-0.25, -0.125, 0.0, 0.125, 0.25)
    val ASPECT_DZ = doubleArrayOf(0.0, 120.0, 80.0, 0.0, -80.0, -120.0, -80.0, 0.0, 80.0)

    fun moistureOffset(twic: Int, gw: Double): Double {
        val twi = if (twic > 0) Enc.TWI_MIN + twic - 0.5 else TWI_REF
        val dm = TWI_GAIN * (twi - TWI_REF)
        val w = ((twi - 8.0) / 5.0).coerceIn(0.0, 1.0)
        return (dm + GW_GAIN * gw * w).coerceIn(-DM_MAX, DM_MAX)
    }

    fun effectiveElev(elev: Double, aspc: Int) = elev + ASPECT_DZ[aspc.coerceIn(0, 8)]

    fun bucket(w: DailyWeather): DoubleArray {
        val m = DoubleArray(w.n)
        var s = BUCKET_START * BUCKET_MM
        for (i in 0 until w.n) {
            val p = if (w.precip[i].isFinite()) w.precip[i] else 0.0
            val e = if (w.et0[i].isFinite()) w.et0[i] else 0.0
            val stress = min(1.0, s / (0.5 * BUCKET_MM))
            s = min(BUCKET_MM, max(0.0, s + p - e * stress))
            m[i] = s / BUCKET_MM
        }
        return m
    }

    fun rainTrigger(precip: DoubleArray, lag: Double, sd: Double): DoubleArray {
        val n = precip.size
        val tmax = ceil(lag + 3 * sd).toInt()
        val k = DoubleArray(tmax + 1) { exp(-0.5 * ((it - lag) / sd).let { x -> x * x }) }
        val out = DoubleArray(n)
        for (i in 0 until n) {
            var s = 0.0
            for (tau in 0..min(tmax, i)) {
                val p = precip[i - tau]
                s += (if (p.isFinite()) p else 0.0) * k[tau]
            }
            out[i] = s
        }
        return out
    }

    /** Arrondi « bancaire » comme Python round(). */
    private fun pyRound(x: Double): Int {
        val r = Math.rint(x)
        return r.toInt()
    }

    fun coldShock(tmean: DoubleArray, lag: Double, sd: Double): DoubleArray {
        val n = tmean.size
        val t = DoubleArray(n) { if (tmean[it].isFinite()) tmean[it] else 0.0 }
        val drop = DoubleArray(n) { -99.0 }
        for (j in 3 until n - 2) {
            drop[j] = (t[j - 3] + t[j - 2] + t[j - 1]) / 3.0 - (t[j] + t[j + 1] + t[j + 2]) / 3.0
        }
        val lo = pyRound(max(0.0, lag - sd))
        val hi = pyRound(lag + sd)
        val out = DoubleArray(n)
        for (i in 0 until n) {
            var best = 0.0
            for (tau in lo..hi) if (i - tau >= 0) best = max(best, drop[i - tau])
            out[i] = best
        }
        return out
    }

    fun season(doy: Int, start: Double, end: Double): Double {
        var d = doy.toDouble()
        var e = end
        if (end < start) {
            if (d < start - SEASON_RAMP) d += 365
            e = end + 365
        }
        return trap(d, start - SEASON_RAMP, start, e, e + SEASON_RAMP)
    }

    fun soilTemp(tair: DoubleArray): DoubleArray {
        val a = 1 - exp(-1 / SOIL_TAU)
        val finite = tair.filter { it.isFinite() }
        val mean = if (finite.isEmpty()) 0.0 else finite.average()
        val t = DoubleArray(tair.size) { if (tair[it].isFinite()) tair[it] else mean }
        var s = t.take(7).average()
        return DoubleArray(t.size) { i -> s += a * (t[i] - s); s }
    }

    class Prep(val trig: DoubleArray, val shock: DoubleArray, val moist: DoubleArray)

    fun prepare(sp: Species, w: DailyWeather) =
        Prep(rainTrigger(w.precip, sp.lag, sp.lagSd), coldShock(w.tmean, sp.lag, sp.lagSd), bucket(w))

    fun fruiting(sp: Species, w: DailyWeather, elev: Double, dm: Double, prep: Prep = prepare(sp, w)): DoubleArray {
        val n = w.n
        val dt = LAPSE * (elev - w.elevation)
        val tair = DoubleArray(n) { w.tmean[it] + dt }
        val ts = soilTemp(tair)
        val win = pyRound(sp.lag)
        val decay = exp(-1 / sp.persistence)
        val out = DoubleArray(n)
        var prev = 0.0
        var lastFrost = Int.MIN_VALUE
        // moyenne glissante de l'humidité sur la fenêtre [i - L, i]
        val cum = DoubleArray(n + 1)
        for (i in 0 until n) cum[i + 1] = cum[i] + prep.moist[i]
        for (i in 0 until n) {
            val tmin = w.tmin[i] + dt
            if (tmin.isFinite() && tmin < sp.frostC) {
                lastFrost = i
                prev = 0.0
            }
            val phi = if (lastFrost != Int.MIN_VALUE) 1 - exp(-(i - lastFrost) / FROST_RECOVERY) else 1.0
            val i0 = max(0, i - win)
            val mbar = (cum[i + 1] - cum[i0]) / (i + 1 - i0)
            val theta = sp.tsoil.t(ts[i])
            val rho = 1 - exp(-prep.trig[i] / sp.rainRef)
            val mu = sp.moisture.t((mbar + dm).coerceIn(0.0, 1.0))
            val bonus = 1 + sp.coldShock * ((prep.shock[i] - 2.0) / 4.0).coerceIn(0.0, 1.0)
            val s = season(w.doy[i], sp.season[0], sp.season[1])
            val raw = min(1.0, s * theta * rho * mu * bonus) * phi
            prev = max(raw, prev * decay)
            out[i] = prev
        }
        return out
    }

    /**
     * Valeurs [bande d'altitude][niveau d'humidité] pour les jours [d0, d1) — float pour la mémoire.
     * Résultat indexé [band * nDm * nDays + dm * nDays + (day - d0)].
     */
    fun lattice(sp: Species, w: DailyWeather, d0: Int, d1: Int): FloatArray {
        val prep = prepare(sp, w)
        val nd = d1 - d0
        val nm = DM_LEVELS.size
        val out = FloatArray(ELEV_BANDS.size * nm * nd)
        for (b in ELEV_BANDS.indices) for (m in 0 until nm) {
            val f = fruiting(sp, w, ELEV_BANDS[b], DM_LEVELS[m], prep)
            for (d in 0 until nd) out[b * nm * nd + m * nd + d] = f[d0 + d].toFloat()
        }
        return out
    }

    /** Interpolation dans un treillis [bande][humidité] pour un jour donné (offset `off`). */
    fun sampleLattice(lat: FloatArray, nd: Int, day: Int, elev: Double, dm: Double): Float {
        val nm = DM_LEVELS.size
        val fb = (elev / 100.0).coerceIn(0.0, (ELEV_BANDS.size - 1).toDouble())
        val b0 = fb.toInt().coerceAtMost(ELEV_BANDS.size - 2)
        val tb = (fb - b0).toFloat()
        val fm = ((dm - DM_LEVELS[0]) / (DM_LEVELS[1] - DM_LEVELS[0])).coerceIn(0.0, (nm - 1).toDouble())
        val m0 = fm.toInt().coerceAtMost(nm - 2)
        val tm = (fm - m0).toFloat()
        fun v(b: Int, m: Int) = lat[b * nm * nd + m * nd + day]
        val a = v(b0, m0) * (1 - tm) + v(b0, m0 + 1) * tm
        val c = v(b0 + 1, m0) * (1 - tm) + v(b0 + 1, m0 + 1) * tm
        return a * (1 - tb) + c * tb
    }

    fun roundTo(x: Double, step: Double) = (x / step).roundToInt() * step
}
