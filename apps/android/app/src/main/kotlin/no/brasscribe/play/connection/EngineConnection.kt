package no.brasscribe.play.connection

import no.brasscribe.play.AppContainer
import no.kalli.scribe.engine.EngineException
import no.kalli.scribe.engine.Health
import no.kalli.scribe.engine.InterfaceMatch
import no.kalli.scribe.engine.InterfaceMismatchException
import no.kalli.scribe.engine.KtorEngineApi
import no.kalli.scribe.engine.LocalHosts

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
        val shared = if (url == settings.url) container.engine() as? KtorEngineApi else null
        val client = shared ?: container.newEngineClient(url, settings.token)
        try {
            var healthAsked: Health? = null

            /** The engine's health says it is the paired one, with this app's interface version: null. Else what the check answers. */
            suspend fun byHealth(): Check? {
                val health = healthOf(client) ?: return Check.Unreachable
                // A token from an earlier version has no server id yet: the engine says it once.
                if (settings.serverId == null) {
                    settings.serverId = health.serverId
                    settings.serverName = health.serverName
                    container.credentials.adopt(health.serverId, health.serverName)
                }
                // Another engine at the address is not the paired one, whatever its version: ours is looked for.
                if (health.serverId != settings.serverId) return notOurs(client)
                InterfaceMatch.of(health.interfaceVersion).takeIf { it != InterfaceMatch.MATCH }?.let { return Check.Mismatch(it) }
                healthAsked = health
                return null
            }

            // One request when paired: the phone's own entry says which engine answers and its interface version.
            // Health is the heartbeat without a credential, for a token from before engines had an id, and for an
            // engine already known to have another interface version (it is asked nothing else).
            val knownOther = client.interfaceMatch.let { it != null && it != InterfaceMatch.MATCH }
            if (settings.token == null || settings.serverId == null || knownOther) byHealth()?.let { return it }
            if (settings.token == null) {
                // A trusted client (the emulator's host alias, loopback) has no credential: health is the heartbeat.
                // Anywhere else no credential means pairing again (a restored backup, a reset Keystore), not "connected".
                return noCredential(healthAsked!!.authRequired, LocalHosts.hostOf(url)?.let(LocalHosts::isTrusted) == true, sameServer = true)
            }
            val me = try {
                client.thisDevice()
            } catch (e: EngineException) {
                android.util.Log.i("BrasscribePlay", "heartbeat to $url: ${e.status}")
                if (e.status == 0) return Check.Unreachable
                // The engine answered, and not with this phone's entry. What that means is its own engine's to say:
                // its health first (which engine it is, and its interface version), then the answer itself.
                if (healthAsked == null) byHealth()?.let { return it }
                return when (e.status) {
                    // The paired engine no longer knows this phone.
                    401 -> Check.Unauthorized
                    // A client the engine lets in without a device entry (a trusted address).
                    404 -> Check.Ok()
                    // It is there and cannot answer: not connected until it can.
                    else -> Check.Unreachable
                }
            }
            if (me.serverId != settings.serverId) return notOurs(client)
            InterfaceMatch.of(me.interfaceVersion).takeIf { it != InterfaceMatch.MATCH }?.let { return Check.Mismatch(it) }
            return Check.Ok(me.rotateAfter)
        } catch (e: InterfaceMismatchException) {
            // An answer that could not be read in full, from an engine with another interface version: the paired one's
            // is "update"; another engine's at the address is not ours to update.
            return if (e.serverId != null && e.serverId != settings.serverId) notOurs(client) else Check.Mismatch(e.update)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            android.util.Log.i("BrasscribePlay", "heartbeat to $url failed: $e")
            return Check.Unreachable
        } finally {
            if (client !== shared) client.close()
        }
    }

    /** Another engine answers at the address: what it said of itself is not kept for the paired one, which is looked for. */
    private fun notOurs(client: KtorEngineApi): Check {
        client.forget()
        return Check.Unreachable
    }

    /**
     * The engine's health, or null when it gives none (it cannot be reached, or answers with an error): an engine
     * that does not say who it is never counts as connected. An answer this app cannot read in full, from an engine
     * with another interface version, is that engine's [InterfaceMismatchException].
     */
    private suspend fun healthOf(client: KtorEngineApi): Health? = try {
        client.health()
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (e: InterfaceMismatchException) {
        throw e
    } catch (e: Exception) {
        android.util.Log.i("BrasscribePlay", "health: $e")
        null
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
