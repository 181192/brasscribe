using System.Text.Json;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>
/// Every tab job the app can send, for every instrument, tuning, layout, answer and capo the screens can produce:
/// what it carries, and under which profile id.
/// </summary>
public class TabJobOptionsTests
{
    /// <summary>One job: the body as it goes to the computer, and what it is meant to be once the computer has filled in its defaults.</summary>
    private sealed record Sent(JsonElement Body, string Instrument, string Tuning, int Capo, string Layout, string Recording, string Octave);

    /// <summary>The request as the app makes it before the tab options complete it: the recording, a title, and a band seat left from a band app's choices.</summary>
    private static JobCreate Request(string profile) => new("audio-1", profile, RenderAudio: true, AllowHeavy: true, Title: "Riff", Seat: "2nd-cornet", Reads: "treble");

    /// <summary>A computer with every profile, and one from before the tab profile: it has the bass tab's id only.</summary>
    private static readonly HashSet<string> Current = ["solo", "brass-band", "orchestra-with-soloist", "pop-rock", TabProfiles.Tab, TabProfiles.BassTab];
    private static readonly HashSet<string> Older = [.. Current.Where(p => p != TabProfiles.Tab)];

    private static Sent SentOf(TabOptions options, IReadOnlySet<string>? listed)
    {
        var job = TabSong.Job(Request(TabProfiles.Tab), options, listed);
        var kind = options.Instrument!.Value;
        var body = JsonDocument.Parse(JsonSerializer.Serialize(job, EngineJsonContext.Default.JobCreate)).RootElement.Clone();
        return new Sent(body, kind.Id()!, options.Tuning!, options.Capo!.Value, WireEnum<TabLayout>.Wire(options.Layout!.Value),
            WireEnum<Recording>.Wire(options.Recording ?? kind.DefaultRecording()), WireEnum<Octave>.Wire(options.Octave!.Value));
    }

    /// <summary>The computers a job for <paramref name="kind"/> is sent to: one with the tab profile, and for a bass also one from before it.</summary>
    private static IEnumerable<IReadOnlySet<string>> Computers(FrettedInstrument kind) => kind.IsBass() ? [Current, Older] : [Current];

    /// <summary>
    /// Your instrument's choices with What is this?'s answers: the first job of a song. (The hand on the neck is not
    /// among them: it never reaches the job, which YourInstrumentTests checks.)
    /// </summary>
    private static List<Sent> FirstJobs()
    {
        var jobs = new List<Sent>();
        foreach (var instrument in Instruments.All)
            foreach (var kind in instrument.Kinds())
                foreach (var tuning in kind.Tunings())
                    foreach (var reads in Enum.GetValues<Reads>())
                        foreach (var answer in new Recording?[] { Recording.Instrument, Recording.Song, null })
                            foreach (var listed in Computers(kind))
                                jobs.Add(SentOf(TabSong.Options(new YourInstrument(kind, tuning, reads: reads), new SongAnswer(answer)), listed));
        // (No answer is sent as the computer's own default for the instrument: the same job as that answer.)
        return [.. jobs.DistinctBy(j => j.Body.GetRawText())];
    }

    [Fact]
    public void Every_choice_of_your_instrument_and_what_is_this_reaches_the_job()
    {
        var jobs = FirstJobs();
        // Every instrument and tuning, read three ways, with either answer; a bass also for the older computer.
        Assert.Equal((11 + 2 + 1 + 5 + 2 + 1 + 2 + 1 + 1) * 3 * 2 + (5 + 2 + 1) * 3 * 2, jobs.Count);
        // Every instrument and tuning the computer has is among them, in every layout.
        var all = WireEnum<FrettedInstrument>.Values.SelectMany(k => k.Tunings().SelectMany(t => new[] { "tab", "tab-and-notation", "notation" }.Select(l => (k.Id()!, t, l))));
        Assert.True(all.ToHashSet().SetEquals(jobs.Select(j => (j.Instrument, j.Tuning, j.Layout))));
        foreach (var job in jobs)
        {
            string? Text(string name) => job.Body.TryGetProperty(name, out var v) ? v.ValueKind == JsonValueKind.Number ? v.GetRawText() : v.GetString() : null;
            // Every instrument goes as a tab job; a bass goes under the older id too, for the computer that has only that.
            Assert.True(Text("profile") == "tab" || (Text("profile") == "bass-tab" && job.Instrument.StartsWith("bass-", StringComparison.Ordinal)), Text("profile"));
            Assert.Equal(job.Instrument, Text("instrument"));
            Assert.Equal(job.Tuning, Text("tuning"));
            Assert.Equal(job.Layout, Text("layout"));
            Assert.Equal(job.Recording, Text("recording"));
            // A first job has no capo and lets the computer check the octave.
            Assert.Equal("0", Text("capo"));
            Assert.Equal("auto", Text("octave"));
            // The fingering style and the chords are the computer's defaults: not named. The band's choices never go.
            foreach (var unsent in new[] { "style", "chords", "seat", "reads", "lead", "key", "transpose" })
                Assert.False(job.Body.TryGetProperty(unsent, out _), $"{unsent} in {job.Body}");
        }
    }

    [Fact]
    public void An_unanswered_job_is_taken_as_the_computer_takes_it()
    {
        foreach (var instrument in Instruments.All)
            foreach (var kind in instrument.Kinds())
            {
                bool alone = instrument is Instrument.Ukulele or Instrument.Mandolin;
                Assert.Equal(alone ? Recording.Instrument : Recording.Song, TabSong.Options(new YourInstrument(kind), new SongAnswer()).Recording);
                // What is this? starts on "Just my instrument" for a ukulele and a mandolin, and with nothing chosen for a guitar and a bass.
                Assert.Equal(alone ? Recording.Instrument : null, TabSong.StartingAnswer(new YourInstrument(kind)));
                // The player's answer always wins.
                Assert.Equal(Recording.Song, TabSong.Options(new YourInstrument(kind), new SongAnswer(Recording.Song)).Recording);
                Assert.Equal(Recording.Instrument, TabSong.Options(new YourInstrument(kind), new SongAnswer(Recording.Instrument)).Recording);
            }
        Assert.Null(TabSong.StartingAnswer(YourInstrument.Default));
    }

    [Fact]
    public void The_profile_id_is_the_one_the_computer_has_for_the_instrument()
    {
        foreach (var kind in Instruments.All.SelectMany(i => i.Kinds()))
        {
            // A computer with the tab profile: every instrument goes under it, a bass too.
            Assert.Equal(TabProfiles.Tab, TabSong.Profile(kind, Current));
            Assert.Equal(TabProfiles.Tab, TabSong.Profile(kind, new HashSet<string> { "tab" }));
            // A computer from before it: a bass still goes, under the id it knows; nothing else can be written there.
            Assert.Equal(kind.IsBass() ? TabProfiles.BassTab : null, TabSong.Profile(kind, Older));
            // A computer that writes no tab at all.
            Assert.Null(TabSong.Profile(kind, new HashSet<string> { "solo", "brass-band" }));
            Assert.Null(TabSong.Profile(kind, new HashSet<string>()));
            // Not known (the computer could not be asked): the id every computer that writes the instrument has.
            Assert.Equal(kind.IsBass() ? TabProfiles.BassTab : TabProfiles.Tab, TabSong.Profile(kind, null));
        }
        Assert.Equal(TabProfiles.Tab, TabSong.Profile(null, null));
        Assert.Null(TabSong.Profile(null, Older));
        // The job carries that id, whatever the request said, also for a song written down again.
        var bass = TabSong.Options(new YourInstrument(FrettedInstrument.Bass5, "drop-a"), new SongAnswer(Recording.Song));
        Assert.Equal("bass-tab", TabSong.Job(Request(TabProfiles.Tab), bass, Older).Profile);
        Assert.Equal("bass-tab", TabSong.Job(Request(TabProfiles.Tab), bass, null).Profile);
        Assert.Equal("tab", TabSong.Job(Request(TabProfiles.BassTab), bass, Current).Profile);
        var again = new SongAnswer(Recording.Instrument, Again: bass with { Tuning = "standard", Capo = 2 });
        Assert.Equal("bass-tab", TabSong.Job(Request(TabProfiles.Tab), TabSong.Options(new YourInstrument(), again), Older).Profile);
        var guitar = TabSong.Options(new YourInstrument(), new SongAnswer(Recording.Song));
        Assert.Equal("tab", TabSong.Job(Request(TabProfiles.Tab), guitar, Current).Profile);
        Assert.Equal("tab", TabSong.Job(Request(TabProfiles.Tab), guitar, null).Profile);
    }

    [Fact]
    public void What_a_computer_said_is_kept_for_that_computer_only_and_is_gone_while_it_is_asked_again()
    {
        var profiles = new ComputerProfiles();
        Assert.Null(profiles.Listed);
        profiles.Asking("mac-1");
        Assert.Equal(new ComputerProfiles.Known("mac-1", Asking: true, Listed: null), profiles.Answer);
        profiles.Answered("mac-1", Current);
        Assert.Same(Current, profiles.Listed);
        // Another computer is asked: what the first said does not count for it, also before it answers.
        profiles.Asking("mac-2");
        Assert.Null(profiles.Listed);
        // The first one's late answer is not taken for the second's.
        profiles.Answered("mac-1", Current);
        Assert.Null(profiles.Listed);
        Assert.True(profiles.Answer!.Asking);
        profiles.Answered("mac-2", Older);
        Assert.Same(Older, profiles.Listed);
        // Asked again, its own earlier answer is gone until the new one is there; a request that fails leaves nothing known.
        profiles.Asking("mac-2");
        Assert.Null(profiles.Listed);
        profiles.Answered("mac-2", null);
        Assert.Equal(new ComputerProfiles.Known("mac-2", Asking: false, Listed: null), profiles.Answer);
        var changed = new List<string?>();
        profiles.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        profiles.Clear();
        Assert.Null(profiles.Answer);
        Assert.Equal([nameof(ComputerProfiles.Answer), nameof(ComputerProfiles.Listed)], changed);
    }

    [Fact]
    public void A_job_of_either_id_is_sent_as_a_tab_job_and_a_band_job_is_left_alone()
    {
        var options = TabSong.Options(new YourInstrument(FrettedInstrument.Ukulele, "low-g"), new SongAnswer(Recording.Instrument));
        foreach (var profile in new[] { TabProfiles.Tab, TabProfiles.BassTab })
        {
            var job = TabSong.Job(Request(profile), options, Current);
            Assert.Equal("tab", job.Profile);
            Assert.True(job.Seat is null && job.Reads is null && job.Lead is null);
            Assert.Equal(("ukulele", "low-g"), (job.Instrument, job.Tuning));
            Assert.Null(job.Chords);
        }
    }
}
