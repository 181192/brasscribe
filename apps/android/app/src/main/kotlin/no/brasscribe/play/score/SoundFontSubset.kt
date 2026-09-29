package no.brasscribe.play.score

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A SoundFont cut down to the samples a few bars need, read straight from the file. alphaTab's
 * synth decodes every sample of every preset whose *program* the MIDI uses, whatever the bank, and
 * every brass preset of the band SoundFont is on program 56, 57, 58 or 60: a bar render with the
 * whole file would hold the file's bytes, alphaTab's copy of the sample chunk and all samples as
 * floats (some 300 MB for the 77 MB phone SoundFont). The subset keeps the file's presets,
 * instruments and zones as they are and changes only the sample chunk:
 *  - a zone whose key range holds a key the bars play keeps its sample, byte for byte;
 *  - every other sample points at a short stretch of silence;
 *  - a preset no note plays is moved to a (bank, program) nothing selects, so alphaTab skips it.
 */
object SoundFontSubset {
    /** A key played on a channel that selects preset (bank, program); [drums] for MIDI channel 10. */
    data class Use(val bank: Int, val program: Int, val key: Int, val drums: Boolean = false)

    /** Bank alphaTab never selects (its bank is at most 16383, and nothing asks for this one). */
    private const val UNUSED_BANK = 1999
    private const val PERCUSSION_BANK = 128
    /** Frames of silence at the start of the new sample chunk, where the samples no note plays point. */
    private const val SILENCE = 64
    /** Zero frames after each sample, as the SoundFont spec asks. */
    private const val GUARD = 46
    private const val GEN_INSTRUMENT = 41
    private const val GEN_KEY_RANGE = 43
    private const val GEN_SAMPLE_ID = 53
    /** Sample address offsets (start, end, loop start, loop end and their coarse parts): a zone with one keeps its sample. */
    private val OFFSET_GENS = setOf(0, 1, 2, 3, 4, 12, 45, 50)

    private class Chunk(val id: String, val data: ByteArray)

    /**
     * The subset of [file] for [uses], as SoundFont bytes. [programs] are all the programs the MIDI
     * selects (alphaTab decodes every preset on one of them): the presets set aside go to a program
     * outside it.
     */
    fun build(file: File, uses: Collection<Use>, programs: Set<Int> = uses.filter { !it.drums }.map { it.program }.toSet()): ByteArray = RandomAccessFile(file, "r").use { raf ->
        val header = ByteArray(12).also { raf.readFully(it) }
        require(String(header, 0, 4, Charsets.US_ASCII) == "RIFF" && String(header, 8, 4, Charsets.US_ASCII) == "sfbk") { "not a SoundFont" }
        var info: ByteArray? = null
        var smplOffset = -1L
        var smplSize = 0L
        val pdta = ArrayList<Chunk>()
        var pos = 12L
        val riffEnd = minOf(raf.length(), 8L + le32(header, 4))
        while (pos + 8 <= riffEnd) {
            val (id, size) = chunkHeader(raf, pos)
            if (id == "LIST") {
                raf.seek(pos + 8)
                val type = ByteArray(4).also { raf.readFully(it) }.toString(Charsets.US_ASCII)
                when (type) {
                    "INFO" -> info = ByteArray(size.toInt() - 4).also { raf.readFully(it) }
                    "sdta", "pdta" -> {
                        var p = pos + 12
                        while (p + 8 <= pos + 8 + size) {
                            val (cid, csize) = chunkHeader(raf, p)
                            if (type == "sdta" && cid == "smpl") { smplOffset = p + 8; smplSize = csize }
                            if (type == "pdta") pdta += Chunk(cid, ByteArray(csize.toInt()).also { raf.seek(p + 8); raf.readFully(it) })
                            p += 8 + csize + (csize and 1)
                        }
                    }
                }
            }
            pos += 8 + size + (size and 1)
        }
        require(smplOffset >= 0) { "no sample chunk" }
        val chunks = pdta.associateBy { it.id }
        fun records(id: String, size: Int): ByteBuffer = ByteBuffer.wrap(chunks.getValue(id).data).order(ByteOrder.LITTLE_ENDIAN).also {
            require(it.capacity() % size == 0) { "bad $id" }
        }
        val phdr = records("phdr", 38)
        val pbag = records("pbag", 4)
        val pgen = records("pgen", 4)
        val inst = records("inst", 22)
        val ibag = records("ibag", 4)
        val igen = records("igen", 4)
        val shdrBytes = chunks.getValue("shdr").data.copyOf()
        val shdr = ByteBuffer.wrap(shdrBytes).order(ByteOrder.LITTLE_ENDIAN)
        val phdrBytes = chunks.getValue("phdr").data.copyOf()
        val phdrOut = ByteBuffer.wrap(phdrBytes).order(ByteOrder.LITTLE_ENDIAN)
        val presets = phdr.capacity() / 38 - 1
        val samples = shdr.capacity() / 46 - 1
        fun u16(b: ByteBuffer, at: Int) = b.getShort(at).toInt() and 0xFFFF

        val keep = BooleanArray(samples)
        val freeProgram = (0..127).firstOrNull { it !in programs } ?: 127
        for (p in 0 until presets) {
            val program = u16(phdr, p * 38 + 20)
            val bank = u16(phdr, p * 38 + 22)
            val keys = uses.filter { if (bank == PERCUSSION_BANK) it.drums else !it.drums && it.bank == bank && it.program == program }
                .map { it.key }.toSet()
            if (keys.isEmpty()) {
                phdrOut.putShort(p * 38 + 20, freeProgram.toShort())
                phdrOut.putShort(p * 38 + 22, UNUSED_BANK.toShort())
                continue
            }
            // Zones as alphaTab builds them: a preset zone's key range (the global zone's by default)
            // narrows its instrument's zones, each of which takes the instrument's global zone's range.
            var global = 0 to 127
            for (b in u16(phdr, p * 38 + 24) until u16(phdr, (p + 1) * 38 + 24)) {
                var range = global
                var instrument = -1
                var offsets = false
                for (g in u16(pbag, b * 4) until u16(pbag, (b + 1) * 4)) {
                    val oper = u16(pgen, g * 4)
                    when (oper) {
                        GEN_KEY_RANGE -> range = (pgen.get(g * 4 + 2).toInt() and 0xFF) to (pgen.get(g * 4 + 3).toInt() and 0xFF)
                        GEN_INSTRUMENT -> instrument = u16(pgen, g * 4 + 2)
                        in OFFSET_GENS -> offsets = true
                    }
                }
                if (instrument < 0) {
                    if (b == u16(phdr, p * 38 + 24)) global = range
                    continue
                }
                if (instrument >= inst.capacity() / 22 - 1) continue
                var instGlobal = 0 to 127
                for (ib in u16(inst, instrument * 22 + 20) until u16(inst, (instrument + 1) * 22 + 20)) {
                    var zone = instGlobal
                    var sample = -1
                    var zoneOffsets = offsets
                    for (g in u16(ibag, ib * 4) until u16(ibag, (ib + 1) * 4)) {
                        when (val oper = u16(igen, g * 4)) {
                            GEN_KEY_RANGE -> zone = (igen.get(g * 4 + 2).toInt() and 0xFF) to (igen.get(g * 4 + 3).toInt() and 0xFF)
                            GEN_SAMPLE_ID -> sample = u16(igen, g * 4 + 2)
                            else -> if (oper in OFFSET_GENS) zoneOffsets = true
                        }
                    }
                    if (sample < 0) {
                        if (ib == u16(inst, instrument * 22 + 20)) instGlobal = zone
                        continue
                    }
                    if (sample >= samples) continue
                    val lo = maxOf(zone.first, range.first)
                    val hi = minOf(zone.second, range.second)
                    if (zoneOffsets || keys.any { it in lo..hi }) keep[sample] = true
                }
            }
        }

        // The new sample chunk: silence, then each kept sample with its guard frames.
        val starts = LongArray(samples)
        var frames = SILENCE.toLong()
        for (s in 0 until samples) if (keep[s]) {
            val start = shdr.getInt(s * 46 + 20).toLong() and 0xFFFFFFFFL
            val end = shdr.getInt(s * 46 + 24).toLong() and 0xFFFFFFFFL
            require(end >= start && end * 2 <= smplSize) { "sample $s outside the sample chunk" }
            starts[s] = frames
            frames += end - start + GUARD
        }
        val smplBytes = frames * 2
        val pdtaOut = pdta.map { c -> when (c.id) { "phdr" -> Chunk(c.id, phdrBytes); "shdr" -> Chunk(c.id, shdrBytes); else -> c } }
        fun padded(n: Int) = n + (n and 1)
        val infoSize = info?.let { 8 + 4 + padded(it.size) } ?: 0
        val sdtaSize = 8 + 4 + 8 + smplBytes
        val pdtaSize = 8 + 4 + pdtaOut.sumOf { 8 + padded(it.data.size) }
        val total = 12 + infoSize + sdtaSize + pdtaSize
        require(total < Int.MAX_VALUE) { "subset too large" }
        // One array for the whole file: the samples are read straight into it.
        val out = ByteBuffer.wrap(ByteArray(total.toInt())).order(ByteOrder.LITTLE_ENDIAN)
        fun id(s: String) { out.put(s.toByteArray(Charsets.US_ASCII)) }
        fun chunk(name: String, data: ByteArray) { id(name); out.putInt(data.size); out.put(data); if (data.size % 2 == 1) out.put(0) }
        id("RIFF"); out.putInt((total - 8).toInt()); id("sfbk")
        info?.let { id("LIST"); out.putInt(4 + padded(it.size)); id("INFO"); out.put(it); if (it.size % 2 == 1) out.put(0) }
        id("LIST"); out.putInt((sdtaSize - 8).toInt()); id("sdta"); id("smpl"); out.putInt(smplBytes.toInt())
        val smplAt = out.position()
        for (s in 0 until samples) {
            val at = s * 46
            val start = shdr.getInt(at + 20).toLong() and 0xFFFFFFFFL
            if (keep[s]) {
                val end = shdr.getInt(at + 24).toLong() and 0xFFFFFFFFL
                raf.seek(smplOffset + start * 2)
                raf.readFully(out.array(), smplAt + (starts[s] * 2).toInt(), ((end - start) * 2).toInt())
                // start, end, loop start and loop end move together
                val shift = starts[s] - start
                for (field in 20..32 step 4) shdr.putInt(at + field, ((shdr.getInt(at + field).toLong() and 0xFFFFFFFFL) + shift).toInt())
            } else {
                shdr.putInt(at + 20, 0)
                shdr.putInt(at + 24, SILENCE)
                shdr.putInt(at + 28, 8)
                shdr.putInt(at + 32, SILENCE - 8)
            }
        }
        out.position(smplAt + smplBytes.toInt())
        id("LIST"); out.putInt(pdtaSize - 8); id("pdta")
        for (c in pdtaOut) chunk(c.id, c.data)
        check(!out.hasRemaining())
        out.array()
    }

    private fun chunkHeader(raf: RandomAccessFile, at: Long): Pair<String, Long> {
        raf.seek(at)
        val h = ByteArray(8).also { raf.readFully(it) }
        return String(h, 0, 4, Charsets.US_ASCII) to le32(h, 4)
    }

    private fun le32(b: ByteArray, at: Int): Long =
        (b[at].toLong() and 0xFF) or ((b[at + 1].toLong() and 0xFF) shl 8) or ((b[at + 2].toLong() and 0xFF) shl 16) or ((b[at + 3].toLong() and 0xFF) shl 24)

}
