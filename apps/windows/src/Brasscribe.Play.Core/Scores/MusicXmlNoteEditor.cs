using System.Xml.Linq;

namespace Brasscribe.Play.Core.Scores;

public static class MusicXmlNoteEditor
{
    private static readonly (string Step, int Alter)[] Sharps = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0), ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)];
    private static readonly (string Step, int Alter)[] Flats = [("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0), ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0)];

    public static string ReplaceTitle(string musicXml, string title)
    {
        var document = XDocument.Parse(musicXml, LoadOptions.PreserveWhitespace);
        var root = document.Root ?? throw new FormatException("Empty MusicXML document");
        XNamespace ns = root.Name.Namespace;
        var work = root.Element(ns + "work");
        if (work is null) { work = new XElement(ns + "work"); root.AddFirst(work); }
        var workTitle = work.Element(ns + "work-title");
        if (workTitle is null) { workTitle = new XElement(ns + "work-title"); work.AddFirst(workTitle); }
        workTitle.Value = title;
        return document.ToString(SaveOptions.DisableFormatting);
    }

    public static string ReplacePitch(string musicXml, string partId, int noteIndex, int midi, int fifths)
    {
        var document = XDocument.Parse(musicXml, LoadOptions.PreserveWhitespace);
        var root = document.Root ?? throw new FormatException("Empty MusicXML document");
        XNamespace ns = root.Name.Namespace;
        var part = root.Elements(ns + "part").FirstOrDefault(p => (string?)p.Attribute("id") == partId)
            ?? throw new KeyNotFoundException($"MusicXML part '{partId}' was not found");
        var notes = part.Elements(ns + "measure").SelectMany(m => m.Elements(ns + "note"))
            .Where(n => n.Element(ns + "grace") is null && n.Element(ns + "cue") is null).ToList();
        if (noteIndex < 0 || noteIndex >= notes.Count) throw new ArgumentOutOfRangeException(nameof(noteIndex));
        var note = notes[noteIndex];
        var pitch = note.Element(ns + "pitch") ?? throw new InvalidOperationException("Selected MusicXML note is not pitched");
        var spelled = Spell(midi, fifths);
        var stepElement = pitch.Element(ns + "step") ?? new XElement(ns + "step");
        var octaveElement = pitch.Element(ns + "octave") ?? new XElement(ns + "octave");
        pitch.Elements(ns + "alter").Remove();
        stepElement.Value = spelled.Step;
        octaveElement.Value = spelled.Octave.ToString(System.Globalization.CultureInfo.InvariantCulture);
        pitch.Elements().Where(e => e.Name != ns + "step" && e.Name != ns + "octave").Remove();
        stepElement.Remove(); octaveElement.Remove();
        pitch.Add(stepElement);
        if (spelled.Alter != 0) pitch.Add(new XElement(ns + "alter", spelled.Alter));
        pitch.Add(octaveElement);
        SetAccidental(note, ns, spelled, fifths);
        return document.ToString(SaveOptions.DisableFormatting);
    }

    /// <summary>
    /// The printed accidental of a changed note: the old one goes (an F♯ made F must not keep its sharp), and
    /// a sharp, flat or natural is printed where the new note leaves the key signature. Accidentals earlier
    /// in the bar are left to the renderer.
    /// </summary>
    private static void SetAccidental(XElement note, XNamespace ns, TalkingScore.TsPitch spelled, int fifths)
    {
        note.Elements(ns + "accidental").Remove();
        if (spelled.Alter == KeyAlter(spelled.Step, fifths)) return;
        var accidental = new XElement(ns + "accidental", spelled.Alter switch { > 0 => "sharp", < 0 => "flat", _ => "natural" });
        // MusicXML order: pitch, duration, tie, instrument, footnote, level, voice, type, dot, then accidental.
        string[] before = ["pitch", "duration", "tie", "instrument", "footnote", "level", "voice", "type", "dot"];
        var anchor = note.Elements().LastOrDefault(e => e.Name.Namespace == ns && before.Contains(e.Name.LocalName));
        if (anchor is null) note.AddFirst(accidental);
        else anchor.AddAfterSelf(accidental);
    }

    /// <summary>What the key signature does to a step: +1 sharpened, -1 flattened, 0 natural.</summary>
    internal static int KeyAlter(string step, int fifths)
    {
        const string sharpOrder = "FCGDAEB", flatOrder = "BEADGCF";
        int n = Math.Clamp(Math.Abs(fifths), 0, 7);
        if (fifths > 0) return sharpOrder.IndexOf(step[0]) is var i and >= 0 && i < n ? 1 : 0;
        if (fifths < 0) return flatOrder.IndexOf(step[0]) is var j and >= 0 && j < n ? -1 : 0;
        return 0;
    }

    /// <summary>A MIDI pitch spelled with sharps, or with flats in flat keys.</summary>
    public static TalkingScore.TsPitch Spell(int midi, int fifths)
    {
        int pitchClass = ((midi % 12) + 12) % 12;
        var (step, alter) = (fifths < 0 ? Flats : Sharps)[pitchClass];
        return new TalkingScore.TsPitch(step, alter, (midi - pitchClass) / 12 - 1);
    }
}