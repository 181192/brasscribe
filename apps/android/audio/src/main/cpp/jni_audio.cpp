// JNI surface of libbrasscribe_audio for no.brasscribe.play.audio.NativeAudio.
#include <jni.h>

#include <string>

#include "output_stage.h"
#include "recorder.h"
#include "sfizz_bridge.h"

namespace {
Recorder& recorder() {
    static Recorder r;
    return r;
}

std::string str(JNIEnv* env, jstring s) {
    const char* c = env->GetStringUTFChars(s, nullptr);
    std::string out(c);
    env->ReleaseStringUTFChars(s, c);
    return out;
}
}  // namespace

#define FN(name) Java_no_brasscribe_play_audio_NativeAudio_##name

extern "C" {

JNIEXPORT jboolean JNICALL FN(recorderStart)(JNIEnv*, jobject, jint sampleRate) {
    return recorder().start(sampleRate) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL FN(recorderStop)(JNIEnv*, jobject) { recorder().stop(); }

JNIEXPORT jint JNICALL FN(recorderRead)(JNIEnv* env, jobject, jfloatArray buffer) {
    const jsize n = env->GetArrayLength(buffer);
    jfloat* dst = env->GetFloatArrayElements(buffer, nullptr);
    const int got = recorder().read(dst, n);
    env->ReleaseFloatArrayElements(buffer, dst, 0);
    return got;
}

JNIEXPORT jint JNICALL FN(recorderSampleRate)(JNIEnv*, jobject) { return recorder().sampleRate(); }
JNIEXPORT jfloat JNICALL FN(recorderLevel)(JNIEnv*, jobject) { return recorder().level(); }
JNIEXPORT jlong JNICALL FN(recorderDropped)(JNIEnv*, jobject) { return recorder().dropped(); }
JNIEXPORT jboolean JNICALL FN(recorderLost)(JNIEnv*, jobject) { return recorder().lost() ? JNI_TRUE : JNI_FALSE; }

JNIEXPORT jboolean JNICALL FN(sfizzAvailable)(JNIEnv*, jobject) { return sfizz_bridge::available() ? JNI_TRUE : JNI_FALSE; }
JNIEXPORT jboolean JNICALL FN(sfizzStart)(JNIEnv*, jobject, jint sampleRate) { return sfizz_bridge::start(sampleRate) ? JNI_TRUE : JNI_FALSE; }
JNIEXPORT void JNICALL FN(sfizzStop)(JNIEnv*, jobject) { sfizz_bridge::stop(); }

JNIEXPORT jboolean JNICALL FN(sfizzLoadFile)(JNIEnv* env, jobject, jint channel, jstring path) {
    return sfizz_bridge::loadFile(channel, str(env, path)) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL FN(sfizzLoadString)(JNIEnv* env, jobject, jint channel, jstring sfz, jstring virtualPath) {
    return sfizz_bridge::loadString(channel, str(env, sfz), str(env, virtualPath)) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jint JNICALL FN(sfizzRegions)(JNIEnv*, jobject, jint channel) { return sfizz_bridge::regions(channel); }
JNIEXPORT void JNICALL FN(sfizzNoteOn)(JNIEnv*, jobject, jint ch, jint note, jint vel) { sfizz_bridge::noteOn(ch, note, vel); }
JNIEXPORT void JNICALL FN(sfizzNoteOff)(JNIEnv*, jobject, jint ch, jint note) { sfizz_bridge::noteOff(ch, note); }
JNIEXPORT void JNICALL FN(sfizzNoteAt)(JNIEnv*, jobject, jint ch, jint note, jint vel, jdouble delay) { sfizz_bridge::noteAt(ch, note, vel, delay); }
JNIEXPORT jdouble JNICALL FN(sfizzPosition)(JNIEnv*, jobject) { return sfizz_bridge::positionSeconds(); }
JNIEXPORT void JNICALL FN(sfizzAllOff)(JNIEnv*, jobject) { sfizz_bridge::allOff(); }
JNIEXPORT void JNICALL FN(sfizzUnloadAll)(JNIEnv*, jobject) { sfizz_bridge::unloadAll(); }
JNIEXPORT void JNICALL FN(sfizzReleaseAll)(JNIEnv*, jobject) { sfizz_bridge::releaseAll(); }
JNIEXPORT void JNICALL FN(sfizzFadeOut)(JNIEnv*, jobject, jdouble seconds) { sfizz_bridge::fadeOut(seconds); }
JNIEXPORT void JNICALL FN(sfizzSetGain)(JNIEnv*, jobject, jint ch, jfloat gain) { sfizz_bridge::setGain(ch, gain); }
JNIEXPORT void JNICALL FN(sfizzSetOutputGain)(JNIEnv*, jobject, jfloat gain) { sfizz_bridge::setOutputGain(gain); }
// The C++ limiter curve, for the tests that hold it to the shared vectors.
JNIEXPORT jfloat JNICALL FN(outputStageLimit)(JNIEnv*, jobject, jfloat x) { return output_stage::limit(x); }
JNIEXPORT jint JNICALL FN(sfizzActiveVoices)(JNIEnv*, jobject) { return sfizz_bridge::activeVoices(); }

JNIEXPORT jint JNICALL FN(sfizzRenderOffline)(JNIEnv* env, jobject, jfloatArray interleaved) {
    const jsize n = env->GetArrayLength(interleaved);
    jfloat* dst = env->GetFloatArrayElements(interleaved, nullptr);
    const int frames = sfizz_bridge::renderOffline(dst, n / 2);
    env->ReleaseFloatArrayElements(interleaved, dst, 0);
    return frames;
}

}  // extern "C"
