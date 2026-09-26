using AlphaTab.Midi;

namespace Brasscribe.Play.Core.Playback;

/// <summary>One part note for the humanizer: Composition ticks (24 per beat), score-tempo seconds, concert MIDI pitch.</summary>
public sealed record HumanizeNote(long Tick, long DurTick, double StartS, double EndS, int Pitch, int Velocity);

/// <summary>A humanized note: played start and end in seconds and velocity.</summary>
public sealed record PlayedNote(double Start, double End, int Pitch, int Velocity, bool Staccato, bool FromComposition);

/// <summary>A player's humanized notes (in <see cref="HumanizeNote"/> order sorted by tick, pitch) and their detune in cents.</summary>
public sealed record HumanizedPart(IReadOnlyList<PlayedNote> Notes, double DetuneCents);

/// <summary>Humanizes one player's notes; null when no humanizer is available.</summary>
public delegate HumanizedPart? Humanize(IReadOnlyList<HumanizeNote> notes, string part, int player, string? compositionJson);

/// <summary>
/// Applies humanized timing and velocity to the playback MIDI that alphaTab generated. Note-on
/// and note-off ticks move to the played seconds (converted through the file's tempo map), velocities
/// follow the humanizer, and each part gets its detune as one pitch bend at the start. The tick
/// lookup that drives the cursor is left alone, so the cursor stays on the score's beats.
/// </summary>
public static class MidiHumanizer
{
    /// <summary>Composition ticks per quarter note.</summary>
    public const int CompositionTicksPerBeat = 24;

    /// <summary>Pitch-bend range of the synth, in semitones either side.</summary>
    private const double BendRangeSemitones = 2;

    public sealed record Track(int Index, string Name, bool Percussion, IReadOnlyList<int> Channels);

    /// <summary>Returns the number of notes that were humanized.</summary>
    public static int Apply(MidiFile midi, IReadOnlyList<Track> tracks, Humanize humanize, string? compositionJson)
    {
        var tempo = TempoMap.Of(midi);
        double division = midi.Division > 0 ? midi.Division : 960;
        var events = midi.Events;

        // Pair note-ons with their note-offs per (channel, key), in file order.
        var open = new Dictionary<(int, int), Queue<NoteEvent>>();
        var notesByTrack = new Dictionary<int, List<(NoteEvent On, NoteEvent Off)>>();
        foreach (var e in events)
        {
            if (e is not NoteEvent n) continue;
            var key = ((int)n.Channel, (int)n.NoteKey);
            if (e is NoteOnEvent && n.NoteVelocity > 0)
            {
                if (!open.TryGetValue(key, out var q)) open[key] = q = new Queue<NoteEvent>();
                q.Enqueue(n);
            }
            else if (e is NoteOffEvent || e is NoteOnEvent)
            {
                if (open.TryGetValue(key, out var q) && q.Count > 0)
                {
                    var on = q.Dequeue();
                    int t = (int)on.Track;
                    if (!notesByTrack.TryGetValue(t, out var list)) notesByTrack[t] = list = [];
                    list.Add((on, n));
                }
            }
        }

        int changed = 0;
        var bends = new List<MidiEvent>();
        var playerOf = new Dictionary<string, int>();
        foreach (var track in tracks)
        {
            int player = playerOf.TryGetValue(track.Name, out int p) ? p : 0;
            playerOf[track.Name] = player + 1;
            if (!notesByTrack.TryGetValue(track.Index, out var pairs) || pairs.Count == 0) continue;

            // The humanizer returns notes sorted by (tick, pitch); sort the same way so indexes line up.
            var sorted = pairs.OrderBy(x => x.On.Tick).ThenBy(x => x.On.NoteKey).ToList();
            var request = sorted.Select(x => new HumanizeNote(
                (long)Math.Round(x.On.Tick * CompositionTicksPerBeat / division),
                (long)Math.Round((x.Off.Tick - x.On.Tick) * CompositionTicksPerBeat / division),
                tempo.Seconds(x.On.Tick), tempo.Seconds(x.Off.Tick),
                (int)x.On.NoteKey, (int)x.On.NoteVelocity)).ToList();
            var result = humanize(request, track.Name, player, compositionJson);
            if (result is null || result.Notes.Count != sorted.Count) continue;

            var starts = new double[sorted.Count];
            var ends = new double[sorted.Count];
            for (int i = 0; i < sorted.Count; i++)
            {
                starts[i] = Math.Max(0, Math.Round(tempo.Ticks(result.Notes[i].Start)));
                ends[i] = Math.Max(starts[i] + 1, Math.Round(tempo.Ticks(result.Notes[i].End)));
            }
            // A note must end before the next note on the same channel and key starts.
            var next = new Dictionary<(int, int), int>();
            var order = Enumerable.Range(0, sorted.Count).OrderBy(i => starts[i]).ToList();
            for (int k = order.Count - 1; k >= 0; k--)
            {
                int i = order[k];
                var key = ((int)sorted[i].On.Channel, (int)sorted[i].On.NoteKey);
                if (next.TryGetValue(key, out int j) && ends[i] >= starts[j]) ends[i] = Math.Max(starts[i] + 1, starts[j] - 1);
                next[key] = i;
            }
            for (int i = 0; i < sorted.Count; i++)
            {
                var (on, off) = sorted[i];
                on.Tick = starts[i];
                off.Tick = ends[i];
                on.NoteVelocity = Math.Clamp(result.Notes[i].Velocity, 1, 127);
                changed++;
            }

            if (!track.Percussion && Math.Abs(result.DetuneCents) > 0.01)
            {
                double value = Math.Clamp(8192 + result.DetuneCents / (BendRangeSemitones * 100) * 8192, 0, 16383);
                foreach (int ch in track.Channels)
                    bends.Add(new PitchBendEvent(track.Index, 0, ch, Math.Round(value)));
            }
        }

        if (changed == 0 && bends.Count == 0) return 0;
        // Keep the file sorted by tick. At one tick the original order stays (stable sort);
        // the detune bends go after alphaTab's own start-of-track events.
        var all = events.Select((e, i) => (e, i)).Concat(bends.Select((e, i) => (e: e, i: i + events.Count)))
            .OrderBy(x => x.e.Tick).ThenBy(x => x.i).Select(x => x.e).ToList();
        events.Clear();
        foreach (var e in all) events.Add(e);
        return changed;
    }

    /// <summary>Ticks to seconds and back through the tempo changes of a MIDI file.</summary>
    internal sealed class TempoMap
    {
        private readonly List<(double Tick, double Seconds, double SecondsPerTick)> _segments = [];

        public static TempoMap Of(MidiFile midi)
        {
            double division = midi.Division > 0 ? midi.Division : 960;
            var map = new TempoMap();
            double tick = 0, seconds = 0, spt = 0.5 / division;
            foreach (var t in midi.Events.OfType<TempoChangeEvent>().OrderBy(e => e.Tick))
            {
                seconds += (t.Tick - tick) * spt;
                tick = t.Tick;
                spt = t.MicroSecondsPerQuarterNote / 1e6 / division;
                if (map._segments.Count > 0 && map._segments[^1].Tick == tick) map._segments[^1] = (tick, seconds, spt);
                else map._segments.Add((tick, seconds, spt));
            }
            if (map._segments.Count == 0 || map._segments[0].Tick > 0) map._segments.Insert(0, (0, 0, 0.5 / division));
            return map;
        }

        public double Seconds(double tick)
        {
            var s = _segments[Find(x => x.Tick <= tick)];
            return s.Seconds + (tick - s.Tick) * s.SecondsPerTick;
        }

        public double Ticks(double seconds)
        {
            var s = _segments[Find(x => x.Seconds <= seconds)];
            return s.Tick + (seconds - s.Seconds) / s.SecondsPerTick;
        }

        private int Find(Func<(double Tick, double Seconds, double SecondsPerTick), bool> atOrBefore)
        {
            int i = 0;
            while (i + 1 < _segments.Count && atOrBefore(_segments[i + 1])) i++;
            return i;
        }
    }
}
