using AlphaTab.Midi;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;

namespace Brasscribe.Play.Core.Tests;

/// <summary>Humanized playback timing applied to alphaTab's playback MIDI, with a stand-in humanizer.</summary>
[Collection(AlphaTabCollection.Name)]
public class HumanizeTests
{
    private static byte[] Fixture() => File.ReadAllBytes(TestPaths.Fixture("two-parts.musicxml"));

    private static List<(double Tick, double Key, double Velocity)> Notes(MidiFile midi) =>
        midi.Events.OfType<NoteOnEvent>().Where(n => n.NoteVelocity > 0).Select(n => (n.Tick, n.NoteKey, n.NoteVelocity)).ToList();

    [Fact]
    public void Without_a_humanizer_playback_keeps_the_score_timing()
    {
        using var a = new AlphaTabScorePlayer(new BufferedSynthOutput());
        a.LoadScore(Fixture());
        using var b = new AlphaTabScorePlayer(new BufferedSynthOutput()) { Humanizer = new ManagedCoreBridge().Humanize };
        b.LoadScore(Fixture());
        Assert.Equal(0, b.HumanizedNotes);
        Assert.Equal(Notes(a.PlaybackMidi!), Notes(b.PlaybackMidi!));
    }

    [Fact]
    public void Played_times_and_velocities_replace_the_score_ones()
    {
        using var plain = new AlphaTabScorePlayer(new BufferedSynthOutput());
        plain.LoadScore(Fixture());
        var seen = new List<(string Part, int Player, int Count)>();
        HumanizedPart Late(IReadOnlyList<HumanizeNote> notes, string part, int player, string? _)
        {
            seen.Add((part, player, notes.Count));
            Assert.Equal(notes.OrderBy(n => n.Tick).ThenBy(n => n.Pitch), notes);
            Assert.All(notes, n => Assert.True(n.EndS > n.StartS));
            return new HumanizedPart(notes.Select(n => new PlayedNote(n.StartS + 0.010, n.EndS + 0.010, n.Pitch, 90, false, false)).ToList(), 5);
        }
        using var human = new AlphaTabScorePlayer(new BufferedSynthOutput()) { Humanizer = Late };
        human.LoadScore(Fixture());

        var a = Notes(plain.PlaybackMidi!);
        var b = Notes(human.PlaybackMidi!);
        Assert.Equal(a.Count, b.Count);
        Assert.Equal(a.Count, human.HumanizedNotes);
        Assert.Equal(human.Tracks.Count, seen.Count);
        Assert.All(b, n => Assert.Equal(90, n.Velocity));
        NativeCoreBridgeTests.AssertSorted(human.PlaybackMidi!);

        // 10 ms later, measured in ticks at the file's tempo.
        var tempo = MidiHumanizer.TempoMap.Of(plain.PlaybackMidi!);
        var shifts = a.OrderBy(n => n.Tick).ThenBy(n => n.Key).Zip(b.OrderBy(n => n.Tick).ThenBy(n => n.Key))
            .Select(x => tempo.Seconds(x.Second.Tick) - tempo.Seconds(x.First.Tick)).ToList();
        Assert.All(shifts, s => Assert.InRange(s, 0.008, 0.012));

        // Each pitched part starts with its detune bend.
        Assert.Contains(human.PlaybackMidi!.Events.OfType<PitchBendEvent>(), e => e.Tick == 0 && e.Value > 8192);
    }

    [Fact]
    public void Tempo_map_round_trips_ticks_and_seconds()
    {
        var midi = new MidiFile { Division = 960 };
        midi.AddEvent(new TempoChangeEvent(0, 500000));   // 120 bpm
        midi.AddEvent(new TempoChangeEvent(3840, 1000000)); // 60 bpm from bar 2
        var map = MidiHumanizer.TempoMap.Of(midi);
        Assert.Equal(2.0, map.Seconds(3840), 6);
        Assert.Equal(3.0, map.Seconds(4800), 6);
        Assert.Equal(4800, map.Ticks(3.0), 6);
        Assert.Equal(960, map.Ticks(0.5), 6);
    }
}
