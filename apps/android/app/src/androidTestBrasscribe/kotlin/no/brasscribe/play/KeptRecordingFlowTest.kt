package no.brasscribe.play

import android.net.Uri
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.brasscribe.play.engine.Profile
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A recording whose score could not be made (no computer here) is kept in Your scores: it is listed by a new
 * process, its row opens What is this? with it, and Delete removes its file from the phone.
 */
@RunWith(AndroidJUnit4::class)
class KeptRecordingFlowTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private val vm get() = ViewModelProvider(rule.activity)[PlayViewModel::class.java]
    private val container get() = (rule.activity.application as PlayApplication).container

    @Before
    fun setUp() {
        // No computer: a band score sent to it cannot be made.
        rule.activity.getSharedPreferences("engine", 0).edit().clear().commit()
        if (rule.onAllNodesWithText("Get started").fetchSemanticsNodes().isNotEmpty()) rule.onAllNodesWithText("Get started")[0].performClick()
        if (rule.onAllNodesWithTag("seat-skip").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("seat-skip").performClick()
        rule.runOnUiThread { container.fixtureSource = null; vm.keptRecordings.value.forEach(vm::deleteKept); vm.home() }
        rule.waitUntil(10_000) { vm.keptRecordings.value.isEmpty() }
    }

    @After
    fun tearDown() {
        rule.runOnUiThread { vm.keptRecordings.value.forEach(vm::deleteKept); vm.home() }
    }

    private fun recording(): File {
        val rate = 22_050
        val samples = ShortArray(rate * 2) { i -> (Math.sin(2 * Math.PI * 233.1 * i / rate) * 9000).toInt().toShort() }
        val data = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN).also { b -> samples.forEach(b::putShort) }.array()
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
            .putInt(rate).putInt(rate * 2).putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size).array()
        return File(rule.activity.cacheDir, "Band practice.wav").apply { writeBytes(header + data) }
    }

    @Test
    fun aRecordingWhoseScoreCouldNotBeMadeIsKeptInYourScoresAndDeletedWithItsFile() {
        rule.runOnUiThread { vm.importUri(Uri.fromFile(recording())) }
        rule.waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        val take = vm.source.value!!.file!!
        rule.runOnUiThread { vm.chooseProfile(Profile.BRASS_BAND); vm.where.value = Where.COMPANION; vm.startTranscription() }
        rule.waitUntil(20_000) { vm.screen.value.last() == Screen.PROBLEM && vm.keptRecordings.value.size == 1 }
        val kept = vm.keptRecordings.value.single()
        assertEquals("Band practice.wav", kept.title)
        assertEquals(SourceKind.FILE, kept.kind)
        assertEquals(2.0, kept.seconds, 0.1)
        // Moved out of the cache, out of the backup, and still the recording in hand.
        assertFalse(take.exists())
        assertEquals(File(rule.activity.noBackupFilesDir, "kept-recordings").canonicalFile, kept.file.canonicalFile.parentFile!!.parentFile)
        rule.waitUntil(5_000) { vm.source.value?.file == kept.file }
        rule.onAllNodesWithText("Your recording is kept in Your scores. You can try again now or later.").fetchSemanticsNodes().let { assertTrue(it.isNotEmpty()) }

        // A new process lists it, and leaves its file alone.
        lateinit var restored: PlayViewModel
        rule.runOnUiThread { restored = PlayViewModel(rule.activity.application, SavedStateHandle()) }
        rule.waitUntil(10_000) { restored.keptRecordings.value.map { it.id } == listOf(kept.id) }
        Thread.sleep(1000)
        assertTrue(kept.file.isFile)

        // On Home it is a row of Your scores: the name, the length and "Not written down yet".
        rule.runOnUiThread { vm.home() }
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("kept-${kept.id}").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(rule.onAllNodesWithText("0:02 · Not written down yet", substring = true).fetchSemanticsNodes().isNotEmpty())
        assertTrue("named without the file's extension", rule.onAllNodesWithText("Band practice").fetchSemanticsNodes().isNotEmpty())
        // A tap opens What is this? with it, read where it is.
        rule.onNodeWithTag("kept-${kept.id}").performScrollTo().performClick()
        rule.waitUntil(10_000) { vm.screen.value.last() == Screen.PROFILE }
        assertEquals(kept.file, vm.source.value?.file)
        assertNotNull("decoded for the phone", vm.source.value?.audio)

        // Delete asks first, and removes the file.
        rule.runOnUiThread { vm.home() }
        rule.waitUntil(5_000) { rule.onAllNodesWithTag("kept-${kept.id}").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithContentDescription(rule.activity.getString(R.string.score_options, "Band practice")).performScrollTo().performClick()
        rule.onNodeWithTag("kept-delete").performClick()
        rule.onNodeWithTag("kept-delete-confirm").performClick()
        rule.waitUntil(5_000) { vm.keptRecordings.value.isEmpty() }
        assertFalse(kept.file.exists())
        assertTrue(rule.onAllNodesWithTag("kept-${kept.id}").fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun stopKeepsTheRecordingAndAScoreMadeFromItTakesItOutOfTheList() {
        rule.runOnUiThread { vm.importUri(Uri.fromFile(recording())) }
        rule.waitUntil(20_000) { vm.screen.value.last() == Screen.PROFILE }
        // A computer that takes its time: Stop while it is being made.
        val assets = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets
        rule.runOnUiThread {
            container.fixtureSource = no.brasscribe.play.engine.FixtureSource { name -> runCatching { assets.open("old-hundredth/$name").use { it.readBytes() } }.getOrNull() }
            vm.chooseProfile(Profile.BRASS_BAND); vm.where.value = Where.COMPANION; vm.startTranscription()
        }
        rule.waitUntil(10_000) { vm.screen.value.last() == Screen.TRANSCRIBE && vm.transcribe.value.running }
        rule.runOnUiThread { vm.back() }
        rule.waitUntil(10_000) { vm.keptRecordings.value.size == 1 }
        val kept = vm.keptRecordings.value.single()
        rule.waitUntil(5_000) { vm.source.value?.file == kept.file }
        // Started again from What is this?, the score is made: the recording leaves Your scores.
        rule.runOnUiThread { vm.startTranscription() }
        rule.waitUntil(60_000) { vm.screen.value.last() == Screen.REVIEW }
        rule.waitUntil(5_000) { vm.keptRecordings.value.isEmpty() }
        // Its file stays while it is the recording in hand, and goes once another takes its place.
        assertTrue(kept.file.isFile)
        rule.runOnUiThread { vm.setSource(Source("Another", SourceKind.FILE, 1.0)) }
        rule.waitUntil(5_000) { !kept.file.exists() }
        rule.runOnUiThread { vm.scores.value.forEach(vm::deleteEntry); container.fixtureSource = null }
    }
}
