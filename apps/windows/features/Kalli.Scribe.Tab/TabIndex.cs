using System.Globalization;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;

namespace Kalli.Scribe.Tab;

/// <summary>
/// One written piece of a note in tab.musicxml. A note is one piece, or several tied ones when it crosses a beat or
/// a bar line, and it is written on each staff of a pair.
/// </summary>
/// <param name="Note">The note's place in the tab's notes (the <c>&lt;?fretted-note N?&gt;</c> instruction).</param>
/// <param name="Staff">0 is the first staff of the part.</param>
/// <param name="Bar">The measure, counted from 0 in the order they are written (a pickup is the first).</param>
/// <param name="BarNumber">The measure's printed number: 0 for a pickup.</param>
/// <param name="Onset">From the start of the measure, in <see cref="TabIndex.Ticks"/> to a quarter note.</param>
/// <param name="Pitch">Sounding MIDI pitch.</param>
/// <param name="Step">The pitch's letter, as the page spells it.</param>
/// <param name="Alter">Semitones from the letter, as the page spells it.</param>
/// <param name="String">1 is the top line; null on a notation staff.</param>
/// <param name="Fret">Null on a notation staff.</param>
/// <param name="First">Where the note starts: the piece no tie comes into.</param>
/// <param name="Confidence">The <c>&lt;?fretted-confidence?&gt;</c> of a doubtful note, on its first piece.</param>
/// <param name="Beat">The beat it starts in, 1 the first, by the time signature in force there; in a pickup, the beat of the full bar it leads into.</param>
/// <param name="Pickup">In a pickup: a first measure shorter than its time signature.</param>
public sealed record TabPiece(int Note, int Staff, int Bar, string BarNumber, int Onset, int Pitch, string Step, int Alter,
    int? String, int? Fret, bool First, double? Confidence, int Beat = 1, bool Pickup = false);

/// <summary>One written measure: its printed number, how long it is and how its beats are counted.</summary>
/// <param name="Number">The printed number: 0 for a pickup.</param>
/// <param name="Length">In <see cref="TabIndex.Ticks"/> to a quarter note: a full bar of its time signature, or what a pickup holds.</param>
/// <param name="Beats">Beats in a full bar of the time signature in force.</param>
/// <param name="BeatTicks">One beat, in <see cref="TabIndex.Ticks"/>.</param>
/// <param name="Pickup">A first measure shorter than its time signature.</param>
public sealed record TabMeasure(string Number, int Length, int Beats, int BeatTicks, bool Pickup = false)
{
    /// <summary>The beat that starts at or before <paramref name="tick"/> of this measure, 1 the first; in a pickup, the beat of the full bar it leads into.</summary>
    public int BeatAt(int tick) => Math.Clamp((Math.Max(tick, 0) + (Pickup ? Beats * BeatTicks - Length : 0)) / BeatTicks + 1, 1, Beats);
}

/// <summary>The boxed "! D1" above a column: the names of the notes that have no place there.</summary>
public sealed record TabNoPlace(int Staff, int Bar, string BarNumber, int Onset, IReadOnlyList<string> Names, int Beat = 1, bool Pickup = false)
{
    public bool Equals(TabNoPlace? other) => other is not null && Staff == other.Staff && Bar == other.Bar && BarNumber == other.BarNumber &&
        Onset == other.Onset && Names.SequenceEqual(other.Names) && Beat == other.Beat && Pickup == other.Pickup;

    public override int GetHashCode() => HashCode.Combine(Staff, Bar, BarNumber, Onset, Names.Count, Beat, Pickup);
}

/// <summary>
/// tab.musicxml as the tab view needs it: which drawn note is which note of the tab's data. The core says so in a
/// processing instruction on every note piece (core/targets/fretted/README.md, The note index); alphaTab drops
/// those when it reads the file, so they are read here, with each piece's measure, start and string, and a drawn
/// note is found again by those.
/// </summary>
public sealed partial class TabIndex
{
    /// <summary>alphaTab's ticks to a quarter note: onsets are kept in them, so they compare with a beat's start.</summary>
    public const int Ticks = 960;

    private readonly ILookup<int, TabPiece> _byNote;

    /// <param name="bars">Measures written.</param>
    /// <param name="tabStaff">The staff with the TAB clef; null in the notation layout.</param>
    /// <param name="header">The words over the first measure: "Drop D: D A D G B E, Capo 3".</param>
    /// <param name="tempo">Quarter notes a minute, as the first measure says; null when it does not.</param>
    /// <param name="measures">The measures in the order they are written; <paramref name="bars"/> of them.</param>
    public TabIndex(IReadOnlyList<TabPiece> pieces, IReadOnlyList<TabNoPlace> noPlace, int bars, int staves, int? tabStaff, string? header,
        int? tempo = null, IReadOnlyList<TabMeasure>? measures = null)
    {
        Pieces = pieces;
        NoPlace = noPlace;
        Bars = bars;
        Staves = staves;
        TabStaff = tabStaff;
        Header = header;
        Tempo = tempo;
        Measures = measures ?? [];
        _byNote = pieces.ToLookup(p => p.Note);
    }

    public IReadOnlyList<TabPiece> Pieces { get; }
    public IReadOnlyList<TabNoPlace> NoPlace { get; }
    /// <summary>Measures written.</summary>
    public int Bars { get; }
    public int Staves { get; }
    /// <summary>The staff with the TAB clef; null in the notation layout.</summary>
    public int? TabStaff { get; }
    /// <summary>The words over the first measure: "Drop D: D A D G B E, Capo 3".</summary>
    public string? Header { get; }
    /// <summary>Quarter notes a minute, as the first measure says; null when it does not.</summary>
    public int? Tempo { get; }
    /// <summary>The measures in the order they are written; <see cref="Bars"/> of them.</summary>
    public IReadOnlyList<TabMeasure> Measures { get; }

    /// <summary>The pieces of <paramref name="note"/> in the order they are written; empty for a note the document does not have.</summary>
    public IReadOnlyList<TabPiece> Of(int note) => [.. _byNote[note]];

    /// <summary>The staff the marks stand on: the tab staff, or the notation staff when it is the only one.</summary>
    public int MarkStaff => TabStaff ?? 0;

    /// <summary>The capo's fret, as the header says it; 0 without one.</summary>
    public int Capo => Header is not null && CapoWords().Match(Header) is { Success: true } m && int.TryParse(m.Groups[1].Value, CultureInfo.InvariantCulture, out int fret) ? fret : 0;

    /// <summary>The tuning's name, as the header says it ("Drop D").</summary>
    public string? TuningName
    {
        get
        {
            if (Header is null) return null;
            int colon = Header.IndexOf(':', StringComparison.Ordinal);
            string name = colon < 0 ? "" : Header[..colon].Trim();
            return name.Length > 0 ? name : null;
        }
    }

    [GeneratedRegex(@"\bCapo (\d+)")]
    private static partial Regex CapoWords();

    [GeneratedRegex(@"<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>\s*(?:\?|![^<]*)</words>(?:(?!</direction>).)*?</direction>\s*", RegexOptions.Singleline)]
    private static partial Regex MarkDirection();

    [GeneratedRegex(@"(<note(?:head)?\b[^>]*?)\s+color=""#[0-9A-Fa-f]{6,8}""")]
    private static partial Regex NoteColour();

    [GeneratedRegex(@"<direction\b[^>]*>(?:(?!</direction>).)*?<words\b[^>]*>([^<]*)</words>(?:(?!</direction>).)*?</direction>\s*", RegexOptions.Singleline)]
    private static partial Regex WordsDirection();

    private static readonly Dictionary<string, int> Steps = new() { ["C"] = 0, ["D"] = 2, ["E"] = 4, ["F"] = 5, ["G"] = 7, ["A"] = 9, ["B"] = 11 };

    /// <summary>
    /// <paramref name="musicXml"/> without the "?" and "!" words and without the doubt colour: the view draws its
    /// marks from the data, and would otherwise show them twice. For the renderer only; the file itself is kept as it is.
    /// </summary>
    public static string WithoutMarks(string musicXml) => NoteColour().Replace(MarkDirection().Replace(musicXml, ""), "$1");

    /// <summary>
    /// <paramref name="musicXml"/> for the renderer: without its marks (<see cref="WithoutMarks"/>) and without the words
    /// over the first measure (the tuning, the strings and the capo). The screen's header says those, and on the page a
    /// mark over the first notes would stand on them.
    /// </summary>
    public static string ForRenderer(string musicXml, string? header)
    {
        string bare = WithoutMarks(musicXml);
        if (header is null) return bare;
        bool done = false;
        return WordsDirection().Replace(bare, m =>
        {
            if (done || m.Groups[1].Value.Trim() != header) return m.Value;
            done = true;
            return "";
        });
    }

    private static string? Text(XElement? e, params string[] path)
    {
        foreach (var name in path) e = e?.Element(name);
        return e?.Value.Trim();
    }

    private static int? Int(XElement? e, params string[] path) =>
        int.TryParse(Text(e, path), NumberStyles.Integer, CultureInfo.InvariantCulture, out int n) ? n : null;

    private static double? Double(string? text) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out double d) ? d : null;

    /// <summary>Rounds half up, as the core and the other apps do (not to even).</summary>
    internal static int Round(double x) => (int)Math.Floor(x + 0.5);

    private static string? Instruction(XElement e, string target) =>
        e.Nodes().OfType<XProcessingInstruction>().FirstOrDefault(p => p.Target == target)?.Data.Trim();

    /// <summary>How long <paramref name="measure"/> is, in divisions: as far as its notes reach.</summary>
    private static int LengthOf(XElement measure)
    {
        int pos = 0, end = 0;
        foreach (var el in measure.Elements())
        {
            switch (el.Name.LocalName)
            {
                case "backup": pos -= Int(el, "duration") ?? 0; break;
                case "forward": pos += Int(el, "duration") ?? 0; break;
                case "note" when el.Element("chord") is null && el.Element("grace") is null: pos += Int(el, "duration") ?? 0; break;
            }
            end = Math.Max(end, pos);
        }
        return end;
    }

    private static XElement? Root(string musicXml)
    {
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore, XmlResolver = null, IgnoreComments = true };
        try
        {
            using var reader = XmlReader.Create(new StringReader(musicXml), settings);
            return XDocument.Load(reader).Root;
        }
        catch (XmlException)
        {
            return null;
        }
    }

    /// <summary>Reads the first part of <paramref name="musicXml"/>. A document that is not MusicXML gives an empty index.</summary>
    public static TabIndex Parse(string musicXml)
    {
        var part = Root(musicXml)?.Element("part");
        if (part is null) return new TabIndex([], [], 0, 1, null, null);
        var pieces = new List<TabPiece>();
        var noPlace = new List<TabNoPlace>();
        int divisions = 1, staves = 1, beats = 4, beatTicks = Ticks;
        int? tabStaff = null, tempo = null;
        string? header = null;
        var measures = part.Elements("measure").ToList();
        var written = new List<TabMeasure>();
        for (int bar = 0; bar < measures.Count; bar++)
        {
            var measure = measures[bar];
            string number = (string?)measure.Attribute("number") is { Length: > 0 } n ? n : (bar + 1).ToString(CultureInfo.InvariantCulture);
            // The time signature and the divisions of this measure are in force from its start.
            if (measure.Element("attributes") is { } a)
            {
                if (Int(a, "divisions") is > 0 and var d) divisions = d;
                if (Int(a, "time", "beats") is > 0 and var b) beats = b;
                if (Int(a, "time", "beat-type") is > 0 and var t) beatTicks = Ticks * 4 / t;
            }
            int pos = 0, last = 0;
            int TicksOf(int p) => p * Ticks / divisions;
            // A pickup is shorter than a bar: its notes are counted in the beats of the bar they lead into.
            int length = TicksOf(LengthOf(measure));
            int full = beats * beatTicks;
            bool pickup = bar == 0 && length >= 1 && length < full;
            int BeatAt(int onset) => (onset + (pickup ? full - length : 0)) / beatTicks + 1;
            written.Add(new TabMeasure(number, pickup ? length : full, beats, beatTicks, pickup));
            foreach (var el in measure.Elements())
            {
                switch (el.Name.LocalName)
                {
                    case "attributes":
                        if (Int(el, "divisions") is > 0 and var d) divisions = d;
                        if (Int(el, "staves") is { } s) staves = Math.Max(staves, s);
                        if (Int(el, "time", "beats") is > 0 and var b) beats = b;
                        if (Int(el, "time", "beat-type") is > 0 and var t) beatTicks = Ticks * 4 / t;
                        foreach (var clef in el.Elements("clef"))
                            if (Text(clef, "sign") == "TAB")
                                tabStaff = (int.TryParse((string?)clef.Attribute("number"), CultureInfo.InvariantCulture, out int c) ? c : 1) - 1;
                        break;
                    case "backup": pos -= Int(el, "duration") ?? 0; break;
                    case "forward": pos += Int(el, "duration") ?? 0; break;
                    case "direction":
                    {
                        int staff = (Int(el, "staff") ?? 1) - 1;
                        foreach (var type in el.Elements("direction-type"))
                            foreach (var words in type.Elements("words"))
                            {
                                string text = words.Value.Trim();
                                if (text == "?") continue;
                                if (text.StartsWith('!') && (string?)words.Attribute("enclosure") == "rectangle")
                                    noPlace.Add(new TabNoPlace(staff, bar, number, TicksOf(pos),
                                        text[1..].Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries), BeatAt(TicksOf(pos)), pickup));
                                else if (header is null && bar == 0 && text.Length > 0) header = text;
                            }
                        if (tempo is null && bar == 0 && Double((string?)el.Element("sound")?.Attribute("tempo")) is { } bpm) tempo = Round(bpm);
                        break;
                    }
                    case "note":
                    {
                        bool chord = el.Element("chord") is not null;
                        bool grace = el.Element("grace") is not null;
                        int onset = chord ? last : pos;
                        if (!chord && !grace) { last = pos; pos += Int(el, "duration") ?? 0; }
                        if (!int.TryParse(Instruction(el, "fretted-note"), NumberStyles.Integer, CultureInfo.InvariantCulture, out int index)) break;
                        if (el.Element("pitch") is not { } pitch || Text(pitch, "step") is not { } step || Int(pitch, "octave") is not { } octave) break;
                        int alter = Round(Double(Text(pitch, "alter")) ?? 0.0);
                        var technical = el.Element("notations")?.Element("technical");
                        pieces.Add(new TabPiece(
                            Note: index, Staff: (Int(el, "staff") ?? 1) - 1, Bar: bar, BarNumber: number, Onset: TicksOf(onset),
                            Pitch: 12 * (octave + 1) + Steps.GetValueOrDefault(step) + alter, Step: step, Alter: alter,
                            String: Int(technical, "string"), Fret: Int(technical, "fret"),
                            First: !el.Elements("tie").Any(t => (string?)t.Attribute("type") == "stop"),
                            Confidence: Double(Instruction(el, "fretted-confidence")),
                            Beat: BeatAt(TicksOf(onset)), Pickup: pickup));
                        break;
                    }
                }
            }
        }
        return new TabIndex(pieces, noPlace, measures.Count, staves, tabStaff, header, tempo, written);
    }
}
