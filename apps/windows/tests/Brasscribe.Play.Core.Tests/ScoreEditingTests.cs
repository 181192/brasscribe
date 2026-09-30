using System.Xml.Linq;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>Corrected notes, "Your scores" and the files the app writes and cleans up.</summary>
public class ScoreEditingTests
{
    private static string OneNote(string pitch, string accidental = "", int fifths = 0) => $"""
        <score-partwise><part-list><score-part id="P1"><part-name>Solo</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>{fifths}</fifths></key></attributes>
        <note><pitch>{pitch}</pitch><duration>1</duration><voice>1</voice><type>quarter</type>{accidental}<stem>up</stem></note></measure></part></score-partwise>
        """;

    private static XElement NoteOf(string xml) => XDocument.Parse(xml).Root!.Element("part")!.Element("measure")!.Element("note")!;

    [Fact]
    public void A_sharp_corrected_to_a_natural_loses_its_sharp()
    {
        var xml = OneNote("<step>F</step><alter>1</alter><octave>4</octave>", "<accidental>sharp</accidental>");
        var note = NoteOf(MusicXmlNoteEditor.ReplacePitch(xml, "P1", 0, midi: 65, fifths: 0));
        Assert.Equal("F", note.Element("pitch")!.Element("step")!.Value);
        Assert.Null(note.Element("pitch")!.Element("alter"));
        Assert.Null(note.Element("accidental"));
    }

    [Fact]
    public void A_note_that_leaves_the_key_gets_its_accidental_in_the_right_place()
    {
        var sharp = NoteOf(MusicXmlNoteEditor.ReplacePitch(OneNote("<step>F</step><octave>4</octave>"), "P1", 0, midi: 66, fifths: 0));
        Assert.Equal("sharp", sharp.Element("accidental")!.Value);
        Assert.Equal("type", ((XElement)sharp.Element("accidental")!.PreviousNode!).Name.LocalName);

        // B♭ in F major is in the key: nothing printed. B natural there needs its natural.
        var inKey = NoteOf(MusicXmlNoteEditor.ReplacePitch(OneNote("<step>A</step><octave>4</octave>", fifths: -1), "P1", 0, midi: 70, fifths: -1));
        Assert.Null(inKey.Element("accidental"));
        var natural = NoteOf(MusicXmlNoteEditor.ReplacePitch(OneNote("<step>A</step><octave>4</octave>", fifths: -1), "P1", 0, midi: 71, fifths: -1));
        Assert.Equal("natural", natural.Element("accidental")!.Value);
    }

    [Theory]
    [InlineData("F", 1, 1)]
    [InlineData("C", 1, 0)]
    [InlineData("C", 2, 1)]
    [InlineData("B", -1, -1)]
    [InlineData("A", -3, -1)]
    [InlineData("D", -3, 0)]
    public void Key_signatures_alter_the_right_steps(string step, int fifths, int alter) =>
        Assert.Equal(alter, MusicXmlNoteEditor.KeyAlter(step, fifths));

    private const string GraceChord = """
        <score-partwise><part-list><score-part id="P1"><part-name>Solo</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>2</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>
        <note><pitch><step>C</step><octave>4</octave></pitch><duration>2.0</duration><voice>1</voice><type>quarter</type></note>
        <note><grace/><pitch><step>D</step><octave>4</octave></pitch><voice>1</voice><type>eighth</type></note>
        <note><grace/><chord/><pitch><step>F</step><octave>4</octave></pitch><voice>1</voice><type>eighth</type></note>
        <note><pitch><step>B</step><alter>-1.0</alter><octave>4</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type></note>
        </measure></part></score-partwise>
        """;

    [Fact]
    public void Grace_chord_tones_stay_off_the_note_before_and_decimal_numbers_read()
    {
        var doc = MusicXmlTalkingScoreBuilder.Build(GraceChord);
        var events = doc.Parts[0].Bars[0].Events;
        Assert.Equal(2, events.Count);
        Assert.Equal(EventKind.Note, events[0].Kind);
        Assert.Null(events[0].Pitches);
        Assert.Equal(-1, events[1].Written!.Alter);
        Assert.Equal(events[0].DurTicks, events[1].Tick);
    }

    private static string TempDir() => Path.Combine(Path.GetTempPath(), "brasscribe-edit-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public void An_opened_file_is_never_written_the_change_goes_to_a_copy()
    {
        string root = TempDir(), outside = TempDir();
        Directory.CreateDirectory(outside);
        try
        {
            string original = Path.Combine(outside, "Mine.musicxml");
            string xml = OneNote("<step>F</step><alter>1</alter><octave>4</octave>", "<accidental>sharp</accidental>");
            File.WriteAllText(original, xml);
            var library = new ScoreLibrary(root);
            var entry = library.AddOpened(original, "Mine", parts: 1, bars: 1, notesToCheck: 0);

            library.SaveMusicXml(entry.Id, MusicXmlNoteEditor.ReplacePitch(xml, "P1", 0, 65, 0));
            library.Rename(entry.Id, "Mine, corrected");

            Assert.Equal(xml, File.ReadAllText(original));
            var copy = Assert.Single(library.Entries);
            Assert.StartsWith(Path.GetFullPath(root), Path.GetFullPath(copy.MusicXmlPath));
            Assert.Contains("Mine, corrected", File.ReadAllText(copy.MusicXmlPath));
            Assert.DoesNotContain("<alter>", File.ReadAllText(copy.MusicXmlPath));
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, true);
            Directory.Delete(outside, true);
        }
    }

    [Fact]
    public void A_score_on_a_drive_that_is_not_connected_stays_listed()
    {
        string root = TempDir(), outside = TempDir();
        Directory.CreateDirectory(outside);
        try
        {
            string file = Path.Combine(outside, "Stick.musicxml");
            File.WriteAllText(file, OneNote("<step>C</step><octave>4</octave>"));
            var library = new ScoreLibrary(root);
            var away = library.AddOpened(file, "Stick", 1, 1, 0);
            library.AddMade("Made", OneNote("<step>D</step><octave>4</octave>"), null, 1, 1, 0, jobId: "j1");
            Directory.Delete(outside, true); // the drive is unplugged

            var reopened = new ScoreLibrary(root);
            var entry = Assert.Single(reopened.Entries, e => e.Id == away.Id);
            Assert.False(entry.IsAvailable);
            reopened.SetNotesToCheck("j1", 3); // saves the index
            Assert.Contains(new ScoreLibrary(root).Entries, e => e.Id == away.Id);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, true);
            if (Directory.Exists(outside)) Directory.Delete(outside, true);
        }
    }

    [Theory]
    [InlineData("Con", "Con_")]
    [InlineData("lpt1", "lpt1_")]
    [InlineData("Old Hundredth", "Old Hundredth")]
    [InlineData("Intro...", "Intro")]
    [InlineData("a/b:c", "a-b-c")]
    [InlineData("  ", "score")]
    public void Export_names_are_ones_windows_accepts(string title, string expected) =>
        Assert.Equal(expected, ExportViewModel.Sanitize(title));

    [Fact]
    public void Exporting_into_a_folder_keeps_the_files_already_there()
    {
        string dir = TempDir();
        Directory.CreateDirectory(dir);
        try
        {
            Assert.Equal(Path.Combine(dir, "Score.pdf"), ExportViewModel.UniquePath(dir, "Score.pdf"));
            File.WriteAllText(Path.Combine(dir, "Score.pdf"), "");
            File.WriteAllText(Path.Combine(dir, "Score (2).pdf"), "");
            Assert.Equal(Path.Combine(dir, "Score (3).pdf"), ExportViewModel.UniquePath(dir, "Score.pdf"));
        }
        finally { Directory.Delete(dir, true); }
    }

    private sealed class NoCapture : ICaptureService
    {
        public bool SupportsAppCapture => false;
        public bool IsCapturing => false;
        public event EventHandler<CaptureLevel>? Level { add { } remove { } }
        public event EventHandler<CaptureNotice>? Notice { add { } remove { } }
        public Task<IReadOnlyList<AudioDevice>> ListMicrophonesAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<AudioDevice>>([]);
        public Task<IReadOnlyList<AudioApp>> ListAudioAppsAsync(CancellationToken ct = default) => Task.FromResult<IReadOnlyList<AudioApp>>([]);
        public Task StartAsync(CaptureRequest request, CancellationToken ct = default) => Task.CompletedTask;
        public Task<CaptureResult> StopAsync(CancellationToken ct = default) => throw new InvalidOperationException("not recording");
    }

    /// <summary>Writes a few bytes as the decoded WAV; a name with "broken" fails halfway, after writing some.</summary>
    private sealed class FakeDecoder : IMediaDecoder
    {
        public async Task<DecodedMedia> DecodeToWavAsync(string inputPath, string outputPath, int? sampleRate = null, CancellationToken ct = default)
        {
            await File.WriteAllBytesAsync(outputPath, [1, 2, 3, 4], ct);
            if (inputPath.Contains("broken")) throw new System.Runtime.InteropServices.COMException("no decoder");
            return new DecodedMedia(outputPath, TimeSpan.FromSeconds(5), false, 44100, 1);
        }
    }

    private sealed class NoDialogs : IFileDialogs
    {
        public Task<string?> PickOpenAsync(IEnumerable<string> extensions) => Task.FromResult<string?>(null);
        public Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description) => Task.FromResult<SaveTarget?>(null);
    }

    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    [Fact]
    public async Task Takes_are_cleaned_up_when_replaced_when_they_fail_and_at_the_next_start()
    {
        string work = TempDir();
        string takes = Path.Combine(work, "takes");
        Directory.CreateDirectory(takes);
        string old = Path.Combine(takes, "left-from-last-time.wav"), other = Path.Combine(takes, "another-window.wav");
        File.WriteAllText(old, "");
        File.SetLastWriteTimeUtc(old, DateTime.UtcNow - StartViewModel.PruneAge - TimeSpan.FromHours(1));
        File.WriteAllText(other, ""); // a take another window of the app works with now
        try
        {
            var said = new Said();
            var start = new StartViewModel(new NoCapture(), new FakeDecoder(), new NoDialogs(), said, ConnectionMonitorTests.Strings(), new Inline(), work);
            Assert.Equal([other], Directory.EnumerateFiles(takes));
            File.Delete(other);

            var ready = new List<SourceAudio>();
            start.SourceReady += (_, s) => ready.Add(s);
            await start.OpenPathAsync(Path.Combine(work, "first.mp3"));
            File.WriteAllText(Path.ChangeExtension(ready[0].WavPath, null) + ".boost1.5.wav", "");
            await start.OpenPathAsync(Path.Combine(work, "second.mp3"));
            Assert.Equal([ready[1].WavPath], Directory.EnumerateFiles(takes));

            await start.OpenPathAsync(Path.Combine(work, "broken.ogg"));
            Assert.Equal([ready[1].WavPath], Directory.EnumerateFiles(takes));
            Assert.Contains("Web Media Extensions", start.ErrorText);
        }
        finally { Directory.Delete(work, true); }
    }

    [Fact]
    public void Aiff_is_not_offered_because_windows_cannot_read_it()
    {
        Assert.Equal(MediaKind.Unsupported, MediaTypes.Classify("take.aiff"));
        Assert.True(MediaTypes.NeedsCodec("take.webm"));
        Assert.False(MediaTypes.NeedsCodec("take.mp3"));
    }

    [Fact]
    public void A_rearrangement_that_has_not_arrived_does_not_count_as_applied()
    {
        var output = new OutputOptionsViewModel(new ManagedCoreBridge(), new Said(), ConnectionMonitorTests.Strings()) { HasEngineJob = true };
        output.ShowingMade(ArrangementOptions.Default);
        var before = output.Applied;
        ArrangementOptions? asked = null;
        output.RearrangeRequested += (_, o) => asked = o;

        output.Difficulty = Difficulty.Easier;
        output.ApplyCommand.Execute(null);

        Assert.NotNull(asked);
        Assert.Equal(before, output.Applied);
        output.ShowingMade(asked!); // the engine's score arrived
        Assert.Equal(asked, output.Applied);
    }
}
