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
    // alphaTab's generated Kotlin API is marked with these; every module that uses it opts in.
    tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask<*>>().configureEach {
        compilerOptions.optIn.addAll("kotlin.contracts.ExperimentalContracts", "kotlin.ExperimentalUnsignedTypes")
    }
    plugins.withId("org.jetbrains.kotlin.jvm") {
        tasks.register("testDebugUnitTest") { dependsOn("test") }
    }
    // -Pscribe.fast (the inner-loop tier, docs/dev/verify.md): unit tests without the Slow category,
    // in the modules that declare it (JUnit fails to start where the category class is missing).
    // (A product's comes from the flow's src/appScreenTest, with the screen tests that also run on a device.)
    val slow = path.startsWith(":products:") || file("src/test/kotlin/no/kalli/scribe/test/Slow.kt").exists()
    if (providers.gradleProperty("scribe.fast").isPresent && slow) {
        // Android unit-test tasks take it directly; the JVM modules' test suite sets its framework itself.
        tasks.withType<Test>().configureEach { useJUnit { excludeCategories("no.kalli.scribe.test.Slow") } }
        plugins.withId("org.jetbrains.kotlin.jvm") {
            the<TestingExtension>().suites.withType<JvmTestSuite>().configureEach {
                useJUnit()
                targets.configureEach { testTask.configure { useJUnit { excludeCategories("no.kalli.scribe.test.Slow") } } }
            }
        }
    }
}
