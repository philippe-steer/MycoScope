package fr.mycoscope.ui

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.sp
import fr.mycoscope.data.Locator
import fr.mycoscope.map.LocationDotOverlay
import kotlinx.coroutines.launch
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import kotlin.math.max

/**
 * Shows the phone's position on [mapView] and zooms to it when the screen opens
 * (asking for permission if needed). Returns an action that re-centres on the position.
 */
@Composable
fun rememberMyLocation(mapView: MapView, dot: LocationDotOverlay, zoom: Double): () -> Unit {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()

    fun locate(center: Boolean) {
        scope.launch {
            val loc = Locator.current(ctx) ?: return@launch
            val p = GeoPoint(loc.latitude, loc.longitude)
            dot.point = p
            dot.accuracyM = loc.accuracy
            if (center) mapView.controller.animateTo(p, max(mapView.zoomLevelDouble, zoom), 700L)
            mapView.invalidate()
        }
    }

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
        if (res.values.any { it }) locate(true)
    }
    val perms = arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION)

    LaunchedEffect(Unit) {
        if (Locator.hasPermission(ctx)) locate(true) else launcher.launch(perms)
    }
    return { if (Locator.hasPermission(ctx)) locate(true) else launcher.launch(perms) }
}

@Composable
fun MyLocationButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    SmallFloatingActionButton(onClick = onClick, modifier = modifier) {
        Text("◎", fontSize = 22.sp)
    }
}
