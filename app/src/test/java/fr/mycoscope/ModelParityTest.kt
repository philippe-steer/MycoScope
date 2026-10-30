package fr.mycoscope

import fr.mycoscope.data.PmTiles
import fr.mycoscope.model.DailyWeather
import fr.mycoscope.model.Model
import fr.mycoscope.model.Species
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/** Compare le modèle Kotlin aux sorties du modèle Python de référence (tests/make_fixture.py). */
class ModelParityTest {
    private val species = Species.parseAll(File("src/main/assets/species.json").readText()).associateBy { it.id }
    private val fx = JSONObject(javaClass.classLoader!!.getResource("model_fixture.json")!!.readText())

    private fun arr(o: JSONObject, k: String): DoubleArray {
        val a = o.getJSONArray(k)
        return DoubleArray(a.length()) { a.getDouble(it) }
    }

    @Test
    fun fruitingMatchesPython() {
        val w = fx.getJSONObject("weather")
        val doy = arr(w, "doy").map { it.toInt() }.toIntArray()
        val dw = DailyWeather(doy, arr(w, "precip"), arr(w, "tmean"), arr(w, "tmin"), arr(w, "et0"), w.getDouble("elevation"))
        val cases = fx.getJSONArray("fruiting")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val sp = species.getValue(c.getString("species"))
            val got = Model.fruiting(sp, dw, c.getDouble("elev"), c.getDouble("dm"))
            val exp = arr(c, "f")
            for (d in exp.indices) assertEquals("${sp.id} ${c.getDouble("elev")} day $d", exp[d], got[d], 1e-5)
        }
    }

    @Test
    fun habitatMatchesPython() {
        val cases = fx.getJSONArray("habitat")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val sp = species.getValue(c.getString("species"))
            val got = sp.habitat(c.getInt("forest"), c.getInt("litho"), c.getInt("phc"), c.getDouble("elev"))
            assertEquals("${sp.id} case $i", c.getDouble("h"), got, 1e-6)
        }
    }

    @Test
    fun tileIdsMatchPmtiles() {
        assertEquals(0L, PmTiles.tileId(0, 0, 0))
        assertEquals(4L, PmTiles.tileId(1, 1, 0))
        assertEquals(495L, PmTiles.tileId(5, 15, 11))
        assertEquals(8120835L, PmTiles.tileId(12, 2030, 1420))
        assertEquals(16777215L, PmTiles.tileId(12, 4095, 4095))
    }
}

class PmTilesReaderTest {
    @Test
    fun readsSampleFile() {
        val f = File(javaClass.classLoader!!.getResource("sample.pmtiles")!!.toURI())
        val r = PmTiles(f.absolutePath, null)
        val h = r.header()
        assertEquals(5, h.minZoom)
        assertEquals(12, h.maxZoom)
        val exp = org.json.JSONArray(javaClass.classLoader!!.getResource("sample_tiles.json")!!.readText())
        for (i in 0 until exp.length()) {
            val e = exp.getJSONObject(i)
            val data = r.tile(e.getInt("z"), e.getInt("x"), e.getInt("y"))!!
            val sha = java.security.MessageDigest.getInstance("SHA-1").digest(data).joinToString("") { "%02x".format(it) }
            assertEquals(e.getString("sha1"), sha)
        }
        org.junit.Assert.assertNull(r.tile(12, 0, 0))
        org.junit.Assert.assertTrue(r.metadata().contains("format_version"))
    }
}
