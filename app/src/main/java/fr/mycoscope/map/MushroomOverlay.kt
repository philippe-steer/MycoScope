package fr.mycoscope.map

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Point
import android.graphics.RectF
import fr.mycoscope.data.FruitField
import fr.mycoscope.data.PmTiles
import fr.mycoscope.model.Enc
import fr.mycoscope.model.Model
import fr.mycoscope.model.Species
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.PI
import kotlin.math.atan
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.sinh
import kotlin.math.tan

object TileMath {
    fun lat(y: Double, z: Int): Double = Math.toDegrees(atan(sinh(PI * (1 - 2 * y / (1 shl z)))))
    fun lon(x: Double, z: Int): Double = x / (1 shl z) * 360.0 - 180.0
    fun tx(lon: Double, z: Int): Double = (lon + 180.0) / 360.0 * (1 shl z)
    fun ty(lat: Double, z: Int): Double {
        val r = Math.toRadians(lat.coerceIn(-85.0, 85.0))
        return (1 - ln(tan(r) + 1 / kotlin.math.cos(r)) / PI) / 2 * (1 shl z)
    }
}

/** Valeurs brutes d'un pixel z12 (pour la fiche « point »). */
class PixelInfo(val color: Int, val lat: Double, val lon: Double)

/**
 * Dessine l'indice champignon d'une espèce : habitat seul, ou habitat × fructification du jour
 * choisi. Les tuiles d'environnement (PMTiles) sont décodées et colorées en tâche de fond,
 * puis gardées en mémoire.
 */
class MushroomOverlay(private val density: Float) : Overlay() {
    enum class Mode { NOW, HABITAT }

    @Volatile var data: PmTiles? = null
    @Volatile var species: Species? = null
    @Volatile var mode = Mode.NOW
    @Volatile var day = 14 // index dans FruitField (0 = J-14)
    @Volatile var fruit: FruitField? = null
    var opacity = 0.85f
    var onError: (String) -> Unit = {}
    var mapView: MapView? = null

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    @OptIn(ExperimentalCoroutinesApi::class)
    private val io = Dispatchers.IO.limitedParallelism(4)
    @OptIn(ExperimentalCoroutinesApi::class)
    private val cpu = Dispatchers.Default.limitedParallelism(2)

    // pixels décodés (ARGB non prémultipliés) par tuile, et images colorées par clé d'état
    private val raw = object : LinkedHashMap<String, IntArray>(64, 0.75f, true) {
        override fun removeEldestEntry(e: MutableMap.MutableEntry<String, IntArray>?) = size > 80
    }
    private val missing = HashSet<String>()
    private val colored = object : LinkedHashMap<String, Bitmap>(64, 0.75f, true) {
        override fun removeEldestEntry(e: MutableMap.MutableEntry<String, Bitmap>?) = size > 60
    }
    private val pending = HashSet<String>()
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG)
    private val pt = Point()

    fun stateKey(): String {
        val f = fruit
        return "${species?.id}|$mode|$day|${if (mode == Mode.NOW) System.identityHashCode(f) else 0}"
    }

    fun refresh() {
        mapView?.postInvalidate()
    }

    fun clearData() = synchronized(raw) { raw.clear(); missing.clear(); synchronized(colored) { colored.clear() } }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow) return
        mapView = mv
        val pm = data ?: return
        val sp = species ?: return
        if (mode == Mode.NOW && fruit == null) return
        val zoom = mv.zoomLevelDouble + ln(density.toDouble()) / ln(2.0) - 0.5
        val z = floor(zoom).toInt().coerceIn(Enc.MIN_ZOOM, Enc.DATA_ZOOM)
        val bb = mv.boundingBox
        val x0 = floor(TileMath.tx(bb.lonWest, z)).toInt()
        val x1 = floor(TileMath.tx(bb.lonEast, z)).toInt()
        val y0 = floor(TileMath.ty(bb.latNorth, z)).toInt()
        val y1 = floor(TileMath.ty(bb.latSouth, z)).toInt()
        if ((x1 - x0 + 1) * (y1 - y0 + 1) > 120) return
        val sk = stateKey()
        paint.alpha = (opacity * 255).toInt()
        for (y in y0..y1) for (x in x0..x1) {
            val key = "$z/$x/$y"
            val bmp = synchronized(colored) { colored["$sk|$key"] }
            if (bmp == null) {
                request(pm, sp, z, x, y, sk)
                // en attendant : tuile parente déjà calculée, recadrée
                drawParent(c, mv, sk, z, x, y)
                continue
            }
            drawTile(c, mv, bmp, null, z, x, y)
        }
    }

    private fun drawTile(c: Canvas, mv: MapView, bmp: Bitmap, src: android.graphics.Rect?, z: Int, x: Int, y: Int) {
        val proj = mv.projection
        proj.toPixels(GeoPoint(TileMath.lat(y.toDouble(), z), TileMath.lon(x.toDouble(), z)), pt)
        val l = pt.x.toFloat()
        val t = pt.y.toFloat()
        proj.toPixels(GeoPoint(TileMath.lat(y + 1.0, z), TileMath.lon(x + 1.0, z)), pt)
        c.drawBitmap(bmp, src, RectF(l, t, pt.x.toFloat(), pt.y.toFloat()), paint)
    }

    private fun drawParent(c: Canvas, mv: MapView, sk: String, z: Int, x: Int, y: Int) {
        var pz = z - 1
        var px = x shr 1
        var py = y shr 1
        while (pz >= Enc.MIN_ZOOM) {
            val b = synchronized(colored) { colored["$sk|$pz/$px/$py"] }
            if (b != null) {
                val d = z - pz
                val n = 1 shl d
                val sz = 256 / n
                val ox = (x - (px shl d)) * sz
                val oy = (y - (py shl d)) * sz
                drawTile(c, mv, b, android.graphics.Rect(ox, oy, ox + sz, oy + sz), z, x, y)
                return
            }
            pz--; px = px shr 1; py = py shr 1
        }
    }

    private fun request(pm: PmTiles, sp: Species, z: Int, x: Int, y: Int, sk: String) {
        val key = "$z/$x/$y"
        val full = "$sk|$key"
        synchronized(pending) { if (!pending.add(full)) return }
        scope.launch(io) {
            try {
                val px = pixels(pm, z, x, y)
                scope.launch(cpu) {
                    try {
                        if (sk != stateKey()) return@launch
                        val bmp = if (px == null) EMPTY else colorize(px, sp, z, x, y)
                        synchronized(colored) { colored[full] = bmp }
                        mapView?.postInvalidate()
                    } finally {
                        synchronized(pending) { pending.remove(full) }
                    }
                }
            } catch (e: Exception) {
                synchronized(pending) { pending.remove(full) }
                onError(e.message ?: e.toString())
            }
        }
    }

    /** Pixels décodés d'une tuile d'environnement (null si hors couverture). */
    fun pixels(pm: PmTiles, z: Int, x: Int, y: Int): IntArray? {
        val key = "$z/$x/$y"
        synchronized(raw) {
            raw[key]?.let { return it }
            if (key in missing) return null
        }
        val bytes = pm.tile(z, x, y)
        if (bytes == null) {
            synchronized(raw) { missing += key }
            return null
        }
        val opt = BitmapFactory.Options().apply {
            inPremultiplied = false // indispensable : le canal alpha porte l'altitude
            inPreferredConfig = Bitmap.Config.ARGB_8888
        }
        val b = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opt) ?: return null
        val px = IntArray(256 * 256)
        b.getPixels(px, 0, 256, 0, 0, 256, 256)
        b.recycle()
        synchronized(raw) { raw[key] = px }
        return px
    }

    /** Pixel z12 sous un point (pour la fiche). */
    fun pixelAt(lat: Double, lon: Double): PixelInfo? {
        val pm = data ?: return null
        val z = Enc.DATA_ZOOM
        val fx = TileMath.tx(lon, z)
        val fy = TileMath.ty(lat, z)
        val x = floor(fx).toInt()
        val y = floor(fy).toInt()
        val px = pixels(pm, z, x, y) ?: return null
        val i = ((fx - x) * 256).toInt().coerceIn(0, 255)
        val j = ((fy - y) * 256).toInt().coerceIn(0, 255)
        return PixelInfo(px[j * 256 + i], lat, lon)
    }

    private fun colorize(px: IntArray, sp: Species, z: Int, x: Int, y: Int): Bitmap {
        val out = IntArray(256 * 256)
        val f = fruit
        val now = mode == Mode.NOW && f != null
        val d = day
        val lats = DoubleArray(256) { TileMath.lat(y + (it + 0.5) / 256.0, z) }
        val lons = DoubleArray(256) { TileMath.lon(x + (it + 0.5) / 256.0, z) }
        for (j in 0 until 256) for (i in 0 until 256) {
            val c = px[j * 256 + i]
            if (!Enc.valid(c)) continue
            val h = sp.habitatPixel(c)
            if (h < 0.02) continue
            var v = h
            if (now) {
                val ee = Model.effectiveElev(Enc.elev(c), Enc.aspc(c))
                v *= f!!.sample(lats[j], lons[i], d, ee, Enc.twic(c))
            }
            out[j * 256 + i] = Ramp.color(v.toFloat())
        }
        return Bitmap.createBitmap(out, 256, 256, Bitmap.Config.ARGB_8888)
    }

    companion object {
        private val EMPTY: Bitmap = Bitmap.createBitmap(1, 1, Bitmap.Config.ARGB_8888)
    }
}

/** Rampe de couleurs (transparent → jaune pâle → orange → rouge brun), alpha croissant. */
object Ramp {
    private val stops = floatArrayOf(0.05f, 0.2f, 0.4f, 0.6f, 0.85f)
    private val cols = intArrayOf(0xFFF6E8A6.toInt(), 0xFFF2C14E.toInt(), 0xFFE8873A.toInt(), 0xFFC4452F.toInt(), 0xFF6E1E2B.toInt())
    private val lut = IntArray(256) { compute(it / 255f) }

    private fun compute(v: Float): Int {
        if (v < stops[0]) return 0
        var k = 0
        while (k < stops.size - 2 && v > stops[k + 1]) k++
        val t = ((v - stops[k]) / (stops[k + 1] - stops[k])).coerceIn(0f, 1f)
        fun ch(c: Int, s: Int) = (c shr s) and 0xFF
        fun mix(s: Int) = (ch(cols[k], s) * (1 - t) + ch(cols[k + 1], s) * t).toInt()
        val a = (110 + 140 * ((v - stops[0]) / (1 - stops[0])).coerceIn(0f, 1f)).toInt()
        return (a shl 24) or (mix(16) shl 16) or (mix(8) shl 8) or mix(0)
    }

    fun color(v: Float): Int = lut[(v.coerceIn(0f, 1f) * 255).toInt()]
    fun stops() = listOf(0.1f, 0.3f, 0.5f, 0.7f, 0.9f).map { it to color(it) }
}
