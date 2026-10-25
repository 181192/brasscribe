import PlaybackKit

/// What makes Brasscribe Play's playback a brass band's.
enum BrassBand {
    /// The band SoundFont (data/sounds/band, `make bandsound`), and where a player may add sounds of their own.
    static let sounds = BandSoundSet(mobile: "brasscribe-band-mobile.sf2", sixteenBit: "brasscribe-band-16bit.sf2",
                                     master: "brasscribe-band.sf2", supportFolder: "Brasscribe/SoundFonts",
                                     repositorySounds: "data/sounds/band", repositoryMapping: "sounds")
}
