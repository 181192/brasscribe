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
import no.brasscribe.play.core.RustCoreBridge
import no.brasscribe.play.pitch.BasicPitch
import no.brasscribe.play.pitch.BeatThis
import no.brasscribe.play.pitch.SoloPipeline
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

    /**
     * Whether the engine may run heavy models on cache misses (and render audio). Off makes a new clip
     * fail fast at its first heavy stage: useful for checking the connection without loading the machine.
     */
    var allowHeavy: Boolean
        get() = prefs.getBoolean("allow_heavy", true)
        set(v) = prefs.edit().putBoolean("allow_heavy", v).apply()

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

    init {
        // Sound pack folders exist from the first start, so instruments can be copied into them.
        runCatching { no.brasscribe.play.score.SoundPack(context) }
    }

    /** The Rust core when its native library is in the APK (scripts/build-core.sh), else the Kotlin fallback. */
    val core: CoreBridge = RustCoreBridge.load() ?: KotlinCoreBridge

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

    fun openPitchModel(): SwiftF0 = SwiftF0(asset(MODEL_ASSET)!!, threads = 2)

    private fun asset(name: String): ByteArray? = runCatching { context.assets.open(name).use { it.readBytes() } }.getOrNull()

    /** SwiftF0 plus Basic Pitch and Beat This! small when their models are bundled. */
    class OpenPipeline(val pipeline: SoloPipeline, private val models: List<AutoCloseable>) : AutoCloseable {
        override fun close() = models.forEach { it.close() }
    }

    fun openSoloPipeline(): OpenPipeline {
        val sw = openPitchModel()
        val bp = asset(BASIC_PITCH_ASSET)?.let { BasicPitch(it) }
        val bt = asset(BEAT_THIS_ASSET)?.let { BeatThis(it) }
        return OpenPipeline(SoloPipeline(sw, bp, bt, core), listOfNotNull(sw, bp, bt))
    }

    /** Band SoundFont presets and balance per part (assets/sounds/mapping.json). */
    val bandSoundMap: no.brasscribe.play.score.BandSoundMap? by lazy {
        asset("sounds/mapping.json")?.let { runCatching { no.brasscribe.play.score.BandSoundMap.parse(String(it)) }.getOrNull() }
    }

    /**
     * brasscribe-band.sf2 (sounds/band.py; 16-bit 149 MB or 24-bit 223 MB) copied to the app's external
     * files under sounds/. Not bundled: it is a separate download like the other sound packs.
     */
    fun bandSoundFont(): java.io.File? = context.getExternalFilesDir(null)?.resolve("sounds")?.also { it.mkdirs() }?.let { d ->
        listOf("brasscribe-band-mobile.sf2", "brasscribe-band-16bit.sf2", "brasscribe-band.sf2").map { d.resolve(it) }.firstOrNull { it.isFile }
            .also { android.util.Log.i("BrasscribePlay", "band SoundFont in $d: ${it?.name ?: "none"}") }
    }

    val deviceName: String get() = "${Build.MANUFACTURER} ${Build.MODEL}"

    companion object {
        const val MODEL_ASSET = "models/swift-f0-window.onnx"
        const val BASIC_PITCH_ASSET = "models/nmp-b1.onnx"
        const val BEAT_THIS_ASSET = "models/beat-this-small0.onnx"
    }
}
