package no.brasscribe.play.connection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CredentialStoreTest {
    class MemoryStore(val map: MutableMap<String, String> = linkedMapOf()) : KeyValueStore {
        override fun get(key: String) = map[key]
        override fun put(key: String, value: String) { map[key] = value }
        override fun remove(key: String) { map.remove(key) }
        override fun keys() = map.keys.toSet()
    }

    /** Stands in for the Keystore: reversible, and visibly not plain text. */
    class XorCipher(private val k: Byte = 0x5A) : SecretCipher {
        var broken = false
        override fun encrypt(plain: ByteArray) = plain.map { (it.toInt() xor k.toInt()).toByte() }.toByteArray()
        override fun decrypt(sealed: ByteArray): ByteArray {
            if (broken) throw javax.crypto.AEADBadTagException("key gone")
            return encrypt(sealed)
        }
    }

    @Test
    fun storesPerServerIdAndNeverInPlainText() {
        val backing = MemoryStore()
        val store = CredentialStore(backing, XorCipher())
        store.put(Credential("s1", "secret-token-1", "d1", "Brasscribe on Mac", "http://198.51.100.2:8765"))
        store.put(Credential("s2", "secret-token-2"))
        assertFalse(backing.map.values.any { it.contains("secret-token") })
        // A fresh store (the next app start) reads what was written.
        val again = CredentialStore(backing, XorCipher())
        assertEquals("secret-token-1", again.get("s1")!!.token)
        assertEquals("http://198.51.100.2:8765", again.get("s1")!!.lastAddress)
        assertEquals(setOf("s1", "s2"), again.serverIds())
        again.remove("s1")
        assertNull(CredentialStore(backing, XorCipher()).get("s1"))
    }

    @Test
    fun migratesThePlainTokenOnceThenDeletesIt() {
        val legacy = MemoryStore(mutableMapOf("token" to "old-plain", "url" to "http://198.51.100.2:8765", "paired" to "true"))
        val backing = MemoryStore()
        val store = CredentialStore(backing, XorCipher())
        assertTrue(store.migrateLegacy(legacy))
        assertNull("plain copy deleted", legacy.get("token"))
        assertEquals("other settings stay", "http://198.51.100.2:8765", legacy.get("url"))
        assertEquals("old-plain", store.get(CredentialStore.LEGACY_ID)!!.token)
        assertFalse("second start: nothing to move", store.migrateLegacy(legacy))
        assertEquals("old-plain", store.get(CredentialStore.LEGACY_ID)!!.token)
    }

    @Test
    fun theEnginesAnswerGivesTheMigratedTokenItsServerId() {
        val store = CredentialStore(MemoryStore(), XorCipher())
        store.migrateLegacy(MemoryStore(mutableMapOf("token" to "old-plain", "url" to "http://a")))
        val adopted = store.adopt("s1", "Brasscribe on Mac")!!
        assertEquals(Credential("s1", "old-plain", null, "Brasscribe on Mac", "http://a"), adopted)
        assertNull(store.get(CredentialStore.LEGACY_ID))
        assertEquals("old-plain", store.get("s1")!!.token)
    }

    @Test
    fun adoptKeepsANewerCredential() {
        val store = CredentialStore(MemoryStore(), XorCipher())
        store.put(Credential("s1", "newer"))
        store.migrateLegacy(MemoryStore(mutableMapOf("token" to "old-plain")))
        assertEquals("newer", store.adopt("s1", "Brasscribe on Mac")!!.token)
    }

    @Test
    fun aRecordThatNoLongerDecryptsIsDropped() {
        val backing = MemoryStore()
        CredentialStore(backing, XorCipher()).put(Credential("s1", "t"))
        val cipher = XorCipher().apply { broken = true }
        assertNull(CredentialStore(backing, cipher).get("s1"))
        assertTrue(backing.map.isEmpty())
    }

    @Test
    fun aCredentialGoesOnlyToTheHostItWasPairedAt() {
        val c = Credential("s1", "tok", lastAddress = "http://192.0.2.20:8765")
        assertTrue(c.mayBeSentTo("http://192.0.2.20:8765"))
        // The same computer on another port is still that computer.
        assertTrue(c.mayBeSentTo("http://192.0.2.20:9000/"))
        assertFalse(c.mayBeSentTo("http://192.0.2.21:8765"))
        assertFalse(c.mayBeSentTo("http://203.0.113.9:8765"))
        assertFalse(c.mayBeSentTo("not a url"))
        assertFalse("no address recorded", c.copy(lastAddress = null).mayBeSentTo("http://192.0.2.20:8765"))
        assertTrue(Credential("s2", "t", lastAddress = "http://[fd00::5]:8765").mayBeSentTo("http://[FD00::5]:8765"))
    }
}
