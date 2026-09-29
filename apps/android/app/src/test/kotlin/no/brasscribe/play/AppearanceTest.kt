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

    @Test fun pinkFollowsThePhone() {
        assertTrue(Appearance.PINK.isDark(systemDark = true))
        assertFalse(Appearance.PINK.isDark(systemDark = false))
        assertEquals(Appearance.PINK, Appearance.fromKey("pink"))
        assertTrue(Appearance.PINK.isPink)
        assertFalse(Appearance.DARK.isPink)
    }

    @Test fun pinkIsHiddenUntilUnlockedAndTheUnlockIsKept() {
        val mem = MemoryStore()
        val store = AppearanceStore(mem)
        assertFalse(store.pinkUnlocked())
        assertFalse(Appearance.PINK in AppearanceStore.choices(store.pinkUnlocked()))
        store.unlockPink()
        assertEquals("true", mem.map[AppearanceStore.PINK_KEY])
        assertTrue(AppearanceStore(mem).pinkUnlocked())
        assertEquals(Appearance.entries, AppearanceStore.choices(true))
        // Switching it off is choosing another option; Pink stays listed.
        store.save(Appearance.PINK)
        assertEquals(Appearance.PINK, AppearanceStore(mem).load())
        store.save(Appearance.LIGHT)
        assertTrue(store.pinkUnlocked())
    }

    @Test fun storedPinkCountsAsUnlocked() {
        val mem = MemoryStore(linkedMapOf(AppearanceStore.KEY to "pink"))
        assertTrue(AppearanceStore(mem).pinkUnlocked())
        assertEquals(Appearance.PINK, AppearanceStore(mem).load())
    }

    @Test fun fiveQuickTapsUnlockOnce() {
        var t = 0L
        val u = PinkUnlock(unlocked = false) { t }
        repeat(4) { assertFalse(u.tap()); t += 1_000 }
        assertTrue(u.tap())
        assertTrue(u.unlocked)
        // No second confirmation.
        repeat(6) { assertFalse(u.tap()) }
    }

    @Test fun aLongPauseStartsTheCountAgain() {
        var t = 0L
        val u = PinkUnlock(unlocked = false) { t }
        repeat(4) { assertFalse(u.tap()); t += 100 }
        t += PinkUnlock.WINDOW_MS + 1
        repeat(4) { assertFalse(u.tap()); t += PinkUnlock.WINDOW_MS }
        assertTrue(u.tap())
    }

    @Test fun alreadyUnlockedNeverConfirmsAgain() {
        val u = PinkUnlock(unlocked = true) { 0L }
        repeat(10) { assertFalse(u.tap()) }
    }
}
