using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Bridge;

/// <summary>
/// The shared symbolic core as the app sees it. The native implementation calls the Rust core
/// (brasscribe_ffi); the managed one decodes Composition JSON directly and uses the C# talking-score
/// code. The app only talks to this interface, so the switch is one line in the composition root.
/// </summary>
public interface ICoreBridge
{
    /// <summary>"managed" or the native core's version string.</summary>
    string Version { get; }
    bool IsNative { get; }

    /// <summary>Parses (and, natively, validates and normalises) Composition JSON.</summary>
    Composition ParseComposition(string json);

    /// <summary>Talking-score structure from the arranged MusicXML and the Composition behind it.</summary>
    TalkingScoreDocument BuildTalkingScore(string musicXml, Composition? composition);

    string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context, TalkingScoreSettings settings, bool byBar = false);

    /// <summary>Arranges a Composition to brass-band MusicXML on the device, or null when this core cannot.</summary>
    string? ArrangeMusicXml(Composition composition, string arranger = "auto");

    /// <summary>
    /// Arranges a Composition again for a lineup (band, small band or quartet), difficulty and key,
    /// and returns MusicXML, or null when this core cannot.
    /// </summary>
    string? ArrangeMusicXmlWith(Composition composition, ArrangementOptions options);

    /// <summary>
    /// Arranges a score from the layered pipeline's stage files (layer MIDI, stems, beats, solo contour)
    /// with a lineup, difficulty and key, or null when this core cannot.
    /// </summary>
    BandArrangement? ArrangeLayersBand(LayerInputs inputs, string title, ArrangementOptions options);

    /// <summary>Humanized timing and velocity for one player's notes, or null when this core has no humanizer.</summary>
    HumanizedPart? Humanize(IReadOnlyList<HumanizeNote> notes, string part, int player, string? compositionJson);

    /// <summary>The 18 seats of the contest band in score order, for "What do you play?"; empty when this core has none.</summary>
    IReadOnlyList<SeatInfo> Seats();

    /// <summary>The player's part in a lineup (the core's name: band, minimal, quartet) for a seat id; null when this core can't say.</summary>
    SeatPart? SeatPartFor(string lineup, string seat);

    /// <summary>Where each part of a Composition's arrangement comes from (your-recording, recording, arranged); empty when unknown.</summary>
    IReadOnlyDictionary<string, string> PartSources(string compositionJson);

    /// <summary>A part's name in Norwegian from the core's one table; the name unchanged when the core doesn't know it.</summary>
    string PartNameNb(string name);
}

/// <summary>One seat of the contest band (the core's <c>bc_seats</c>).</summary>
/// <param name="Id">The seat option value ("2nd-cornet").</param>
/// <param name="Name">The part's name ("2nd Cornet").</param>
/// <param name="NbName">The part's Norwegian name ("2. kornett").</param>
/// <param name="Instrument">The instrument id ("bb-cornet", "euphonium").</param>
/// <param name="Clef">The band part's own clef.</param>
/// <param name="Reads">The clefs a player of this seat may read, the band's own first; empty for percussion.</param>
public sealed record SeatInfo(string Id, string Name, string NbName, string Instrument, string Clef, IReadOnlyList<string> Reads);

/// <summary>The player's part in a lineup for their seat (the core's <c>bc_seat_part</c>).</summary>
/// <param name="Part">The lineup's part; null when the lineup has none (percussion in the small band).</param>
/// <param name="Exact">The seat's own part.</param>
/// <param name="SameKey">The part is in the seat's key, so it reads without transposing.</param>
public sealed record SeatPart(string? Part, bool Exact, bool SameKey);

/// <summary>The three sources of a part (the core's <c>part_sources</c>).</summary>
public static class PartSource
{
    public const string YourRecording = "your-recording";
    public const string Recording = "recording";
    public const string Arranged = "arranged";
}

public sealed class ManagedCoreBridge : ICoreBridge
{
    public string Version => "managed";
    public bool IsNative => false;

    public Composition ParseComposition(string json) => CompositionJson.Parse(json);

    public TalkingScoreDocument BuildTalkingScore(string musicXml, Composition? composition) =>
        MusicXmlTalkingScoreBuilder.Build(musicXml, composition);

    public string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext context, TalkingScoreSettings settings, bool byBar = false) =>
        Announcer.Announce(part, bar, ev, context, settings, byBar);

    /// <summary>Arranging needs the Rust core or the engine; the managed bridge has no arranger.</summary>
    public string? ArrangeMusicXml(Composition composition, string arranger = "auto") => null;

    public string? ArrangeMusicXmlWith(Composition composition, ArrangementOptions options) => null;

    public BandArrangement? ArrangeLayersBand(LayerInputs inputs, string title, ArrangementOptions options) => null;

    /// <summary>Without the core, playback keeps the score's exact timing.</summary>
    public HumanizedPart? Humanize(IReadOnlyList<HumanizeNote> notes, string part, int player, string? compositionJson) => null;

    /// <summary>The seats and their parts come from the core only; without it nobody is asked.</summary>
    public IReadOnlyList<SeatInfo> Seats() => [];

    public SeatPart? SeatPartFor(string lineup, string seat) => null;

    public IReadOnlyDictionary<string, string> PartSources(string compositionJson) => new Dictionary<string, string>();

    public string PartNameNb(string name) => name;
}

public static class CoreBridge
{
    /// <summary>The native core when brasscribe_ffi loads, otherwise the managed fallback.</summary>
    public static ICoreBridge Create() => NativeCoreBridge.TryCreate() ?? (ICoreBridge)new ManagedCoreBridge();
}
