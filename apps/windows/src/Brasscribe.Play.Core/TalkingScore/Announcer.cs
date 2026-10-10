using System.Globalization;
using System.Text;

namespace Brasscribe.Play.Core.TalkingScore;

/// <summary>
/// Builds talking-score announcements in English and Norwegian bokmål following
/// docs/accessibility/talking-score-spec.md; the conformance vectors are the reference.
/// Output never depends on the current culture: numbers are formatted by hand.
/// </summary>
public static class Announcer
{
    /// <summary>The number of a pickup (anacrusis): spoken as "pickup", never as a bar number (spec §4.10).</summary>
    public const int PickupBar = 0;

    public static string Announce(AnnouncePart part, AnnounceBar bar, TsEvent ev, AnnounceContext ctx,
        TalkingScoreSettings s, bool byBar = false)
    {
        var L = s.Nb ? Lexicon.Nb : Lexicon.En;

        if (ev.Kind == EventKind.ModeChange) return ModeChange(part, s, L);

        var sb = new StringBuilder();

        // Region change: entering a free-time passage, or a tempo resuming after one.
        if (bar.FreeRegion is { } region && bar.EnteringRegion)
        {
            int secs = RoundInt(region.EndS - region.StartS);
            sb.Append(L.AdLibEntry(region.StartBar, region.EndBar, secs)).Append(". ");
        }
        else if (bar.ATempo && bar.TempoMarked is { } resume)
        {
            sb.Append(L.ATempo(RoundInt(resume))).Append(". ");
        }

        bool partChanged = ctx.Part is not null && ctx.Part != part.Name;
        if (partChanged) sb.Append(s.Nb ? part.NameNb ?? part.Name : part.Name).Append(". ");

        bool inFreeTime = bar.FreeRegion is { Notation: "proportional" } && ev.TimeS is not null;
        var changes = BarChanges(bar, L);
        bool showBar = s.Verbosity == Verbosity.Full || byBar || ctx.Bar != bar.Number || partChanged || changes.Count > 0
                       || ev.Kind == EventKind.BarRest;

        if (ev.Kind == EventKind.BarRest)
        {
            if (bar.Number == PickupBar)
            {
                // The pickup is named, and is not one of the bars counted.
                int after = ev.Bars - 1;
                sb.Append(L.Pickup);
                if (after > 0) sb.Append(' ').Append(L.And).Append(' ').Append(after == 1 ? L.Bar(1) : L.BarsRange(1, after));
                sb.Append(": ").Append(after > 1 ? L.RestBars(after) : L.RestWord);
            }
            else
            {
                sb.Append(ev.Bars > 1
                    ? L.BarsRange(bar.Number, bar.Number + ev.Bars - 1) + ": " + L.RestBars(ev.Bars)
                    : L.Bar(bar.Number) + ": " + L.RestWholeBar);
            }
            return sb.ToString();
        }

        if (s.Verbosity != Verbosity.Brief && showBar)
        {
            sb.Append(L.Bar(bar.Number));
            if (s.Verbosity == Verbosity.Full && bar.TotalBars > 0 && bar.Number != PickupBar) sb.Append(L.Of).Append(bar.TotalBars);
            foreach (var c in changes) sb.Append(", ").Append(c);
            sb.Append(", ");
        }

        // Position.
        if (inFreeTime) sb.Append(L.AtTime(ev.TimeS!.Value));
        else if (ev.Pos is { } pos) sb.Append(s.Verbosity == Verbosity.Brief ? L.PositionBrief(pos) : L.Position(pos));
        sb.Append(": ");

        // Body.
        int key = s.PitchMode == PitchMode.Concert ? ConcertKey(bar.KeyFifths, part.Transpose) : bar.KeyFifths;
        bool brief = s.Verbosity == Verbosity.Brief;
        switch (ev.Kind)
        {
            case EventKind.Held:
            {
                var p = PitchOf(ev, s, key, L);
                sb.Append(p).Append(' ').Append(L.Held).Append(", ").Append(L.From);
                if (ev.HeldFrom is { } from)
                {
                    if (from.Bar != bar.Number) sb.Append(L.Bar(from.Bar)).Append(' ');
                    sb.Append(L.Position(new TsPos(from.Beat, from.Num, from.Den, from.Compound)));
                }
                return sb.ToString();
            }
            case EventKind.Rest:
                sb.Append(L.Rest(ev.Type ?? "quarter", ev.Dots, brief));
                break;
            case EventKind.Chord:
            {
                var pitches = (ev.Pitches ?? [])
                    .Select(cp => s.PitchMode == PitchMode.Concert ? cp.Concert : cp.Written)
                    .OrderBy(Midi)
                    .Select(p => L.Pitch(p, key, s.OctaveStyle)).ToList();
                sb.Append(L.Chord(pitches.Count)).Append(": ").Append(string.Join(", ", pitches))
                  .Append(", ").Append(L.Duration(ev.Type ?? "quarter", ev.Dots, brief));
                break;
            }
            case EventKind.Unpitched:
            {
                var names = (s.Nb ? ev.InstrumentsNb ?? ev.Instruments : ev.Instruments) ?? [];
                sb.Append(L.JoinAnd(names)).Append(", ").Append(L.Duration(ev.Type ?? "quarter", ev.Dots, brief));
                break;
            }
            default:
                if (s.Verbosity == Verbosity.Full && ev.Written is not null && ev.Concert is not null)
                {
                    int wkey = bar.KeyFifths, ckey = ConcertKey(bar.KeyFifths, part.Transpose);
                    sb.Append(L.WrittenSounds(L.Pitch(ev.Written, wkey, s.OctaveStyle), L.Pitch(ev.Concert, ckey, s.OctaveStyle)));
                }
                else
                {
                    sb.Append(PitchOf(ev, s, key, L));
                }
                sb.Append(brief ? " " : ", ").Append(L.Duration(ev.Type ?? "quarter", ev.Dots, brief));
                break;
        }

        // Modifiers: tie, tuplet, articulation, dynamic, performed, confidence.
        var mods = new List<string>();
        if (ev.Tie is { Start: true } tie)
        {
            if (tie.ChainBeats is { } total) mods.Add(L.TiedChain(total));
            else if (tie.Next is { } next) mods.Add(L.TiedTo(L.Duration(next.Type, next.Dots, false), next.Bar != bar.Number ? next.Bar : null));
        }
        if (ev.Tuplet is { } t) mods.Add(L.Tuplet(t));
        foreach (var a in ev.Articulations) mods.Add(L.Articulation(a));
        if (ev.Dynamic is { } d) mods.Add(L.Dynamic(d));
        if (bar.FreeRegion is not null && ev.PerformedS is >= 1.0) mods.Add(L.HeldAbout(RoundHalf(ev.PerformedS.Value)));
        if (ev.Confidence is { } conf && !ev.Checked)
        {
            var level = Scores.Note.CertaintyOf(conf);
            if (level == Scores.Certainty.VeryUncertain) mods.Add(L.VeryUncertain);
            else if (level == Scores.Certainty.Uncertain) mods.Add(L.Uncertain);
            else if (s.Verbosity == Verbosity.Full && s.AnnounceConfident) mods.Add(L.Confident);

            if (s.Verbosity == Verbosity.Full && (level != Scores.Certainty.Confident || s.AnnounceConfident))
            {
                mods.Add(L.ConfidencePercent(RoundInt(conf * 100)));
                if (ev.Sources.Count > 0) mods.Add(L.Sources(ev.Sources.Select(SourceName).ToList()));
            }
        }
        foreach (var m in mods) sb.Append(", ").Append(m);
        return sb.ToString();
    }

    /// <summary>The bar in brief form joined with ", " ("Read bar").</summary>
    public static string ReadBar(AnnouncePart part, AnnounceBar bar, IEnumerable<TsEvent> events, TalkingScoreSettings s)
    {
        var brief = s with { Verbosity = Verbosity.Brief };
        var ctx = new AnnounceContext(part.Name, bar.Number, s.PitchMode);
        var calm = bar with { EnteringRegion = false, ATempo = false, KeyChanged = false, TimeChanged = null, TempoMarked = null, Rehearsal = null };
        var L = s.Nb ? Lexicon.Nb : Lexicon.En;
        var items = events.Select(e => Announce(part, calm, e, ctx, brief)).ToList();
        return L.Bar(bar.Number) + ": " + string.Join(", ", items);
    }

    private static string ModeChange(AnnouncePart part, TalkingScoreSettings s, Lexicon L)
    {
        if (s.PitchMode == PitchMode.Concert) return L.ConcertPitch;
        string? instrument = s.Nb ? part.InstrumentNb ?? part.Instrument : part.Instrument;
        return instrument is null ? L.WrittenPitch : L.WrittenPitch + ", " + L.InstrumentName(instrument);
    }

    private static List<string> BarChanges(AnnounceBar bar, Lexicon L)
    {
        var list = new List<string>();
        if (bar.KeyChanged) list.Add(L.Key(bar.KeyFifths));
        if (bar.TimeChanged is { } t) list.Add(L.Time(t));
        if (bar.TempoMarked is { } bpm && !bar.ATempo) list.Add(L.Tempo(RoundInt(bpm)));
        if (bar.Rehearsal is { } r) list.Add(L.Rehearsal(r));
        return list;
    }

    private static string PitchOf(TsEvent ev, TalkingScoreSettings s, int key, Lexicon L)
    {
        var p = s.PitchMode == PitchMode.Concert ? ev.Concert ?? ev.Written : ev.Written ?? ev.Concert;
        return p is null ? "" : L.Pitch(p, key, s.OctaveStyle);
    }

    /// <summary>Key signature in concert pitch: the written key moved by the part's transposition.</summary>
    public static int ConcertKey(int writtenFifths, TsTranspose? t)
    {
        if (t is null || t.Chromatic % 12 == 0) return writtenFifths;
        int shift = ((t.Chromatic * 7) % 12 + 12) % 12; // semitones to fifths
        if (shift > 6) shift -= 12;
        int k = writtenFifths + shift;
        if (k > 7) k -= 12;
        if (k < -7) k += 12;
        return k;
    }

    internal static int Midi(TsPitch p)
    {
        int pc = p.Step switch { "C" => 0, "D" => 2, "E" => 4, "F" => 5, "G" => 7, "A" => 9, "B" => 11, _ => 0 };
        return (p.Octave + 1) * 12 + pc + p.Alter;
    }

    /// <summary>Display names for transcription sources; unknown names pass through.</summary>
    /// <summary>A note as the review screen shows it: "G, half note", "F♯, quarter note" · "Fiss, fjerdedelsnote".</summary>
    public static string NoteLabel(TsEvent ev, TalkingScoreSettings s)
    {
        var pitch = s.PitchMode == PitchMode.Concert ? ev.Concert ?? ev.Written : ev.Written ?? ev.Concert;
        if (ev.Kind == EventKind.Chord && ev.Pitches is { Count: > 0 } chord)
            pitch = s.PitchMode == PitchMode.Concert ? chord[^1].Concert : chord[^1].Written;
        string name = pitch is null ? "" : PitchLabel(pitch, s.Nb);
        string type = ev.Type is { } t ? (s.Nb ? NbLexicon.TypeName(t, false) : EnLexicon.TypeName(t, false)) : "";
        if (ev.Dots > 0 && type.Length > 0) type = (s.Nb ? "punktert " : "dotted ") + type;
        return name.Length == 0 ? type : type.Length == 0 ? name : $"{name}, {type}";
    }

    /// <summary>A pitch name without its octave: "F♯", "B♭" · Norwegian "Fiss", "B".</summary>
    public static string PitchLabel(TsPitch p, bool nb) => nb
        ? NbLexicon.Name(p.Step, p.Alter)
        : p.Step + p.Alter switch { 2 => "𝄪", 1 => "♯", -1 => "♭", -2 => "𝄫", _ => "" };

    public static string SourceName(string source) => source.ToLowerInvariant() switch
    {
        "swiftf0" or "swift-f0" => "SwiftF0",
        "muscriptor" => "MuScriptor",
        "basic-pitch" or "basicpitch" or "bp" => "Basic Pitch",
        "mega-53" or "mega53" => "Mega-53",
        "beat-this" => "Beat This!",
        _ => source,
    };

    /// <summary>Rounds half away from zero, as Rust's f64::round does.</summary>
    internal static int RoundInt(double x) => (int)Math.Round(x, MidpointRounding.AwayFromZero);

    internal static double RoundHalf(double x) => Math.Round(x * 2, MidpointRounding.AwayFromZero) / 2;
}

/// <summary>Word lists and phrase builders per language.</summary>
internal abstract class Lexicon
{
    public static readonly Lexicon En = new EnLexicon();
    public static readonly Lexicon Nb = new NbLexicon();

    public abstract char DecimalSeparator { get; }
    public abstract string Of { get; }
    public abstract string Held { get; }
    public abstract string From { get; }
    public abstract string RestWholeBar { get; }
    public abstract string Uncertain { get; }
    public abstract string VeryUncertain { get; }
    public abstract string Confident { get; }
    public abstract string ConcertPitch { get; }
    public abstract string WrittenPitch { get; }
    public abstract string And { get; }
    public abstract string Pickup { get; }
    public abstract string RestWord { get; }

    public abstract string Bar(int n);
    public abstract string BarsRange(int a, int b);
    public abstract string RestBars(int n);
    public abstract string Position(TsPos p);
    public abstract string PositionBrief(TsPos p);
    public abstract string Pitch(TsPitch p, int keyFifths, OctaveStyle style);
    public abstract string Duration(string type, int dots, bool brief);
    public abstract string Rest(string type, int dots, bool brief);
    public abstract string Chord(int n);
    public abstract string TiedTo(string duration, int? bar);
    public abstract string TiedChain(double beats);
    public abstract string Tuplet(TsTuplet t);
    public abstract string Articulation(string a);
    public abstract string HeldAbout(double seconds);
    public abstract string AtTime(double seconds);
    public abstract string AdLibEntry(int startBar, int endBar, int seconds);
    public abstract string ATempo(int bpm);
    public abstract string Key(int fifths);
    public abstract string Time(TsTime t);
    public abstract string Tempo(int bpm);
    public abstract string Rehearsal(string mark);
    public abstract string ConfidencePercent(int percent);
    public abstract string Sources(IReadOnlyList<string> names);
    public abstract string WrittenSounds(string written, string sounds);
    public abstract string InstrumentName(string instrument);

    public string Dynamic(string d) => d switch
    {
        "ppp" => "pianississimo",
        "pp" => "pianissimo",
        "p" => "piano",
        "mp" => "mezzo-piano",
        "mf" => "mezzo-forte",
        "f" => "forte",
        "ff" => "fortissimo",
        "fff" => "fortississimo",
        "sfz" => "sforzando",
        "fp" => "forte-piano",
        _ => d,
    };

    public string JoinAnd(IReadOnlyList<string> items) => items.Count switch
    {
        0 => "",
        1 => items[0],
        _ => string.Join(", ", items.Take(items.Count - 1)) + " " + And + " " + items[^1],
    };

    /// <summary>A number with at most one decimal and the language's separator, culture-free.</summary>
    public string Number(double x)
    {
        double r = Math.Round(x, 1, MidpointRounding.AwayFromZero);
        if (Math.Abs(r - Math.Round(r)) < 1e-9) return ((long)Math.Round(r)).ToString(CultureInfo.InvariantCulture);
        return r.ToString("0.0", CultureInfo.InvariantCulture).Replace('.', DecimalSeparator);
    }

    protected static bool KeyAlters(char step, int fifths)
    {
        const string sharps = "FCGDAEB";
        const string flats = "BEADGCF";
        return fifths > 0 ? sharps[..Math.Min(fifths, 7)].Contains(step)
             : fifths < 0 && flats[..Math.Min(-fifths, 7)].Contains(step);
    }

    protected static string Fraction(TsPos p) => $"{p.Num}/{p.Den}";

    /// <summary>In compound time, the offset in sixths of the beat when it is one: the even sixths are
    /// the beat's three eighths, all six its sixteenths; none is a triplet.</summary>
    protected static int? Sixths(TsPos p, int num, int den) =>
        p.Compound == true && num > 0 && 6 % den == 0 ? num * 6 / den : null;

    protected static (int Num, int Den) Reduce(int num, int den)
    {
        int g = Gcd(Math.Abs(num), Math.Abs(den));
        return g == 0 ? (num, den) : (num / g, den / g);
    }

    private static int Gcd(int a, int b) => b == 0 ? a : Gcd(b, a % b);
}

internal sealed class EnLexicon : Lexicon
{
    public override char DecimalSeparator => '.';
    public override string Of => " of ";
    public override string Held => "held";
    public override string From => "from ";
    public override string RestWholeBar => "rest, whole bar";
    public override string Uncertain => "uncertain";
    public override string VeryUncertain => "very uncertain";
    public override string Confident => "confident";
    public override string ConcertPitch => "Concert pitch";
    public override string WrittenPitch => "Written pitch";
    public override string And => "and";
    public override string Pickup => "pickup";
    public override string RestWord => "rest";

    public override string Bar(int n) => n == Announcer.PickupBar ? Pickup : $"bar {n}";
    public override string BarsRange(int a, int b) => $"bars {a} to {b}";
    public override string RestBars(int n) => $"rest, {n} bars";

    public override string Position(TsPos p) => "beat " + PositionBrief(p);

    public override string PositionBrief(TsPos p)
    {
        var (num, den) = Reduce(p.Num, p.Den);
        if (Sixths(p, num, den) is { } k)
            return k % 2 == 0 ? $"{p.Beat}, eighth {k / 2 + 1}" : $"{p.Beat}, sixteenth {k + 1}";
        return (num, den) switch
        {
            (0, _) => $"{p.Beat}",
            (1, 2) => $"{p.Beat} and",
            (1, 4) => $"{p.Beat} e",
            (3, 4) => $"{p.Beat} a",
            (1, 3) => $"{p.Beat}, triplet 2",
            (2, 3) => $"{p.Beat}, triplet 3",
            _ => $"{p.Beat} plus {num}/{den}",
        };
    }

    public override string Pitch(TsPitch p, int keyFifths, OctaveStyle style)
    {
        string acc = p.Alter switch
        {
            2 => "-double-sharp",
            1 => "-sharp",
            -1 => "-flat",
            -2 => "-double-flat",
            0 when KeyAlters(p.Step[0], keyFifths) => "-natural",
            _ => "",
        };
        return $"{p.Step}{acc} {p.Octave}";
    }

    internal static string TypeName(string type, bool brief) => type switch
    {
        "breve" => brief ? "double whole" : "double whole note",
        "whole" => brief ? "whole" : "whole note",
        "half" => brief ? "half" : "half note",
        "quarter" => brief ? "quarter" : "quarter note",
        "eighth" => brief ? "eighth" : "eighth note",
        "16th" => brief ? "sixteenth" : "sixteenth note",
        "32nd" => brief ? "thirty-second" : "thirty-second note",
        "64th" => brief ? "sixty-fourth" : "sixty-fourth note",
        _ => type,
    };

    private static string DotWord(int dots) => dots switch { 0 => "", 1 => "dotted ", 2 => "double-dotted ", _ => "triple-dotted " };

    public override string Duration(string type, int dots, bool brief) => DotWord(dots) + TypeName(type, brief);

    public override string Rest(string type, int dots, bool brief) => DotWord(dots) + TypeName(type, true) + " rest";

    public override string Chord(int n) => $"chord, {n} notes";
    public override string TiedTo(string duration, int? bar) => bar is null ? $"tied to {duration}" : $"tied to {duration} in bar {bar}";

    public override string TiedChain(double beats) => $"tied, {Beats(beats)} beats in all";

    private string Beats(double b)
    {
        double whole = Math.Floor(b);
        return Math.Abs(b - whole - 0.5) < 1e-9 ? $"{(long)whole} and a half" : Number(b);
    }

    public override string Tuplet(TsTuplet t) => t.Actual == 3 && t.Normal == 2
        ? $"triplet, {t.Index} of 3"
        : $"{t.Actual} in the time of {t.Normal}, {t.Index} of {t.Actual}";

    public override string Articulation(string a) => a switch
    {
        "fermata" => "fermata",
        "accent" => "accent",
        "staccato" => "staccato",
        "tenuto" => "tenuto",
        "marcato" or "strong-accent" => "marcato",
        "trill" => "trill",
        "trill-sharp" => "trill with sharp",
        "trill-flat" => "trill with flat",
        "trill-natural" => "trill with natural",
        "trill-double-sharp" => "trill with double sharp",
        "trill-flat-flat" => "trill with double flat",
        _ => a,
    };

    public override string HeldAbout(double seconds) => $"held about {Number(seconds)} seconds";

    public override string AtTime(double seconds)
    {
        int s = Announcer.RoundInt(seconds);
        if (s < 60) return $"at {s} {(s == 1 ? "second" : "seconds")}";
        int m = s / 60, r = s % 60;
        return $"at {m} {(m == 1 ? "minute" : "minutes")} {r} {(r == 1 ? "second" : "seconds")}";
    }

    public override string AdLibEntry(int a, int b, int s)
    {
        string bars = a != Announcer.PickupBar ? $"bars {a} to {b}" : b == Announcer.PickupBar ? Pickup : $"pickup to bar {b}";
        return $"Ad lib, free time, {bars}, about {s} seconds";
    }
    public override string ATempo(int bpm) => $"A tempo, {bpm} beats per minute";

    public override string Key(int fifths) => fifths switch
    {
        0 => "no sharps or flats",
        1 => "key 1 sharp",
        -1 => "key 1 flat",
        > 0 => $"key {fifths} sharps",
        _ => $"key {-fifths} flats",
    };

    public override string Time(TsTime t) => $"{t.Beats} {t.BeatType} time";
    public override string Tempo(int bpm) => $"tempo {bpm}";
    public override string Rehearsal(string mark) => $"rehearsal {mark}";
    public override string ConfidencePercent(int percent) => $"confidence {percent} percent";
    public override string Sources(IReadOnlyList<string> names) => (names.Count == 1 ? "source " : "sources ") + JoinAnd(names);
    public override string WrittenSounds(string written, string sounds) => $"written {written}, sounds {sounds}";

    public override string InstrumentName(string instrument) =>
        instrument.Replace("♭", "-flat").Replace("♯", "-sharp");
}

internal sealed class NbLexicon : Lexicon
{
    public override char DecimalSeparator => ',';
    public override string Of => " av ";
    public override string Held => "holdes";
    public override string From => "fra ";
    public override string RestWholeBar => "pause hele takten";
    public override string Uncertain => "usikker";
    public override string VeryUncertain => "svært usikker";
    public override string Confident => "sikker";
    public override string ConcertPitch => "Klingende tone";
    public override string WrittenPitch => "Skrevet tone";
    public override string And => "og";
    public override string Pickup => "opptakt";
    public override string RestWord => "pause";

    public override string Bar(int n) => n == Announcer.PickupBar ? Pickup : $"takt {n}";
    public override string BarsRange(int a, int b) => $"takt {a} til {b}";
    public override string RestBars(int n) => $"pause, {n} takter";

    public override string Position(TsPos p) => "slag " + PositionBrief(p);

    public override string PositionBrief(TsPos p)
    {
        var (num, den) = Reduce(p.Num, p.Den);
        if (Sixths(p, num, den) is { } k)
            return k % 2 == 0 ? $"{p.Beat}, {k / 2 + 1}. åttendedel" : $"{p.Beat}, {k + 1}. sekstendedel";
        return (num, den) switch
        {
            (0, _) => $"{p.Beat}",
            (1, 2) => $"{p.Beat}-og",
            (1, 4) => $"{p.Beat}, 2. av 4",
            (3, 4) => $"{p.Beat}, 4. av 4",
            (1, 3) => $"{p.Beat}, triol 2",
            (2, 3) => $"{p.Beat}, triol 3",
            _ => $"{p.Beat} pluss {num}/{den}",
        };
    }

    /// <summary>German-derived names: B♭ = B, B♮ = H, E♭ = Ess, A♭ = Ass.</summary>
    public static string Name(string step, int alter)
    {
        string letter = step == "B" ? "H" : step;
        return (step, alter) switch
        {
            ("B", -1) => "B",
            ("E", -1) => "Ess",
            ("A", -1) => "Ass",
            (_, -1) => letter + "ess",
            (_, 1) => letter + "iss",
            (_, 2) => letter + " dobbeltkryss",
            (_, -2) => letter + " dobbelt-b",
            _ => letter,
        };
    }

    public override string Pitch(TsPitch p, int keyFifths, OctaveStyle style)
    {
        string name = Name(p.Step, p.Alter);
        if (style == OctaveStyle.Helmholtz)
        {
            string lower = name.ToLowerInvariant();
            return p.Octave switch
            {
                <= 1 => $"kontra {name}",
                2 => $"store {name}",
                3 => $"lille {lower}",
                4 => $"enstrøken {lower}",
                5 => $"tostrøken {lower}",
                6 => $"trestrøken {lower}",
                _ => $"{lower} {p.Octave}",
            };
        }
        return $"{name} {p.Octave}";
    }

    internal static string TypeName(string type, bool brief) => type switch
    {
        "breve" => "brevis",
        "whole" => brief ? "hel" : "helnote",
        "half" => brief ? "halv" : "halvnote",
        "quarter" => brief ? "fjerdedel" : "fjerdedelsnote",
        "eighth" => brief ? "åttendedel" : "åttendedelsnote",
        "16th" => brief ? "sekstendedel" : "sekstendedelsnote",
        "32nd" => brief ? "trettitodel" : "trettitodelsnote",
        "64th" => brief ? "sekstifiredel" : "sekstifiredelsnote",
        _ => type,
    };

    private static string RestName(string type) => type switch
    {
        "breve" => "brevispause",
        "whole" => "helpause",
        "half" => "halvpause",
        "quarter" => "fjerdedelspause",
        "eighth" => "åttendedelspause",
        "16th" => "sekstendedelspause",
        "32nd" => "trettitodelspause",
        "64th" => "sekstifiredelspause",
        _ => type + " pause",
    };

    private static string DotWord(int dots) => dots switch { 0 => "", 1 => "punktert ", 2 => "dobbeltpunktert ", _ => "trippelpunktert " };

    public override string Duration(string type, int dots, bool brief) => DotWord(dots) + TypeName(type, brief);
    public override string Rest(string type, int dots, bool brief) => DotWord(dots) + RestName(type);
    public override string Chord(int n) => $"akkord, {n} toner";
    public override string TiedTo(string duration, int? bar) => bar is null ? $"bundet til {duration}" : $"bundet til {duration} i takt {bar}";

    public override string TiedChain(double beats)
    {
        double whole = Math.Floor(beats);
        string b = Math.Abs(beats - whole - 0.5) < 1e-9 ? $"{(long)whole} og et halvt" : Number(beats);
        return $"bundet, {b} slag i alt";
    }

    public override string Tuplet(TsTuplet t) => t.Actual == 3 && t.Normal == 2
        ? $"triol, {t.Index} av 3"
        : $"{t.Actual} på {t.Normal}, {t.Index} av {t.Actual}";

    public override string Articulation(string a) => a switch
    {
        "fermata" => "fermat",
        "accent" => "aksent",
        "staccato" => "staccato",
        "tenuto" => "tenuto",
        "marcato" or "strong-accent" => "marcato",
        "trill" => "trille",
        "trill-sharp" => "trille med kryss",
        "trill-flat" => "trille med b",
        "trill-natural" => "trille med oppløsningstegn",
        "trill-double-sharp" => "trille med dobbeltkryss",
        "trill-flat-flat" => "trille med dobbelt-b",
        _ => a,
    };

    public override string HeldAbout(double seconds) => $"holdes omtrent {Number(seconds)} sekunder";

    public override string AtTime(double seconds)
    {
        int s = Announcer.RoundInt(seconds);
        if (s < 60) return $"ved {s} {(s == 1 ? "sekund" : "sekunder")}";
        int m = s / 60, r = s % 60;
        return $"ved {m} {(m == 1 ? "minutt" : "minutter")} {r} {(r == 1 ? "sekund" : "sekunder")}";
    }

    public override string AdLibEntry(int a, int b, int s)
    {
        string bars = a != Announcer.PickupBar ? $"takt {a} til {b}" : b == Announcer.PickupBar ? Pickup : $"opptakt til takt {b}";
        return $"Ad lib, fritt tempo, {bars}, omtrent {s} sekunder";
    }
    public override string ATempo(int bpm) => $"A tempo, {bpm} slag per minutt";

    public override string Key(int fifths) => fifths switch
    {
        0 => "ingen faste fortegn",
        > 0 => $"{fifths} kryss",
        _ => $"{-fifths} b",
    };

    public override string Time(TsTime t)
    {
        string unit = t.BeatType switch
        {
            1 => "hel",
            2 => "halvdels",
            4 => "fjerdedels",
            8 => "åttendedels",
            16 => "sekstendedels",
            _ => $"{t.BeatType}-dels",
        };
        return $"{t.Beats} {unit} takt";
    }

    public override string Tempo(int bpm) => $"tempo {bpm}";
    public override string Rehearsal(string mark) => $"øvingsbokstav {mark}";
    public override string ConfidencePercent(int percent) => $"sikkerhet {percent} prosent";
    public override string Sources(IReadOnlyList<string> names) => (names.Count == 1 ? "kilde " : "kilder ") + JoinAnd(names);
    public override string WrittenSounds(string written, string sounds) => $"skrevet {written}, klinger {sounds}";
    public override string InstrumentName(string instrument) => instrument;
}
