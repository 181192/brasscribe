using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;

namespace Kalli.Scribe.Tab;

/// <summary>The instruments of "Your instrument", in the order they are listed (<see cref="Instruments.Kinds"/>).</summary>
public enum Instrument
{
    Guitar,
    Bass,
    /// <summary>Soprano, concert and tenor are one kind: they are tuned alike. The baritone is tuned as a guitar's top four strings.</summary>
    Ukulele,
    Mandolin,
}

public static class Instruments
{
    /// <summary>Every instrument, in the order they are listed.</summary>
    public static IReadOnlyList<Instrument> All { get; } = Enum.GetValues<Instrument>();

    /// <summary>The kinds of it that can be chosen: a guitar or a bass by its number of strings, a ukulele by its size.</summary>
    public static IReadOnlyList<FrettedInstrument> Kinds(this Instrument instrument) => instrument switch
    {
        Instrument.Guitar => [FrettedInstrument.Guitar6, FrettedInstrument.Guitar7, FrettedInstrument.Guitar8],
        Instrument.Bass => [FrettedInstrument.Bass4, FrettedInstrument.Bass5, FrettedInstrument.Bass6],
        Instrument.Ukulele => [FrettedInstrument.Ukulele, FrettedInstrument.UkuleleBaritone],
        _ => [FrettedInstrument.Mandolin],
    };

    /// <summary>A capo is used on it: asked about on Check the song.</summary>
    public static bool TakesCapo(this Instrument instrument) => instrument is Instrument.Guitar or Instrument.Ukulele;

    /// <summary>The instrument <paramref name="kind"/> is a kind of; null for one this version does not offer.</summary>
    public static Instrument? Of(FrettedInstrument kind)
    {
        foreach (var i in All) if (i.Kinds().Contains(kind)) return i;
        return null;
    }
}

/// <summary>
/// Which hand frets. Tab is the same for all three; chord boxes and the fretboard turn round for the two
/// right-hand setups. <see cref="YourInstrumentStore"/> keeps them by <see cref="TabEnums.Id(FrettingHand)"/>.
/// </summary>
public enum FrettingHand
{
    /// <summary>The left hand frets: most players.</summary>
    Left,
    /// <summary>The right hand frets, on an instrument strung for it.</summary>
    Right,
    /// <summary>The right hand frets on an ordinary instrument turned upside down: the low string is nearest the floor.</summary>
    RightUpsideDown,
}

/// <summary>What the player reads. Its id is the engine's <c>layout</c>.</summary>
public enum Reads
{
    Tab,
    TabAndNotation,
    Notation,
}

public static class TabEnums
{
    public static string Id(this FrettingHand hand) => hand switch
    {
        FrettingHand.Left => "left",
        FrettingHand.Right => "right",
        _ => "right-upside-down",
    };

    public static string Id(this Reads reads) => reads switch
    {
        Reads.Tab => "tab",
        Reads.TabAndNotation => "tab-and-notation",
        _ => "notation",
    };

    /// <summary>The engine's layout for what the player reads.</summary>
    public static TabLayout Layout(this Reads reads) => WireEnum<TabLayout>.Of(reads.Id());
}

/// <summary>The options of a <c>tab</c> job that come from the player's instrument, as the engine's ids.</summary>
public sealed record TabJobOptions(string Instrument, string Tuning, string Layout);

/// <summary>
/// The player's answer to "Your instrument": what new tabs are written for. A song already written keeps the
/// instrument it was made for.
///
/// <see cref="Kind"/> is the engine's instrument and <see cref="Tuning"/> one of the tunings the engine has for
/// it ("standard", "drop-d", "high-g"); together they name a preset of the core's <c>target-fretted</c> crate
/// (<see cref="Preset"/>, "guitar-drop-d").
/// </summary>
public sealed record YourInstrument
{
    /// <summary>A null <paramref name="tuning"/> is the kind's usual one.</summary>
    public YourInstrument(FrettedInstrument kind = FrettedInstrument.Guitar6, string? tuning = null,
        FrettingHand hand = FrettingHand.Left, Reads reads = Reads.Tab)
    {
        Kind = kind;
        Tuning = tuning ?? kind.DefaultTuning();
        Hand = hand;
        Reads = reads;
    }

    public FrettedInstrument Kind { get; init; }
    public string Tuning { get; init; }
    public FrettingHand Hand { get; init; }
    public Reads Reads { get; init; }

    /// <summary>"Not now": a six-string guitar in standard tuning, the left hand frets, tab.</summary>
    public static YourInstrument Default { get; } = new();

    /// <summary>Guitar, bass, ukulele or mandolin.</summary>
    public Instrument Instrument => Instruments.Of(Kind) ?? Instruments.Of(Default.Kind)!.Value;

    /// <summary>The number of strings, for a guitar or a bass (they are chosen by it); null for the others.</summary>
    public int? Strings => StringsOf(Kind);

    /// <summary>The engine's <c>instrument</c>: "guitar-6", "bass-4", "ukulele", "mandolin".</summary>
    public string Family => Valid().Kind.Id()!;

    /// <summary>The crate's preset id for this instrument in this tuning.</summary>
    public string Preset { get { var v = Valid(); return v.Kind.Preset(v.Tuning); } }

    /// <summary>The tunings offered for this instrument, its usual one first.</summary>
    public IReadOnlyList<string> Tunings => Kind.Tunings();

    /// <summary>Another instrument: its first kind in its usual tuning. The same instrument changes nothing.</summary>
    public YourInstrument WithInstrument(Instrument other)
    {
        if (other == Instrument) return this;
        var kind = other.Kinds()[0];
        return this with { Kind = kind, Tuning = kind.DefaultTuning() };
    }

    /// <summary>Another kind of the instrument: the tuning stays when the new kind has it, and is its usual one otherwise.</summary>
    public YourInstrument WithKind(FrettedInstrument other) => (this with { Kind = other }).Valid();

    /// <summary>
    /// This answer with every part that can't be chosen replaced by its default: an instrument this version does
    /// not offer, a tuning the instrument has no preset for.
    /// </summary>
    public YourInstrument Valid()
    {
        if (Instruments.Of(Kind) is null) return this with { Kind = Default.Kind, Tuning = Default.Tuning };
        return Kind.Tunings().Contains(Tuning) ? this : this with { Tuning = Kind.DefaultTuning() };
    }

    /// <summary>What a job is asked for. The fretting hand changes only how things are drawn, so it is not among them.</summary>
    public TabJobOptions JobOptions()
    {
        var v = Valid();
        return new TabJobOptions(v.Kind.Id()!, v.Tuning, v.Reads.Id());
    }

    /// <summary>The number of strings a guitar or a bass is chosen by ("guitar-7" has 7); null for a ukulele and a mandolin.</summary>
    public static int? StringsOf(FrettedInstrument kind)
    {
        if (Instruments.Of(kind) is not (Instrument.Guitar or Instrument.Bass)) return null;
        var id = kind.Id();
        return id is not null && int.TryParse(id[(id.LastIndexOf('-') + 1)..], System.Globalization.NumberStyles.None,
            System.Globalization.CultureInfo.InvariantCulture, out int n) ? n : null;
    }
}

/// <summary>
/// Keeps the answer in the device's settings. Anything stored that this version can't offer reads as its default.
/// </summary>
public sealed class YourInstrumentStore(ISettingsStore store)
{
    /// <summary>The engine's instrument id.</summary>
    public const string KindKey = "fret_kind";
    public const string TuningKey = "fret_tuning";
    public const string HandKey = "fret_hand";
    public const string ReadsKey = "fret_reads";

    public YourInstrument Load()
    {
        string? id = store.Get<string?>(KindKey, null);
        FrettedInstrument? stored = Instruments.All.SelectMany(i => i.Kinds()).Cast<FrettedInstrument?>().FirstOrDefault(k => k!.Value.Id() == id);
        var kind = stored ?? YourInstrument.Default.Kind;
        string? hand = store.Get<string?>(HandKey, null);
        string? reads = store.Get<string?>(ReadsKey, null);
        return new YourInstrument(
            kind,
            // A tuning stored for an instrument this version can't read says nothing about the default one.
            stored is null ? null : store.Get<string?>(TuningKey, null),
            Enum.GetValues<FrettingHand>().Cast<FrettingHand?>().FirstOrDefault(h => h!.Value.Id() == hand) ?? YourInstrument.Default.Hand,
            Enum.GetValues<Reads>().Cast<Reads?>().FirstOrDefault(r => r!.Value.Id() == reads) ?? YourInstrument.Default.Reads).Valid();
    }

    public void Save(YourInstrument value)
    {
        var v = value.Valid();
        store.Set(KindKey, v.Kind.Id()!);
        store.Set(TuningKey, v.Tuning);
        store.Set(HandKey, v.Hand.Id());
        store.Set(ReadsKey, v.Reads.Id());
    }
}
