using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using AlphaTab.Model;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// What alphaTab 1.8.4's MusicXML importer gets wrong for a brass-band score, and the fixes, applied around every
/// alphaTab parse (only alphaTab sees the changed bytes; saved and exported files keep the original).
/// <list type="bullet">
/// <item>Ties: an unnumbered stop is paired with an open start by comparing the stop's written pitch with the
/// starts' sounding pitch. In a transposing part the tie fails (the note sounds again) or joins a stale start on
/// another note, which then holds for seconds. A note whose start comes before its stop ties to itself and the
/// MIDI generator recurses until the stack overflows. <see cref="Prepare"/> numbers every tie (as the arranger
/// writes them since the ties were numbered) and puts a note's stop before its start.</item>
/// <item>Trills: alphaTab plays the auxiliary two semitones above the written note, whatever the key, the
/// accidental-mark or the transposition. <see cref="ApplyTrills"/> sets each trill's auxiliary from the
/// MusicXML: the next letter up, its accidental from the accidental-mark, else from the key.</item>
/// </list>
/// </summary>
public static class AlphaTabMusicXml
{
    /// <summary>A trill in the MusicXML: part and measure (0-based), onset in the measure (alphaTab ticks), its
    /// sounding key and the semitones up to its auxiliary.</summary>
    public sealed record Trill(int Part, int Measure, int OnsetTicks, int Key, int AuxSemitones);

    /// <summary>The MusicXML alphaTab should parse, and the trills to apply after it has.</summary>
    public sealed record Prepared(byte[] MusicXml, IReadOnlyList<Trill> Trills);

    private static readonly Regex PartRx = new(@"<part\b.*?</part>", RegexOptions.Singleline | RegexOptions.Compiled);
    private static readonly Regex NoteRx = new(@"<note\b.*?</note>", RegexOptions.Singleline | RegexOptions.Compiled);
    private static readonly Regex TiedRx = new(@"<tied\b[^>]*?/>|<tied\b[^>]*>\s*</tied>", RegexOptions.Singleline | RegexOptions.Compiled);
    private static readonly Regex TypeRx = new(@"\btype=""(start|stop)""", RegexOptions.Compiled);

    public static Prepared Prepare(byte[] musicXml)
    {
        string text = Encoding.UTF8.GetString(musicXml);
        bool ties = text.Contains("<tied", StringComparison.Ordinal);
        bool trills = text.Contains("<trill-mark", StringComparison.Ordinal);
        if (!ties && !trills) return new(musicXml, []);
        if (ties) text = PartRx.Replace(text, m => NumberTies(m.Value));
        var bytes = ties ? Encoding.UTF8.GetBytes(text) : musicXml;
        return new(bytes, trills ? FindTrills(bytes) : []);
    }

    /// <summary>
    /// One part: a note's stop goes before its start, and every tie without a number gets one. A start takes the
    /// lowest number no open tie holds, its stop the number of the open tie on the same pitch (the arranger's
    /// writer does the same).
    /// </summary>
    internal static string NumberTies(string part)
    {
        var open = new List<(string Key, string Number)>();
        return NoteRx.Replace(part, m =>
        {
            string note = m.Value;
            var tied = TiedRx.Matches(note);
            if (tied.Count == 0) return note;
            string key = PitchKey(note);
            // stop before start, the rest in place
            var ordered = tied.Cast<Match>().OrderBy(t => TypeRx.Match(t.Value) is { Success: true } x && x.Groups[1].Value == "start" ? 1 : 0).ToList();
            var replaced = new List<string>();
            foreach (var t in ordered)
            {
                string el = t.Value;
                var type = TypeRx.Match(el);
                if (!type.Success) { replaced.Add(el); continue; }
                var number = Regex.Match(el, @"\bnumber=""([^""]*)""");
                string n;
                if (type.Groups[1].Value == "start")
                {
                    n = number.Success ? number.Groups[1].Value
                        : Enumerable.Range(1, 1000).First(i => open.All(o => o.Number != i.ToString())).ToString();
                    open.RemoveAll(o => o.Number == n);
                    open.Add((key, n));
                }
                else
                {
                    int at = number.Success ? open.FindIndex(o => o.Number == number.Groups[1].Value) : open.FindLastIndex(o => o.Key == key);
                    n = number.Success ? number.Groups[1].Value : at >= 0 ? open[at].Number : "1";
                    if (at >= 0) open.RemoveAt(at);
                }
                replaced.Add(number.Success ? el : el.Replace("<tied ", $"<tied number=\"{n}\" "));
            }
            // write the reordered elements back into the slots the ties took
            var sb = new StringBuilder();
            int pos = 0;
            for (int i = 0; i < tied.Count; i++)
            {
                sb.Append(note, pos, tied[i].Index - pos).Append(replaced[i]);
                pos = tied[i].Index + tied[i].Length;
            }
            return sb.Append(note, pos, note.Length - pos).ToString();
        });
    }

    private static string PitchKey(string note)
    {
        static string Field(string s, string tag) => Regex.Match(s, $"<{tag}>(.*?)</{tag}>", RegexOptions.Singleline) is { Success: true } m ? m.Groups[1].Value.Trim() : "";
        string pitch = Field(note, "pitch");
        if (pitch.Length > 0)
        {
            // an <alter>0</alter> and no <alter> are the same pitch
            double alter = double.TryParse(Field(pitch, "alter"), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double a) ? a : 0;
            return $"{Field(pitch, "step")}{alter.ToString(System.Globalization.CultureInfo.InvariantCulture)}/{Field(pitch, "octave")}";
        }
        string unp = Field(note, "unpitched");
        return $"u{Field(unp, "display-step")}/{Field(unp, "display-octave")}";
    }

    private static readonly string[] Steps = ["C", "D", "E", "F", "G", "A", "B"];
    private static readonly int[] StepSemis = [0, 2, 4, 5, 7, 9, 11];

    /// <summary>Alter of each letter in a key signature of <paramref name="fifths"/>.</summary>
    private static int KeyAlter(int fifths, int step)
    {
        const string sharps = "FCGDAEB";
        char letter = Steps[step][0];
        int i = sharps.IndexOf(letter);
        if (fifths > 0) return i < fifths ? 1 : 0;
        if (fifths < 0) return 6 - i < -fifths ? -1 : 0;
        return 0;
    }

    private static int AccidentalAlter(string mark) => mark switch
    {
        "sharp" => 1, "natural" => 0, "flat" => -1, "double-sharp" or "sharp-sharp" => 2, "flat-flat" => -2,
        _ => int.MinValue,
    };

    /// <summary>Every trill-marked note of the MusicXML, in part order.</summary>
    public static List<Trill> FindTrills(byte[] musicXml)
    {
        var trills = new List<Trill>();
        using var reader = XmlReader.Create(new MemoryStream(musicXml), new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore, XmlResolver = null });
        var doc = new XmlDocument { XmlResolver = null };
        doc.Load(reader);
        int partIndex = -1;
        foreach (XmlElement part in doc.DocumentElement!.GetElementsByTagName("part"))
        {
            partIndex++;
            int divisions = 1, fifths = 0, transpose = 0, measureIndex = -1;
            foreach (XmlElement measure in part.GetElementsByTagName("measure"))
            {
                measureIndex++;
                int pos = 0, last = 0;
                foreach (XmlNode child in measure.ChildNodes)
                {
                    if (child is not XmlElement el) continue;
                    switch (el.Name)
                    {
                        case "attributes":
                            if (Int(el, "divisions") is int d && d > 0) divisions = d;
                            if (Int(el, "key/fifths") is int f) fifths = f;
                            if (el.SelectSingleNode("transpose") is XmlElement tr)
                                transpose = (Int(tr, "chromatic") ?? 0) + 12 * (Int(tr, "octave-change") ?? 0);
                            break;
                        case "backup": pos -= Int(el, "duration") ?? 0; break;
                        case "forward": pos += Int(el, "duration") ?? 0; break;
                        case "note":
                            bool chord = el.SelectSingleNode("chord") != null, grace = el.SelectSingleNode("grace") != null;
                            int onset = chord ? last : pos;
                            if (!chord && !grace) { last = pos; pos += Int(el, "duration") ?? 0; }
                            if (grace || el.SelectSingleNode("notations/ornaments/trill-mark") is null || el.SelectSingleNode("pitch") is not XmlElement p) break;
                            int step = Array.IndexOf(Steps, p.SelectSingleNode("step")?.InnerText.Trim() ?? "C");
                            int alter = (int)Math.Round(double.TryParse(p.SelectSingleNode("alter")?.InnerText, System.Globalization.CultureInfo.InvariantCulture, out double a) ? a : 0);
                            int octave = Int(p, "octave") ?? 4;
                            int written = 12 * (octave + 1) + StepSemis[Math.Max(0, step)] + alter;
                            int auxStep = (Math.Max(0, step) + 1) % 7, auxOctave = octave + (step == 6 ? 1 : 0);
                            string? mark = el.SelectSingleNode("notations/ornaments/accidental-mark")?.InnerText.Trim();
                            int auxAlter = mark is not null && AccidentalAlter(mark) is int ma && ma != int.MinValue ? ma : KeyAlter(fifths, auxStep);
                            int aux = 12 * (auxOctave + 1) + StepSemis[auxStep] + auxAlter;
                            trills.Add(new Trill(partIndex, measureIndex, onset * 960 / divisions, written + transpose, aux - written));
                            break;
                    }
                }
            }
        }
        return trills;
    }

    private static int? Int(XmlNode el, string path) =>
        el.SelectSingleNode(path) is { } n && int.TryParse(n.InnerText.Trim(), out int v) ? v : null;

    /// <summary>
    /// Sets each trilled note's auxiliary in the loaded score from <paramref name="trills"/> (matched by track,
    /// bar, onset and sounding key). Returns how many trills were set.
    /// </summary>
    public static int ApplyTrills(Score score, IReadOnlyList<Trill> trills)
    {
        if (trills.Count == 0) return 0;
        var byPlace = trills.GroupBy(t => (t.Part, t.Measure, t.OnsetTicks, t.Key)).ToDictionary(g => g.Key, g => g.First().AuxSemitones);
        int set = 0;
        foreach (var track in score.Tracks)
            foreach (var staff in track.Staves)
                foreach (var bar in staff.Bars)
                    foreach (var voice in bar.Voices)
                        foreach (var beat in voice.Beats)
                            foreach (var note in beat.Notes)
                            {
                                if (!note.IsTrill) continue;
                                int key = (int)note.RealValue;
                                if (byPlace.TryGetValue(((int)track.Index, (int)bar.Index, (int)beat.PlaybackStart, key), out int semis))
                                {
                                    note.TrillValue = key + semis;
                                    set++;
                                }
                            }
        return set;
    }
}
