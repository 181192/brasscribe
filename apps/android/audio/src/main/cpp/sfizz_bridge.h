#pragma once

#include <string>

// The realistic playback tier: one sfizz synth per MIDI channel (one per part), mixed into an Oboe
// output stream. sfizz_player.cpp implements it; sfizz_stub.cpp reports it as unavailable.
namespace sfizz_bridge {
bool available();
bool start(int sampleRate);
void stop();
bool loadFile(int channel, const std::string& path);
bool loadString(int channel, const std::string& sfz, const std::string& virtualPath);
int regions(int channel);
void noteOn(int channel, int note, int velocity);
void noteOff(int channel, int note);
// Note on (velocity > 0) or off (0) [delaySeconds] after the current output position, sample-accurate.
void noteAt(int channel, int note, int velocity, double delaySeconds);
// Output position (seconds of audio rendered).
double positionSeconds();
void allOff();
// Drops queued events and releases every held note (the SFZ release plays out).
void releaseAll();
// Stop: drops queued events, fades the output to silence over [seconds], then cuts every voice.
void fadeOut(double seconds);
void setGain(int channel, float gain);
// Renders frames offline into interleaved stereo (used by tests and for exporting audio).
int renderOffline(float* interleaved, int frames);
int activeVoices();
}  // namespace sfizz_bridge
