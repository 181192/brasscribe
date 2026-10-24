plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.compose)
}

/*
 * Brasscribe's design system for Android, generated from its tokens by design/tokens/build.py into design/dist: the neutral
 * theme (no.kalli.scribe.design, the same declarations in every brand with this brand's values) and Brasscribe's own roles
 * (no.kalli.brasscribe.design), compiled as they are; the icon drawables, the display face (as res/font/display) and the
 * launcher icons, synced into one generated res folder (res/font may hold only fonts, so the font's licence goes to
 * the assets). Every brand's module has the namespace no.kalli.scribe.design, so the shared screens name the same R.
 */
val repoRoot = rootProject.extra["repoRoot"] as File
val dist = File(repoRoot, "design/dist")
val displayFont = "instrument_serif"

android {
    namespace = "no.kalli.scribe.design"
    compileSdk = 37
    defaultConfig { minSdk = 36 }
    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    sourceSets {
        getByName("main") {
            kotlin.directories.add(File(dist, "android/kotlin").path)
            res.directories.add(layout.buildDirectory.dir("generated/design/res").get().asFile.path)
            assets.directories.add(layout.buildDirectory.dir("generated/design/assets").get().asFile.path)
        }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

val designResources = tasks.register<Sync>("syncDesignResources") {
    val font = displayFont
    into(layout.buildDirectory.dir("generated/design/res"))
    from(File(dist, "android/res")) {
        exclude("font/OFL.txt")
        rename { if (it == "$font.ttf") "display.ttf" else it }
    }
    from(File(dist, "icons/android/res"))
}
val designLicence = tasks.register<Sync>("syncDesignLicence") {
    val font = displayFont
    into(layout.buildDirectory.dir("generated/design/assets/licences"))
    from(File(dist, "android/res/font")) {
        include("OFL.txt")
        rename { "${font.replace('_', '-')}-OFL.txt" }
    }
}
tasks.named("preBuild") { dependsOn(designResources, designLicence) }

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
}
