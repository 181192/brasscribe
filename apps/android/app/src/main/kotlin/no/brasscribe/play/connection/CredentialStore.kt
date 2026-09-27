package no.brasscribe.play.connection

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.util.Base64

/** A small string store: SharedPreferences on the phone, a map in tests. */
interface KeyValueStore {
    fun get(key: String): String?
    fun put(key: String, value: String)
    fun remove(key: String)
    fun keys(): Set<String>
}

/** Encrypts the stored credentials. On the phone an AES-GCM key that never leaves the Android Keystore. */
interface SecretCipher {
    fun encrypt(plain: ByteArray): ByteArray
    fun decrypt(sealed: ByteArray): ByteArray
}

/** What this phone keeps per computer it has paired with. */
@Serializable
data class Credential(
    @SerialName("server_id") val serverId: String,
    val token: String,
    @SerialName("device_id") val deviceId: String? = null,
    @SerialName("server_name") val serverName: String = "",
    @SerialName("last_address") val lastAddress: String? = null,
)

/**
 * Per-device credentials keyed by the engine's server id, encrypted with [cipher] before they reach
 * [store]. A record that no longer decrypts (a restored backup, a reset Keystore) is dropped: the phone
 * then pairs again, which is the only way back anyway.
 */
class CredentialStore(private val store: KeyValueStore, private val cipher: SecretCipher) {
    private val cache = HashMap<String, Credential?>()
    private val json = Json { ignoreUnknownKeys = true }

    @Synchronized
    fun get(serverId: String): Credential? = cache.getOrPut(serverId) {
        val sealed = store.get(KEY_PREFIX + serverId) ?: return@getOrPut null
        runCatching {
            json.decodeFromString(Credential.serializer(), cipher.decrypt(Base64.getDecoder().decode(sealed)).decodeToString())
        }.getOrElse {
            store.remove(KEY_PREFIX + serverId)
            null
        }
    }

    @Synchronized
    fun put(c: Credential) {
        val sealed = cipher.encrypt(json.encodeToString(Credential.serializer(), c).encodeToByteArray())
        store.put(KEY_PREFIX + c.serverId, Base64.getEncoder().encodeToString(sealed))
        cache[c.serverId] = c
    }

    @Synchronized
    fun remove(serverId: String) {
        store.remove(KEY_PREFIX + serverId)
        cache[serverId] = null
    }

    fun serverIds(): Set<String> = store.keys().filter { it.startsWith(KEY_PREFIX) }.map { it.removePrefix(KEY_PREFIX) }.toSet()

    /**
     * Moves a token kept in plain text by earlier versions (engine prefs "token") into this store, then
     * deletes the plain copy. Its server id is not known until the engine answers, so it waits under
     * [LEGACY_ID] until [adopt] gives it one. Returns true when something was moved.
     */
    fun migrateLegacy(legacy: KeyValueStore, tokenKey: String = "token", urlKey: String = "url"): Boolean {
        val token = legacy.get(tokenKey)?.takeIf { it.isNotBlank() }
        if (token == null) {
            legacy.remove(tokenKey)
            return false
        }
        if (get(LEGACY_ID) == null) put(Credential(LEGACY_ID, token, lastAddress = legacy.get(urlKey)))
        legacy.remove(tokenKey)
        return true
    }

    /** The engine at the legacy record's address told us its id: the record moves there, unless one exists. */
    @Synchronized
    fun adopt(serverId: String, serverName: String): Credential? {
        get(serverId)?.let { return it }
        val legacy = get(LEGACY_ID) ?: return null
        val moved = legacy.copy(serverId = serverId, serverName = serverName)
        put(moved)
        remove(LEGACY_ID)
        return moved
    }

    companion object {
        const val KEY_PREFIX = "cred."
        const val LEGACY_ID = "legacy"
    }
}
