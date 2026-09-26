// Realistic playback tier: sfizz (BSD-2) instruments rendered into an Oboe output stream.
//
// One synth per MIDI channel (a part). Note events from Kotlin are queued under a mutex and applied at
// the start of the next audio callback; the callback only try-locks, so it never blocks on the UI.
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

constexpr int kChannels = 16;
constexpr int kBlock = 256;

struct Event {
    int channel;
    int note;
    int velocity;  // 0 = note off
};

class Player : public oboe::AudioStreamDataCallback {
public:
    ~Player() { close(); }

    bool open(int sampleRate) {
        close();
        oboe::AudioStreamBuilder b;
        b.setDirection(oboe::Direction::Output)
            ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
            ->setSharingMode(oboe::SharingMode::Shared)
            ->setFormat(oboe::AudioFormat::Float)
            ->setChannelCount(oboe::ChannelCount::Stereo)
            ->setUsage(oboe::Usage::Media)
            ->setContentType(oboe::ContentType::Music)
            ->setDataCallback(this);
        if (sampleRate > 0) b.setSampleRate(sampleRate);
        if (b.openStream(stream_) != oboe::Result::OK) return false;
        rate_ = stream_->getSampleRate();
        {
            std::lock_guard<std::mutex> g(mutex_);
            for (auto& s : synths_) if (s) configure(s);
        }
        return stream_->requestStart() == oboe::Result::OK;
    }

    void close() {
        if (stream_) {
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

    void allOff() {
        std::lock_guard<std::mutex> g(mutex_);
        pending_.clear();
        for (auto& s : synths_) if (s) sfizz_all_sound_off(s);
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
        for (const auto& e : pending_) {
            auto* s = synths_[e.channel];
            if (!s) continue;
            if (e.velocity > 0) sfizz_send_note_on(s, 0, e.note, e.velocity);
            else sfizz_send_note_off(s, 0, e.note, 0);
        }
        pending_.clear();
        std::fill(out, out + frames * 2, 0.f);
        int done = 0;
        while (done < frames) {
            const int n = std::min(kBlock, frames - done);
            for (int ch = 0; ch < kChannels; ++ch) {
                auto* s = synths_[ch];
                if (!s || !loaded_[ch]) continue;
                float* bufs[2] = {left_.data(), right_.data()};
                sfizz_render_block(s, bufs, 2, n);
                const float g = gains_[ch];
                for (int i = 0; i < n; ++i) {
                    out[(done + i) * 2] += left_[i] * g;
                    out[(done + i) * 2 + 1] += right_[i] * g;
                }
            }
            done += n;
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
    std::array<float, kChannels> gains_{1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};
    std::vector<Event> pending_;
    std::array<float, kBlock> left_{};
    std::array<float, kBlock> right_{};
    int rate_ = 48000;
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
void noteOn(int channel, int note, int velocity) { player().push({channel, note, std::max(1, velocity)}); }
void noteOff(int channel, int note) { player().push({channel, note, 0}); }
void allOff() { player().allOff(); }
void setGain(int channel, float gain) { player().setGain(channel, gain); }
int renderOffline(float* interleaved, int frames) { return player().renderOffline(interleaved, frames); }
int activeVoices() { return player().activeVoices(); }
}  // namespace sfizz_bridge
