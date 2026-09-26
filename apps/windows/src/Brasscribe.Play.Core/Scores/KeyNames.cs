namespace Brasscribe.Play.Core.Scores;

/// <summary>
/// Key names for people: "B♭ major" / "B-dur", and the written key a transposing instrument reads
/// for a concert key (a B♭ cornet reads D major when the band sounds C major).
/// </summary>
public static class KeyNames
{
    private static readonly string[] En = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
    private static readonly string[] Nb = ["C", "Dess", "D", "Ess", "E", "F", "Fiss", "G", "Ass", "A", "B", "H"];

    /// <summary>Tonics as Brasscribe on your computer and the core take them, by pitch class.</summary>
    public static readonly string[] Tonics = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];

    public static int PitchClassOf(string tonic) => Array.IndexOf(Tonics, tonic.TrimEnd('m'));

    /// <summary>The tonic pitch class of a key signature (major, or minor a minor third below).</summary>
    public static int TonicOf(int fifths, bool minor) => Mod(7 * fifths + (minor ? 9 : 0), 12);

    public static string Tonic(int pitchClass, bool nb) => (nb ? Nb : En)[Mod(pitchClass, 12)];

    /// <summary>"B♭ major", "g minor" in Norwegian style ("B-dur", "g-moll").</summary>
    public static string Name(int pitchClass, bool minor, bool nb)
    {
        string t = Tonic(pitchClass, nb);
        if (nb) return minor ? $"{t.ToLowerInvariant()}-moll" : $"{t}-dur";
        return minor ? $"{t} minor" : $"{t} major";
    }

    /// <summary>The written tonic for an instrument whose sound is <paramref name="chromatic"/> semitones from its written notes.</summary>
    public static int WrittenOf(int concertPitchClass, int chromatic) => Mod(concertPitchClass - chromatic, 12);

    /// <summary>The instrument's key as players say it: "B♭", "E♭", "F"; null for C instruments.</summary>
    public static string? InstrumentKey(int chromatic, bool nb) => Mod(chromatic, 12) switch
    {
        0 => null,
        var pc => Tonic(pc, nb),
    };

    private static int Mod(int a, int m) => ((a % m) + m) % m;
}
