package no.brasscribe.play.connection

import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.NotFoundException
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer

/**
 * Reads the pairing QR code from a camera frame, on the phone (ZXing). Nothing is sent anywhere: the
 * frame is the camera's grey plane (the Y of YUV 4:2:0), `rowStride` bytes a row, and only the text of
 * a QR code comes out. A code drawn light on dark (the computer in dark mode) reads as well.
 */
class QrDecoder {
    private val reader = MultiFormatReader().apply {
        setHints(mapOf(
            DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
            DecodeHintType.TRY_HARDER to true,
            DecodeHintType.ALSO_INVERTED to true,
        ))
    }

    /** The QR code's text in this frame, or null when there is none (or it can't be read). */
    fun decode(luminance: ByteArray, width: Int, height: Int, rowStride: Int = width): String? {
        require(width > 0 && height > 0 && rowStride >= width) { "frame $width x $height, row stride $rowStride" }
        require(luminance.size >= rowStride * (height - 1) + width) { "frame is ${luminance.size} bytes, too short" }
        val source = PlanarYUVLuminanceSource(luminance, rowStride, height, 0, 0, width, height, false)
        return try {
            reader.decodeWithState(BinaryBitmap(HybridBinarizer(source))).text
        } catch (_: NotFoundException) {
            null
        } catch (_: ReaderException) {
            null
        } finally {
            reader.reset()
        }
    }
}
