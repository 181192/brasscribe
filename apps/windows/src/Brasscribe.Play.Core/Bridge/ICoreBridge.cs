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
}

public static class CoreBridge
{
    /// <summary>The native core when brasscribe_ffi loads, otherwise the managed fallback.</summary>
    public static ICoreBridge Create() => NativeCoreBridge.TryCreate() ?? (ICoreBridge)new ManagedCoreBridge();
}
