package no.brasscribe.play.audio

/** JNI surface of libbrasscribe_audio (Oboe microphone capture and the sfizz playback tier). */
internal object NativeAudio {
    init {
        System.loadLibrary("brasscribe_audio")
    }

    external fun recorderStart(sampleRate: Int): Boolean
    external fun recorderStop()
    external fun recorderRead(buffer: FloatArray): Int
    external fun recorderSampleRate(): Int
    external fun recorderLevel(): Float
    external fun recorderDropped(): Long

    external fun sfizzAvailable(): Boolean
    external fun sfizzStart(sampleRate: Int): Boolean
    external fun sfizzStop()
    external fun sfizzLoadFile(channel: Int, path: String): Boolean
    external fun sfizzLoadString(channel: Int, sfz: String, virtualPath: String): Boolean
    external fun sfizzRegions(channel: Int): Int
    external fun sfizzNoteOn(channel: Int, note: Int, velocity: Int)
    external fun sfizzNoteOff(channel: Int, note: Int)
    external fun sfizzNoteAt(channel: Int, note: Int, velocity: Int, delaySeconds: Double)
    external fun sfizzPosition(): Double
    external fun sfizzAllOff()
    external fun sfizzSetGain(channel: Int, gain: Float)
    external fun sfizzActiveVoices(): Int
    external fun sfizzRenderOffline(interleaved: FloatArray): Int
}
