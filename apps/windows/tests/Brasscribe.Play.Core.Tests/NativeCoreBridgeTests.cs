using AlphaTab.Midi;
using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// The Rust core through its C ABI. Runs when BRASSCRIBE_FFI_PATH points at a built
/// brasscribe_ffi (libbrasscribe_ffi.dylib, .so or brasscribe_ffi.dll); skipped otherwise.
/// </summary>
[Collection(AlphaTabCollection.Name)]
public class NativeCoreBridgeTests(ITestOutputHelper log)
{
    /// <summary>Notes, chords and unpitched notes of the golden arrangement (data/golden/mikkel-arranged-band).</summary>
    private const int GoldenNotes = 5949;

    private const string MikkelTitle = "Mikkel — solo cornet & brass band (draft)";

    private static NativeCoreBridge? Bridge()
    {
        if (Environment.GetEnvironmentVariable("BRASSCRIBE_FFI_PATH") is not { Length: > 0 }) return null;
        var bridge = NativeCoreBridge.TryCreate();
        Assert.NotNull(bridge); // the path is set: the library must load
        return bridge;
    }

    [Fact]
    public void Normalizes_and_arranges_the_golden_composition()
    {
        var bridge = Bridge();
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (bridge is null || json is null || golden is null) return;

        log.WriteLine($"native core {bridge.Version}");
        Assert.True(bridge.IsNative);
        var composition = bridge.ParseComposition(File.ReadAllText(json));
        Assert.Equal(5, composition.Voices.Count);

        var xml = bridge.ArrangeMusicXml(composition, "layers")!;
        var mine = MusicXmlTalkingScoreBuilder.Build(xml);
        var reference = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(golden));
        Assert.Equal(reference.Parts.Select(p => p.Name), mine.Parts.Select(p => p.Name));
        for (int p = 0; p < reference.Parts.Count; p++)
            log.WriteLine($"{reference.Parts[p].Name}: reference {Notes(reference.Parts[p])} notes, core {Notes(mine.Parts[p])}");
        Assert.Equal(GoldenNotes, reference.Parts.Sum(Notes));
        Assert.Equal(GoldenNotes, mine.Parts.Sum(Notes));
    }

    [Fact]
    public void Arranges_the_golden_from_its_layer_inputs()
    {
        var bridge = Bridge();
        var layers = TestPaths.RepoFile("data/mikkel/repro/layers/solo-sw.mid");
        var golden = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        if (bridge is null || layers is null || golden is null) return;

        var inputs = LayerInputs.FromDirectory(Path.GetDirectoryName(layers)!, contourPath: MikkelContour());
        Assert.NotNull(inputs);
        log.WriteLine($"contour: {(inputs.Contour is null ? "none" : $"{inputs.Contour.Times.Length} frames")}");

        var band = bridge.ArrangeLayersBand(inputs, MikkelTitle, ArrangementOptions.Default)!;
        var mine = MusicXmlTalkingScoreBuilder.Build(band.MusicXml);
        var reference = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(golden));
        Assert.Equal(reference.Parts.Select(p => p.Name), mine.Parts.Select(p => p.Name));
        for (int p = 0; p < reference.Parts.Count; p++)
            Assert.Equal(Notes(reference.Parts[p]), Notes(mine.Parts[p]));
        Assert.Equal(GoldenNotes, mine.Parts.Sum(Notes));
        Assert.Equal(reference.Parts.Count, band.Parts.Count);
        Assert.NotNull(band.SeparationCheck);
        Assert.Equal(5, bridge.ParseComposition(band.CompositionJson).Voices.Count);

        // The options reach the arranger: the minimal lineup has fewer parts, a key moves the notes.
        var minimal = bridge.ArrangeLayersBand(inputs with { Wav = new byte[]?[4] }, MikkelTitle, new ArrangementOptions("minimal", "easier"))!;
        Assert.True(MusicXmlTalkingScoreBuilder.Build(minimal.MusicXml).Parts.Count < reference.Parts.Count);
    }

    [Fact]
    public void Contour_as_borrowed_arrays_gives_the_score_the_json_contour_gives()
    {
        var bridge = Bridge();
        var layers = TestPaths.RepoFile("data/mikkel/repro/layers/solo-sw.mid");
        var contourPath = MikkelContour();
        if (bridge is null || layers is null || contourPath is null) return;

        var inputs = LayerInputs.FromDirectory(Path.GetDirectoryName(layers)!, contourPath: contourPath)!;
        Assert.NotNull(inputs.Contour);
        var arrays = bridge.ArrangeLayersBand(inputs, MikkelTitle, ArrangementOptions.Default, contourAsJson: false)!;
        var json = bridge.ArrangeLayersBand(inputs, MikkelTitle, ArrangementOptions.Default, contourAsJson: true)!;
        Assert.Equal(json.MusicXml, arrays.MusicXml);
        Assert.Equal(json.CompositionJson, arrays.CompositionJson);
        Assert.Equal(json.SeparationCheck, arrays.SeparationCheck);
        Assert.Equal(json.Parts, arrays.Parts);
        // Not vacuous: without the contour the score differs.
        var none = bridge.ArrangeLayersBand(inputs with { Contour = null }, MikkelTitle, ArrangementOptions.Default)!;
        Assert.NotEqual(arrays.MusicXml, none.MusicXml);
    }

    [Fact]
    public void Talking_score_from_the_core_matches_the_managed_builder_on_the_golden()
    {
        var bridge = Bridge();
        var xmlPath = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        if (bridge is null || xmlPath is null || json is null) return;

        string xml = File.ReadAllText(xmlPath);
        var composition = bridge.ParseComposition(File.ReadAllText(json));
        var native = bridge.BuildTalkingScore(xml, composition);
        var managed = MusicXmlTalkingScoreBuilder.Build(xml, composition);

        Assert.Equal(managed.Title, native.Title);
        Assert.Equal(managed.TotalBars, native.TotalBars);
        Assert.Equal(managed.Parts.Select(p => p.Name), native.Parts.Select(p => p.Name));
        Assert.Equal(GoldenNotes, native.Parts.Sum(Notes));
        int mismatches = 0;
        for (int p = 0; p < managed.Parts.Count; p++)
        {
            Assert.Equal(managed.Parts[p].Bars.Count, native.Parts[p].Bars.Count);
            for (int b = 0; b < managed.Parts[p].Bars.Count; b++)
            {
                var (me, ne) = (managed.Parts[p].Bars[b].Events, native.Parts[p].Bars[b].Events);
                Assert.Equal(me.Count, ne.Count);
                for (int e = 0; e < me.Count; e++)
                    if (me[e].Kind != ne[e].Kind || me[e].Tick != ne[e].Tick || me[e].DurTicks != ne[e].DurTicks || me[e].Written != ne[e].Written)
                        mismatches++;
            }
        }
        Assert.Equal(0, mismatches);

        // Announcements agree over a stretch of the solo part.
        var settings = new TalkingScoreSettings();
        var part = native.Parts[0];
        for (int b = 0; b < Math.Min(24, part.Bars.Count); b++)
            foreach (var ev in part.Bars[b].Events.Take(3))
            {
                var ap = new AnnouncePart(part.Name, part.NameNb, part.Instrument, part.InstrumentNb, part.Transpose);
                var ab = new AnnounceBar(part.Bars[b].Number, part.Bars[b].KeyFifths, TotalBars: native.TotalBars);
                var ctx = new AnnounceContext(part.Name, part.Bars[b].Number, PitchMode.Written);
                Assert.Equal(Announcer.Announce(ap, ab, ev, ctx, settings), bridge.Announce(ap, ab, ev, ctx, settings));
            }
    }

    [Fact]
    public void Humanized_golden_keeps_every_note_sorted_and_close_to_the_score()
    {
        var bridge = Bridge();
        var xmlPath = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        if (bridge is null || xmlPath is null || json is null) return;
        var xml = File.ReadAllBytes(xmlPath);

        using var plain = new AlphaTabScorePlayer(new BufferedSynthOutput());
        plain.LoadScore(xml);
        using var human = new AlphaTabScorePlayer(new BufferedSynthOutput()) { Humanizer = bridge.Humanize, PerformanceJson = File.ReadAllText(json) };
        human.LoadScore(xml);
        using var again = new AlphaTabScorePlayer(new BufferedSynthOutput()) { Humanizer = bridge.Humanize, PerformanceJson = File.ReadAllText(json) };
        again.LoadScore(xml);

        var a = NoteOns(plain.PlaybackMidi!);
        var b = NoteOns(human.PlaybackMidi!);
        Assert.Equal(a.Count, b.Count);
        Assert.Equal(a.Count, human.HumanizedNotes);
        AssertSorted(human.PlaybackMidi!);
        Assert.Equal(NoteOns(again.PlaybackMidi!).Select(n => (n.Tick, n.NoteVelocity)), b.Select(n => (n.Tick, n.NoteVelocity)));

        var tempo = MidiHumanizer.TempoMap.Of(plain.PlaybackMidi!);
        var before = a.GroupBy(n => (n.Track, n.NoteKey)).ToDictionary(g => g.Key, g => g.Select(n => tempo.Seconds(n.Tick)).Order().ToList());
        var after = b.GroupBy(n => (n.Track, n.NoteKey)).ToDictionary(g => g.Key, g => g.Select(n => tempo.Seconds(n.Tick)).Order().ToList());
        double worst = before.Max(kv => kv.Value.Zip(after[kv.Key]).Max(x => Math.Abs(x.First - x.Second)));
        int moved = a.Zip(b).Count(x => x.First.Tick != x.Second.Tick || x.First.NoteVelocity != x.Second.NoteVelocity);
        log.WriteLine($"{b.Count} notes, {moved} changed, largest shift {worst * 1000:F1} ms");
        Assert.True(moved > b.Count / 2);
        Assert.InRange(worst, 0.001, 0.2);
        Assert.All(b, n => Assert.InRange(n.NoteVelocity, 1, 127));
    }

    /// <summary>"Change note…" on the golden: the change goes into the Composition and the whole score is arranged again.</summary>
    [Fact]
    public void A_changed_note_is_arranged_again_with_its_new_pitch()
    {
        var bridge = Bridge();
        var xmlPath = TestPaths.RepoFile(TestPaths.GoldenMusicXml);
        var json = TestPaths.RepoFile(TestPaths.GoldenComposition);
        if (bridge is null || xmlPath is null || json is null) return;
        var strings = new Services.ReswStrings(Services.ReswStrings.Parse(System.Xml.Linq.XDocument.Load(
            Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", "en-US", "Resources.resw"))));
        var quiet = new QuietAnnouncer();
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        var score = new ViewModels.ScoreViewModel(bridge, new ViewModels.PlayerViewModel(player, quiet, strings, new InlineUi()), quiet, strings);
        var composition = bridge.ParseComposition(File.ReadAllText(json));
        score.Load(File.ReadAllText(xmlPath), composition);
        int arranged = 0;
        score.Rearrange = c => { arranged++; return bridge.ArrangeMusicXml(c, "layers"); };
        var review = new ViewModels.ReviewViewModel(score, quiet, strings);
        review.Load();
        int before = review.AllItems.Count;
        Assert.True(review.Current!.IsMine); // the solo part comes first
        var item = review.Items.First(i => i.Event.CompositionVoiceId is not null);
        review.Select(item);
        var ev = item.Event;
        var note = composition.Voices.First(v => v.Id == ev.CompositionVoiceId).Notes.First(n => n.Start == ev.CompositionNoteStart);
        int oldPitch = note.Pitch;
        Assert.True(review.ChangeNote(1));
        Assert.Equal(1, arranged);
        Assert.Equal(oldPitch + 1, note.Pitch);
        Assert.Equal(1.0, note.Confidence);
        review.Load();
        Assert.True(review.AllItems.Count < before);
        var moved = score.Document!.Parts.SelectMany(p => p.Bars).SelectMany(b => b.Events)
            .FirstOrDefault(e => e.CompositionVoiceId == ev.CompositionVoiceId && e.CompositionNoteStart == ev.CompositionNoteStart);
        Assert.NotNull(moved);
        Assert.Equal((oldPitch + 1) % 12, Announcer.Midi(moved.Concert!) % 12);
        Assert.False(moved.IsUncertain);
        log.WriteLine($"changed bar {item.BarNumber} from {oldPitch} to {oldPitch + 1}; {before} → {review.AllItems.Count} notes to check");
    }

    private sealed class QuietAnnouncer : Services.IAnnouncer
    {
        public void Announce(string text, Services.AnnouncementKind kind = Services.AnnouncementKind.Status) { }
    }

    private sealed class InlineUi : Services.IUiDispatcher
    {
        public void Post(Action action) => action();
    }

    [Fact]
    public void Invalid_json_raises_a_core_error()
    {
        var bridge = Bridge();
        if (bridge is null) return;
        var e = Assert.Throws<CoreBridgeException>(() => bridge.ParseComposition("{\"title\": 3}"));
        Assert.NotEqual(0, e.Status);
    }

    [Fact]
    public void Default_bridge_is_native_when_the_library_loads()
    {
        var bridge = Bridge();
        if (bridge is null) return;
        Assert.True(CoreBridge.Create().IsNative);
    }

    [Fact]
    public void Layer_options_name_the_full_lineup_band_and_keep_every_contour_frame()
    {
        var contour = new SoloContour([0, 0.01, 0.02], [440, double.NaN, 0], [-20, double.NaN, -140]);
        var o = System.Text.Json.Nodes.JsonNode.Parse(NativeCoreBridge.LayersOptions(contour, new ArrangementOptions("full", "standard", "Bb")))!;
        Assert.Equal("band", o["lineup"]!.GetValue<string>());
        Assert.Equal("standard", o["difficulty"]!.GetValue<string>());
        Assert.Equal("Bb", o["key"]!.GetValue<string>());
        Assert.Equal(3, o["solo_contour"]!["pitch_hz"]!.AsArray().Count);
        Assert.Equal(3, o["solo_contour"]!["loudness_db"]!.AsArray().Count);
        Assert.Equal("minimal", System.Text.Json.Nodes.JsonNode.Parse(NativeCoreBridge.LayersOptions(null, new ArrangementOptions("minimal")))!["lineup"]!.GetValue<string>());
    }

    [Fact]
    public void Contour_npz_reads_back()
    {
        var path = MikkelContour();
        if (path is null) return;
        var c = LayerInputs.ReadContour(File.ReadAllBytes(path));
        Assert.Equal(c.Times.Length, c.PitchHz.Length);
        Assert.Equal(c.Times.Length, c.LoudnessDb.Length);
        Assert.True(c.Times.Length > 1000);
        Assert.True(c.Times.Zip(c.Times.Skip(1)).All(x => x.Second > x.First));
    }

    /// <summary>The SwiftF0 contour the golden was arranged with: next to the layers, else in the engine cache.</summary>
    private static string? MikkelContour()
    {
        if (TestPaths.RepoFile("data/mikkel/repro/layers/solo-sw.contour.npz") is { } here) return here;
        var objects = TestPaths.RepoFile("data/mikkel/repro/mix.beats") is { } beats
            ? Path.Combine(Path.GetDirectoryName(beats)!, "..", "..", "cache", "objects")
            : null;
        if (objects is null || !Directory.Exists(objects)) return null;
        foreach (var f in Directory.EnumerateFiles(objects, "solo-sw.contour.npz", SearchOption.AllDirectories).Order())
        {
            var hash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(f)));
            if (hash.StartsWith("06d60fa5aae3", StringComparison.Ordinal)) return f;
        }
        return null;
    }

    private static List<NoteEvent> NoteOns(MidiFile midi) =>
        midi.Events.OfType<NoteOnEvent>().Where(n => n.NoteVelocity > 0).Cast<NoteEvent>().ToList();

    internal static void AssertSorted(MidiFile midi)
    {
        double last = double.MinValue;
        foreach (var e in midi.Events)
        {
            Assert.True(e.Tick >= last, $"event at {e.Tick} after {last}");
            last = e.Tick;
        }
    }

    private static int Notes(TsPart part) =>
        part.Bars.Sum(b => b.Events.Count(e => e.Kind is EventKind.Note or EventKind.Chord or EventKind.Unpitched));
}
