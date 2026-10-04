package no.brasscribe.play.connection

import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import no.brasscribe.play.engine.PairLink
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The pairing QR code is read on the phone. These frames are what the camera hands the decoder: a grey
 * plane, its rows padded past the width as a phone's camera pads them, the code somewhere in it.
 */
class QrDecoderTest {
    private val link = "brasscribe://pair?v=1&id=srv-7f3a&name=Brasscribe%20on%20Kari%E2%80%99s%20Mac" +
        "&h=192.168.0.20:8765,[fd00::5]:8765&code=482913&fp=abc_-DEF"

    /** A camera frame of [width] x [height] (rows [rowStride] bytes) with [text]'s QR code at ([left], [top]). */
    private fun frame(
        text: String, width: Int = 640, height: Int = 480, rowStride: Int = 704, size: Int = 300,
        left: Int = 170, top: Int = 90, inverted: Boolean = false, turned: Boolean = false,
    ): ByteArray {
        val code = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, size, size,
            mapOf(EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M, EncodeHintType.MARGIN to 4))
        val (dark, light) = if (inverted) 230.toByte() to 25.toByte() else 25.toByte() to 230.toByte()
        // The padding past the width is never looked at: filled with noise to show it.
        val bytes = ByteArray(rowStride * height) { (it * 31 % 251).toByte() }
        for (y in 0 until height) for (x in 0 until width) {
            val cx = x - left
            val cy = y - top
            val inCode = cx in 0 until size && cy in 0 until size
            val on = inCode && (if (turned) code[cy, size - 1 - cx] else code[cx, cy])
            bytes[y * rowStride + x] = if (on) dark else light
        }
        return bytes
    }

    /** [into] with [text]'s QR code also drawn at ([left], [top]). */
    private fun alsoDrawn(into: ByteArray, text: String, left: Int, top: Int, size: Int = 200, rowStride: Int = 704): ByteArray {
        val code = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, size, size, mapOf(EncodeHintType.MARGIN to 4))
        for (y in 0 until size) for (x in 0 until size) into[(top + y) * rowStride + left + x] = if (code[x, y]) 25.toByte() else 230.toByte()
        return into
    }

    private val isPairing: (String) -> Boolean = { PairLink.parse(it) != null }

    @Test
    fun withAnotherCodeInViewThePairingLinkIsTaken() {
        // A poster's code next to the computer's, the poster's found first (left of it).
        val both = alsoDrawn(frame(link, width = 640, height = 480, size = 260, left = 370, top = 110), "https://example.org/menu", left = 20, top = 140)
        assertEquals(link, QrDecoder().decode(both, 640, 480, 704, isPairing))
    }

    @Test
    fun aCodeThatIsNotAPairingLinkIsPassedOver() {
        assertNull(QrDecoder().decode(frame("https://example.org/menu"), 640, 480, 704, isPairing))
        assertEquals("https://example.org/menu", QrDecoder().decode(frame("https://example.org/menu"), 640, 480, 704))
    }

    @Test
    fun readsThePairingLinkAsTheComputerShowsIt() {
        val text = QrDecoder().decode(frame(link), 640, 480, 704)
        assertEquals(link, text)
        val parsed = PairLink.parse(text!!)
        assertNotNull("the scanned text is a pairing link", parsed)
        assertEquals("srv-7f3a", parsed!!.serverId)
        assertEquals(listOf("192.168.0.20:8765", "[fd00::5]:8765"), parsed.hosts)
        assertEquals("482913", parsed.code)
    }

    @Test
    fun readsACodeShownLightOnDark() {
        assertEquals(link, QrDecoder().decode(frame(link, inverted = true), 640, 480, 704))
    }

    @Test
    fun readsACodeHeldOnItsSide() {
        assertEquals(link, QrDecoder().decode(frame(link, turned = true), 640, 480, 704))
    }

    @Test
    fun readsAFrameWithoutPadding() {
        assertEquals(link, QrDecoder().decode(frame(link, rowStride = 640), 640, 480))
    }

    @Test
    fun aFrameWithoutACodeReadsAsNothing() {
        val blank = ByteArray(640 * 480) { 128.toByte() }
        assertNull(QrDecoder().decode(blank, 640, 480))
    }

    @Test
    fun oneDecoderReadsFrameAfterFrame() {
        val decoder = QrDecoder()
        assertNull(decoder.decode(ByteArray(640 * 480) { 128.toByte() }, 640, 480))
        assertEquals(link, decoder.decode(frame(link), 640, 480, 704))
        assertEquals("brasscribe://pair?v=1&id=a&h=10.0.0.2:8765&code=1",
            decoder.decode(frame("brasscribe://pair?v=1&id=a&h=10.0.0.2:8765&code=1", left = 20, top = 20), 640, 480, 704))
    }
}
