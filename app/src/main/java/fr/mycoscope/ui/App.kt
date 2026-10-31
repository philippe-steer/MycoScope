package fr.mycoscope.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import fr.mycoscope.BuildConfig
import fr.mycoscope.data.FruitField
import fr.mycoscope.data.PmTiles
import fr.mycoscope.data.Piezo
import fr.mycoscope.data.Store
import fr.mycoscope.data.WeatherGrid
import fr.mycoscope.data.WxField
import fr.mycoscope.map.LocationDotOverlay
import fr.mycoscope.map.MushroomOverlay
import fr.mycoscope.map.PixelInfo
import fr.mycoscope.map.Ramp
import fr.mycoscope.map.createMap
import fr.mycoscope.map.setTopo
import fr.mycoscope.model.Enc
import fr.mycoscope.model.Model
import fr.mycoscope.model.Species
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.overlay.MapEventsOverlay
import java.io.File
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val FR = Locale.FRANCE
private fun dayLabel(offset: Int): String {
    val d = LocalDate.now().plusDays(offset.toLong())
    val s = DateTimeFormatter.ofPattern("EEE d MMM", FR).format(d)
    return when (offset) {
        0 -> "Aujourd'hui ($s)"
        else -> "$s (J${if (offset > 0) "+" else ""}$offset)"
    }
}

@Composable
fun MycoApp() {
    val ctx = LocalContext.current
    val store = remember { Store(ctx.applicationContext) }
    val species = remember {
        val txt = ctx.assets.open("species.json").bufferedReader().readText()
        Model.loadGains(txt)
        Species.parseAll(txt)
    }
    var spId by remember { mutableStateOf(store.species) }
    val sp = species.firstOrNull { it.id == spId } ?: species.first()
    var habitatMode by remember { mutableStateOf(store.habitatMode) }
    var dayOffset by remember { mutableIntStateOf(0) }
    var topo by remember { mutableStateOf(store.topo) }
    var dataUrl by remember { mutableStateOf(store.dataUrl.ifBlank { BuildConfig.DATA_URL }) }
    var status by remember { mutableStateOf("") }
    var dataError by remember { mutableStateOf<String?>(null) }
    var probe by remember { mutableStateOf<GeoPoint?>(null) }
    var info by remember { mutableStateOf<PointInfo?>(null) }
    var showSettings by remember { mutableStateOf(false) }
    var showNotice by remember { mutableStateOf(!store.acceptedNotice) }
    var showSpecies by remember { mutableStateOf(false) }
    var viewTick by remember { mutableIntStateOf(0) }
    var fruitTick by remember { mutableIntStateOf(0) }
    var wx by remember { mutableStateOf<WxField?>(null) }

    val density = LocalDensity.current.density
    val mapView = remember { createMap(ctx, topo, GeoPoint(store.lastLat, store.lastLon), store.lastZoom) }
    val overlay = remember { MushroomOverlay(density) }
    val dot = remember { LocationDotOverlay(density) }
    val locate = rememberMyLocation(mapView, dot, 13.0)

    DisposableEffect(Unit) {
        val events = MapEventsOverlay(object : MapEventsReceiver {
            override fun singleTapConfirmedHelper(p: GeoPoint?): Boolean { probe = p; return true }
            override fun longPressHelper(p: GeoPoint?): Boolean = false
        })
        mapView.overlays.add(0, events)
        mapView.overlays.add(overlay)
        mapView.overlays.add(dot)
        overlay.mapView = mapView
        overlay.onError = { msg -> mapView.post { status = "Couches : $msg" } }
        mapView.addMapListener(object : MapListener {
            override fun onScroll(event: ScrollEvent?): Boolean { viewTick++; return false }
            override fun onZoom(event: ZoomEvent?): Boolean { viewTick++; return false }
        })
        mapView.onResume()
        onDispose {
            val c = mapView.mapCenter
            store.lastLat = c.latitude
            store.lastLon = c.longitude
            store.lastZoom = mapView.zoomLevelDouble
            mapView.onPause()
            mapView.onDetach()
        }
    }

    // Source des couches environnementales
    LaunchedEffect(dataUrl) {
        dataError = null
        val dir = File(ctx.filesDir, "env/" + Integer.toHexString(dataUrl.hashCode()))
        val pm = PmTiles(dataUrl, dir, fr.mycoscope.data.Http.UA)
        val err = withContext(Dispatchers.IO) { runCatching { pm.header() }.exceptionOrNull() }
        if (err != null) {
            dataError = "Couches d'habitat indisponibles (${err.message}).\n" +
                "Elles sont produites par le pipeline du dépôt (release « data-v1 »). " +
                "Vous pouvez indiquer une autre source dans ⚙."
            overlay.data = null
        } else {
            overlay.clearData()
            overlay.data = pm
        }
        overlay.refresh()
    }

    LaunchedEffect(spId, habitatMode, dayOffset) {
        store.species = spId
        store.habitatMode = habitatMode
        overlay.species = sp
        overlay.mode = if (habitatMode) MushroomOverlay.Mode.HABITAT else MushroomOverlay.Mode.NOW
        overlay.day = dayOffset - WeatherGrid.SHOW_FROM
        overlay.refresh()
    }

    // Météo du treillis pour la zone visible (après une pause dans les déplacements)
    LaunchedEffect(viewTick, habitatMode) {
        if (habitatMode) return@LaunchedEffect
        delay(500)
        val bb = mapView.boundingBox
        val s = WeatherGrid.spacingFor(bb.latNorth - bb.latSouth, bb.lonEast - bb.lonWest)
        val cur = wx
        if (cur != null && cur.s == s && cur.covers(bb.latSouth, bb.latNorth, bb.lonWest, bb.lonEast)) return@LaunchedEffect
        status = "Météo des 60 derniers jours…"
        try {
            val f = WeatherGrid.field(bb.latSouth, bb.latNorth, bb.lonWest, bb.lonEast, s)
            runCatching { Piezo.refresh(bb.latSouth, bb.latNorth, bb.lonWest, bb.lonEast) }
            wx = f
            if (f.partial != null) {
                status = "Météo partielle (${f.partial}) : suite dans ${f.retryIn} s"
                delay(f.retryIn * 1000 + 500)
                viewTick++ // relance : les points déjà reçus sont en cache
            } else status = ""
        } catch (e: Exception) {
            status = "Météo indisponible : ${e.message ?: e.javaClass.simpleName}"
            if ((e.message ?: "").contains("nouvel essai")) {
                delay(65_000)
                viewTick++
            }
        }
    }

    LaunchedEffect(wx, spId) {
        val w = wx ?: return@LaunchedEffect
        val ff = withContext(Dispatchers.Default) { FruitField(sp, w, Piezo.field(w)) }
        overlay.fruit = ff
        fruitTick++
        overlay.refresh()
    }

    LaunchedEffect(topo) {
        store.topo = topo
        mapView.setTopo(topo)
    }

    // Fiche d'un point touché
    LaunchedEffect(probe, spId, fruitTick) {
        val p = probe ?: run { info = null; return@LaunchedEffect }
        val px = withContext(Dispatchers.IO) { runCatching { overlay.pixelAt(p.latitude, p.longitude) }.getOrNull() }
        info = PointInfo(p, px, overlay.fruit?.takeIf { it.sp.id == sp.id })
    }

    Box(Modifier.fillMaxSize()) {
        AndroidView(factory = { mapView }, modifier = Modifier.fillMaxSize())

        // ---- haut : espèce + mode
        Column(Modifier.statusBarsPadding().padding(8.dp).fillMaxWidth()) {
            Surface(shape = RoundedCornerShape(14.dp), tonalElevation = 3.dp, shadowElevation = 3.dp) {
                Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(14.dp).background(Color(sp.color), RoundedCornerShape(7.dp)))
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text(sp.nameFr + if (sp.experimental) " (expérimental)" else "",
                            fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                        Text(sp.latin, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    TextButton(onClick = { showSpecies = true }) { Text("Changer") }
                    TextButton(onClick = { showSettings = true }) { Text("⚙", fontSize = 18.sp) }
                }
            }
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(selected = !habitatMode, onClick = { habitatMode = false }, label = { Text("Conditions du jour") })
                FilterChip(selected = habitatMode, onClick = { habitatMode = true }, label = { Text("Habitat seul") })
            }
        }

        // ---- bas : date, légende, état
        Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                SmallFloatingActionButton(onClick = locate) { Text("◎", fontSize = 22.sp) }
            }
            Spacer(Modifier.height(6.dp))
            Surface(shape = RoundedCornerShape(14.dp), tonalElevation = 3.dp, shadowElevation = 3.dp) {
                Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                    dataError?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
                    if (!habitatMode) {
                        Text(dayLabel(dayOffset), fontWeight = FontWeight.SemiBold)
                        Slider(
                            value = dayOffset.toFloat(),
                            onValueChange = { dayOffset = Math.round(it) },
                            valueRange = WeatherGrid.SHOW_FROM.toFloat()..WeatherGrid.SHOW_TO.toFloat(),
                            steps = WeatherGrid.SHOW_TO - WeatherGrid.SHOW_FROM - 1,
                        )
                    } else {
                        Text("Habitat potentiel (essences, géologie, sol, altitude)", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    }
                    Legend()
                    if (status.isNotEmpty()) Text(status, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }

        info?.let { PointCard(it, sp, dayOffset, Modifier.align(Alignment.Center).padding(16.dp)) { probe = null } }
    }

    if (showSpecies) SpeciesDialog(species, spId, { spId = it; showSpecies = false }) { showSpecies = false }
    if (showSettings) SettingsDialog(
        topo, dataUrl,
        onTopo = { topo = it },
        onUrl = { u -> store.dataUrl = u; dataUrl = u.ifBlank { BuildConfig.DATA_URL } },
    ) { showSettings = false }
    if (showNotice) NoticeDialog { store.acceptedNotice = true; showNotice = false }
}

@Composable
private fun Legend() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("faible", fontSize = 11.sp)
        Spacer(Modifier.width(6.dp))
        Canvas(Modifier.weight(1f).height(10.dp)) {
            val n = 40
            for (k in 0 until n) {
                val v = 0.05f + 0.95f * k / (n - 1)
                drawRect(Color(Ramp.color(v)), topLeft = androidx.compose.ui.geometry.Offset(size.width * k / n, 0f),
                    size = androidx.compose.ui.geometry.Size(size.width / n + 1, size.height))
            }
        }
        Spacer(Modifier.width(6.dp))
        Text("très favorable", fontSize = 11.sp)
    }
}

class PointInfo(val p: GeoPoint, val px: PixelInfo?, val fruit: FruitField?)

@Composable
private fun PointCard(info: PointInfo, sp: Species, dayOffset: Int, modifier: Modifier, onClose: () -> Unit) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp).verticalScroll(rememberScrollState())) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(sp.nameFr, fontWeight = FontWeight.Bold, fontSize = 17.sp, modifier = Modifier.weight(1f))
                TextButton(onClick = onClose) { Text("Fermer") }
            }
            Text("%.5f, %.5f".format(Locale.US, info.p.latitude, info.p.longitude), fontSize = 11.sp)
            val c = info.px?.color
            if (c == null || !Enc.valid(c)) {
                Text("Pas de données d'habitat ici.", fontSize = 13.sp)
            } else {
                val h = sp.habitatPixel(c)
                val elev = Enc.elev(c)
                Spacer(Modifier.height(6.dp))
                Text("Habitat : ${(h * 100).toInt()} %", fontWeight = FontWeight.SemiBold)
                Text("Peuplement : ${Enc.FOREST_LABEL[Enc.forest(c)] ?: "?"}", fontSize = 13.sp)
                Text("Géologie : ${Enc.LITHO_LABEL[Enc.litho(c)] ?: "?"} · pH ${Enc.PH_LABEL[Enc.phc(c)]}", fontSize = 13.sp)
                Text("Altitude ≈ ${elev.toInt()} m · exposition ${Enc.ASPECT_LABEL[Enc.aspc(c).coerceIn(0, 8)]}" +
                    " · humidité topo. (TWI) ${Enc.twic(c)}/15", fontSize = 13.sp)
                val f = info.fruit
                if (f != null) {
                    val ee = Model.effectiveElev(elev, Enc.aspc(c))
                    val ser = f.series(info.p.latitude, info.p.longitude, ee, Enc.twic(c))
                    Spacer(Modifier.height(8.dp))
                    Text("Fructification J-14 … J+7 (aujourd'hui en trait)", fontSize = 12.sp)
                    SeriesChart(ser, dayOffset - WeatherGrid.SHOW_FROM, -WeatherGrid.SHOW_FROM)
                    val w = f.nearestWeather(info.p.latitude, info.p.longitude)
                    if (w != null) {
                        val t = WeatherGrid.TODAY
                        val p15 = (t - 14 until t).sumOf { w.precip[it].takeIf { v -> v.isFinite() } ?: 0.0 }
                        val p7f = (t until minOf(w.n, t + 7)).sumOf { w.precip[it].takeIf { v -> v.isFinite() } ?: 0.0 }
                        Text("Pluie : %.0f mm sur 14 j · prévue %.0f mm sur 7 j".format(FR, p15, p7f), fontSize = 12.sp)
                    }
                }
            }
            if (sp.lookalikes.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Text("⚠ Confusions : " + sp.lookalikes, fontSize = 12.sp, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun SeriesChart(v: FloatArray, sel: Int, today: Int) {
    val line = MaterialTheme.colorScheme.onSurface
    Canvas(Modifier.fillMaxWidth().height(70.dp).padding(vertical = 4.dp)) {
        val n = v.size
        val bw = size.width / n
        for (i in 0 until n) {
            val h = v[i].coerceIn(0f, 1f) * size.height
            drawRect(Color(if (h > 0) Ramp.color(maxOf(v[i], 0.06f)) else 0),
                topLeft = androidx.compose.ui.geometry.Offset(i * bw + 1, size.height - h),
                size = androidx.compose.ui.geometry.Size(bw - 2, h))
            if (i == sel) drawRect(line, topLeft = androidx.compose.ui.geometry.Offset(i * bw, 0f),
                size = androidx.compose.ui.geometry.Size(bw, size.height), style = Stroke(1.5f))
        }
        drawLine(line, androidx.compose.ui.geometry.Offset(today * bw + bw / 2, 0f),
            androidx.compose.ui.geometry.Offset(today * bw + bw / 2, size.height), strokeWidth = 2f)
    }
}

@Composable
private fun SpeciesDialog(species: List<Species>, current: String, onPick: (String) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Fermer") } },
        title = { Text("Champignon recherché") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                species.forEach { s ->
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(12.dp).background(Color(s.color), RoundedCornerShape(6.dp)))
                        Spacer(Modifier.width(8.dp))
                        TextButton(onClick = { onPick(s.id) }, modifier = Modifier.weight(1f)) {
                            Column(Modifier.fillMaxWidth()) {
                                Text(s.nameFr + if (s.experimental) " · expérimental" else "",
                                    fontWeight = if (s.id == current) FontWeight.Bold else FontWeight.Normal)
                                Text(s.latin, fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        },
    )
}

@Composable
private fun SettingsDialog(topo: Boolean, url: String, onTopo: (Boolean) -> Unit, onUrl: (String) -> Unit, onDismiss: () -> Unit) {
    var u by remember { mutableStateOf(if (url == BuildConfig.DATA_URL) "" else url) }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = { onUrl(u.trim()); onDismiss() }) { Text("OK") } },
        title = { Text("Réglages") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Fond topographique (OpenTopoMap)", Modifier.weight(1f))
                    Switch(checked = topo, onCheckedChange = onTopo)
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(u, { u = it }, label = { Text("Source des couches (.pmtiles)") },
                    placeholder = { Text("par défaut : release data-v1") }, singleLine = true)
                Text("URL https ou chemin d'un fichier local. Les zones consultées restent en cache " +
                    "pour un usage hors réseau.", fontSize = 11.sp)
                Spacer(Modifier.height(10.dp))
                Text("Sources", fontWeight = FontWeight.SemiBold)
                Text("Météo : Open-Meteo (CC-BY 4.0). Nappes : Hub'Eau / ADES (BRGM). Forêts : IGN BD Forêt® V2. " +
                    "Géologie : BRGM BD Charm-50. Sols : ISRIC SoilGrids. Relief : Copernicus DEM. " +
                    "Fonds : © contributeurs OpenStreetMap, OpenTopoMap (CC-BY-SA).", fontSize = 11.sp)
                Text("MycoScope ${BuildConfig.VERSION_NAME} — GPL-3.0", fontSize = 11.sp)
            }
        },
    )
}

@Composable
private fun NoticeDialog(onOk: () -> Unit) {
    AlertDialog(
        onDismissRequest = {},
        confirmButton = { TextButton(onClick = onOk) { Text("J'ai compris") } },
        title = { Text("Avant de partir en forêt") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState(), enabled = false)) {
                Text("MycoScope estime des zones et des périodes favorables à partir de cartes et de la météo. " +
                    "Il n'identifie aucun champignon et peut se tromper.\n\n" +
                    "• Ne consommez jamais un champignon sans certitude absolue : faites vérifier par un " +
                    "pharmacien ou une société mycologique. En cas de symptômes, appelez le 15 ou un centre antipoison.\n" +
                    "• La cueillette est réglementée (arrêtés préfectoraux et municipaux, quotas) et la plupart " +
                    "des forêts appartiennent à quelqu'un : demandez l'autorisation en forêt privée.\n" +
                    "• Respectez le milieu : coupez ou dévissez, ne ratissez pas, laissez les jeunes et les vieux.")
            }
        },
    )
}
