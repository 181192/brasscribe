#include "recorder.h"

#include <android/log.h>

#include <cmath>

#define LOG_TAG "brasscribe-recorder"

bool Recorder::start(int sampleRate) {
    stop();
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
    oboe::Result r = builder.openStream(stream_);
    if (r != oboe::Result::OK) {
        // Some devices have no unprocessed input; fall back to the default voice-recognition preset.
        builder.setInputPreset(oboe::InputPreset::VoiceRecognition);
        r = builder.openStream(stream_);
    }
    if (r != oboe::Result::OK) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "openStream: %s", oboe::convertToText(r));
        return false;
    }
    sampleRate_ = stream_->getSampleRate();
    ring_ = std::make_unique<RingBuffer>(static_cast<size_t>(sampleRate_) * 10);
    dropped_ = 0;
    r = stream_->requestStart();
    if (r != oboe::Result::OK) {
        __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, "requestStart: %s", oboe::convertToText(r));
        stream_->close();
        stream_.reset();
        return false;
    }
    return true;
}

void Recorder::stop() {
    if (stream_) {
        stream_->requestStop();
        stream_->close();
        stream_.reset();
    }
}

int Recorder::read(float* dst, int n) {
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

void Recorder::onErrorAfterClose(oboe::AudioStream*, oboe::Result error) {
    __android_log_print(ANDROID_LOG_WARN, LOG_TAG, "stream closed: %s", oboe::convertToText(error));
}
