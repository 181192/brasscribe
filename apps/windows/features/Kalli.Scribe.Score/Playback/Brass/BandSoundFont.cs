namespace Kalli.Scribe.Playback.Brass;

/// <summary>
/// The band SoundFont (sounds/band.py → brasscribe-band.sf2) with its part map from
/// sounds/mapping.json (parts[].band_soundfont): every brass part has its own preset at
/// (bank, GM program), drums are bank 128 program 0, and balance is applied as channel gain
/// (channel_gain_db), because it is not stored in the SoundFont.
/// </summary>
public sealed class BandSoundFont
{
    private BandSoundFont(PartSoundResolver resolver, string? soundFontPath)
    {
        Resolver = resolver;
        SoundFontPath = soundFontPath;
    }

    /// <summary>The SoundFont file, read only when it is applied to a player.</summary>
    public string? SoundFontPath { get; }
    public PartSoundResolver Resolver { get; }

    /// <summary>
    /// Reads the part map from mapping.json; the SoundFont file is optional (tests of the map need none).
    /// The SoundFont itself (195 MB for Windows) is read by <see cref="ApplyTo"/>, so an app can load the
    /// map before its first frame and leave the file to a background task.
    /// </summary>
    public static BandSoundFont Load(string mappingJson, string? soundFontPath = null) =>
        new(PartSoundResolver.Load(mappingJson), soundFontPath is not null && File.Exists(soundFontPath) ? soundFontPath : null);

    /// <summary>
    /// The sound of a part by its name as the arranger (or any other writer) names it: E♭ Bass,
    /// 2nd Cornet, Tenor Horn, Tuba …, then by its 0-based GM program. Null only for a non-brass part.
    /// </summary>
    public TrackSound? For(string partName, int? gmProgram = null) => Resolver.Resolve(partName, null, gmProgram)?.Sound;

    /// <summary>
    /// Routes the player's parts to this map at once, then reads and loads the SoundFont (reading and
    /// parsing a band SF2 takes a moment, so the app does both off the UI thread).
    /// </summary>
    public Task ApplyTo(AlphaTabScorePlayer player, bool inBackground = false)
    {
        player.SoundMap = For;
        if (SoundFontPath is not { } path) return Task.CompletedTask;
        if (!inBackground)
        {
            player.LoadSoundFont(File.ReadAllBytes(path));
            return Task.CompletedTask;
        }
        return Task.Run(() => player.LoadSoundFont(File.ReadAllBytes(path)));
    }
}
