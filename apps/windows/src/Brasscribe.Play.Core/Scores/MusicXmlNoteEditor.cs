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
        var pitch = notes[noteIndex].Element(ns + "pitch") ?? throw new InvalidOperationException("Selected MusicXML note is not pitched");
        int pitchClass = ((midi % 12) + 12) % 12;
        var (step, alter) = (fifths < 0 ? Flats : Sharps)[pitchClass];
        var stepElement = pitch.Element(ns + "step") ?? new XElement(ns + "step");
        var octaveElement = pitch.Element(ns + "octave") ?? new XElement(ns + "octave");
        pitch.Elements(ns + "alter").Remove();
        stepElement.Value = step;
        octaveElement.Value = ((midi - pitchClass) / 12 - 1).ToString(System.Globalization.CultureInfo.InvariantCulture);
        pitch.Elements().Where(e => e.Name != ns + "step" && e.Name != ns + "octave").Remove();
        stepElement.Remove(); octaveElement.Remove();
        pitch.Add(stepElement);
        if (alter != 0) pitch.Add(new XElement(ns + "alter", alter));
        pitch.Add(octaveElement);
        return document.ToString(SaveOptions.DisableFormatting);
    }
}