#include "recorder.h"

#include <android/log.h>

#include <cmath>

#define LOG_TAG "brasscribe-recorder"

oboe::Result Recorder::openLocked(int sampleRate, bool convert) {
    oboe::AudioStreamBuilder builder;
    builder.setDirection(oboe::Direction::Input)
        ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
        ->setSharingMode(oboe::SharingMode::Shared)
        ->setFormat(oboe::AudioFormat::Float)
        ->setChannelCount(oboe::ChannelCount::Mono)
        ->setInputPreset(oboe::InputPreset::Unprocessed)
        ->setDataCallback(this)
        ->setErrorCallback(this);
    if (sampleRate > 0) builder.setSampleRate(sampleRate);
    // Reopened mid-take on another device: the take keeps its rate, Oboe converts.
    if (convert) builder.setSampleRateConversionQuality(oboe::SampleRateConversionQuality::Medium);
    oboe::Result r = builder.openStream(stream_);
    if (r != oboe::Result::OK) {
        // Some devices have no unprocessed input; fall back to the default voice-recognition preset.
        builder.setInputPreset(oboe::InputPreset::VoiceRecognition);
        r = builder.openStream(stream_);
    }
    return r;
}

void Recorder::closeLocked() {
    if (!stream_) return;
    // A blocking stop: once it returns, the callback no longer runs, so the ring can be replaced.
    stream_->stop();
    stream_->close();
    stream_.reset();
}

bool Recorder::start(int sampleRate) {
    std::lock_guard<std::mutex> l(lifecycle_);
    wanted_ = false;
    closeLocked();
    oboe::Result r = openLocked(sampleRate, false);
    if (r != oboe::Result::OK) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "openStream: %s", oboe::convertToText(r));
        stream_.reset();
        return false;
    }
    const int rate = stream_->getSampleRate();
    {
        std::lock_guard<std::mutex> g(ringMutex_);
        ring_ = std::make_unique<RingBuffer>(static_cast<size_t>(rate) * 10);
    }
    sampleRate_ = rate;
    dropped_ = 0;
    lost_ = false;
    wanted_ = true;
    r = stream_->requestStart();
    if (r != oboe::Result::OK) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "requestStart: %s", oboe::convertToText(r));
        wanted_ = false;
        stream_->close();
        stream_.reset();
        return false;
    }
    return true;
}

void Recorder::stop() {
    std::lock_guard<std::mutex> l(lifecycle_);
    wanted_ = false;
    closeLocked();
}

int Recorder::read(float* dst, int n) {
    std::lock_guard<std::mutex> g(ringMutex_);
    if (!ring_) return 0;
    return static_cast<int>(ring_->read(dst, static_cast<size_t>(n)));
}

oboe::DataCallbackResult Recorder::onAudioReady(oboe::AudioStream*, void* audioData, int32_t numFrames) {
    const auto* in = static_cast<const float*>(audioData);
    float peak = 0.f;
    for (int32_t i = 0; i < numFrames; ++i) peak = std::fmax(peak, std::fabs(in[i]));
    level_.store(peak);
    const size_t written = ring_->write(in, static_cast<size_t>(numFrames));
    if (written < static_cast<size_t>(numFrames)) dropped_ += static_cast<long>(numFrames - written);
    return oboe::DataCallbackResult::Continue;
}

// A headset or Bluetooth microphone came or went: Oboe closed the stream. The take goes on from the new
// input at the same rate (Oboe's recommended way back); if that fails, [lost] tells Kotlin to end the take.
// A start or stop from the app at the same moment wins (it holds the lock).
void Recorder::onErrorAfterClose(oboe::AudioStream* stream, oboe::Result error) {
    __android_log_print(ANDROID_LOG_WARN, LOG_TAG, "stream closed: %s", oboe::convertToText(error));
    std::unique_lock<std::mutex> l(lifecycle_, std::try_to_lock);
    if (!l.owns_lock() || !wanted_ || stream_.get() != stream) return;
    stream_.reset();
    if (error == oboe::Result::ErrorDisconnected) {
        const int rate = sampleRate_.load();
        if (openLocked(rate, true) == oboe::Result::OK && stream_->getSampleRate() == rate &&
            stream_->requestStart() == oboe::Result::OK) {
            __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "input reopened after a device change");
            return;
        }
        if (stream_) { stream_->close(); stream_.reset(); }
    }
    wanted_ = false;
    lost_ = true;
}
