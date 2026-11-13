package fr.mycoscope.data

import android.content.Context

/** Réglages persistants (SharedPreferences). */
class Store(ctx: Context) {
    private val sp = ctx.getSharedPreferences("mycoscope", Context.MODE_PRIVATE)

    var species: String
        get() = sp.getString("species", "cepe_bordeaux") ?: "cepe_bordeaux"
        set(v) { sp.edit().putString("species", v).apply() }

    var topo: Boolean
        get() = sp.getBoolean("topo", true)
        set(v) { sp.edit().putBoolean("topo", v).apply() }

    var forests: Boolean
        get() = sp.getBoolean("forests", false)
        set(v) { sp.edit().putBoolean("forests", v).apply() }

    var habitatMode: Boolean
        get() = sp.getBoolean("habitat", false)
        set(v) { sp.edit().putBoolean("habitat", v).apply() }

    var acceptedNotice: Boolean
        get() = sp.getBoolean("notice1", false)
        set(v) { sp.edit().putBoolean("notice1", v).apply() }

    /** Source des couches : URL https ou chemin de fichier local ; vide = valeur par défaut. */
    var dataUrl: String
        get() = sp.getString("dataUrl", "") ?: ""
        set(v) { sp.edit().putString("dataUrl", v).apply() }

    var lastLat: Double
        get() = sp.getFloat("lat", 46.6f).toDouble()
        set(v) { sp.edit().putFloat("lat", v.toFloat()).apply() }
    var lastLon: Double
        get() = sp.getFloat("lon", 2.4f).toDouble()
        set(v) { sp.edit().putFloat("lon", v.toFloat()).apply() }
    var lastZoom: Double
        get() = sp.getFloat("zoom", 6f).toDouble()
        set(v) { sp.edit().putFloat("zoom", v.toFloat()).apply() }

    /** Dernière zone affichée (sud, nord, ouest, est) : la mise à jour en arrière-plan la reprend. */
    fun saveBox(s: Double, n: Double, w: Double, e: Double) {
        sp.edit().putString("box", "$s,$n,$w,$e").apply()
    }
    val box: DoubleArray?
        get() = sp.getString("box", null)?.split(",")?.mapNotNull { it.toDoubleOrNull() }?.takeIf { it.size == 4 }?.toDoubleArray()

    var autoUpdate: Boolean
        get() = sp.getBoolean("autoUpdate", true)
        set(v) { sp.edit().putBoolean("autoUpdate", v).apply() }
}
