package no.brasscribe.play

import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Collections
import java.util.concurrent.Executors

/** What a worker reports is shown on the caller's thread, in order, and never after the work has ended. */
class ReportedHereTest {
    private val main = Executors.newSingleThreadExecutor { Thread(it, "the main thread") }
    private val worker = Executors.newSingleThreadExecutor { Thread(it, "a worker") }

    /** The thread's own name (a coroutine being debugged adds its name to it). */
    private fun here() = Thread.currentThread().name.substringBefore(" @")

    @After
    fun stop() {
        main.shutdownNow()
        worker.shutdownNow()
    }

    @Test
    fun aReportFromAWorkerIsShownOnTheCallersThread() = runBlocking {
        val shownOn = Collections.synchronizedList(mutableListOf<String>())
        val shown = Collections.synchronizedList(mutableListOf<Int>())
        var reportedOn = ""
        val result = withContext(main.asCoroutineDispatcher()) {
            reportedHere<Int, String>(worker.asCoroutineDispatcher(), show = { shown += it; shownOn += here() }) { report ->
                reportedOn = here()
                for (i in 1..200) {
                    report(i)
                    Thread.sleep(1)
                }
                "done"
            }
        }
        assertEquals("done", result)
        assertEquals("a worker", reportedOn)
        assertTrue("something was shown", shown.isNotEmpty())
        assertEquals(setOf("the main thread"), shownOn.toSet())
        assertEquals("in the order it was reported", shown.sorted(), shown.toList())
    }

    @Test
    fun nothingIsShownOnceTheWorkHasEnded() = runBlocking {
        var value: Int? = null
        withContext(main.asCoroutineDispatcher()) {
            repeat(200) {
                reportedHere<Int, Unit>(worker.asCoroutineDispatcher(), show = { value = it }) { report -> report(1); report(2) }
                // What the caller sets after the work stays: no report comes in behind it.
                value = null
                withContext(worker.asCoroutineDispatcher()) { }
                assertEquals(null, value)
            }
        }
    }

    @Test
    fun aFailureOfTheWorkReachesTheCaller() {
        val failure = runCatching {
            runBlocking(main.asCoroutineDispatcher()) {
                reportedHere<Int, Unit>(worker.asCoroutineDispatcher(), show = { }) { report -> report(1); error("unreadable") }
            }
        }.exceptionOrNull()
        assertEquals("unreadable", failure?.message)
    }
}
