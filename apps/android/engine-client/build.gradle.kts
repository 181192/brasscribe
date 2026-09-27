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
    inputs.file("openapi.json").withPropertyName("openapi")
    inputs.files(fileTree(File(repoRoot, "data/golden/mikkel-arranged-band"))).withPropertyName("golden")
}

/**
 * Refreshes the vendored API description from the engine once it is in the same checkout.
 * The contract test compares the client against this file.
 */
val syncOpenApi = tasks.register("syncOpenApi") {
    val source = File(repoRoot, "engine/openapi.json")
    val target = file("openapi.json")
    inputs.files(source)
    onlyIf { source.isFile }
    // Only the one file: a copy into the project folder would own every other task's inputs too.
    outputs.file(target)
    doLast { source.copyTo(target, overwrite = true) }
}
tasks.test { mustRunAfter(syncOpenApi) }
