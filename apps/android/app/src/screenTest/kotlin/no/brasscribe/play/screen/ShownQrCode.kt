package no.brasscribe.play.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import no.brasscribe.play.ui.QrCamera

/**
 * A camera for the pairing scanner that sees [code] (the text of a QR code) as soon as it is shown, or, when it
 * is null, a grey picture with nothing to read. The decoding itself is QrDecoderTest's.
 */
class ShownQrCode(private val code: String?) : QrCamera {
    @Composable
    override fun View(modifier: Modifier, onCode: (String) -> Unit, onUnavailable: () -> Unit) {
        Box(modifier.background(Color(0xFF5A5A5A)))
        if (code != null) LaunchedEffect(code) { onCode(code) }
    }
}
