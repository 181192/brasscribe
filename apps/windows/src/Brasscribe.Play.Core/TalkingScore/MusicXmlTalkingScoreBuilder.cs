using System.Globalization;
using System.Xml;
using System.Xml.Linq;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.TalkingScore;

/// <summary>
/// Builds the talking-score structure (spec §6) from a partwise MusicXML score plus, when available,
/// the Composition it was arranged from. The MusicXML gives what is printed (spelled written pitch,
/// types, ties, tuplets); the Composition adds confidence, sources, performed time and free regions.
/// Tick and DurTicks are in <see cref="TicksPerQuarter"/> units, exact for the tuplets the engine writes.
/// </summary>
public static class MusicXmlTalkingScoreBuilder
{
    public const int TicksPerQuarter = 10080;

    /// <summary>Confidence given to notes the MusicXML colours as uncertain when no Composition matches them.</summary>
    public const double ColourOnlyConfidence = 0.55;

    public static TalkingScoreDocument Build(string musicXml, Composition? composition = null)
    {
        var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore, XmlResolver = null };
        using var reader = XmlReader.Create(new StringReader(musicXml), settings);
        var doc = XDocument.Load(reader);
        var root = doc.Root ?? throw new FormatException("Empty MusicXML document");
        if (root.Name.LocalName != "score-partwise") throw new FormatException("Only score-partwise MusicXML is supported");

        var ts = new TalkingScoreDocument
        {
            Title = (string?)root.Element("work")?.Element("work-title") ?? (string?)root.Element("movement-title") ?? "",
        };

        var partInfo = root.Element("part-list")?.Elements("score-part").ToDictionary(
            sp => (string)sp.Attribute("id")!,
            sp => (Name: (string?)sp.Element("part-name") ?? "Part",
                   Instrument: (string?)sp.Element("score-instrument")?.Element("instrument-name"))) ?? [];

        var matcher = composition is null ? null : new CompositionMatcher(composition);
        var measureStartQuarters = new List<double>();
        bool firstPart = true;

        foreach (var partEl in root.Elements("part"))
        {
            string id = (string)partEl.Attribute("id")!;
            var (name, instrument) = partInfo.TryGetValue(id, out var info) ? info : ("Part", null);
            var part = new TsPart
            {
                Id = id,
                Name = name,
                NameNb = PartNames.Nb(name),
                Instrument = instrument,
                InstrumentNb = instrument is null ? null : PartNames.InstrumentNb(instrument),
            };

            int divisions = 1, fifths = 0;
            var time = new TsTime(4, 4);
            double partQuarter = 0;
            int tupletCount = 0;
            var pendingTies = new List<(TsEvent Event, int Midi, int Bar)>();
            var chains = new Dictionary<TsEvent, ChainInfo>(ReferenceEqualityComparer.Instance);
            ChainInfo ChainHead(TsEvent e) => chains.TryGetValue(e, out var ci) ? ci : chains[e] = new ChainInfo(e);

            foreach (var m in partEl.Elements("measure"))
            {
                int number = int.TryParse((string?)m.Attribute("number"), NumberStyles.Integer, CultureInfo.InvariantCulture, out var n)
                    ? n : part.Bars.Count + 1;
                double? tempo = null;
                string? rehearsal = null;
                string? pendingDynamic = null;
                long offset = 0; // in divisions
                long measureLength = 0;
                TsEvent? last = null;

                if (firstPart) measureStartQuarters.Add(partQuarter);

                var bar = new TsBar { Number = number };
                foreach (var el in m.Elements())
                {
                    switch (el.Name.LocalName)
                    {
                        case "attributes":
                            divisions = (int?)el.Element("divisions") ?? divisions;
                            fifths = (int?)el.Element("key")?.Element("fifths") ?? fifths;
                            if (el.Element("time") is { } t)
                                time = new TsTime((int?)t.Element("beats") ?? 4, (int?)t.Element("beat-type") ?? 4);
                            if (el.Element("transpose") is { } tr)
                                part.Transpose = new TsTranspose((int?)tr.Element("chromatic") ?? 0, (int?)tr.Element("diatonic") ?? 0,
                                    (int?)tr.Element("octave-change") ?? 0);
                            if ((string?)el.Element("clef")?.Element("sign") == "percussion") part.Percussion = true;
                            break;
                        case "direction":
                            if (el.Descendants("sound").Attributes("tempo").FirstOrDefault() is { } ta
                                && double.TryParse(ta.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var bpm))
                                tempo = bpm;
                            if (el.Descendants("rehearsal").FirstOrDefault() is { } rh) rehearsal = rh.Value.Trim();
                            if (el.Descendants("dynamics").FirstOrDefault()?.Elements().FirstOrDefault() is { } dyn)
                                pendingDynamic = dyn.Name.LocalName;
                            break;
                        case "backup":
                            offset -= (long?)el.Element("duration") ?? 0;
                            break;
                        case "forward":
                            offset += (long?)el.Element("duration") ?? 0;
                            measureLength = Math.Max(measureLength, offset);
                            break;
                        case "note":
                        {
                            long dur = (long?)el.Element("duration") ?? 0;
                            bool chord = el.Element("chord") is not null;
                            bool grace = el.Element("grace") is not null;
                            string voice = (string?)el.Element("voice") ?? "1";
                            if (chord && last is not null)
                            {
                                AddChordTone(last, el, part);
                                continue;
                            }
                            long start = offset;
                            if (!grace) offset += dur;
                            measureLength = Math.Max(measureLength, offset);
                            if (grace || voice != "1")
                            {
                                if (voice != "1") last = null;
                                continue;
                            }

                            var ev = ReadNote(el, start, dur, divisions, time, part, ref tupletCount);
                            if (ev is null) continue;
                            if (pendingDynamic is not null && ev.Kind != EventKind.Rest && ev.Kind != EventKind.BarRest)
                            {
                                ev.Dynamic = pendingDynamic;
                                pendingDynamic = null;
                            }

                            double absQuarter = partQuarter + (double)start / divisions;
                            if (ev.Concert is { } concert)
                            {
                                int midi = Announcer.Midi(concert);
                                if (matcher?.Match(absQuarter, midi) is { } hit)
                                {
                                    ev.Confidence = hit.Confidence;
                                    ev.Sources = [.. hit.Sources];
                                    if (hit.OnsetS is { } on) ev.TimeS = on;
                                    if (hit.OnsetS is { } a && hit.OffsetS is { } b) ev.PerformedS = b - a;
                                    foreach (var art in hit.Articulations)
                                        if (!ev.Articulations.Contains(art)) ev.Articulations.Add(art);
                                }
                                else if (el.Attribute("color") is not null || el.Element("notehead")?.Attribute("color") is not null)
                                {
                                    ev.Confidence = ColourOnlyConfidence;
                                }
                                if (ev.TimeS is null && composition is not null)
                                    ev.TimeS = composition.SecondsAt(absQuarter * composition.TicksPerBeat);

                                // Ties: close any open tie on this pitch, open a new one when this note starts one.
                                bool stops = HasTie(el, "stop");
                                if (stops)
                                {
                                    int i = pendingTies.FindIndex(p => p.Midi == midi);
                                    if (i >= 0)
                                    {
                                        var (from, _, fromBar) = pendingTies[i];
                                        pendingTies.RemoveAt(i);
                                        from.Tie = (from.Tie ?? new TsTie(Start: true)) with
                                        {
                                            Next = new TsTieNext(number, ev.Type ?? "quarter", ev.Dots),
                                        };
                                        ev.Tie = new TsTie(Stop: true, Start: HasTie(el, "start"));
                                        ChainHead(from).ChainLength += ev.DurTicks;
                                        ChainHead(from).ChainCount++;
                                        chains[ev] = ChainHead(from);
                                    }
                                }
                                if (HasTie(el, "start"))
                                {
                                    ev.Tie = (ev.Tie ?? new TsTie()) with { Start = true };
                                    pendingTies.Add((ev, midi, number));
                                    if (!chains.ContainsKey(ev)) chains[ev] = new ChainInfo(ev);
                                }
                            }
                            bar.Events.Add(ev);
                            last = ev;
                            break;
                        }
                    }
                }

                bar.KeyFifths = fifths;
                bar.Time = time;
                bar.TempoBpm = tempo;
                bar.Rehearsal = rehearsal;
                part.Bars.Add(bar);
                partQuarter += measureLength > 0 ? (double)measureLength / divisions : 4.0 * time.Beats / time.BeatType;
            }

            foreach (var chain in chains.Values.Distinct())
                if (chain.ChainCount > 2 && chain.Head.Tie is { } t)
                    chain.Head.Tie = t with { ChainBeats = (double)chain.ChainLength / TicksPerQuarter };
            ts.Parts.Add(part);
            firstPart = false;
        }

        ts.TotalBars = ts.Parts.Count == 0 ? 0 : ts.Parts.Max(p => p.Bars.Count);
        if (composition is not null && ts.Parts.Count > 0)
            ts.FreeRegions = MapFreeRegions(composition, measureStartQuarters, ts.Parts[0]);
        return ts;
    }

    // Tie chains: the first note of a chain longer than two notes announces the total length.
    private sealed class ChainInfo(TsEvent head)
    {
        public TsEvent Head { get; } = head;
        public long ChainLength { get; set; } = head.DurTicks;
        public int ChainCount { get; set; } = 1;
    }

    private static bool HasTie(XElement note, string type) =>
        note.Elements("tie").Any(t => (string?)t.Attribute("type") == type)
        || note.Element("notations")?.Elements("tied").Any(t => (string?)t.Attribute("type") == type) == true;

    private static TsEvent? ReadNote(XElement el, long start, long dur, int divisions, TsTime time, TsPart part, ref int tupletCount)
    {
        var ev = new TsEvent
        {
            Tick = (int)(start * TicksPerQuarter / divisions),
            DurTicks = (int)(dur * TicksPerQuarter / divisions),
            Pos = Position(start, divisions, time),
            Type = (string?)el.Element("type"),
            Dots = el.Elements("dot").Count(),
        };

        if (el.Element("rest") is { } rest)
        {
            if ((string?)rest.Attribute("measure") == "yes" || ev.Type is null && start == 0)
            {
                ev.Kind = EventKind.BarRest;
                ev.Pos = new TsPos(1);
            }
            else ev.Kind = EventKind.Rest;
            ev.Type ??= TypeFromDuration(dur, divisions);
            return ev;
        }

        ev.Type ??= TypeFromDuration(dur, divisions);

        if (el.Element("time-modification") is { } tm)
        {
            int actual = (int?)tm.Element("actual-notes") ?? 3, normal = (int?)tm.Element("normal-notes") ?? 2;
            ev.Tuplet = new TsTuplet(actual, normal, tupletCount % actual + 1);
            tupletCount++;
        }
        else tupletCount = 0;

        if (el.Element("notations") is { } nots)
        {
            foreach (var a in nots.Element("articulations")?.Elements() ?? [])
                ev.Articulations.Add(a.Name.LocalName);
            if (nots.Element("fermata") is not null) ev.Articulations.Add("fermata");
            if (nots.Element("dynamics")?.Elements().FirstOrDefault() is { } d) ev.Dynamic = d.Name.LocalName;
        }

        if (el.Element("unpitched") is { } up)
        {
            ev.Kind = EventKind.Unpitched;
            var (en, nb) = PartNames.Drum((string?)up.Element("display-step") ?? "C", (int?)up.Element("display-octave") ?? 5,
                (string?)el.Element("notehead"));
            ev.Instruments = [en];
            ev.InstrumentsNb = [nb];
            return ev;
        }

        if (el.Element("pitch") is not { } p) return null;
        var written = new TsPitch((string?)p.Element("step") ?? "C", (int?)p.Element("alter") ?? 0, (int?)p.Element("octave") ?? 4);
        ev.Kind = EventKind.Note;
        ev.Written = written;
        ev.Concert = part.Percussion ? written : ToConcert(written, part.Transpose);
        if (el.Element("notehead")?.Attribute("parentheses")?.Value == "yes") ev.Confidence ??= 0.3;
        return ev;
    }

    private static void AddChordTone(TsEvent head, XElement el, TsPart part)
    {
        if (el.Element("unpitched") is { } up)
        {
            var (en, nb) = PartNames.Drum((string?)up.Element("display-step") ?? "C", (int?)up.Element("display-octave") ?? 5,
                (string?)el.Element("notehead"));
            if (head.Instruments is not null && !head.Instruments.Contains(en)) head.Instruments.Add(en);
            if (head.InstrumentsNb is not null && !head.InstrumentsNb.Contains(nb)) head.InstrumentsNb.Add(nb);
            return;
        }
        if (el.Element("pitch") is not { } p || head.Written is null) return;
        var written = new TsPitch((string?)p.Element("step") ?? "C", (int?)p.Element("alter") ?? 0, (int?)p.Element("octave") ?? 4);
        if (head.Kind == EventKind.Note)
        {
            head.Kind = EventKind.Chord;
            head.Pitches = [new TsChordPitch(head.Written, head.Concert ?? head.Written)];
        }
        head.Pitches!.Add(new TsChordPitch(written, part.Percussion ? written : ToConcert(written, part.Transpose)));
    }

    /// <summary>Concert pitch keeping the diatonic spelling: written + chromatic semitones, + diatonic steps.</summary>
    public static TsPitch ToConcert(TsPitch written, TsTranspose t)
    {
        const string steps = "CDEFGAB";
        int stepIndex = steps.IndexOf(written.Step[0]);
        int diatonic = t.Diatonic + 7 * t.Octave;
        int chromatic = t.Chromatic + 12 * t.Octave;
        int absStep = written.Octave * 7 + stepIndex + diatonic;
        int octave = Math.DivRem(absStep, 7, out int rem);
        if (rem < 0) { rem += 7; octave--; }
        var target = new TsPitch(steps[rem].ToString(), 0, octave);
        int alter = Announcer.Midi(written) + chromatic - Announcer.Midi(target);
        return target with { Alter = alter };
    }

    internal static TsPos Position(long offset, int divisions, TsTime time)
    {
        bool compound = time.BeatType == 8 && time.Beats % 3 == 0 && time.Beats > 3;
        long beatDiv = (long)divisions * 4 / time.BeatType * (compound ? 3 : 1);
        if (beatDiv <= 0) return new TsPos(1);
        long beat = offset / beatDiv;
        long rem = offset % beatDiv;
        long g = Gcd(rem, beatDiv);
        return rem == 0 ? new TsPos((int)beat + 1) : new TsPos((int)beat + 1, (int)(rem / g), (int)(beatDiv / g));
    }

    private static long Gcd(long a, long b) => b == 0 ? a : Gcd(b, a % b);

    private static string TypeFromDuration(long dur, int divisions)
    {
        double q = (double)dur / divisions;
        return q switch
        {
            >= 8 => "breve",
            >= 4 => "whole",
            >= 2 => "half",
            >= 1 => "quarter",
            >= 0.5 => "eighth",
            >= 0.25 => "16th",
            >= 0.125 => "32nd",
            _ => "64th",
        };
    }

    private static List<TsFreeRegion> MapFreeRegions(Composition c, List<double> measureStarts, TsPart part)
    {
        var result = new List<TsFreeRegion>();
        foreach (var r in c.FreeRegions)
        {
            double startQ = (double)r.Start / c.TicksPerBeat, endQ = (double)r.End / c.TicksPerBeat;
            int startBar = BarAt(startQ), endBar = BarAt(Math.Max(startQ, endQ - 1e-6));
            result.Add(new TsFreeRegion
            {
                StartBar = part.Bars[Math.Clamp(startBar, 0, part.Bars.Count - 1)].Number,
                EndBar = part.Bars[Math.Clamp(endBar, 0, part.Bars.Count - 1)].Number,
                StartS = r.StartS,
                EndS = r.EndS,
                TempoBpm = r.TempoBpm,
                Notation = r.Notation,
                Label = r.Label,
            });
        }
        return result;

        int BarAt(double q)
        {
            int i = measureStarts.FindLastIndex(s => s <= q + 1e-9);
            return Math.Max(0, i);
        }
    }

    /// <summary>
    /// Finds the Composition note behind a printed note: same onset (in quarters from tick 0) and the
    /// same concert pitch, else the same pitch class (the arranger may move a line by octaves).
    /// </summary>
    private sealed class CompositionMatcher
    {
        private readonly Dictionary<long, List<Note>> _byOnset = [];
        private readonly int _tpb;

        public CompositionMatcher(Composition c)
        {
            _tpb = c.TicksPerBeat;
            foreach (var n in c.Voices.Where(v => v.Layer != "drums" && v.Role != VoiceRole.Rhythm).SelectMany(v => v.Notes))
            {
                long key = n.Start;
                if (!_byOnset.TryGetValue(key, out var list)) _byOnset[key] = list = [];
                list.Add(n);
            }
        }

        public Note? Match(double quarter, int midi)
        {
            long tick = (long)Math.Round(quarter * _tpb);
            for (long d = 0; d <= 1; d++)
            {
                foreach (long t in d == 0 ? [tick] : new[] { tick - 1, tick + 1 })
                {
                    if (!_byOnset.TryGetValue(t, out var list)) continue;
                    var exact = list.FirstOrDefault(n => n.Pitch == midi);
                    if (exact is not null) return exact;
                    var pc = list.FirstOrDefault(n => ((n.Pitch - midi) % 12 + 12) % 12 == 0);
                    if (pc is not null) return pc;
                }
            }
            return null;
        }
    }
}

/// <summary>Norwegian part and instrument names (spec §7, a proposal) and drum-kit positions.</summary>
public static class PartNames
{
    private static readonly Dictionary<string, string> Nb_ = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Soprano Cornet"] = "Sopran-kornett",
        ["Solo Cornet"] = "Solokornett",
        ["Repiano Cornet"] = "Repiano-kornett",
        ["2nd Cornet"] = "2. kornett",
        ["3rd Cornet"] = "3. kornett",
        ["Flugelhorn"] = "Flygelhorn",
        ["Solo Horn"] = "Solo althorn",
        ["1st Horn"] = "1. althorn",
        ["2nd Horn"] = "2. althorn",
        ["1st Baritone"] = "1. baryton",
        ["2nd Baritone"] = "2. baryton",
        ["1st Trombone"] = "1. trombone",
        ["2nd Trombone"] = "2. trombone",
        ["Bass Trombone"] = "Basstrombone",
        ["Euphonium"] = "Eufonium",
        ["E♭ Bass"] = "Ess-bass",
        ["B♭ Bass"] = "B-bass",
        ["Percussion"] = "Slagverk",
    };

    public static string Nb(string en) => Nb_.TryGetValue(en, out var nb) ? nb : en;

    public static string InstrumentNb(string en)
    {
        string s = en
            .Replace("Soprano Cornet", "sopran-kornett").Replace("Cornet", "kornett")
            .Replace("Flugelhorn", "flygelhorn").Replace("Tenor Horn", "althorn").Replace("Horn", "althorn")
            .Replace("Baritone", "baryton").Replace("Euphonium", "eufonium").Replace("Bass Trombone", "basstrombone")
            .Replace("Trombone", "trombone").Replace("Drum Kit", "trommesett");
        s = s.Replace(" in B♭", " i B").Replace(" in E♭", " i Ess").Replace(" in C", " i C");
        if (s.Length > 0) s = char.ToLowerInvariant(s[0]) + s[1..];
        return s;
    }

    /// <summary>Common drum-set staff positions: F4 bass drum, C5 snare, x on G5 hi-hat, and so on.</summary>
    public static (string En, string Nb) Drum(string step, int octave, string? notehead) => (step, octave, notehead) switch
    {
        ("F", 4, _) or ("E", 4, _) => ("bass drum", "stortromme"),
        ("C", 5, _) => ("snare drum", "skarptromme"),
        ("G", 5, "x") => ("hi-hat", "hi-hat"),
        ("A", 5, "x") => ("crash cymbal", "crashcymbal"),
        ("F", 5, "x") => ("ride cymbal", "ridecymbal"),
        ("D", 4, "x") => ("pedal hi-hat", "pedal-hi-hat"),
        ("E", 5, _) or ("D", 5, _) => ("tom", "tom"),
        ("A", 4, _) => ("floor tom", "gulvtom"),
        _ => ("drum", "tromme"),
    };
}
