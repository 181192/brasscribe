#pragma once

#include <oboe/Oboe.h>

#include <atomic>
#include <memory>
#include <mutex>

#include "ring_buffer.h"

// Microphone capture through Oboe (AAudio on API 27+): mono float, low latency, samples handed to
// Kotlin through a ring buffer, plus a running peak level for the input meter.
//
// The ring has one writer (the audio callback) and one reader (Kotlin's read loop). A new take makes a
// new ring only once the old stream has stopped, and under the reader's lock, so a read never runs on a
// ring that is being replaced.
class Recorder : public oboe::AudioStreamDataCallback, public oboe::AudioStreamErrorCallback {
public:
    bool start(int sampleRate);
    void stop();
    int read(float* dst, int n);
    int sampleRate() const { return sampleRate_.load(); }
    // Peak of the last callback, 0..1.
    float level() const { return level_.load(); }
    // Samples dropped because Kotlin did not read fast enough.
    long dropped() const { return dropped_.load(); }
    // The input went away (a headset unplugged) and no stream at the take's rate could be opened again.
    bool lost() const { return lost_.load(); }

    oboe::DataCallbackResult onAudioReady(oboe::AudioStream* stream, void* audioData, int32_t numFrames) override;
    void onErrorAfterClose(oboe::AudioStream* stream, oboe::Result error) override;

private:
    oboe::Result openLocked(int sampleRate, bool convert);
    void closeLocked();

    // Guards the stream and whether one is wanted; the audio callback never takes it.
    std::mutex lifecycle_;
    bool wanted_ = false;
    std::shared_ptr<oboe::AudioStream> stream_;
    // Guards [ring_] against being replaced while Kotlin reads it.
    std::mutex ringMutex_;
    std::unique_ptr<RingBuffer> ring_;
    std::atomic<int> sampleRate_{0};
    std::atomic<float> level_{0.f};
    std::atomic<long> dropped_{0};
    std::atomic<bool> lost_{false};
};
