package no.brasscribe.play

import no.brasscribe.play.connection.CredentialStoreTest.MemoryStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AppearanceTest {
    @Test fun matchSystemFollowsThePhone() {
        assertTrue(Appearance.SYSTEM.isDark(systemDark = true))
        assertFalse(Appearance.SYSTEM.isDark(systemDark = false))
    }

    @Test fun lightAndDarkIgnoreThePhone() {
        for (system in listOf(true, false)) {
            assertFalse(Appearance.LIGHT.isDark(system))
            assertTrue(Appearance.DARK.isDark(system))
        }
    }

    @Test fun missingOrUnknownValueIsMatchSystem() {
        assertEquals(Appearance.SYSTEM, Appearance.fromKey(null))
        assertEquals(Appearance.SYSTEM, Appearance.fromKey("sepia"))
        assertEquals(Appearance.DARK, Appearance.fromKey("dark"))
    }

    @Test fun storeRoundTripsAndDropsTheDefault() {
        val mem = MemoryStore()
        val store = AppearanceStore(mem)
        assertEquals(Appearance.SYSTEM, store.load())
        store.save(Appearance.DARK)
        assertEquals("dark", mem.map[AppearanceStore.KEY])
        assertEquals(Appearance.DARK, AppearanceStore(mem).load())
        store.save(Appearance.LIGHT)
        assertEquals(Appearance.LIGHT, store.load())
        store.save(Appearance.SYSTEM)
        assertNull(mem.map[AppearanceStore.KEY])
        assertEquals(Appearance.SYSTEM, store.load())
    }
}
