plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.roborazzi) apply false
}

/** The repository root (two levels up): golden fixtures and converted models live under data/ and models/ there. */
val repoRoot: File = rootDir.parentFile.parentFile
extra["repoRoot"] = repoRoot

// `./gradlew testDebugUnitTest` also runs the plain Kotlin/JVM modules' tests.
subprojects {
    plugins.withId("org.jetbrains.kotlin.jvm") {
        tasks.register("testDebugUnitTest") { dependsOn("test") }
    }
    // -Pbrasscribe.fast (the inner-loop tier, docs/dev/verify.md): unit tests without the Slow category,
    // in the modules that declare it (JUnit fails to start where the category class is missing).
    // (The app's is in src/screenTest, with the screen tests that also run on a device.)
    val slow = listOf("test", "screenTest").any { file("src/$it/kotlin/no/brasscribe/play/test/Slow.kt").exists() }
    if (providers.gradleProperty("brasscribe.fast").isPresent && slow) {
        // Android unit-test tasks take it directly; the JVM modules' test suite sets its framework itself.
        tasks.withType<Test>().configureEach { useJUnit { excludeCategories("no.brasscribe.play.test.Slow") } }
        plugins.withId("org.jetbrains.kotlin.jvm") {
            the<TestingExtension>().suites.withType<JvmTestSuite>().configureEach {
                useJUnit()
                targets.configureEach { testTask.configure { useJUnit { excludeCategories("no.brasscribe.play.test.Slow") } } }
            }
        }
    }
}
