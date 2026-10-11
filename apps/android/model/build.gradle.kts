import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    api(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
}

val repoRoot = rootProject.extra["repoRoot"] as File

tasks.test {
    // Tests that read the golden Mikkel output skip themselves when this directory is absent.
    systemProperty("brasscribe.golden", File(repoRoot, "data/golden/mikkel-arranged-band").absolutePath)
    // Re-run when the golden output is re-saved.
    inputs.files(fileTree(File(repoRoot, "data/golden/mikkel-arranged-band")) { include("composition.json") }).withPropertyName("golden")
    // The talking-score conformance vectors, read where every other port reads them.
    systemProperty("brasscribe.vectors", File(repoRoot, "docs/accessibility/talking-score-vectors.json").absolutePath)
    inputs.file(File(repoRoot, "docs/accessibility/talking-score-vectors.json")).withPropertyName("vectors")
}
