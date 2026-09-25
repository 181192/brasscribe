package no.brasscribe.play

import android.content.Context
import android.os.Build
import io.ktor.client.engine.okhttp.OkHttp
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.KtorEngineApi
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.KotlinCoreBridge
import no.brasscribe.play.pitch.SwiftF0

/** Companion engine settings, kept in SharedPreferences. */
class EngineSettings(context: Context) {
    private val prefs = context.getSharedPreferences("engine", Context.MODE_PRIVATE)

    var url: String
        get() = prefs.getString("url", null) ?: DEFAULT_URL
        set(v) = prefs.edit().putString("url", v).apply()

    var token: String?
        get() = prefs.getString("token", null)
        set(v) = prefs.edit().putString("token", v).apply()

    /** True once the user connected to a real engine; false means the built-in sample engine. */
    var paired: Boolean
        get() = prefs.getBoolean("paired", false)
        set(v) = prefs.edit().putBoolean("paired", v).apply()

    var useFixture: Boolean
        get() = prefs.getBoolean("fixture", true)
        set(v) = prefs.edit().putBoolean("fixture", v).apply()

    companion object {
        /** The emulator's alias for the host machine, and the engine's default port. */
        const val DEFAULT_URL = "http://10.0.2.2:8765"
    }
}

/**
 * Everything the app shares: the core bridge, the engine (companion or built-in sample), the on-device
 * pitch model. Created once by [PlayApplication].
 */
class AppContainer(private val context: Context) {
    val settings = EngineSettings(context)

    /** The Rust core replaces this once its UniFFI bindings ship (see README, "CoreBridge"). */
    val core: CoreBridge = KotlinCoreBridge

    /** Golden Mikkel output packaged in debug builds (assets/fixtures). */
    val fixtureSource: FixtureSource? = runCatching {
        context.assets.open("fixtures/composition.json").close()
        FixtureSource { name -> runCatching { context.assets.open("fixtures/$name").use { it.readBytes() } }.getOrNull() }
    }.getOrNull()

    val hasFixtures: Boolean get() = fixtureSource != null

    val usingFixture: Boolean get() = hasFixtures && (settings.useFixture || !settings.paired)

    private var cachedEngine: Pair<String, EngineApi>? = null

    fun engine(): EngineApi? {
        val key = if (usingFixture) "fixture" else "${settings.url}|${settings.token}|${settings.paired}"
        cachedEngine?.takeIf { it.first == key }?.let { return it.second }
        val api: EngineApi = when {
            usingFixture -> FixtureEngineApi(fixtureSource!!, stageSeconds = 0.7)
            settings.paired -> KtorEngineApi(settings.url, OkHttp.create(), settings.token)
            else -> return null
        }
        cachedEngine = key to api
        return api
    }

    fun newEngineClient(url: String): KtorEngineApi = KtorEngineApi(url, OkHttp.create())

    fun engineLabel(): String = if (usingFixture) "sample" else settings.url.removePrefix("http://").removePrefix("https://")

    /** SwiftF0 export from models/convert, bundled as an asset when it was present at build time. */
    val hasPitchModel: Boolean by lazy { runCatching { context.assets.open(MODEL_ASSET).close() }.isSuccess }

    fun openPitchModel(): SwiftF0 = SwiftF0(context.assets.open(MODEL_ASSET).use { it.readBytes() }, threads = 2)

    val deviceName: String get() = "${Build.MANUFACTURER} ${Build.MODEL}"

    companion object {
        const val MODEL_ASSET = "models/swift-f0-window.onnx"
    }
}
