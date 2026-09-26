// Built when no sfizz checkout is configured (-Pbrasscribe.sfizzDir). Every call reports the realistic
// tier as unavailable, and the app falls back to the alphaTab synth with its SoundFont.
#include "sfizz_bridge.h"

namespace sfizz_bridge {
bool available() { return false; }
bool start(int) { return false; }
void stop() {}
bool loadFile(int, const std::string&) { return false; }
bool loadString(int, const std::string&, const std::string&) { return false; }
int regions(int) { return 0; }
void noteOn(int, int, int) {}
void noteOff(int, int) {}
void allOff() {}
void setGain(int, float) {}
int renderOffline(float*, int) { return 0; }
int activeVoices() { return 0; }
}  // namespace sfizz_bridge
