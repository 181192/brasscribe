package no.brasscribe.play

import android.content.Context
import android.content.res.Configuration
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import java.net.InetAddress
import no.brasscribe.play.engine.EngineApi
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.FixtureSource
import no.brasscribe.play.engine.KtorEngineApi
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.KotlinCoreBridge
import no.brasscribe.play.core.RustCoreBridge
import no.brasscribe.play.connection.Credential
import no.brasscribe.play.connection.CredentialStore
import no.brasscribe.play.connection.KeystoreCipher
import no.brasscribe.play.connection.PrefsStore
import no.brasscribe.play.pitch.BasicPitch
import no.brasscribe.play.pitch.BeatThis
import no.brasscribe.play.pitch.SoloPipeline
import no.brasscribe.play.pitch.SwiftF0

/**
 * Companion engine settings, kept in SharedPreferences. The credential itself is not here: it is in
 * [credentials] (Keystore-encrypted), keyed by [serverId].
 */
class EngineSettings(context: Context, val credentials: CredentialStore) {
    private val prefs = context.getSharedPreferences("engine", Context.MODE_PRIVATE)

    init {
        // Earlier versions kept the token here in plain text: move it into the encrypted store once.
        credentials.migrateLegacy(PrefsStore(prefs))
    }

    /** The last address the engine answered at. */
    var url: String
        get() = prefs.getString("url", null) ?: DEFAULT_URL
        set(v) = prefs.edit().putString("url", v).apply()

    /** The engine's stable id; null until an engine has answered (or for a token from an earlier version). */
    var serverId: String?
        get() = prefs.getString("server_id", null)
        set(v) = prefs.edit().putString("server_id", v).apply()

    /** "Brasscribe on <computer>", as the engine calls itself. */
    var serverName: String
        get() = prefs.getString("server_name", null) ?: ""
        set(v) = prefs.edit().putString("server_name", v).apply()

    /** This phone's credential for the current engine, if it has one. */
    val credential: Credential? get() = credentials.get(serverId ?: CredentialStore.LEGACY_ID)

    val token: String? get() = credential?.token

    /** True once the user connected to an engine. */
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

    companion object {
        /** The emulator's alias for the host machine, and the engine's default port. */
        const val DEFAULT_URL = "http://10.0.2.2:8765"
    }
}

/**
 * Everything the app shares: the core bridge, the engine on the paired computer, the on-device
 * pitch model. Created once by [PlayApplication].
 */
class AppContainer(private val context: Context) {
    val credentials = CredentialStore(PrefsStore(context.getSharedPreferences(CREDENTIALS_PREFS, Context.MODE_PRIVATE)), KeystoreCipher())
    val settings = EngineSettings(context, credentials)
    private val prefs = context.getSharedPreferences("play", Context.MODE_PRIVATE)
    private val appearanceStore = AppearanceStore(PrefsStore(context.getSharedPreferences(AppearanceStore.PREFS, Context.MODE_PRIVATE)))

    /** Settings › Display › Appearance. Compose state, so the theme changes at once when it is set. */
    var appearance: Appearance by androidx.compose.runtime.mutableStateOf(appearanceStore.also { it.migrate(systemDark()) }.load())
        private set

    fun updateAppearance(value: Appearance) {
        appearanceStore.save(value)
        appearance = value
    }

    /** Whether the hidden Pink palette is listed in Appearance. Compose state, like [appearance]. */
    var pinkUnlocked: Boolean by androidx.compose.runtime.mutableStateOf(appearanceStore.pinkUnlocked())
        private set

    fun unlockPink() {
        appearanceStore.unlockPink()
        pinkUnlocked = true
    }

    /** Hides Pink again, so device tests can walk the unlock from the start. */
    @androidx.annotation.VisibleForTesting
    fun forgetPink() {
        if (appearance.isPink) updateAppearance(Appearance.SYSTEM)
        appearanceStore.forgetPink()
        pinkUnlocked = false
    }

    /** Whether the phone is in dark theme now; null when it doesn't say. */
    private fun systemDark(): Boolean? = when (context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) {
        Configuration.UI_MODE_NIGHT_YES -> true
        Configuration.UI_MODE_NIGHT_NO -> false
        else -> null
    }

    private val seatStore = SeatStore(PrefsStore(context.getSharedPreferences(AppearanceStore.PREFS, Context.MODE_PRIVATE)))

    /**
     * Settings › Your instrument: what this player plays. Per phone, like Appearance. Changing it never
     * re-arranges a score: it is the default "your part" of new scores and of scores with none picked.
     */
    var seat: SeatChoice by androidx.compose.runtime.mutableStateOf(seatStore.load())
        private set

    fun updateSeat(value: SeatChoice) {
        seatStore.save(value)
        seat = value
    }

    /** The first-run screen (three points and Get started) has been seen. */
    /** Scores open with the realistic sound (SFZ instruments) instead of the standard one. */
    var realisticByDefault: Boolean
        get() = prefs.getBoolean("realistic_default", false)
        set(v) = prefs.edit().putBoolean("realistic_default", v).apply()

    var firstRunDone: Boolean
        get() = prefs.getBoolean("first_run_done", false)
        set(v) = prefs.edit().putBoolean("first_run_done", v).apply()

    /** Settings → Display: the stand's control layer never hides by itself. */
    var standKeepControls: Boolean
        get() = prefs.getBoolean("stand_keep_controls", false)
        set(v) = prefs.edit().putBoolean("stand_keep_controls", v).apply()

    /** Settings → Display: playback turns the stand's pages (on by default). */
    var standFollow: Boolean
        get() = prefs.getBoolean("stand_follow", true)
        set(v) = prefs.edit().putBoolean("stand_follow", v).apply()

    /** "Tap the music to show the controls." has been shown once, and does not come back. */
    var standHintShown: Boolean
        get() = prefs.getBoolean("stand_hint_shown", false)
        set(v) = prefs.edit().putBoolean("stand_hint_shown", v).apply()

    /** Tests stand in for TalkBack or Switch Access here (the stand keeps its controls); null asks the system. */
    var assistiveOverride: Boolean? by androidx.compose.runtime.mutableStateOf(null)

    init {
        // Sound pack folders exist from the first start, so instruments can be copied into them.
        runCatching { no.brasscribe.play.score.SoundPack(context) }
        // "Open the music stand when I turn the phone sideways" is gone; so is what it stored.
        prefs.edit().remove("stand_on_turn").apply()
    }

    /** The scores kept on this phone ("Your scores"). */
    val scoreLibrary = SavedScoreLibrary(java.io.File(context.filesDir, "scores"))

    /** The recordings kept in Your scores before they have a score; out of the backup (`noBackupFilesDir`). */
    val keptRecordings = KeptRecordingStore(java.io.File(context.noBackupFilesDir, "kept-recordings"),
        keepFor = Product.KEPT_RECORDING_DAYS?.let { java.util.concurrent.TimeUnit.DAYS.toMillis(it.toLong()) })

    /** The Rust core when its native library is in the APK (scripts/build-core.sh), else the Kotlin fallback. */
    val core: CoreBridge = (RustCoreBridge.load() ?: KotlinCoreBridge).also { c -> no.brasscribe.play.ui.PartNames.nb = c::partNameNb }

    /** The contest band's seats, from the core; empty without it (then "What do you play?" is not asked). */
    val seats: List<no.brasscribe.play.model.Seat> by lazy { runCatching { core.seats() }.getOrDefault(emptyList()) }

    /**
     * Instrumented tests only: a finished score served in place of a paired computer
     * (apps/fixtures, packaged in the test APK). Null in the app.
     */
    var fixtureSource: FixtureSource? = null
        set(v) { field = v; cachedEngine = null }

    val usingFixture: Boolean get() = fixtureSource != null

    /**
     * The version About shows: the app's own. The screen catalogue puts a fixed one in, so its pictures of About
     * stay the same from one release to the next.
     */
    var shownVersion: String = BuildConfig.VERSION_NAME

    /** The camera under the pairing scanner: the phone's own; tests put one in that shows them a code. */
    var qrCamera: no.brasscribe.play.ui.QrCamera = no.brasscribe.play.ui.PhoneQrCamera

    /** Tests only: how long each of the fixture computer's stages takes. */
    var fixtureStageSeconds: Double = 0.7
        set(v) { field = v; cachedEngine = null }

    private var cachedEngine: Pair<String, EngineApi>? = null

    /**
     * The client for the paired engine: one per address and network, kept while they stay the same. The
     * token is not part of it: each call hands the current one to the client, so a rotated token or a new
     * pairing needs no new connection pool. A client that is replaced is closed.
     */
    @Synchronized
    fun engine(): EngineApi? {
        if (!usingFixture && !settings.paired) { dropEngine(); return null }
        val network = if (usingFixture) null else lanNetwork(settings.url)
        val key = if (usingFixture) "fixture" else "${settings.url}|${network?.networkHandle}"
        val api = cachedEngine?.takeIf { it.first == key }?.second ?: run {
            dropEngine()
            val created: EngineApi = if (usingFixture) FixtureEngineApi(fixtureSource!!, stageSeconds = fixtureStageSeconds)
            else KtorEngineApi(settings.url, httpEngine(network))
            cachedEngine = key to created
            created
        }
        (api as? KtorEngineApi)?.token = settings.token
        return api
    }

    private fun dropEngine() {
        // Requests already under way finish; the client takes no new ones.
        (cachedEngine?.second as? AutoCloseable)?.let { runCatching { it.close() } }
        cachedEngine = null
    }

    fun newEngineClient(url: String, token: String? = null): KtorEngineApi = KtorEngineApi(url, httpEngine(lanNetwork(url)), token)

    private fun httpEngine(network: Network?) = no.brasscribe.play.connection.EngineHttp.engine(network?.socketFactory)

    /**
     * The network whose link owns a private engine address. When Wi-Fi is weak, Android can make mobile
     * data the default network, and a LAN address sent there never arrives.
     */
    @Suppress("DEPRECATION")
    private fun lanNetwork(url: String): Network? {
        val host = runCatching { java.net.URI(url).host?.removeSurrounding("[", "]") }.getOrNull() ?: return null
        if (!host.contains(':') && !host.matches(Regex("""\d{1,3}(\.\d{1,3}){3}"""))) return null
        val address = runCatching { InetAddress.getByName(host) }.getOrNull() ?: return null
        if (!address.isSiteLocalAddress && !address.isLinkLocalAddress) return null
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return null
        val owner = cm.allNetworks.firstOrNull { n ->
            cm.getLinkProperties(n)?.routes?.any { it.destination.prefixLength > 0 && it.matches(address) } == true
        }
        // Binding is only needed when another network is the default. A network this app may not bind to
        // (EPERM, seen on emulators) is left to the system's routing instead of failing every request.
        return owner?.takeIf { it != cm.activeNetwork && canBind(it) }
    }

    private fun canBind(network: Network): Boolean =
        runCatching { java.net.Socket().use { network.bindSocket(it) } }.isSuccess

    val discovery by lazy { EngineDiscovery(context) }

    /** A second discovery session, for finding the paired engine again by its server id. */
    val reconnectDiscovery by lazy { EngineDiscovery(context) }

    fun engineLabel(): String = if (usingFixture) FixtureEngineApi.SERVER_NAME else settings.url.removePrefix("http://").removePrefix("https://")

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

    /** Basic Pitch and Beat This! small are bundled: the phone can make a band draft. */
    val hasBandModels: Boolean by lazy {
        listOf(BASIC_PITCH_ASSET, BEAT_THIS_ASSET).all { runCatching { context.assets.open(it).close() }.isSuccess }
    }

    /** Basic Pitch on the whole mix and Beat This! small, for a band draft ([hasBandModels] must be true). */
    class OpenBandPipeline(val pipeline: no.brasscribe.play.pitch.BandDraftPipeline, private val models: List<AutoCloseable>) : AutoCloseable {
        override fun close() = models.forEach { it.close() }
    }

    fun openBandDraftPipeline(): OpenBandPipeline {
        val bp = BasicPitch(requireNotNull(asset(BASIC_PITCH_ASSET)) { "Basic Pitch is not bundled" })
        val bt = runCatching { BeatThis(requireNotNull(asset(BEAT_THIS_ASSET)) { "Beat This! is not bundled" }) }
            .onFailure { bp.close() }.getOrThrow()
        return OpenBandPipeline(no.brasscribe.play.pitch.BandDraftPipeline(bp, bt, core), listOf(bp, bt))
    }

    /** Band SoundFont presets and balance per part (assets/sounds/mapping.json). */
    val bandSoundMap: no.brasscribe.play.score.BandSoundMap? by lazy {
        asset("sounds/mapping.json")?.let { runCatching { no.brasscribe.play.score.BandSoundMap.parse(String(it)) }.getOrNull() }
    }

    /**
     * A band SoundFont sideloaded to the app's external files under sounds/ (overrides the bundled one).
     * Without it the score player loads the phone SoundFont bundled in the APK (score/BandSoundFontFile).
     */
    fun bandSoundFont(): java.io.File? = context.getExternalFilesDir(null)?.resolve("sounds")?.also { it.mkdirs() }
        .let { no.brasscribe.play.score.BandSoundFontFile.sideloaded(context) }
        .also { android.util.Log.i("BrasscribePlay", "sideloaded band SoundFont: ${it?.name ?: "none"}") }

    val deviceName: String get() = "${Build.MANUFACTURER} ${Build.MODEL}"

    companion object {
        /** Encrypted credentials; excluded from backup (res/xml/backup_rules.xml, data_extraction_rules.xml). */
        const val CREDENTIALS_PREFS = "credentials"
        const val MODEL_ASSET = "models/swift-f0-window.onnx"
        const val BASIC_PITCH_ASSET = "models/nmp-b1.onnx"
        const val BEAT_THIS_ASSET = "models/beat-this-small0.onnx"
    }
}
