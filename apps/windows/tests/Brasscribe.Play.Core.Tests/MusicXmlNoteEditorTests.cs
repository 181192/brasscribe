using System.Xml.Linq;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;

namespace Brasscribe.Play.Core.Tests;

public sealed class MusicXmlNoteEditorTests
{
    private const string Xml = """
        <score-partwise><work><work-title>Old</work-title></work><part-list><score-part id="P1"><part-name>Solo</part-name></score-part></part-list><part id="P1"><measure number="1"><note><grace/><pitch><step>C</step><octave>4</octave></pitch></note><note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration></note><note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration></note></measure></part></score-partwise>
        """;

    [Fact]
    public void ReplacesScoreTitle()
    {
        var edited = MusicXmlNoteEditor.ReplaceTitle(Xml, "New & improved");
        var root = XDocument.Parse(edited).Root!;
        Assert.Equal("New & improved", root.Element("work")?.Element("work-title")?.Value);
    }

    [Fact]
    public void ReplacesTheIndexedNoteAndSkipsGraceNotes()
    {
        var edited = MusicXmlNoteEditor.ReplacePitch(Xml, "P1", 1, midi: 77, fifths: -2);
        var notes = XDocument.Parse(edited).Root!.Element("part")!.Element("measure")!.Elements("note").ToArray();
        Assert.Equal("D", notes[1].Element("pitch")?.Element("step")?.Value);
        Assert.Equal("F", notes[2].Element("pitch")?.Element("step")?.Value);
        Assert.Equal("5", notes[2].Element("pitch")?.Element("octave")?.Value);
    }

    [Fact]
    public void LibraryPersistsRenamedScoreAndPitchChanges()
    {
        string root = Path.Combine(Path.GetTempPath(), "brasscribe-library-" + Guid.NewGuid().ToString("N"));
        try
        {
            var library = new ScoreLibrary(root);
            var composition = new Composition
            {
                Title = "Old",
                Voices = [new Voice { Id = "solo", Role = VoiceRole.Melody, Notes = [new Note { Pitch = 60, Start = 0, Dur = 24 }] }],
            };
            var entry = library.AddMade("Old", Xml, composition, parts: 1, bars: 1, notesToCheck: 0, jobId: null);
            library.Rename(entry.Id, "Rehearsal");
            var corrected = MusicXmlNoteEditor.ReplacePitch(Xml, "P1", 1, midi: 77, fifths: -2);
            composition.Voices[0].Notes[0].Pitch = 61;
            library.SaveMusicXml(entry.Id, corrected, CompositionJson.Serialize(composition));

            var reopened = Assert.Single(new ScoreLibrary(root).Entries);
            Assert.Equal("Rehearsal", reopened.Title);
            Assert.Equal("F", XDocument.Load(reopened.MusicXmlPath).Descendants("pitch").Last().Element("step")?.Value);
            var sidecar = CompositionJson.Parse(File.ReadAllText(reopened.CompositionPath!));
            Assert.Equal("Rehearsal", sidecar.Title);
            Assert.Equal(61, sidecar.Voices[0].Notes[0].Pitch);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}