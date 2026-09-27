package no.brasscribe.play.connection

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.OffsetDateTime

/** The four connection states every Play app shows (the same words on all platforms). */
sealed interface ConnectionState {
    /** The last heartbeat was answered. */
    data class Connected(val serverName: String) : ConnectionState
    /** Heartbeats fail; trying the last address, then looking for the server id on the network. */
    data class Reconnecting(val serverName: String) : ConnectionState
    /** No computer paired ([paired] false), or it could not be found for two minutes. */
    data class Offline(val paired: Boolean) : ConnectionState
    /** The computer answered 401 to the stored credential: only pairing again helps. */
    data class NeedsPairing(val serverName: String) : ConnectionState
}

/** The computer this phone talks to. [url] is the last address that answered. */
data class Target(val serverId: String, val serverName: String, val url: String)

sealed interface Check {
    /** Answered. [rotateAfter] is set when the engine told us when to rotate this device's token. */
    data class Ok(val rotateAfter: String? = null) : Check
    data object Unauthorized : Check
    data object Unreachable : Check
}

/** What the monitor needs from the app: the stored target and the network. */
interface ConnectionHost {
    fun target(): Target?
    /** GET /v1/devices/me at [url] with the stored credential. */
    suspend fun check(url: String): Check
    /** The address the engine with [serverId] advertises on the local network now, if it can be found. */
    suspend fun find(serverId: String): String?
    /** The engine answered at a new address: remember it. */
    fun moved(url: String)
    /** Gets a new token (POST /v1/devices/me/rotate) and stores it before it is used. */
    suspend fun rotate()
}

/**
 * Heartbeat and reconnect (contract: presence). While the app is in front and paired it checks the
 * credential every [heartbeatMs]. When that fails it retries the last address, then the address mDNS
 * gives for the server id, backing off 2, 4, 8 … 30 s, and gives up after [giveUpMs]. Only a 401 means
 * pair again. [start] on foreground, [stop] on background, [retry] for "Connect" and network changes.
 */
class ConnectionMonitor(
    private val scope: CoroutineScope,
    private val host: ConnectionHost,
    private val now: () -> Long = System::currentTimeMillis,
    private val heartbeatMs: Long = 20_000,
    private val giveUpMs: Long = 120_000,
) {
    // Until the first check answers, the last known state is kept; at launch that is "connected" when paired.
    private val _state = MutableStateFlow(host.target()?.let { ConnectionState.Connected(it.serverName) } ?: ConnectionState.Offline(paired = false))
    val state: StateFlow<ConnectionState> = _state.asStateFlow()
    private val _lastAnswered = MutableStateFlow<Long?>(null)
    /** When the engine last answered a heartbeat (for the tech details). */
    val lastAnswered: StateFlow<Long?> = _lastAnswered.asStateFlow()
    private var job: Job? = null
    private var lastRotateAttempt: Long? = null

    val running: Boolean get() = job?.isActive == true

    @Synchronized
    fun start() {
        if (job?.isActive == true) return
        // Once given up or told to pair again, only the user (or a network change) starts it again.
        if (_state.value is ConnectionState.NeedsPairing) return
        // Back in front after giving up: one quiet try, so the row does not flip to "looking for" on every
        // return (or rotation). "Connect" and a network change search properly.
        val quiet = _state.value == ConnectionState.Offline(paired = true)
        job = scope.launch { run(quiet) }
    }

    @Synchronized
    fun stop() {
        job?.cancel()
        job = null
    }

    /** Starts over now, whatever the state: after pairing, "Connect", or a network change. */
    @Synchronized
    fun retry() {
        stop()
        val t = host.target()
        _state.value = when {
            t == null -> ConnectionState.Offline(paired = false)
            // "Connect" after giving up: say it is looking.
            _state.value == ConnectionState.Offline(paired = true) -> ConnectionState.Reconnecting(t.serverName)
            // Just paired: the check that follows confirms it.
            _state.value is ConnectionState.Offline || _state.value is ConnectionState.NeedsPairing -> ConnectionState.Connected(t.serverName)
            else -> _state.value
        }
        job = scope.launch { run() }
    }

    /** The network changed: worth trying at once unless all is well or pairing is needed. */
    fun networkChanged() {
        when (_state.value) {
            is ConnectionState.Reconnecting, is ConnectionState.Offline -> if (host.target() != null) retry()
            else -> Unit
        }
    }

    private suspend fun run(quiet: Boolean = false) {
        var failingSince: Long? = null
        var failures = 0
        var backoff = FIRST_BACKOFF_MS
        while (true) {
            val t = host.target()
            if (t == null) {
                _state.value = ConnectionState.Offline(paired = false)
                return
            }
            var r = host.check(t.url)
            if (r == Check.Unreachable) {
                val found = host.find(t.serverId)
                if (found != null && found != t.url) {
                    val again = host.check(found)
                    if (again != Check.Unreachable) {
                        host.moved(found)
                        r = again
                    }
                }
            }
            // A check can learn the engine's name (a token from an earlier version had none).
            val name = host.target()?.serverName ?: t.serverName
            when (r) {
                is Check.Ok -> {
                    _state.value = ConnectionState.Connected(name)
                    _lastAnswered.value = now()
                    failingSince = null
                    failures = 0
                    backoff = FIRST_BACKOFF_MS
                    if (rotateDue(r.rotateAfter, now()) && lastRotateAttempt.let { it == null || now() - it > ROTATE_RETRY_MS }) {
                        lastRotateAttempt = now()
                        runCatching { host.rotate() }
                    }
                    delay(heartbeatMs)
                }
                Check.Unauthorized -> {
                    _state.value = ConnectionState.NeedsPairing(name)
                    return
                }
                Check.Unreachable -> {
                    if (quiet) return
                    val since = failingSince ?: now().also { failingSince = it }
                    if (now() - since >= giveUpMs) {
                        _state.value = ConnectionState.Offline(paired = true)
                        return
                    }
                    // One missed heartbeat is not news (a Wi-Fi hiccup); the second one is.
                    if (++failures >= 2 || _state.value !is ConnectionState.Connected) _state.value = ConnectionState.Reconnecting(t.serverName)
                    delay(backoff)
                    backoff = (backoff * 2).coerceAtMost(MAX_BACKOFF_MS)
                }
            }
        }
    }

    companion object {
        const val FIRST_BACKOFF_MS = 2_000L
        const val MAX_BACKOFF_MS = 30_000L
        /** A failed rotation is tried again at most this often (the old token keeps working meanwhile). */
        const val ROTATE_RETRY_MS = 60 * 60 * 1000L

        /** True when the engine's `rotate_after` (ISO 8601, e.g. "2026-10-27T09:00:00+00:00") has passed. */
        fun rotateDue(rotateAfter: String?, nowMs: Long): Boolean {
            if (rotateAfter.isNullOrBlank()) return false
            val at = runCatching { OffsetDateTime.parse(rotateAfter).toInstant().toEpochMilli() }.getOrNull() ?: return false
            return nowMs >= at
        }
    }
}
