package no.brasscribe.play.connection

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ConnectionMonitorTest {
    private val name = "Brasscribe on Mac"

    /** A scripted engine: [answer] decides each check by address; every call is recorded. */
    private class FakeHost(var target: Target?, var answer: (String) -> Check) : ConnectionHost {
        val checks = mutableListOf<String>()
        var findResult: String? = null
        var finds = 0
        var rotations = 0
        override fun target() = target
        override suspend fun check(url: String): Check { checks += url; return answer(url) }
        override suspend fun find(serverId: String): String? { finds++; return findResult }
        override fun moved(url: String) { target = target?.copy(url = url) }
        override suspend fun rotate() { rotations++ }
    }

    private fun TestScope.monitor(host: FakeHost) =
        ConnectionMonitor(backgroundScope, host, now = { testScheduler.currentTime })

    @Test
    fun noComputerPairedIsOffline() = runTest {
        val m = monitor(FakeHost(null) { Check.Ok() })
        m.start(); runCurrent()
        assertEquals(ConnectionState.Offline(paired = false), m.state.value)
    }

    @Test
    fun heartbeatEveryTwentySecondsWhileConnected() = runTest {
        val host = FakeHost(Target("s1", name, "http://a")) { Check.Ok() }
        val m = monitor(host)
        m.start(); runCurrent()
        assertEquals(ConnectionState.Connected(name), m.state.value)
        advanceTimeBy(60_001)
        assertEquals(4, host.checks.size)
        m.stop()
        advanceTimeBy(60_000)
        assertEquals("stopped in the background", 4, host.checks.size)
    }

    @Test
    fun oneMissedHeartbeatKeepsConnectedTheSecondSaysLookingFor() = runTest {
        var up = true
        val host = FakeHost(Target("s1", name, "http://a")) { if (up) Check.Ok() else Check.Unreachable }
        val m = monitor(host)
        m.start(); runCurrent()
        up = false
        advanceTimeBy(20_001)
        assertEquals(ConnectionState.Connected(name), m.state.value)
        advanceTimeBy(2_001)
        assertEquals(ConnectionState.Reconnecting(name), m.state.value)
        up = true
        advanceTimeBy(4_001)
        assertEquals(ConnectionState.Connected(name), m.state.value)
    }

    @Test
    fun backsOffTwoFourEightUpToThirtyThenGivesUpAfterTwoMinutes() = runTest {
        val host = FakeHost(Target("s1", name, "http://a")) { Check.Unreachable }
        val m = monitor(host)
        m.start(); runCurrent()
        val times = mutableListOf<Long>()
        var seen = 0
        while (m.running && testScheduler.currentTime < 200_000) {
            advanceTimeBy(500)
            if (host.checks.size > seen) { seen = host.checks.size; times += testScheduler.currentTime }
        }
        val gaps = times.zipWithNext { a, b -> ((b - a + 499) / 1000) }
        assertEquals(listOf(2L, 4L, 8L, 16L, 30L, 30L, 30L), gaps.take(7))
        assertEquals(ConnectionState.Offline(paired = true), m.state.value)
        assertTrue("gave up near two minutes, at ${testScheduler.currentTime}", testScheduler.currentTime in 120_000..152_000)
        assertTrue("looked for the server id each time", host.finds >= 7)
    }

    @Test
    fun findsTheEngineAtANewAddressByItsServerId() = runTest {
        val host = FakeHost(Target("s1", name, "http://old")) { url -> if (url == "http://new") Check.Ok() else Check.Unreachable }
        host.findResult = "http://new"
        val m = monitor(host)
        m.start(); runCurrent()
        assertEquals(ConnectionState.Connected(name), m.state.value)
        assertEquals("http://new", host.target!!.url)
        assertEquals(listOf("http://old", "http://new"), host.checks)
    }

    @Test
    fun only401MeansPairAgainAndItStopsTheHeartbeat() = runTest {
        val host = FakeHost(Target("s1", name, "http://a")) { Check.Unauthorized }
        val m = monitor(host)
        m.start(); runCurrent()
        assertEquals(ConnectionState.NeedsPairing(name), m.state.value)
        assertFalse(m.running)
        m.start(); advanceTimeBy(60_000)
        assertEquals("foreground again does not hammer a revoked credential", 1, host.checks.size)
        host.answer = { Check.Ok() }
        m.retry(); runCurrent()
        assertEquals(ConnectionState.Connected(name), m.state.value)
    }

    @Test
    fun connectAfterGivingUpSaysLookingForAtOnce() = runTest {
        val host = FakeHost(Target("s1", name, "http://a")) { Check.Unreachable }
        val m = monitor(host)
        m.start(); advanceTimeBy(200_000)
        assertEquals(ConnectionState.Offline(paired = true), m.state.value)
        m.retry()
        assertEquals(ConnectionState.Reconnecting(name), m.state.value)
    }

    @Test
    fun networkChangeRetriesOnlyWhenNotConnected() = runTest {
        val host = FakeHost(Target("s1", name, "http://a")) { Check.Ok() }
        val m = monitor(host)
        m.start(); runCurrent()
        m.networkChanged(); runCurrent()
        assertEquals(1, host.checks.size)
        host.answer = { Check.Unreachable }
        advanceTimeBy(22_001)
        assertEquals(ConnectionState.Reconnecting(name), m.state.value)
        host.answer = { Check.Ok() }
        m.networkChanged(); runCurrent()
        assertEquals(ConnectionState.Connected(name), m.state.value)
    }

    @Test
    fun rotatesOnceWhenDue() = runTest {
        val host = FakeHost(Target("s1", name, "http://a")) { Check.Ok(rotateAfter = "1970-01-01T00:00:00+00:00") }
        val m = monitor(host)
        m.start(); advanceTimeBy(100_000)
        assertEquals("a failed or slow rotation is not retried every heartbeat", 1, host.rotations)
    }

    @Test
    fun rotateDueReadsTheEnginesTimestamps() {
        val at = java.time.OffsetDateTime.parse("2026-10-27T09:00:00+00:00").toInstant().toEpochMilli()
        assertFalse(ConnectionMonitor.rotateDue("2026-10-27T09:00:00+00:00", at - 1))
        assertTrue(ConnectionMonitor.rotateDue("2026-10-27T09:00:00+00:00", at))
        assertTrue(ConnectionMonitor.rotateDue("2026-10-27T09:00:00Z", at + 1))
        assertFalse(ConnectionMonitor.rotateDue("", at))
        assertFalse(ConnectionMonitor.rotateDue("not a date", at))
        assertFalse(ConnectionMonitor.rotateDue(null, at))
    }
}
