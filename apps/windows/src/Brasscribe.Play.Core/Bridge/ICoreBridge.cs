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
}

public static class CoreBridge
{
    /// <summary>The native core when brasscribe_ffi loads, otherwise the managed fallback.</summary>
    public static ICoreBridge Create() => NativeCoreBridge.TryCreate() ?? (ICoreBridge)new ManagedCoreBridge();
}
