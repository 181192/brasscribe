package no.kalli.scribe.play

import kotlinx.coroutines.runBlocking
import no.kalli.scribe.engine.EngineApi
import no.kalli.scribe.engine.FixtureEngineApi
import no.kalli.scribe.engine.Health
import no.kalli.scribe.engine.JobCreate
import no.kalli.scribe.engine.Profile
import org.junit.Assert.assertEquals
import org.junit.Test

/** What can be done about a score the computer wrote before it was fully set up ([writeAgainNow]). */
class WriteAgainTest {
    private class Computer(var notSetUp: List<String> = emptyList(), private val fixture: FixtureEngineApi = FixtureEngineApi({ null })) :
        EngineApi by fixture {
        override suspend fun health(): Health = fixture.health().copy(notSetUp = notSetUp)
    }

    private fun score(jobId: String?, audioId: String?) =
        TranscriptionResult(null, "<x/>", Profile.SOLO, onDevice = false, jobId = jobId, audioId = audioId, beforeSetup = true)

    /** A score saved on the phone and opened again has only its job: the computer says which recording that was. */
    @Test
    fun aReopenedScoreFindsItsRecordingThroughItsJob() = runBlocking {
        val computer = Computer()
        val job = computer.createJob(JobCreate("a1", Profile.SOLO.id))
        val reopened = score(job.id, audioId = null)
        assertEquals(true, reopened.canBeWrittenAgain)
        assertEquals(WriteAgain.OFFER to "a1", writeAgainNow(reopened, computer))
    }

    @Test
    fun whileTheComputerIsNotSetUpNothingIsOffered() = runBlocking {
        val computer = Computer(notSetUp = listOf("band-writer"))
        assertEquals(WriteAgain.NOT_SET_UP to "a1", writeAgainNow(score("j1", "a1"), computer))
    }

    /** The computer no longer knows the job: there is no recording to write down again from, and nothing is promised. */
    @Test
    fun aRecordingTheComputerNoLongerHasIsSaidSo() = runBlocking {
        assertEquals(WriteAgain.RECORDING_GONE to null, writeAgainNow(score("gone", audioId = null), Computer()))
    }

    /** Without a computer to ask, the offer stands with what the app knows. */
    @Test
    fun withoutAComputerToAskTheOfferStands() = runBlocking {
        assertEquals(WriteAgain.OFFER to "a1", writeAgainNow(score("j1", "a1"), engine = null))
    }
}
