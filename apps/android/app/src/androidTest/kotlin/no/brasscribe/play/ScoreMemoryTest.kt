package no.brasscribe.play

import android.os.Debug
import android.os.SystemClock
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import no.brasscribe.play.score.BandSoundFontFile
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.concurrent.thread
import no.brasscribe.play.test.DeviceOnly

/**
 * Peak memory while scores open, sampled every 10 ms: Java heap in use (what largeHeap raises) and the
 * native heap. alphaTab holds the band SoundFont at about three times its size, so it loads only once
 * a score has been open a moment, or at the first Play: scores opened and left at once stay near the
 * ordinary heap (192 MB on the emulator, 576 MB with largeHeap). A score left after playing takes its
 * SoundFont with it, and Play after a moment's reading starts at once. Needs the band SoundFont
 * bundled or sideloaded; skipped without it.
 */
@RunWith(AndroidJUnit4::class)
@DeviceOnly
class ScoreMemoryTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val container get() = (rule.activity.application as PlayApplication).container
    private val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]

    @Volatile private var sampling = true
    @Volatile private var peakHeap = 0L
    @Volatile private var peakNative = 0L

    private fun used(): Long { val rt = Runtime.getRuntime(); return rt.totalMemory() - rt.freeMemory() }

    private val sampler = thread(start = false, name = "memory-sampler") {
        while (sampling) {
            peakHeap = maxOf(peakHeap, used())
            peakNative = maxOf(peakNative, Debug.getNativeHeapAllocatedSize())
            Thread.sleep(10)
        }
    }

    private fun resetPeaks() { peakHeap = used(); peakNative = Debug.getNativeHeapAllocatedSize() }

    private lateinit var library: LibrarySnapshot

    @Before
    fun setUp() {
        assumeScreenUsable(rule.activity)
        library = LibrarySnapshot(rule.activity)
        container.firstRunDone = true
        container.standHintShown = true
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithText("Get started").performClick()
    }

    @After
    fun tearDown() {
        sampling = false
        runCatching { vm.scoreController?.let { c -> if (c.state.value.playing) rule.runOnUiThread { c.stop() } } }
        if (::library.isInitialized) library.deleteAdded()
    }

    private fun gc() { repeat(3) { Runtime.getRuntime().gc(); System.runFinalization(); Thread.sleep(100) } }

    /** The hymn's bars [times] over in every part, renumbered: a band score of about Mikkel's size (2 MB). */
    private fun repeated(xml: String, times: Int): String {
        val part = Regex("""(<part\s+id="[^"]+"\s*>)(.*?)(</part>)""", RegexOption.DOT_MATCHES_ALL)
        val measure = Regex("""<measure\b[^>]*>.*?</measure>""", RegexOption.DOT_MATCHES_ALL)
        return part.replace(xml) { m ->
            val bars = measure.findAll(m.groupValues[2]).map { it.value }.toList()
            var n = 0
            val body = (0 until times).joinToString("\n") {
                bars.joinToString("\n") { b -> n++; b.replaceFirst(Regex("""number="[^"]*""""), "number=\"$n\"") }
            }
            m.groupValues[1] + body + m.groupValues[3]
        }
    }

    private fun scoreXml(): String =
        repeated(instrumentation.context.assets.open("old-hundredth/brass-band.musicxml").use { it.readBytes() }.decodeToString(), TIMES)
            .replace(Regex("""<work-title>[^<]*</work-title>"""), "<work-title>Memory Probe</work-title>")

    private fun openFromHome() {
        rule.waitUntil(10_000) { rule.onAllNodesWithText("Memory Probe", substring = true).fetchSemanticsNodes().isNotEmpty() }
        val before = vm.scoreController
        rule.onAllNodesWithText("Memory Probe", substring = true).onFirst().performClick()
        rule.waitUntil(30_000) { vm.scoreController.let { it !== before && it?.state?.value?.loaded == true } }
        val c = vm.scoreController!!
        rule.waitUntil(30_000) { c.renders.value > 0 }
    }

    /** Plays the open score until the band SoundFont is in, then stops; the milliseconds until it played. */
    private fun playOnce(): Long {
        val c = vm.scoreController!!
        val t0 = SystemClock.uptimeMillis()
        rule.runOnUiThread { c.togglePlay() }
        rule.waitUntil(30_000) { c.state.value.playing }
        val ms = SystemClock.uptimeMillis() - t0
        rule.waitUntil(30_000) { c.state.value.bandSoundFont }
        Thread.sleep(300)
        rule.runOnUiThread { c.stop() }
        Thread.sleep(200)
        return ms
    }

    private fun leave() {
        rule.runOnUiThread { vm.back() }
        rule.waitUntil(10_000) { rule.onAllNodesWithTag("score-view").fetchSemanticsNodes().isEmpty() }
    }

    @Test
    fun readingScoresFitsTheOrdinaryHeapAndPlayStartsPromptly() {
        assumeTrue("no band SoundFont", BandSoundFontFile.bundled(rule.activity) || BandSoundFontFile.sideloaded(rule.activity) != null)
        val xml = scoreXml()
        val what = "Old Hundredth x$TIMES (${xml.length shr 10} KB)"
        val file = File(rule.activity.cacheDir, "Memory Probe.musicxml").apply { writeText(xml) }
        gc()
        val base = used()
        val baseNative = Debug.getNativeHeapAllocatedSize()
        resetPeaks()
        sampler.start()

        // Three opens in a row, each left as soon as it shows: no SoundFont, the ordinary heap is enough.
        rule.runOnUiThread { vm.openScoreUri(android.net.Uri.fromFile(file)) }
        rule.waitUntil(30_000) { vm.scoreController?.state?.value?.loaded == true && vm.scoreController!!.renders.value > 0 }
        var soundFontWhileFlipping = vm.scoreController!!.state.value.bandSoundFont
        rule.runOnUiThread { vm.home() }
        rule.waitForIdle()
        repeat(2) {
            openFromHome()
            soundFontWhileFlipping = soundFontWhileFlipping || vm.scoreController!!.state.value.bandSoundFont
            leave()
        }
        val flipHeap = peakHeap
        val flipNative = peakNative

        // Open and play at once: the SoundFont loads for this Play, which waits for it.
        resetPeaks()
        openFromHome()
        val playAtOnceMs = playOnce()
        leave()

        // Left after playing: the synth and its SoundFont go with the screen.
        Thread.sleep(300)
        gc()
        val retained = used()

        // Open and read a moment: the SoundFont is loaded meanwhile, so Play starts at once.
        resetPeaks()
        openFromHome()
        rule.waitUntil(10_000) { vm.scoreController!!.state.value.bandSoundFont }
        Thread.sleep(500)
        val playAfterReadingMs = playOnce()
        val playHeap = peakHeap
        val playNative = peakNative
        sampling = false
        val limit = Runtime.getRuntime().maxMemory()
        android.util.Log.i("ScoreMemoryTest", ("%s: base heap %d MB, native %d MB; three opens left at once peak at heap %d MB, " +
            "native %d MB (band SoundFont loaded: %b); Play at once %d ms; left, %d MB of heap stay; " +
            "Play after reading %d ms, peak heap %d MB, native %d MB; heap limit %d MB")
            .format(what, base shr 20, baseNative shr 20, flipHeap shr 20, flipNative shr 20, soundFontWhileFlipping, playAtOnceMs,
                retained shr 20, playAfterReadingMs, playHeap shr 20, playNative shr 20, limit shr 20))
        assertTrue("no band SoundFont for a score left at once", !soundFontWhileFlipping)
        // Peaks count garbage not yet collected too (150-180 MB here); one loaded SoundFont alone adds some 220 MB,
        // and before, three opens held two or three of them (540 MB of the 576 MB limit).
        assertTrue("three opens peak ${(flipHeap - base) shr 20} MB over the heap in use before", flipHeap - base < 220L shl 20)
        assertTrue("Play at once took $playAtOnceMs ms", playAtOnceMs < 2_000)
        assertTrue("a played score left behind keeps ${(retained - base) shr 20} MB of heap (the SoundFont is about 220 MB)",
            retained - base < 64L shl 20)
        assertTrue("Play after reading took $playAfterReadingMs ms", playAfterReadingMs < 150)
    }

    private companion object {
        const val TIMES = 16
    }
}
