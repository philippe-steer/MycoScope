package fr.mycoscope.data

import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.GZIPInputStream

/**
 * Lecteur PMTiles v3 minimal : en-tête, répertoires (racine + feuilles, gzip), tuiles brutes.
 * Source : URL HTTP(S) (requêtes Range, redirections suivies à la main pour garder l'en-tête
 * Range, ex. assets GitHub) ou fichier local. Les tuiles lues sont gardées dans `cacheDir`,
 * ce qui permet de revoir hors réseau les zones déjà consultées.
 */
class PmTiles(private val source: String, private val cacheDir: File?, private val userAgent: String = "MycoScope") {

    class Header(
        val rootOffset: Long, val rootLength: Long,
        val metadataOffset: Long, val metadataLength: Long,
        val leafOffset: Long, val leafLength: Long,
        val tileDataOffset: Long, val tileDataLength: Long,
        val internalCompression: Int, val tileCompression: Int, val tileType: Int,
        val minZoom: Int, val maxZoom: Int,
        val minLon: Double, val minLat: Double, val maxLon: Double, val maxLat: Double,
    )

    class Entry(val tileId: Long, val offset: Long, val length: Int, val runLength: Int)

    @Volatile private var header: Header? = null
    private var root: List<Entry> = emptyList()
    private val leaves = object : LinkedHashMap<Long, List<Entry>>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Long, List<Entry>>?) = size > 64
    }
    @Volatile private var resolved: Pair<String, Long>? = null
    private val isFile = !source.startsWith("http")

    // ------------------------------------------------------------------ octets
    private fun readRange(offset: Long, length: Long): ByteArray {
        if (isFile) {
            RandomAccessFile(source, "r").use { f ->
                val b = ByteArray(minOf(length, f.length() - offset).toInt())
                f.seek(offset)
                f.readFully(b)
                return b
            }
        }
        var url = resolvedUrl()
        repeat(6) {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.instanceFollowRedirects = false
            conn.connectTimeout = 15_000
            conn.readTimeout = 60_000
            conn.setRequestProperty("User-Agent", userAgent)
            conn.setRequestProperty("Range", "bytes=$offset-${offset + length - 1}")
            try {
                when (val code = conn.responseCode) {
                    206 -> return conn.inputStream.use { it.readBytes() }
                    416 -> return ByteArray(0)
                    200 -> {
                        // serveur sans Range : on lit jusqu'à l'offset voulu (fichier petit seulement)
                        return conn.inputStream.use { s -> s.skipFully(offset); s.readN(length.toInt()) }
                    }
                    in 300..399 -> {
                        url = URL(URL(url), conn.getHeaderField("Location")).toString()
                        resolved = url to System.currentTimeMillis()
                    }
                    else -> throw IOException("HTTP $code")
                }
            } finally {
                conn.disconnect()
            }
        }
        throw IOException("trop de redirections")
    }

    /** Les URL signées des assets GitHub expirent après quelques minutes. */
    private fun resolvedUrl(): String {
        val r = resolved
        return if (r != null && System.currentTimeMillis() - r.second < 60_000) r.first else source
    }

    private fun InputStream.skipFully(n: Long) {
        var left = n
        while (left > 0) {
            val k = skip(left)
            if (k <= 0) { if (read() < 0) throw IOException("EOF"); left-- } else left -= k
        }
    }

    private fun InputStream.readN(n: Int): ByteArray {
        val b = ByteArray(n)
        var o = 0
        while (o < n) { val k = read(b, o, n - o); if (k < 0) break; o += k }
        return b
    }

    // ------------------------------------------------------------------ structure
    @Synchronized
    fun header(): Header {
        header?.let { return it }
        val cached = cacheDir?.let { File(it, "head.bin") }
        val buf = if (cached != null && cached.exists() && cached.length() > 127L) cached.readBytes()
        else readRange(0, 16384).also { b -> cached?.let { it.parentFile?.mkdirs(); it.writeBytes(b) } }
        if (String(buf, 0, 7) != "PMTiles" || buf[7].toInt() != 3) throw IOException("fichier PMTiles v3 invalide")
        fun u64(o: Int): Long { var v = 0L; for (i in 7 downTo 0) v = (v shl 8) or (buf[o + i].toLong() and 0xFF); return v }
        fun i32(o: Int): Int { var v = 0; for (i in 3 downTo 0) v = (v shl 8) or (buf[o + i].toInt() and 0xFF); return v }
        val h = Header(
            u64(8), u64(16), u64(24), u64(32), u64(40), u64(48), u64(56), u64(64),
            buf[97].toInt(), buf[98].toInt(), buf[99].toInt(), buf[100].toInt(), buf[101].toInt(),
            i32(102) / 1e7, i32(106) / 1e7, i32(110) / 1e7, i32(114) / 1e7,
        )
        root = parseDirectory(decompress(buf.copyOfRange(h.rootOffset.toInt(), (h.rootOffset + h.rootLength).toInt()), h.internalCompression))
        header = h
        return h
    }

    fun metadata(): String {
        val h = header()
        return String(decompress(readRange(h.metadataOffset, h.metadataLength), h.internalCompression))
    }

    private fun decompress(b: ByteArray, compression: Int): ByteArray = when (compression) {
        1, 0 -> b
        2 -> GZIPInputStream(ByteArrayInputStream(b)).use { it.readBytes() }
        else -> throw IOException("compression $compression non gérée")
    }

    private fun parseDirectory(b: ByteArray): List<Entry> {
        var p = 0
        fun varint(): Long {
            var v = 0L
            var shift = 0
            while (true) {
                val x = b[p++].toInt() and 0xFF
                v = v or ((x and 0x7F).toLong() shl shift)
                if (x and 0x80 == 0) return v
                shift += 7
            }
        }
        val n = varint().toInt()
        val ids = LongArray(n)
        var last = 0L
        for (i in 0 until n) { last += varint(); ids[i] = last }
        val runs = IntArray(n) { varint().toInt() }
        val lens = IntArray(n) { varint().toInt() }
        val offs = LongArray(n)
        for (i in 0 until n) {
            val v = varint()
            offs[i] = if (i > 0 && v == 0L) offs[i - 1] + lens[i - 1] else v - 1
        }
        return List(n) { Entry(ids[it], offs[it], lens[it], runs[it]) }
    }

    private fun find(entries: List<Entry>, id: Long): Entry? {
        var m = 0
        var n = entries.size - 1
        while (m <= n) {
            val k = (n + m) ushr 1
            val c = id - entries[k].tileId
            if (c > 0) m = k + 1 else if (c < 0) n = k - 1 else return entries[k]
        }
        if (n >= 0) {
            val e = entries[n]
            if (e.runLength == 0) return e
            if (id - e.tileId < e.runLength) return e
        }
        return null
    }

    /** Octets bruts de la tuile, ou null si elle n'existe pas. */
    fun tile(z: Int, x: Int, y: Int): ByteArray? {
        val cf = cacheDir?.let { File(it, "$z/$x/$y.t") }
        if (cf != null && cf.exists()) return cf.readBytes().takeIf { it.isNotEmpty() }
        val h = header()
        if (z < h.minZoom || z > h.maxZoom) return null
        val id = tileId(z, x, y)
        var dir = root
        repeat(4) {
            val e = find(dir, id) ?: return null.also { cf?.let { f -> f.parentFile?.mkdirs(); f.writeBytes(ByteArray(0)) } }
            if (e.runLength > 0) {
                val data = readRange(h.tileDataOffset + e.offset, e.length.toLong())
                cf?.let { f -> f.parentFile?.mkdirs(); f.writeBytes(data) }
                return data
            }
            val key = e.offset
            dir = synchronized(leaves) { leaves[key] } ?: parseDirectory(
                decompress(readRange(h.leafOffset + e.offset, e.length.toLong()), h.internalCompression)
            ).also { synchronized(leaves) { leaves[key] = it } }
        }
        return null
    }

    companion object {
        /** Identifiant de tuile (courbe de Hilbert), identique à pmtiles.tile.zxy_to_tileid. */
        fun tileId(z: Int, x0: Int, y0: Int): Long {
            var acc = ((1L shl (z * 2)) - 1) / 3
            var x = x0.toLong()
            var y = y0.toLong()
            var a = z - 1
            while (a >= 0) {
                val s = 1L shl a
                val rx = s and x
                val ry = s and y
                acc += ((3 * rx) xor ry) shl a
                if (ry == 0L) {
                    if (rx != 0L) {
                        x = s - 1 - x
                        y = s - 1 - y
                    }
                    val t = x; x = y; y = t
                }
                a--
            }
            return acc
        }
    }
}
