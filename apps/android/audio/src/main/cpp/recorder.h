#pragma once

#include <oboe/Oboe.h>

#include <atomic>
#include <memory>

#include "ring_buffer.h"

// Microphone capture through Oboe (AAudio on API 27+): mono float, low latency, samples handed to
// Kotlin through a ring buffer, plus a running peak level for the input meter.
class Recorder : public oboe::AudioStreamDataCallback, public oboe::AudioStreamErrorCallback {
public:
    bool start(int sampleRate);
    void stop();
    int read(float* dst, int n);
    int sampleRate() const { return sampleRate_; }
    // Peak of the last callback, 0..1.
    float level() const { return level_.load(); }
    // Samples dropped because Kotlin did not read fast enough.
    long dropped() const { return dropped_.load(); }

    oboe::DataCallbackResult onAudioReady(oboe::AudioStream* stream, void* audioData, int32_t numFrames) override;
    void onErrorAfterClose(oboe::AudioStream* stream, oboe::Result error) override;

private:
    std::shared_ptr<oboe::AudioStream> stream_;
    std::unique_ptr<RingBuffer> ring_;
    int sampleRate_ = 0;
    std::atomic<float> level_{0.f};
    std::atomic<long> dropped_{0};
};
