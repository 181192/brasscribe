package no.kalli.fretscribe;

import alphaTab.core.ecmaScript.Float32Array;
import alphaTab.core.ecmaScript.Set;
import alphaTab.io.IReadable;
import alphaTab.synth.soundfont.Hydra;
import alphaTab.synth.synthesis.TinySoundFont;

/**
 * alphaTab's SoundFont synthesizer on its own, without alphaTab's player: one program on one channel.
 * The synthesizer's classes are internal to alphaTab's Kotlin (its player is their only user there), so
 * they are reached from Java, which reads them as they are compiled. SoundFontVoicesTest plays through
 * them, and fails when a new alphaTab has changed them.
 */
final class SoundFontSynth {
    private final TinySoundFont synth;

    SoundFontSynth(IReadable soundFont, double program, double sampleRate) {
        synth = new TinySoundFont(sampleRate);
        Hydra hydra = new Hydra();
        hydra.load(soundFont);
        Set<Double> programs = new Set<>();
        programs.add(program);
        synth.loadPresets(hydra, programs, new Set<>(), false);
        if (!synth.hasSamplesForProgram(program)) throw new IllegalStateException("the SoundFont has no program " + program);
        synth.channelSetPresetNumber(0, program, false);
    }

    void noteOn(double key, double velocity) {
        synth.channelNoteOn(0, key, velocity);
    }

    void noteOff(double key) {
        synth.channelNoteOff(0, key);
    }

    void soundsOff() {
        synth.channelSoundsOffAll(0);
    }

    /** Renders frames stereo frames into the buffer from the sample at. */
    void render(Float32Array buffer, double at, double frames) {
        synth.synthesize(buffer, at, frames);
    }
}
