package no.brasscribe.play.core

import org.junit.Assert.assertNotNull
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * The tests of the Rust core skip themselves when its host library does not load, so that the suite runs
 * without a build of the core. That must not hide a library that is there: when the folder the tests load
 * from (`jna.library.path`) holds a build of the core, it has to load.
 */
class HostCoreIsUsedTest {
    @Test
    fun aBuiltHostCoreLoads() {
        val dir = System.getProperty("jna.library.path")?.let(::File)
        val built = dir?.listFiles { f -> f.isFile && f.name.endsWith("_ffi." + System.mapLibraryName("x").substringAfterLast('.')) }.orEmpty()
        assumeTrue("no host build of the Rust core in ${dir ?: "jna.library.path (not set)"}", built.isNotEmpty())
        assertNotNull(
            "the core is built (${built.joinToString { it.name }}) but did not load, so every test of the native core would skip: " +
                "the bindings and the library do not go together; build the core again (scripts/core-artifacts.sh ensure host)",
            RustCoreBridge.load(),
        )
    }
}
