import Testing

extension Tag {
    /// Renders seconds of audio. The fast tier skips these suites by name (`make package-test-fast`,
    /// APPLE_SLOW in apps/apple/Makefile); swift test has no tag filter.
    @Tag static var slow: Self
}

import PlaybackKit

/// The band sound set the tests play, as Brasscribe Play hands it in.
let testBand = BandSoundSet(mobile: "brasscribe-band-mobile.sf2", sixteenBit: "brasscribe-band-16bit.sf2",
                            master: "brasscribe-band.sf2", supportFolder: "Brasscribe/SoundFonts")

/// Plays with the band's sounds (`BandSounds.set`), as the app does from launch.
func withTheBand() { BandSounds.set = testBand }
