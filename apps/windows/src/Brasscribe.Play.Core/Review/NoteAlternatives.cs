using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Review;

/// <summary>A note sounding in a transcription: onset in seconds and MIDI pitch.</summary>
public readonly record struct HeardNote(double OnsetS, int Pitch);

/// <summary>What else a note could be.</summary>
public enum AlternativeKind { OtherListening, Semitone, Octave }

/// <summary>A pitch the note could be instead: semitones from the written note, its name, and why it is offered.</summary>
public sealed record NoteAlternative(int Semitones, string Name, AlternativeKind Kind);

/// <summary>
/// The alternatives "Change note…" offers for an uncertain note (usability review 2, P1-9): what the
/// other transcriptions of that layer heard at the same onset first, then a semitone either side and
/// an octave either side. It also finds the Composition note behind a printed note, which is where a
/// change or a kept note is written.
/// </summary>
public static class NoteAlternatives
{
    /// <summary>How far apart two onsets may be and still be the same note.</summary>
    public const double OnsetWindowS = 0.08;

    private static readonly string[] Sharps = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
    private static readonly string[] Flats = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"];
    private static readonly string[] NbSharps = ["C", "Ciss", "D", "Diss", "E", "F", "Fiss", "G", "Giss", "A", "Aiss", "H"];
    private static readonly string[] NbFlats = ["C", "Dess", "D", "Ess", "E", "F", "Gess", "G", "Ass", "A", "B", "H"];

    /// <summary>A pitch name without octave, spelled for the key (sharps in sharp keys).</summary>
    public static string Spell(int midi, int keyFifths, bool nb)
    {
        int pc = ((midi % 12) + 12) % 12;
        bool flats = keyFifths < 0;
        return (nb ? flats ? NbFlats : NbSharps : flats ? Flats : Sharps)[pc];
    }

    /// <summary>The Composition note behind a printed event: same onset in seconds and the same pitch class.</summary>
    public static (Voice Voice, Note Note)? SourceOf(Composition composition, TsEvent ev)
    {
        if (ev.TimeS is not { } time || ev.Concert is not { } concert) return null;
        int pc = ((Announcer.Midi(concert) % 12) + 12) % 12;
        (Voice, Note)? best = null;
        double bestDist = OnsetWindowS;
        foreach (var v in composition.Voices)
            foreach (var n in v.Notes)
            {
                if (n.OnsetS is not { } on || ((n.Pitch % 12) + 12) % 12 != pc) continue;
                double d = Math.Abs(on - time);
                if (d <= bestDist) { bestDist = d; best = (v, n); }
            }
        return best;
    }

    /// <summary>
    /// The alternatives for a note: distinct pitches the other transcriptions heard within
    /// <see cref="OnsetWindowS"/> of its onset (moved into the note's octave when they are an octave
    /// apart only), then ±1 semitone and ±1 octave. <paramref name="writtenMidi"/> names them as written.
    /// </summary>
    public static IReadOnlyList<NoteAlternative> For(Note note, int writtenMidi, int keyFifths, bool nb,
        IEnumerable<IReadOnlyList<HeardNote>>? otherListenings = null)
    {
        var result = new List<NoteAlternative>();
        var seen = new HashSet<int> { 0 };
        void Add(int semitones, AlternativeKind kind)
        {
            if (!seen.Add(semitones)) return;
            result.Add(new NoteAlternative(semitones, Spell(writtenMidi + semitones, keyFifths, nb), kind));
        }
        if (note.OnsetS is { } onset && otherListenings is not null)
        {
            var heard = otherListenings.SelectMany(l => l)
                .Where(h => Math.Abs(h.OnsetS - onset) <= OnsetWindowS)
                .GroupBy(h => h.Pitch - note.Pitch)
                .OrderByDescending(g => g.Count()).ThenBy(g => Math.Abs(g.Key));
            foreach (var g in heard)
            {
                int d = g.Key;
                // An octave (or two) off is the same note in another register: offered as an octave below.
                if (d != 0 && d % 12 == 0) continue;
                if (Math.Abs(d) > 12) d = Math.Sign(d) * (Math.Abs(d) % 12);
                if (d != 0) Add(d, AlternativeKind.OtherListening);
            }
        }
        Add(-1, AlternativeKind.Semitone);
        Add(+1, AlternativeKind.Semitone);
        Add(-12, AlternativeKind.Octave);
        Add(+12, AlternativeKind.Octave);
        return result;
    }
}

/// <summary>The notes of a Standard MIDI file with their onsets in seconds (tempo changes applied).</summary>
public static class MidiNotes
{
    public static IReadOnlyList<HeardNote> Read(byte[] smf)
    {
        var notes = new List<(long Tick, int Pitch)>();
        var tempos = new List<(long Tick, int Usq)>();
        int division = 480;
        int pos = 0;
        string Chunk() => System.Text.Encoding.ASCII.GetString(smf, pos, 4);
        int Be32(int at) => smf[at] << 24 | smf[at + 1] << 16 | smf[at + 2] << 8 | smf[at + 3];
        if (smf.Length < 14 || Chunk() != "MThd") return [];
        division = smf[12] << 8 | smf[13];
        if ((division & 0x8000) != 0) return []; // SMPTE time is not used by the transcribers
        pos = 8 + Be32(4);
        while (pos + 8 <= smf.Length)
        {
            string id = Chunk();
            int len = Be32(pos + 4);
            int start = pos + 8, end = Math.Min(smf.Length, start + len);
            if (id == "MTrk") ReadTrack(smf, start, end, notes, tempos);
            pos = end;
        }
        tempos.Sort((a, b) => a.Tick.CompareTo(b.Tick));
        double Seconds(long tick)
        {
            double s = 0; long last = 0; int usq = 500000;
            foreach (var (t, u) in tempos)
            {
                if (t >= tick) break;
                s += (t - last) * usq / 1e6 / division;
                last = t; usq = u;
            }
            return s + (tick - last) * usq / 1e6 / division;
        }
        return notes.Select(n => new HeardNote(Seconds(n.Tick), n.Pitch)).OrderBy(n => n.OnsetS).ToList();
    }

    private static void ReadTrack(byte[] b, int i, int end, List<(long, int)> notes, List<(long, int)> tempos)
    {
        long tick = 0;
        int status = 0;
        int Var()
        {
            int v = 0;
            while (i < end)
            {
                int c = b[i++];
                v = (v << 7) | (c & 0x7F);
                if ((c & 0x80) == 0) break;
            }
            return v;
        }
        while (i < end)
        {
            tick += Var();
            if (i >= end) break;
            int s = b[i];
            if (s >= 0x80) { status = s; i++; }
            if (status == 0xFF)
            {
                int type = b[i++];
                int len = Var();
                if (type == 0x51 && len == 3 && i + 3 <= end) tempos.Add((tick, b[i] << 16 | b[i + 1] << 8 | b[i + 2]));
                i += len;
                status = 0;
            }
            else if (status is 0xF0 or 0xF7) { i += Var(); status = 0; }
            else
            {
                int kind = status & 0xF0;
                int d1 = b[i++];
                if (kind is 0xC0 or 0xD0) continue;
                int d2 = i < end ? b[i++] : 0;
                if (kind == 0x90 && d2 > 0 && (status & 0x0F) != 9) notes.Add((tick, d1));
            }
        }
    }
}
