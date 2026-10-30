package fr.mycoscope.map

import android.content.Context
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay

/**
 * Fond OpenTopoMap (courbes de niveau, chemins : utile en forêt) ou OpenStreetMap.
 * User-Agent identifié (MainActivity), en-têtes de cache respectés, attribution visible.
 */
fun createMap(ctx: Context, topo: Boolean, center: GeoPoint, zoom: Double): MapView = MapView(ctx).apply {
    setTileSource(if (topo) TileSourceFactory.OpenTopo else TileSourceFactory.MAPNIK)
    setMultiTouchControls(true)
    zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
    setTilesScaledToDpi(true)
    setMinZoomLevel(5.0)
    setMaxZoomLevel(17.0)
    setHorizontalMapRepetitionEnabled(false)
    setVerticalMapRepetitionEnabled(false)
    overlays.add(CopyrightOverlay(ctx))
    controller.setZoom(zoom)
    controller.setCenter(center)
}

fun MapView.setTopo(topo: Boolean) {
    setTileSource(if (topo) TileSourceFactory.OpenTopo else TileSourceFactory.MAPNIK)
}
