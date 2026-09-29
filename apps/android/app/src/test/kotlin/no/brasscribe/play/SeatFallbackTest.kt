package no.brasscribe.play

import kotlinx.coroutines.runBlocking
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.engine.EngineException
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.Job
import no.brasscribe.play.engine.JobCreate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/** An engine from before the trumpet seat: it refuses seats it doesn't know with a 422 and no refusal code. */
private class OldEngine(private val known: Set<String>, val seen: MutableList<String?> = mutableListOf()) :
    EngineApi by FixtureEngineApi({ null }) {
    override suspend fun createJob(request: JobCreate): Job {
        seen += request.seat
        if (request.seat != null && request.seat !in known) throw EngineException(422, "seat: input should be one of …")
        return Job("j", request.profile, no.brasscribe.play.engine.JobStatus.QUEUED, 0.0, emptyList())
    }
}

class SeatFallbackTest {
    @Test
    fun anOlderEngineWritesATrumpetsPartAsTheSoloCornet() = runBlocking {
        val old = OldEngine(setOf("solo-cornet"))
        val (_, fellBack) = old.createJobForSeat(JobCreate(seat = "trumpet", lead = "seat"))
        assertEquals(true, fellBack)
        assertEquals(listOf("trumpet", "solo-cornet"), old.seen)
    }

    @Test
    fun aKnownSeatGoesThroughOnce() = runBlocking {
        val new = OldEngine(setOf("trumpet"))
        assertEquals(false, new.createJobForSeat(JobCreate(seat = "trumpet")).second)
        assertEquals(listOf("trumpet"), new.seen)
    }

    @Test
    fun otherRefusalsAreNotRetried() {
        val old = OldEngine(emptySet())
        assertThrows(EngineException::class.java) { runBlocking { old.createJobForSeat(JobCreate(seat = "euphonium")) } }
        assertEquals(listOf("euphonium"), old.seen)
    }
}
