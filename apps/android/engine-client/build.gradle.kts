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
    api(project(":model"))
    api(libs.kotlinx.coroutines.core)
    api(libs.ktor.client.core)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)

    testImplementation(libs.junit)
    testImplementation(libs.ktor.client.mock)
    testImplementation(libs.kotlinx.coroutines.test)
}

val repoRoot = rootProject.extra["repoRoot"] as File

tasks.test {
    systemProperty("brasscribe.golden", File(repoRoot, "data/golden/mikkel-arranged-band").absolutePath)
    systemProperty("brasscribe.openapi", file("openapi.json").absolutePath)
}

/**
 * Refreshes the vendored API description from the engine once it is in the same checkout.
 * The contract test compares the client against this file.
 */
tasks.register<Copy>("syncOpenApi") {
    from(File(repoRoot, "engine/openapi.json"))
    into(projectDir)
}
