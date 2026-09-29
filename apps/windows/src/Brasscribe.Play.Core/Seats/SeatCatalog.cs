using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Services;

namespace Brasscribe.Play.Core.Seats;

/// <summary>
/// The player's answer to "What do you play?": a seat of the contest band, "none" (I conduct or listen), or not
/// set (Not now, or never asked). Stored as the core's seat id, so every lineup resolves it through the core.
/// </summary>
public sealed record SeatChoice(string? Seat, string? Reads)
{
    /// <summary>"I conduct or listen": no part is the player's, and scores open on every part.</summary>
    public const string None = "none";

    public static readonly SeatChoice NotSet = new(null, null);
    public static readonly SeatChoice Conductor = new(None, null);

    public bool IsSet => Seat is not null;
    public bool IsConductor => Seat == None;

    /// <summary>A seat of the band (not "none", not unset): the id the engine and the core take.</summary>
    public string? SeatId => Seat is { } s && s != None ? s : null;
}

/// <summary>One tile of "What do you play?": an instrument and the seats it offers (Cornet: Solo, Repiano, 2nd, 3rd).</summary>
/// <param name="Key">The instrument id of the core ("bb-cornet").</param>
/// <param name="Label">The tile's words: an app name for the four instruments with parts, else the seat's own core name.</param>
/// <param name="SpokenLabel">The same words for screen readers, with ♭ read as "flat".</param>
/// <param name="Seats">The seats of the instrument, in score order.</param>
/// <param name="Detail">The tile's second line (the key: "E♭ cornet", "in E♭"); empty when none.</param>
public sealed record InstrumentTile(string Key, string Label, string SpokenLabel, IReadOnlyList<SeatInfo> Seats, string Detail = "")
{
    public bool HasParts => Seats.Count > 1;
    public SeatInfo Only => Seats[0];
}

/// <summary>
/// The seats as the picker shows them, from the core's <c>seats()</c> (the one table of part names, Norwegian included).
/// The tiles carry short instrument words (the mockup's, the same on every platform); the parts, Settings and
/// "(you)" use the core's seat names.
/// </summary>
public sealed class SeatCatalog
{
    private readonly IStrings _s;

    public SeatCatalog(ICoreBridge core, IStrings strings)
    {
        _s = strings;
        All = core.Seats();
        Tiles = All.GroupBy(x => x.Instrument).Select(g =>
        {
            var seats = g.ToList();
            string? key = TileKey(g.Key);
            string label = key is not null ? strings["Seat_Tile_" + key] : Name(seats[0]);
            string detail = key is not null && strings["Seat_TileDetail_" + key] is var d && d != "-" ? d : "";
            string spoken = detail.Length > 0 ? Spoken(label) + ", " + Spoken(detail) : Spoken(label);
            return new InstrumentTile(g.Key, label, spoken, seats, detail);
        }).OrderBy(t => TileOrder.IndexOf(t.Key) is var i and >= 0 ? i : int.MaxValue).ToList();
    }

    /// <summary>Every seat, in score order; empty when the core can't say (then nobody is asked).</summary>
    public IReadOnlyList<SeatInfo> All { get; }

    /// <summary>The instrument tiles, in score order.</summary>
    public IReadOnlyList<InstrumentTile> Tiles { get; }

    public bool IsAvailable => All.Count > 0;

    private bool Nb => _s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || _s.Language.StartsWith("no", StringComparison.OrdinalIgnoreCase);

    public SeatInfo? Find(string? id) => id is null ? null : All.FirstOrDefault(x => x.Id == id);

    /// <summary>The seat's part name in the UI language (the core's table).</summary>
    public string Name(SeatInfo seat) => Nb ? seat.NbName : seat.Name;

    /// <summary>A name for screen readers: "E flat Bass" (Norwegian names have no ♭).</summary>
    public string Spoken(string label) => label.Replace("♭", " flat", StringComparison.Ordinal);

    public InstrumentTile? TileOf(string? seatId) => seatId is null ? null : Tiles.FirstOrDefault(t => t.Seats.Any(x => x.Id == seatId));

    /// <summary>The words of a reading: "Treble clef in B♭", "Treble clef in E♭" or "Bass clef, as it sounds".</summary>
    public string ReadsLabel(SeatInfo seat, string reads) => _s[ReadsKey(seat, reads)];

    /// <summary>The Settings value: "1st Baritone · treble clef in B♭", "2nd Cornet", "I conduct or listen" or "Not set".</summary>
    public string Describe(SeatChoice choice)
    {
        if (!choice.IsSet) return _s["Seat_NotSet"];
        if (choice.IsConductor) return _s["Seat_None"];
        if (Find(choice.Seat) is not { } seat) return _s["Seat_NotSet"];
        string name = Name(seat);
        if (seat.Reads.Count < 2) return name;
        string reads = choice.Reads ?? seat.Reads[0];
        return _s.Format("Seat_Value", name, _s[ReadsKey(seat, reads) + "_Value"]);
    }

    private static string ReadsKey(SeatInfo seat, string reads) =>
        reads == "bass" ? "Seat_ReadsBass" : seat.Instrument.StartsWith("eb-", StringComparison.Ordinal) ? "Seat_ReadsTrebleEb" : "Seat_ReadsTrebleBb";

    /// <summary>The tile's words by the core's instrument id; an instrument the app doesn't know is named by its first seat.</summary>
    private static string? TileKey(string instrument) => instrument switch
    {
        "bb-cornet" => "Cornet",
        "eb-soprano-cornet" => "Soprano",
        "flugelhorn" => "Flugelhorn",
        "eb-tenor-horn" => "TenorHorn",
        "baritone" => "Baritone",
        "euphonium" => "Euphonium",
        "tenor-trombone" => "Trombone",
        "bass-trombone" => "BassTrombone",
        "eb-bass" => "EbBass",
        "bb-bass" => "BbBass",
        "drum-kit" => "Percussion",
        _ => null,
    };

    /// <summary>The tiles' order, as in the mockup: the cornets first, the basses and percussion last.</summary>
    private static readonly List<string> TileOrder =
        ["bb-cornet", "eb-soprano-cornet", "flugelhorn", "eb-tenor-horn", "baritone", "euphonium", "tenor-trombone", "bass-trombone", "eb-bass", "bb-bass", "drum-kit"];

    /// <summary>
    /// Instruments whose part can carry the tune (the core's Melody and Solo roles). A stopgap until the core's
    /// seat rows say it themselves; remove it then.
    /// </summary>
    private static readonly HashSet<string> TuneInstruments = ["eb-soprano-cornet", "bb-cornet", "flugelhorn", "eb-tenor-horn", "tenor-trombone", "euphonium"];

    /// <summary>The band part (by name) can carry the tune.</summary>
    public bool CarriesTune(string part) => All.FirstOrDefault(x => x.Name == part) is { } s && TuneInstruments.Contains(s.Instrument);
}
