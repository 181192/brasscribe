package no.brasscribe.play.connection

import no.brasscribe.play.AppContainer
import no.brasscribe.play.engine.EngineException
import no.brasscribe.play.engine.InterfaceMatch
import no.brasscribe.play.engine.KtorEngineApi
import no.brasscribe.play.engine.LocalHosts

/**
 * [ConnectionHost] over the app's settings, encrypted credentials and the engine API. The heartbeat
 * reuses the app's engine client for the current address; another address gets a short-lived client.
 */
class EngineConnection(private val container: AppContainer) : ConnectionHost {
    private val settings get() = container.settings

    override fun target(): Target? {
        if (!settings.paired || container.usingFixture) return null
        return Target(settings.serverId ?: CredentialStore.LEGACY_ID, settings.serverName, settings.url)
    }

    override fun networkOpen(): Boolean = container.computerInReach()

    override suspend fun check(url: String): Check {
        val current = url == settings.url
        val shared = if (current) container.engine() as? KtorEngineApi else null
        val client = shared ?: container.newEngineClient(url, settings.token)
        try {
            // First of all, and at every heartbeat: an engine with another interface version is asked nothing else.
            val health = client.health()
            val match = InterfaceMatch.of(health.interfaceVersion)
            if (match != InterfaceMatch.MATCH) return Check.Mismatch(match)
            // A token from an earlier version has no server id yet: ask the engine for it once.
            if (settings.serverId == null) {
                val h = health
                settings.serverId = h.serverId
                settings.serverName = h.serverName
                container.credentials.adopt(h.serverId, h.serverName)
            }
            if (settings.token == null) {
                // A trusted client (the emulator's host alias, loopback) has no credential: health is the heartbeat.
                // Anywhere else no credential means pairing again (a restored backup, a reset Keystore), not "connected".
                val h = health
                return noCredential(h.authRequired, LocalHosts.hostOf(url)?.let(LocalHosts::isTrusted) == true, h.serverId == settings.serverId)
            }
            return Check.Ok(client.thisDevice().rotateAfter)
        } catch (e: EngineException) {
            android.util.Log.i("BrasscribePlay", "heartbeat to $url: ${e.status}")
            return when (e.status) {
                0 -> Check.Unreachable
                401 -> if (sameServer(client)) Check.Unauthorized else Check.Unreachable
                // 404: a trusted client with no device entry. Any other answer means the engine is there.
                else -> Check.Ok()
            }
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            android.util.Log.i("BrasscribePlay", "heartbeat to $url failed: $e")
            return Check.Unreachable
        } finally {
            if (client !== shared) client.close()
        }
    }

    companion object {
        /**
         * The heartbeat's answer when this phone holds no credential: connected only where the engine lets it
         * in without one; else pair again, when it is the paired engine that asks for one.
         */
        fun noCredential(authRequired: Boolean, trustedHost: Boolean, sameServer: Boolean): Check = when {
            !authRequired && trustedHost -> Check.Ok()
            sameServer -> Check.Unauthorized
            else -> Check.Unreachable
        }
    }

    /** A 401 counts only from the engine the credential belongs to, not from another one at the same address. */
    private suspend fun sameServer(client: KtorEngineApi): Boolean =
        runCatching { client.health().serverId == settings.serverId }.getOrDefault(false)

    override suspend fun find(serverId: String): String? =
        if (serverId == CredentialStore.LEGACY_ID) null else container.reconnectDiscovery.find(serverId)

    override fun moved(url: String) {
        settings.url = url
        settings.credential?.let { container.credentials.put(it.copy(lastAddress = url)) }
    }

    override suspend fun rotate() {
        val c = settings.credential ?: return
        val client = container.newEngineClient(settings.url, c.token)
        try {
            val r = client.rotateToken()
            // Stored before it is used: the old token keeps working until the new one is first seen.
            container.credentials.put(c.copy(token = r.token, deviceId = r.deviceId))
        } finally {
            client.close()
        }
    }
}
