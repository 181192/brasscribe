package no.brasscribe.play.ui

import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import no.brasscribe.play.connection.QrDecoder

/**
 * The camera under the pairing scanner: what it sees, and the text of the first QR code in view. The
 * app's is [PhoneQrCamera]; tests put their own in [no.brasscribe.play.AppContainer.qrCamera].
 */
interface QrCamera {
    /**
     * Shows the camera; calls [onCode] once, on the main thread, with the first QR code it reads, or
     * [onUnavailable] when the camera can't be opened.
     */
    @Composable
    fun View(modifier: Modifier, onCode: (String) -> Unit, onUnavailable: () -> Unit)
}

/**
 * The phone's back camera (CameraX), each frame read on the phone by [QrDecoder]. Frames are only
 * looked at for the code: none is kept, written or sent.
 */
object PhoneQrCamera : QrCamera {
    @Composable
    override fun View(modifier: Modifier, onCode: (String) -> Unit, onUnavailable: () -> Unit) {
        val context = LocalContext.current
        val owner = LocalLifecycleOwner.current
        val currentOnCode by rememberUpdatedState(onCode)
        val currentOnUnavailable by rememberUpdatedState(onUnavailable)
        val preview = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }
        DisposableEffect(owner) {
            val main = ContextCompat.getMainExecutor(context)
            val worker = Executors.newSingleThreadExecutor()
            val decoder = QrDecoder()
            val done = AtomicBoolean(false)
            var disposed = false
            val future = ProcessCameraProvider.getInstance(context)
            var provider: ProcessCameraProvider? = null
            val shown = Preview.Builder().build().also { it.surfaceProvider = preview.surfaceProvider }
            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(worker) { image ->
                image.use {
                    if (done.get()) return@use
                    val plane = it.planes[0]
                    val buffer = plane.buffer
                    val bytes = ByteArray(buffer.remaining()).also(buffer::get)
                    val text = decoder.decode(bytes, it.width, it.height, plane.rowStride)
                    if (text != null && done.compareAndSet(false, true)) main.execute { currentOnCode(text) }
                }
            }
            future.addListener({
                if (disposed) return@addListener
                val p = runCatching { future.get() }.getOrNull() ?: return@addListener currentOnUnavailable()
                provider = p
                runCatching {
                    p.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, shown, analysis)
                }.recoverCatching {
                    // A phone with only a front camera (or a tablet) still scans.
                    p.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, shown, analysis)
                }.onFailure { currentOnUnavailable() }
            }, main)
            onDispose {
                disposed = true
                done.set(true)
                provider?.unbind(shown, analysis)
                analysis.clearAnalyzer()
                worker.shutdown()
            }
        }
        AndroidView({ preview }, modifier)
    }
}
