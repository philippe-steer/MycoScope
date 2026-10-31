package fr.mycoscope.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import org.json.JSONObject
import org.osmdroid.tileprovider.MapTileProviderBasic
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.util.MapTileIndex
import org.osmdroid.views.overlay.TilesOverlay
import java.util.Locale

/**
 * Forêts publiques gérées par l'ONF (domaniales et non domaniales : communales, sectionales,
 * départementales, établissements publics), servies par la Géoplateforme IGN.
 * Une forêt hors de cette couche est, dans l'immense majorité des cas, privée.
 */
object Forests {
    private const val WMTS = "https://data.geopf.fr/wmts"
    private const val LAYER = "FORETS.PUBLIQUES"
    const val LEGEND_URL = "https://data.geopf.fr/annexes/ressources/legendes/onf_forets_publiques.png"

    private val source = object : OnlineTileSourceBase(
        "ONF_FORETS_PUBLIQUES", 3, 16, 256, ".png", arrayOf(WMTS),
        "Forêts publiques © ONF / IGN Géoplateforme",
    ) {
        override fun getTileURLString(index: Long): String {
            val z = MapTileIndex.getZoom(index)
            val x = MapTileIndex.getX(index)
            val y = MapTileIndex.getY(index)
            return "$WMTS?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=$LAYER" +
                "&STYLE=FORETS%20PUBLIQUES%20ONF&TILEMATRIXSET=PM_3_16&TILEMATRIX=$z&TILEROW=$y&TILECOL=$x&FORMAT=image/png"
        }
    }

    fun overlay(ctx: Context): TilesOverlay {
        val provider = MapTileProviderBasic(ctx.applicationContext, source)
        return TilesOverlay(provider, ctx.applicationContext).apply {
            loadingBackgroundColor = android.graphics.Color.TRANSPARENT
            loadingLineColor = android.graphics.Color.TRANSPARENT
        }
    }

    class Info(val name: String?, val domaniale: Boolean?) {
        val isPublic get() = name != null || domaniale != null
        fun label(): String = when {
            !isPublic -> "Hors forêt publique : forêt vraisemblablement privée (accord du propriétaire nécessaire)"
            domaniale == true -> "${name ?: "Forêt domaniale"} — domaniale (État, gérée par l'ONF)"
            else -> "${name ?: "Forêt publique"} — publique non domaniale (commune, département ou établissement public)"
        }
    }

    /** Forêt publique au point (GetFeatureInfo du WMS vecteur), null si le service ne répond pas. */
    suspend fun infoAt(lat: Double, lon: Double): Info? = runCatching {
        val d = 0.002
        val bbox = String.format(Locale.US, "%.5f,%.5f,%.5f,%.5f", lat - d, lon - d, lat + d, lon + d)
        val url = "https://data.geopf.fr/wms-v/ows?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo" +
            "&LAYERS=$LAYER&QUERY_LAYERS=$LAYER&CRS=EPSG:4326&BBOX=$bbox&WIDTH=21&HEIGHT=21&I=10&J=10" +
            "&INFO_FORMAT=application/json&FEATURE_COUNT=1"
        val feats = JSONObject(Http.getText(url)).optJSONArray("features")
        if (feats == null || feats.length() == 0) return@runCatching Info(null, null)
        val p = feats.getJSONObject(0).optJSONObject("properties") ?: JSONObject()
        val name = p.optString("llib2_frt").ifBlank { p.optString("llib_frt") }.ifBlank { null }
        val dom = when (p.optString("cdom_frt").uppercase(Locale.ROOT)) {
            "OUI" -> true
            "NON" -> false
            else -> name?.contains("domaniale", ignoreCase = true)
        }
        Info(name ?: "Forêt publique", dom)
    }.getOrNull()

    @Volatile private var legend: Bitmap? = null

    suspend fun legend(): Bitmap? {
        legend?.let { return it }
        return runCatching {
            val b = Http.getBytes(LEGEND_URL)
            BitmapFactory.decodeByteArray(b, 0, b.size)
        }.getOrNull()?.also { legend = it }
    }
}
