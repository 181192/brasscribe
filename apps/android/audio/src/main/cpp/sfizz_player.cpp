// Realistic playback tier: sfizz (BSD-2) instruments rendered into an Oboe output stream.
//
// One synth per MIDI channel (a part). Note events from Kotlin are queued under a mutex and applied at
// the start of the next audio callback; the callback only try-locks, so it never blocks on the UI.
//
// Score playback is not latency-critical (events are scheduled 0.25 s ahead), so the stream asks for
// no low-latency path and a buffer of several bursts: an underrun there is an audible gap, which is
// the worst failure a player can have. Stop and seek release the sounding notes (their SFZ release)
// instead of cutting them.
#include <android/log.h>
#include <oboe/Oboe.h>
#include <sfizz.h>

#include <algorithm>
#include <array>
#include <memory>
#include <mutex>
#include <vector>

#include "sfizz_bridge.h"

#define LOG_TAG "brasscribe-sfizz"

namespace {

constexpr int kChannels = 32;
constexpr int kBlock = 256;
constexpr int kBufferBursts = 4;
// Floats of every sample kept in memory; sfizz streams the rest from storage on a background thread.
// sfizz's default (8192) is 0.19 s at 44.1 kHz: a slow phone read then plays silence. 32768 covers the
// attack and first 0.7 s of every note while keeping a band of ~17 parts near 100 MB.
constexpr unsigned kPreloadFloats = 32768;

struct Event {
    int channel;
    int note;
    int velocity;  // 0 = note off
    long long atFrame;  // absolute output frame; <= now plays at the start of the next block
};

class Player : public oboe::AudioStreamDataCallback {
public:
    ~Player() { close(); }

    bool open(int sampleRate) {
        close();
        oboe::AudioStreamBuilder b;
        b.setDirection(oboe::Direction::Output)
            ->setPerformanceMode(oboe::PerformanceMode::None)
            ->setSharingMode(oboe::SharingMode::Shared)
            ->setFormat(oboe::AudioFormat::Float)
            ->setChannelCount(oboe::ChannelCount::Stereo)
            ->setUsage(oboe::Usage::Media)
            ->setContentType(oboe::ContentType::Music)
            ->setDataCallback(this);
        if (sampleRate > 0) b.setSampleRate(sampleRate);
        if (b.openStream(stream_) != oboe::Result::OK) return false;
        rate_ = stream_->getSampleRate();
        const int burst = stream_->getFramesPerBurst();
        if (burst > 0) stream_->setBufferSizeInFrames(std::min(stream_->getBufferCapacityInFrames(), burst * kBufferBursts));
        __android_log_print(ANDROID_LOG_INFO, LOG_TAG, "stream %d Hz, burst %d, buffer %d frames", rate_, burst,
                            stream_->getBufferSizeInFrames());
        {
            std::lock_guard<std::mutex> g(mutex_);
            for (auto& s : synths_) if (s) configure(s);
        }
        return stream_->requestStart() == oboe::Result::OK;
    }

    void close() {
        if (stream_) {
            auto xruns = stream_->getXRunCount();
            if (xruns && xruns.value() > 0)
                __android_log_print(ANDROID_LOG_WARN, LOG_TAG, "stream closed after %d underruns", xruns.value());
            stream_->requestStop();
            stream_->close();
            stream_.reset();
        }
    }

    sfizz_synth_t* synth(int ch) {
        if (ch < 0 || ch >= kChannels) return nullptr;
        if (!synths_[ch]) {
            synths_[ch] = sfizz_create_synth();
            configure(synths_[ch]);
        }
        return synths_[ch];
    }

    void configure(sfizz_synth_t* s) {
        sfizz_set_sample_rate(s, static_cast<float>(rate_));
        sfizz_set_samples_per_block(s, kBlock);
        sfizz_set_preload_size(s, kPreloadFloats);
    }

    bool load(int ch, const std::string& path, const std::string* text) {
        std::lock_guard<std::mutex> g(mutex_);
        auto* s = synth(ch);
        if (!s) return false;
        const bool ok = text ? sfizz_load_string(s, path.c_str(), text->c_str()) : sfizz_load_file(s, path.c_str());
        loaded_[ch] = ok && sfizz_get_num_regions(s) > 0;
        return loaded_[ch];
    }

    int regions(int ch) {
        std::lock_guard<std::mutex> g(mutex_);
        return (ch >= 0 && ch < kChannels && synths_[ch]) ? sfizz_get_num_regions(synths_[ch]) : 0;
    }

    void push(Event e) {
        std::lock_guard<std::mutex> g(mutex_);
        pending_.push_back(e);
    }

    /** Queues an event [delaySeconds] after the current output position. */
    void pushDelayed(int channel, int note, int velocity, double delaySeconds) {
        std::lock_guard<std::mutex> g(mutex_);
        const long long at = frame_ + static_cast<long long>(std::max(0.0, delaySeconds) * rate_);
        pending_.push_back({channel, note, velocity, at});
    }

    double positionSeconds() {
        std::lock_guard<std::mutex> g(mutex_);
        return static_cast<double>(frame_) / rate_;
    }

    /** Hard cut: every voice silenced at once (only for tearing the tier down). */
    void allOff() {
        std::lock_guard<std::mutex> g(mutex_);
        pending_.clear();
        for (auto& s : synths_) if (s) sfizz_all_sound_off(s);
        for (auto& h : held_) h.fill(0);
    }

    /**
     * The user pressed stop: queued events are dropped and the output fades to silence over
     * [seconds] (no click, no ringing on), then every voice is cut and the gain restored.
     */
    void fadeOut(double seconds) {
        std::lock_guard<std::mutex> g(mutex_);
        pending_.clear();
        fadeTotal_ = std::max(1, static_cast<int>(seconds * rate_));
        fadeLeft_ = fadeTotal_;
    }

    /** Seek: drops events not yet played and releases every held note (its SFZ release plays out). */
    void releaseAll() {
        std::lock_guard<std::mutex> g(mutex_);
        pending_.clear();
        for (int ch = 0; ch < kChannels; ++ch) {
            for (int note = 0; note < 128; ++note) {
                if (held_[ch][note] > 0) pending_.push_back({ch, note, 0, 0});
            }
        }
    }

    void setGain(int ch, float gain) {
        std::lock_guard<std::mutex> g(mutex_);
        if (ch >= 0 && ch < kChannels) gains_[ch] = gain;
    }

    int activeVoices() {
        std::lock_guard<std::mutex> g(mutex_);
        int n = 0;
        for (auto& s : synths_) if (s) n += sfizz_get_num_active_voices(s);
        return n;
    }

    // Renders into interleaved stereo; caller holds the lock.
    void renderLocked(float* out, int frames) {
        std::fill(out, out + frames * 2, 0.f);
        int done = 0;
        while (done < frames) {
            const int n = std::min(kBlock, frames - done);
            // Events due in this block go to sfizz with their offset inside it (sample-accurate).
            const long long blockStart = frame_;
            auto due = std::stable_partition(pending_.begin(), pending_.end(),
                                             [&](const Event& e) { return e.atFrame >= blockStart + n; });
            for (auto it = due; it != pending_.end(); ++it) {
                auto* s = synths_[it->channel];
                if (!s) continue;
                const int delay = static_cast<int>(std::max<long long>(0, it->atFrame - blockStart));
                auto& held = held_[it->channel][it->note & 127];
                if (it->velocity > 0) {
                    sfizz_send_note_on(s, delay, it->note, it->velocity);
                    held = static_cast<unsigned char>(std::min(255, held + 1));
                } else {
                    sfizz_send_note_off(s, delay, it->note, 0);
                    held = 0;  // a note-off ends every voice of this pitch in sfizz
                }
            }
            std::array<bool, kChannels> touched{};
            for (auto it = due; it != pending_.end(); ++it)
                if (it->channel >= 0 && it->channel < kChannels) touched[it->channel] = true;
            pending_.erase(due, pending_.end());
            for (int ch = 0; ch < kChannels; ++ch) {
                auto* s = synths_[ch];
                if (!s || !loaded_[ch]) continue;
                // An idle synth (no voice, nothing queued this block) adds nothing: skip its render.
                if (!touched[ch] && sfizz_get_num_active_voices(s) == 0) continue;
                float* bufs[2] = {left_.data(), right_.data()};
                sfizz_render_block(s, bufs, 2, n);
                const float g = gains_[ch];
                for (int i = 0; i < n; ++i) {
                    out[(done + i) * 2] += left_[i] * g;
                    out[(done + i) * 2 + 1] += right_[i] * g;
                }
            }
            if (fadeLeft_ > 0) {
                for (int i = 0; i < n; ++i) {
                    const float k = fadeLeft_ > 0 ? static_cast<float>(fadeLeft_) / fadeTotal_ : 0.f;
                    out[(done + i) * 2] *= k;
                    out[(done + i) * 2 + 1] *= k;
                    if (fadeLeft_ > 0) --fadeLeft_;
                }
                if (fadeLeft_ == 0) {
                    for (auto* s : synths_) if (s) sfizz_all_sound_off(s);
                    for (auto& h : held_) h.fill(0);
                }
            }
            done += n;
            frame_ += n;
        }
    }

    int renderOffline(float* out, int frames) {
        std::lock_guard<std::mutex> g(mutex_);
        renderLocked(out, frames);
        return frames;
    }

    oboe::DataCallbackResult onAudioReady(oboe::AudioStream*, void* data, int32_t frames) override {
        auto* out = static_cast<float*>(data);
        std::unique_lock<std::mutex> lock(mutex_, std::try_to_lock);
        if (!lock.owns_lock()) {
            std::fill(out, out + frames * 2, 0.f);
            return oboe::DataCallbackResult::Continue;
        }
        renderLocked(out, frames);
        return oboe::DataCallbackResult::Continue;
    }

private:
    std::shared_ptr<oboe::AudioStream> stream_;
    std::mutex mutex_;
    std::array<sfizz_synth_t*, kChannels> synths_{};
    std::array<bool, kChannels> loaded_{};
    std::array<float, kChannels> gains_ = [] { std::array<float, kChannels> g{}; g.fill(1.f); return g; }();
    std::array<std::array<unsigned char, 128>, kChannels> held_{};
    int fadeTotal_ = 1;
    int fadeLeft_ = 0;
    std::vector<Event> pending_;
    std::array<float, kBlock> left_{};
    std::array<float, kBlock> right_{};
    int rate_ = 48000;
    long long frame_ = 0;
};

Player& player() {
    static Player p;
    return p;
}

}  // namespace

namespace sfizz_bridge {
bool available() { return true; }
bool start(int sampleRate) { return player().open(sampleRate); }
void stop() { player().close(); }
bool loadFile(int channel, const std::string& path) { return player().load(channel, path, nullptr); }
bool loadString(int channel, const std::string& sfz, const std::string& virtualPath) { return player().load(channel, virtualPath, &sfz); }
int regions(int channel) { return player().regions(channel); }
void noteOn(int channel, int note, int velocity) { player().push({channel, note, std::max(1, velocity), 0}); }
void noteOff(int channel, int note) { player().push({channel, note, 0, 0}); }
void noteAt(int channel, int note, int velocity, double delaySeconds) { player().pushDelayed(channel, note, velocity, delaySeconds); }
double positionSeconds() { return player().positionSeconds(); }
void allOff() { player().allOff(); }
void releaseAll() { player().releaseAll(); }
void fadeOut(double seconds) { player().fadeOut(seconds); }
void setGain(int channel, float gain) { player().setGain(channel, gain); }
int renderOffline(float* interleaved, int frames) { return player().renderOffline(interleaved, frames); }
int activeVoices() { return player().activeVoices(); }
}  // namespace sfizz_bridge
