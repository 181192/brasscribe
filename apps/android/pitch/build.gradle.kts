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
    // The ai.onnxruntime Java API is identical in the desktop and Android artifacts: the app adds
    // onnxruntime-android at runtime, the JVM tests run the same code on the desktop build.
    compileOnly(libs.onnxruntime.jvm)
    testImplementation(libs.onnxruntime.jvm)
    testImplementation(libs.junit)
}

val repoRoot = rootProject.extra["repoRoot"] as File

tasks.test {
    systemProperty("brasscribe.swiftf0", File(repoRoot, "models/converted/swift-f0/swift-f0-window.onnx").absolutePath)
    systemProperty("brasscribe.pitchFixtures", file("src/test/resources").absolutePath)
}
