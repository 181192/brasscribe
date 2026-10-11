package no.brasscribe.play

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress
import java.util.concurrent.Executors

/**
 * Finds engines on the local network that advertise `_brasscribe._tcp` (`brasscribe serve --lan`).
 * Discovery only suggests addresses; the engine still requires pairing. mDNS does not cross the
 * emulator's NAT, so on an emulator the list stays empty and 10.0.2.2 remains the way in.
 */
class EngineDiscovery(private val context: Context) {
    /** [id] is the engine's server id from the TXT record (null for engines that do not advertise one). */
    data class Found(val name: String, val url: String, val id: String? = null)

    private val nsd = context.getSystemService(NsdManager::class.java)
    private val executor = Executors.newSingleThreadExecutor()
    private val _engines = MutableStateFlow<List<Found>>(emptyList())
    val engines: StateFlow<List<Found>> = _engines.asStateFlow()

    private val found = linkedMapOf<String, Found>()
    private val callbacks = mutableMapOf<String, NsdManager.ServiceInfoCallback>()
    private var listener: NsdManager.DiscoveryListener? = null

    @Synchronized
    fun start() {
        // Until the player allows the local network (Android 17) there is nothing to look on.
        if (listener != null || !LocalNetwork.allowed(context)) return
        val l = object : NsdManager.DiscoveryListener {
            override fun onServiceFound(info: NsdServiceInfo) = watch(info)
            override fun onServiceLost(info: NsdServiceInfo) = lost(info.serviceName)
            override fun onDiscoveryStarted(serviceType: String) = Unit
            override fun onDiscoveryStopped(serviceType: String) = Unit
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) = synchronized(this@EngineDiscovery) { listener = null }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
        }
        listener = l
        runCatching { nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, l) }.onFailure { listener = null }
    }

    @Synchronized
    fun stop() {
        listener?.let { runCatching { nsd.stopServiceDiscovery(it) } }
        listener = null
        callbacks.values.forEach { runCatching { nsd.unregisterServiceInfoCallback(it) } }
        callbacks.clear()
        found.clear()
        _engines.value = emptyList()
    }

    @Synchronized
    private fun watch(info: NsdServiceInfo) {
        val name = info.serviceName
        if (name in callbacks) return
        val cb = object : NsdManager.ServiceInfoCallback {
            override fun onServiceUpdated(info: NsdServiceInfo) = put(name, engineUrl(info.hostAddresses, info.port), serverId(info))
            override fun onServiceLost() = lost(name)
            override fun onServiceInfoCallbackRegistrationFailed(errorCode: Int) = synchronized(this@EngineDiscovery) { callbacks.remove(name); Unit }
            override fun onServiceInfoCallbackUnregistered() = Unit
        }
        callbacks[name] = cb
        nsd.registerServiceInfoCallback(info, executor, cb)
    }

    @Synchronized
    private fun put(name: String, url: String?, id: String?) {
        if (listener == null) return
        if (url == null) found.remove(name) else found[name] = Found(name, url, id)
        _engines.value = found.values.sortedBy { it.name }
    }

    @Synchronized
    private fun lost(name: String) {
        callbacks.remove(name)?.let { runCatching { nsd.unregisterServiceInfoCallback(it) } }
        found.remove(name)
        _engines.value = found.values.sortedBy { it.name }
    }

    private fun serverId(info: NsdServiceInfo): String? =
        runCatching { info.attributes["id"]?.decodeToString()?.takeIf { it.isNotBlank() } }.getOrNull()

    /**
     * The address the engine with [serverId] advertises, waiting at most [timeoutMs]. Uses its own
     * discovery session, so a screen that starts and stops [engines] does not end it.
     */
    suspend fun find(serverId: String, timeoutMs: Long = 6_000): String? {
        // Several finds at once (the heartbeat and a pairing link) share the session: the last one out stops it.
        finders.acquire()
        return try {
            kotlinx.coroutines.withTimeoutOrNull(timeoutMs) {
                engines.first { list -> list.any { it.id == serverId } }.first { it.id == serverId }.url
            }
        } finally {
            finders.release()
        }
    }

    private val finders = SharedSession(::start, ::stop)

    /** Starts on the first [acquire] and stops on the matching last [release]. */
    internal class SharedSession(private val start: () -> Unit, private val stop: () -> Unit) {
        private var users = 0

        @Synchronized
        fun acquire() { if (users++ == 0) start() }

        @Synchronized
        fun release() { if (users > 0 && --users == 0) stop() }
    }

    companion object {
        const val SERVICE_TYPE = "_brasscribe._tcp"

        /**
         * Base URL for a resolved service. Engines also advertise VPN and virtual-adapter addresses, so a private
         * (RFC 1918) IPv4 wins, then any IPv4, then a routable IPv6 (link-local needs a scope a URL can't carry).
         */
        fun engineUrl(addresses: List<InetAddress>, port: Int): String? {
            if (port <= 0) return null
            val v4 = addresses.filterIsInstance<Inet4Address>()
            val a = v4.firstOrNull { it.isSiteLocalAddress } ?: v4.firstOrNull()
                ?: addresses.firstOrNull { it is Inet6Address && !it.isLinkLocalAddress }
            return when (a) {
                is Inet4Address -> "http://${a.hostAddress}:$port"
                is Inet6Address -> "http://[${a.hostAddress?.substringBefore('%')}]:$port"
                else -> null
            }
        }
    }
}
