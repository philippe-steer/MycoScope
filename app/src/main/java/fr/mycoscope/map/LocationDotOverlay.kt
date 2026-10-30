package fr.mycoscope.map

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.max

/** "You are here": blue dot with white ring and an accuracy halo. */
class LocationDotOverlay(private val density: Float) : Overlay() {
    @Volatile var point: GeoPoint? = null
    @Volatile var accuracyM: Float = 0f

    private val halo = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x332F80ED }
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF1A73E8.toInt() }
    private val shadowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x40000000 }

    override fun draw(c: Canvas, osmv: MapView, shadow: Boolean) {
        if (shadow) return
        val p = point ?: return
        val pt = osmv.projection.toPixels(p, null)
        val x = pt.x.toFloat()
        val y = pt.y.toFloat()
        if (accuracyM > 0f) {
            val r = osmv.projection.metersToPixels(accuracyM)
            if (r > 12f * density) c.drawCircle(x, y, r, halo)
        }
        c.drawCircle(x, y + 1.5f * density, 9.5f * density, shadowPaint)
        c.drawCircle(x, y, 9f * density, ring)
        c.drawCircle(x, y, max(6f * density, 1f), dot)
    }
}
