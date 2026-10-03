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
    // ONNX Runtime's desktop build starts a telemetry uploader unless it runs in CI. An upload that answers while
    // the test JVM exits takes a lock that is already gone, and the JVM aborts (SIGABRT) after the tests passed.
    // Without the uploader there is no such thread.
    environment("ORT_DISABLE_TELEMETRY", "1")
    systemProperty("brasscribe.swiftf0", File(repoRoot, "models/converted/swift-f0/swift-f0-window.onnx").absolutePath)
    inputs.files(fileTree(File(repoRoot, "models/converted/swift-f0")) { include("swift-f0-window.onnx") }).withPropertyName("model")
    // Converted models (models/converted/<model>/...); tests needing one skip when it is absent.
    systemProperty("brasscribe.models", File(repoRoot, "models/converted").absolutePath)
    systemProperty("brasscribe.data", File(repoRoot, "data").absolutePath)
    systemProperty("brasscribe.pitchFixtures", file("src/test/resources").absolutePath)
}
