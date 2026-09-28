#pragma once

#include <cmath>

// The output stage every Play app shares (sounds/playback-levels.json): make-up gain, then a
// memoryless soft limiter, linear up to kThreshold and tanh towards kCeiling above it. No attack or
// release, so it cannot pump; below the threshold every part keeps its level. The Kotlin twin is
// no.brasscribe.play.audio.OutputStage; both are tested against sounds/output-stage-vectors.json.
namespace output_stage {

constexpr float kThreshold = 0.8f;
constexpr float kCeiling = 0.98f;

inline float limit(float x) {
    const float a = std::fabs(x);
    if (a <= kThreshold) return x;
    constexpr float knee = kCeiling - kThreshold;
    return std::copysign(kThreshold + knee * std::tanh((a - kThreshold) / knee), x);
}

}  // namespace output_stage
