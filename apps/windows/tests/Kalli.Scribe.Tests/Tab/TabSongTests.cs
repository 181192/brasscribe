using System.Text.RegularExpressions;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>
/// A tab job as it is sent for a song, Check the song's rows and the song's line in Your songs. The recorded results
/// are apps/fixtures/bass-line, guitar-line and ukulele-line.
/// </summary>
public class TabSongTests
{
    private static TabResult Recorded(string take = "bass-line") => TabFixtures.Tab(take);

    private static readonly string[] Alone = ["beats", "transcribe.bass.basic-pitch", "transcribe.bass.swift-f0", "notes", "arrange", "export"];

    private static string[] AloneFor(string kind) => ["beats", $"transcribe.{kind}.basic-pitch", $"transcribe.{kind}.swift-f0", "notes", "arrange", "export"];

    [Fact]
    public void The_job_carries_the_instrument_and_the_answer_for_the_song()
    {
        var mine = new YourInstrument(FrettedInstrument.Bass5, tuning: "drop-a", reads: Reads.TabAndNotation);
        Assert.Equal(
            new TabOptions(FrettedInstrument.Bass5, "drop-a", Capo: 0, Style: null, Recording: Recording.Instrument, Octave: Octave.Auto, Layout: TabLayout.TabAndNotation),
            TabSong.Options(mine, new SongAnswer(Recording.Instrument)));
        Assert.Equal(Recording.Song, TabSong.Options(mine, new SongAnswer(Recording.Song)).Recording);
        // Every instrument, tuning and layout of Your instrument reaches the job as it is.
        foreach (var kind in Instruments.All.SelectMany(i => i.Kinds()))
            foreach (var tuning in kind.Tunings())
                foreach (var reads in Enum.GetValues<Reads>())
                    foreach (var recording in new[] { Recording.Song, Recording.Instrument })
                    {
                        var o = TabSong.Options(new YourInstrument(kind, tuning, reads: reads), new SongAnswer(recording));
                        Assert.Equal(kind, o.Instrument);
                        Assert.Equal(tuning, o.Tuning);
                        Assert.Equal(reads.Id(), WireEnum<TabLayout>.IdOf(o.Layout!.Value));
                        Assert.Equal(recording, o.Recording);
                        Assert.Equal(0, o.Capo);
                        Assert.Equal(Octave.Auto, o.Octave);
                        Assert.Null(o.Style);
                        Assert.Null(o.Chords);
                    }
        // The hand never reaches the job.
        Assert.Equal(TabSong.Options(new YourInstrument(), new SongAnswer(Recording.Song)),
            TabSong.Options(new YourInstrument(hand: FrettingHand.Right), new SongAnswer(Recording.Song)));
    }

    [Fact]
    public void A_song_is_written_down_again_with_the_options_it_was_made_with_and_one_change()
    {
        var tab = Recorded();
        // Read back from the result and its job: nothing else has to remember the answers.
        var made = SongCheck.OptionsOf(tab, Alone);
        Assert.Equal(new TabOptions(FrettedInstrument.Bass4, "standard", Capo: 0, Style: FingeringStyle.AsPlayed,
            Recording: Recording.Instrument, Octave: Octave.Auto, Layout: TabLayout.Tab), made);
        // A full song was separated first.
        Assert.Equal(Recording.Song, SongCheck.OptionsOf(tab, ["beats", "stems", .. Alone.Skip(1)]).Recording);
        // What the player chose for the octave is kept; what the computer chose stays its to choose.
        Assert.Equal(Octave.Auto, SongCheck.OptionsOf(tab with { OctaveShift = -12 }, Alone).Octave);
        Assert.Equal(Octave.Down, SongCheck.OptionsOf(tab with { OctaveShift = -12, OctaveSource = OctaveSource.Chosen }, Alone).Octave);
        Assert.Equal(Octave.Up, SongCheck.OptionsOf(tab with { OctaveShift = 12, OctaveSource = OctaveSource.Chosen }, Alone).Octave);
        Assert.Equal(Octave.AsHeard, SongCheck.OptionsOf(tab with { OctaveSource = OctaveSource.Chosen }, Alone).Octave);
        var fiveString = SongCheck.OptionsOf(tab with { Preset = "bass-5-drop-a", Layout = TabLayout.Notation }, Alone);
        Assert.Equal((FrettedInstrument.Bass5, "drop-a", TabLayout.Notation), (fiveString.Instrument!.Value, fiveString.Tuning, fiveString.Layout!.Value));

        // Use Drop D: those options with the tuning changed are the job, whatever Your instrument says now.
        var again = made with { Tuning = "drop-d" };
        Assert.Equal(again, TabSong.Options(new YourInstrument(FrettedInstrument.Bass6, reads: Reads.Notation), new SongAnswer(again.Recording, Again: again)));
        // Continue on What is this? starts afresh: the player's instrument as it is now.
        Assert.Equal("standard", TabSong.Options(new YourInstrument(), new SongAnswer(Recording.Instrument)).Tuning);
    }

    [Fact]
    public void A_guitar_or_a_ukulele_song_is_written_down_again_for_the_same_instrument()
    {
        var guitar = SongCheck.OptionsOf(Recorded("guitar-line"), AloneFor("guitar"));
        Assert.Equal(new TabOptions(FrettedInstrument.Guitar6, "standard", Capo: 0, Style: FingeringStyle.AsPlayed,
            Recording: Recording.Instrument, Octave: Octave.Auto, Layout: TabLayout.Tab), guitar);
        var ukulele = SongCheck.OptionsOf(Recorded("ukulele-line"), AloneFor("ukulele"));
        Assert.Equal((FrettedInstrument.Ukulele, "high-g"), (ukulele.Instrument!.Value, ukulele.Tuning));
        // Chords are never asked for: the computer writes them as they were heard.
        Assert.Null(guitar.Chords);
        Assert.Null(ukulele.Chords);
        // Every preset reads back as its instrument and tuning, also the ones named unlike the others.
        var tab = Recorded("guitar-line");
        foreach (var kind in Instruments.All.SelectMany(i => i.Kinds()))
            foreach (var tuning in kind.Tunings())
            {
                var made = SongCheck.OptionsOf(tab with { Preset = kind.Preset(tuning) }, AloneFor("guitar"));
                Assert.Equal((kind, tuning), (made.Instrument!.Value, made.Tuning));
                Assert.Equal(tuning, SongCheck.TuningOf(kind.Preset(tuning)));
                Assert.Equal(kind, SongCheck.KindOf(kind.Preset(tuning)));
            }
        Assert.Null(SongCheck.TuningOf("banjo-open-g"));
        // The capo the tab was written for is kept; a capo chosen on Check the song is the one change.
        var capo = SongCheck.OptionsOf(tab with { Instrument = tab.Instrument with { Capo = 2 } }, AloneFor("guitar"));
        Assert.Equal(2, capo.Capo);
        Assert.Equal(capo with { Capo = 5 }, TabSong.Options(new YourInstrument(FrettedInstrument.Bass4), new SongAnswer(capo.Recording, Again: capo with { Capo = 5 })));
    }

    [Fact]
    public void The_capo_is_asked_about_for_a_guitar_and_a_ukulele()
    {
        static SongRow.Capo? CapoOf(TabResult t) => SongCheck.Rows(t).OfType<SongRow.Capo>().SingleOrDefault();
        Assert.Equal(new SongRow.Capo(0), CapoOf(Recorded("guitar-line")));
        Assert.Equal(new SongRow.Capo(0), CapoOf(Recorded("ukulele-line")));
        var guitar = Recorded("guitar-line");
        Assert.Equal(new SongRow.Capo(3), CapoOf(guitar with { Instrument = guitar.Instrument with { Capo = 3 } }));
        foreach (var kind in Instruments.All.SelectMany(i => i.Kinds()))
        {
            bool asked = CapoOf(guitar with { Preset = kind.Preset() }) is not null;
            Assert.Equal(Instruments.Of(kind) is Instrument.Guitar or Instrument.Ukulele, asked);
        }
        // A bass has no capo row; one whose tab was written for a capo still says so.
        var bass = Recorded();
        Assert.Null(CapoOf(bass));
        Assert.Equal(new SongRow.Capo(2), CapoOf(bass with { Instrument = bass.Instrument with { Capo = 2 } }));
        Assert.Equal(Enumerable.Range(0, 13), SongCheck.CapoFrets);
        // Under the tuning, before the octave and the rest.
        Assert.Equal([typeof(SongRow.Tuning), typeof(SongRow.Capo)], SongCheck.Rows(guitar).Take(2).Select(r => r.GetType()));
    }

    [Fact]
    public void Notes_left_out_and_notes_added_are_said_only_when_there_are_some()
    {
        var tab = Recorded("guitar-line");
        Assert.Equal(0, tab.UnplayableDropped);
        Assert.DoesNotContain(SongCheck.Rows(tab), r => r is SongRow.LeftOut or SongRow.Added);
        Assert.DoesNotContain(SongCheck.Rows(Recorded()), r => r is SongRow.LeftOut or SongRow.Added or SongRow.Capo);
        var rows = SongCheck.Rows(tab with { UnplayableDropped = 3, InferredNotes = 2 });
        Assert.Equal(new SongRow.LeftOut(3), rows.OfType<SongRow.LeftOut>().Single());
        Assert.Equal(new SongRow.Added(2), rows.OfType<SongRow.Added>().Single());
        // Last on the screen, after the notes to check.
        Assert.Equal([typeof(SongRow.LeftOut), typeof(SongRow.Added)], rows.TakeLast(2).Select(r => r.GetType()));
        // Overtones and faint notes that were not played are not the player's to check: no row for them.
        Assert.True(tab.LeftoversDropped > 0);
        Assert.Equal(SongCheck.Rows(tab with { LeftoversDropped = 0, DoubledNotes = 0 }), SongCheck.Rows(tab with { LeftoversDropped = 40, DoubledNotes = 6 }));
    }

    [Fact]
    public void The_recorded_guitar_sounds_like_another_tuning_which_is_offered()
    {
        var tab = Recorded("guitar-line");
        var row = SongCheck.Rows(tab).OfType<SongRow.Tuning>().Single();
        Assert.Equal("standard", row.Written);
        Assert.Equal(SongCheck.TuningOf(tab.TuningSuggestions[0].Preset), row.SoundsLike);
        Assert.True(row.SoundsLike is not null && FrettedInstrument.Guitar6.Tunings().Contains(row.SoundsLike) && row.SoundsLike != "standard");
        // The ukulele's take fits the tuning it was written for.
        Assert.Equal(new SongRow.Tuning("high-g", null, FrettedInstrument.Ukulele), SongCheck.Rows(Recorded("ukulele-line")).OfType<SongRow.Tuning>().Single());
    }

    [Fact]
    public void The_job_is_a_tab_job_with_none_of_the_bands_options()
    {
        var request = new JobCreate("audio-1", TabProfiles.Tab, Title: "Riff", Seat: "2nd-cornet", Reads: "treble", Lead: "seat");
        var job = TabSong.Job(request, TabSong.Options(new YourInstrument(FrettedInstrument.Bass4, tuning: "bead"), new SongAnswer(Recording.Instrument)),
            new HashSet<string> { "tab", "bass-tab" });
        Assert.Equal("tab", job.Profile);
        Assert.Equal("audio-1", job.AudioId);
        Assert.Equal("Riff", job.Title);
        Assert.True(job.Seat is null && job.Reads is null && job.Lead is null);
        Assert.Equal("bass-4", job.Instrument);
        Assert.Equal("bead", job.Tuning);
        Assert.Equal("instrument", job.Recording);
        Assert.Equal(0, job.Capo);
        Assert.Equal("auto", job.Octave);
        Assert.Equal("tab", job.Layout);
        Assert.Null(job.Style);
    }

    private sealed record Take(string Name);

    [Fact]
    public void The_answer_stays_with_its_recording()
    {
        var answers = new SongAnswers<Take>();
        var riff = new Take("riff.wav");
        var other = new Take("other.wav");
        answers.Set(riff, new SongAnswer(Recording.Instrument));
        Assert.Equal(new SongAnswer(Recording.Instrument), answers.Of(riff));
        // Another recording has not been asked about: nothing is chosen for it, also the same file opened again.
        Assert.Equal(new SongAnswer(), answers.Of(other));
        Assert.Equal(new SongAnswer(), answers.Of(new Take("riff.wav")));
        Assert.Equal(new SongAnswer(), answers.Of(null));
        answers.Set(other, new SongAnswer(Recording.Song));
        Assert.Equal(new SongAnswer(), answers.Of(riff));
        // Kept where it is now: the answers go with it.
        var moved = new Take("kept/other.wav");
        answers.Moved(other, moved);
        Assert.Equal(new SongAnswer(Recording.Song), answers.Of(moved));
        answers.Moved(riff, other);
        Assert.Equal(new SongAnswer(Recording.Song), answers.Of(moved));
    }

    [Fact]
    public void The_recorded_tab_has_nothing_unusual_so_it_shows_the_tuning_and_the_key_and_tempo()
    {
        Assert.Equal(
            [new SongRow.Tuning("standard", null, FrettedInstrument.Bass4), new SongRow.KeyAndTempo(Fifths: 1, Minor: true, Bpm: 100, Beats: 2, BeatUnit: 4)],
            SongCheck.Rows(Recorded()));
    }

    [Fact]
    public void A_tuning_that_fits_better_is_offered()
    {
        var tab = Recorded();
        var dropD = tab.TuningSuggestions.First(s => s.Preset == "bass-4-drop-d");
        var suggested = tab with { TuningSuggestions = [dropD, .. tab.TuningSuggestions.Where(s => s != dropD)] };
        Assert.Equal(new SongRow.Tuning("standard", "drop-d", FrettedInstrument.Bass4), SongCheck.Rows(suggested)[0]);
        // Written for the tuning that fits best: nothing to offer.
        Assert.Equal(new SongRow.Tuning("drop-d", null, FrettedInstrument.Bass4), SongCheck.Rows(suggested with { Preset = "bass-4-drop-d" })[0]);
        Assert.Equal("drop-a", SongCheck.TuningOf("bass-5-drop-a"));
        Assert.Equal("eb-standard", SongCheck.TuningOf("bass-4-eb-standard"));
        Assert.Equal("standard", SongCheck.TuningOf("guitar-standard"));
        Assert.Null(SongCheck.TuningOf("guitar-6-standard"));
        Assert.Equal(FrettedInstrument.Bass5, SongCheck.KindOf("bass-5-drop-a"));
    }

    [Fact]
    public void The_octave_row_is_there_when_the_line_or_single_notes_were_moved_or_the_player_chose()
    {
        var tab = Recorded();
        static SongRow.Octave? OctaveOf(TabResult t) => SongCheck.Rows(t).OfType<SongRow.Octave>().SingleOrDefault();
        Assert.Null(OctaveOf(tab));
        Assert.Equal(new SongRow.Octave(-12, Chosen: false, NotesMoved: 0), OctaveOf(tab with { OctaveShift = -12 }));
        Assert.Equal(new SongRow.Octave(-24, Chosen: false, NotesMoved: 0), OctaveOf(tab with { OctaveShift = -24 }));
        Assert.Equal(new SongRow.Octave(0, Chosen: false, NotesMoved: 3), OctaveOf(tab with { OctaveNotesMoved = 3 }));
        Assert.Equal(new SongRow.Octave(12, Chosen: true, NotesMoved: 0), OctaveOf(tab with { OctaveShift = 12, OctaveSource = OctaveSource.Chosen }));
        // "As it was heard" was chosen: the row stays, so the choice can be given back to the computer.
        Assert.Equal(new SongRow.Octave(0, Chosen: true, NotesMoved: 0), OctaveOf(tab with { OctaveSource = OctaveSource.Chosen }));
    }

    [Fact]
    public void The_reference_pitch_row_is_there_only_when_the_recording_is_off()
    {
        var tab = Recorded();
        static SongRow.ReferencePitch? ReferenceOf(TabResult t) => SongCheck.Rows(t).OfType<SongRow.ReferencePitch>().SingleOrDefault();
        // The recording is 2 cents flat: in tune.
        Assert.Null(ReferenceOf(tab));
        Assert.Null(ReferenceOf(tab with { ReferencePitch = null }));
        Assert.Null(ReferenceOf(tab with { ReferencePitch = new ReferencePitch(10.0, 0.8, false) }));
        Assert.Equal(new SongRow.ReferencePitch(30, Retuned: true), ReferenceOf(tab with { ReferencePitch = new ReferencePitch(30.2, 0.8, true) }));
        Assert.Equal(new SongRow.ReferencePitch(-18, Retuned: false), ReferenceOf(tab with { ReferencePitch = new ReferencePitch(-17.6, 0.8, false) }));
        // Half a cent is rounded up, as everywhere else.
        Assert.Equal(new SongRow.ReferencePitch(13, Retuned: false), ReferenceOf(tab with { ReferencePitch = new ReferencePitch(12.5, 0.8, false) }));
    }

    [Fact]
    public void Doubtful_notes_and_notes_with_no_place_are_counted()
    {
        var tab = Recorded();
        var notes = tab.Notes.Select((n, i) => i switch
        {
            0 or 1 or 2 => n with { Confidence = 0.2 },
            3 => n with { String = null, Fret = null, OutOfRange = true },
            4 => n with { String = null, Fret = null },
            _ => n,
        }).ToList();
        var rows = SongCheck.Rows(tab with { Notes = notes });
        Assert.Equal(new SongRow.Doubtful(3), rows.OfType<SongRow.Doubtful>().Single());
        Assert.Equal(new SongRow.NoPlace(2), rows.OfType<SongRow.NoPlace>().Single());
        // In the order of the screen: tuning, key and tempo, then the notes.
        Assert.Equal([typeof(SongRow.Tuning), typeof(SongRow.KeyAndTempo), typeof(SongRow.Doubtful), typeof(SongRow.NoPlace)], rows.Select(r => r.GetType()));
        // A note at the threshold is not doubtful.
        Assert.DoesNotContain(SongCheck.Rows(tab with { Notes = [.. tab.Notes.Select(n => n with { Confidence = 0.4 })] }), r => r is SongRow.Doubtful);
    }

    [Fact]
    public void A_saved_songs_line_is_read_from_its_tab_and_its_notes()
    {
        string xml = TabFixtures.MusicXml("bass-line");
        string composition = TabFixtures.Text("bass-line", "composition.json");
        Assert.Equal([28, 33, 38, 43], SongFacts.OpenStringsOf(xml));
        Assert.Equal(new SongFacts(4, "standard", 0, FrettedInstrument.Bass4), SongFacts.Of(xml, composition));
        // Two notes the computer was unsure of.
        int n = 0;
        string unsure = Regex.Replace(composition, @"""confidence"": [0-9.]+", m => n++ < 2 ? "\"confidence\": 0.25" : m.Value);
        Assert.Equal(new SongFacts(4, "standard", 2, FrettedInstrument.Bass4), SongFacts.Of(xml, unsure));
        // Drop D: the lowest string a whole step down.
        var first = new Regex("<tuning-step>E</tuning-step>");
        string dropD = first.Replace(xml, "<tuning-step>D</tuning-step>", 1);
        Assert.Equal(new SongFacts(4, "drop-d", 0, FrettedInstrument.Bass4), SongFacts.Of(dropD, null));
        // A tuning with no name here still says how many strings; a score that is no tab says nothing.
        string odd = first.Replace(xml, "<tuning-step>C</tuning-step>", 1);
        Assert.Equal(new SongFacts(4, null, 0), SongFacts.Of(odd, null));
        Assert.Equal(new SongFacts(null, null, 0), SongFacts.Of("<score-partwise/>", null));
        // A guitar's and a ukulele's tab name their instrument and tuning the same way.
        Assert.Equal(new SongFacts(6, "standard", 0, FrettedInstrument.Guitar6), SongFacts.Of(TabFixtures.MusicXml("guitar-line"), null));
        Assert.Equal(new SongFacts(4, "high-g", 0, FrettedInstrument.Ukulele), SongFacts.Of(TabFixtures.MusicXml("ukulele-line"), null));
        // Notes that can't be read are none to check.
        Assert.Equal(0, SongFacts.Of(xml, "not json").ToCheck);
    }

    [Fact]
    public void The_open_strings_are_the_crates_presets()
    {
        Assert.Equal(Instruments.All.SelectMany(i => i.Kinds()).SelectMany(kind => kind.Tunings().Select(t => kind.Preset(t))), SongFacts.OpenStrings.Keys);
        // No two tunings share their strings, so a tab's staff names its instrument and its tuning.
        Assert.Equal(SongFacts.OpenStrings.Count, SongFacts.OpenStrings.Values.Select(v => string.Join(",", v)).Distinct().Count());
        string source = File.ReadAllText(TestPaths.RepoFile("core/targets/fretted/src/instrument.rs")!);
        // The crate's own tests list the open strings, highest first.
        var listed = Regex.Matches(source, @"assert_eq!\(open\(""([^""]+)""\), vec!\[([0-9, ]+)]\);")
            .ToDictionary(m => m.Groups[1].Value, m => m.Groups[2].Value.Split(',').Select(p => int.Parse(p.Trim(), System.Globalization.CultureInfo.InvariantCulture)).Order().ToList());
        Assert.NotEmpty(listed);
        foreach (var (preset, open) in listed) Assert.Equal(open, SongFacts.OpenStrings[preset]);
        // The ones the crate's tests do not list: the same strings as the recorded tabs name for their tuning.
        Assert.Equal(SongFacts.OpenStrings["guitar-standard"], Recorded("guitar-line").Instrument.Tuning.Strings.Select(s => s.OpenPitch).Order());
        Assert.Equal(SongFacts.OpenStrings["ukulele-high-g"], Recorded("ukulele-line").Instrument.Tuning.Strings.Select(s => s.OpenPitch).Order());
    }
}
