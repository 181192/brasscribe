plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}

/** The repository root (two levels up): golden fixtures and converted models live under data/ and models/ there. */
val repoRoot: File = rootDir.parentFile.parentFile
extra["repoRoot"] = repoRoot

// `./gradlew testDebugUnitTest` also runs the plain Kotlin/JVM modules' tests.
subprojects {
    plugins.withId("org.jetbrains.kotlin.jvm") {
        tasks.register("testDebugUnitTest") { dependsOn("test") }
    }
}
