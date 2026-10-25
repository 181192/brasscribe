using System.Globalization;
using System.Text.RegularExpressions;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>
/// Which drawn note is which note of the tab's data: the index read from tab.musicxml (<see cref="TabIndex"/>) and
/// the marks made from it (<see cref="TabMarks"/>), on the recorded fixtures (apps/fixtures/bass-line and
/// bass-line-marks) and on small documents written here as the core writes them (core/targets/fretted/README.md).
/// </summary>
public class TabIndexTests
{
    private const int T = TabIndex.Ticks;

    /// <summary>A note piece as the core writes it.</summary>
    private static string Note(int index, string step, int octave, int duration, int? @string = null, int? fret = null, int? alter = null,
        bool chord = false, int? staff = null, string tie = "", string? confidence = null)
    {
        var ties = tie.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return $"""
            <note{(confidence is not null ? " color=\"#9A5200\"" : "")}>
              {(chord ? "<chord />" : "")}
              <pitch><step>{step}</step>{(alter is { } a ? $"<alter>{a}</alter>" : "")}<octave>{octave}</octave></pitch>
              <duration>{duration}</duration>
              {string.Concat(ties.Select(t => $"<tie type=\"{t}\" />"))}
              <voice>1</voice><type>quarter</type>
              {(staff is { } s ? $"<staff>{s}</staff>" : "")}
              {(confidence is not null ? "<notehead color=\"#9A5200\">normal</notehead>" : "")}
              <notations>
                {string.Concat(ties.Select(t => $"<tied type=\"{t}\" />"))}
                {(@string is not null ? $"<technical><string>{@string}</string><fret>{fret}</fret></technical>" : "")}
              </notations>
              <?fretted-note {index}?>
              {(confidence is not null ? $"<?fretted-confidence {confidence}?>" : "")}
            </note>
            """;
    }

    private static string Rest(int duration, int? staff = null) =>
        $"<note><rest /><duration>{duration}</duration><voice>1</voice>{(staff is { } s ? $"<staff>{s}</staff>" : "")}</note>";

    private static string Words(string text, int? staff = null, bool boxed = false) =>
        $"<direction placement=\"above\"><direction-type><words{(boxed ? " enclosure=\"rectangle\"" : "")}>{text}</words></direction-type>{(staff is { } s ? $"<staff>{s}</staff>" : "")}</direction>";

    private static string Backup(int duration) => $"<backup><duration>{duration}</duration></backup>";

    /// <summary>A part of <paramref name="measures"/> in 4/4 with 24 divisions: a tab staff alone, a notation staff alone, or the pair (notation above).</summary>
    private static string Document(string layout, string[] measures, string first = "1", string header = "Standard: E A D G")
    {
        string clefs = layout switch
        {
            "tab" => "<clef><sign>TAB</sign><line>5</line></clef>",
            "notation" => "<clef><sign>F</sign><line>4</line><clef-octave-change>-1</clef-octave-change></clef>",
            _ => "<staves>2</staves><clef number=\"1\"><sign>F</sign><line>4</line></clef><clef number=\"2\"><sign>TAB</sign><line>5</line></clef>",
        };
        string attributes = $"<attributes><divisions>24</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>{clefs}</attributes>";
        var body = measures.Select((m, i) =>
        {
            string number = i == 0 ? first : (int.Parse(first, CultureInfo.InvariantCulture) + i).ToString(CultureInfo.InvariantCulture);
            return $"<measure number=\"{number}\">{(i == 0 ? attributes + Words(header, layout == "pair" ? 1 : null) : "")}{m}</measure>";
        });
        return $"""
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
            <score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Bass</part-name></score-part></part-list>
            <part id="P1">{string.Join("\n", body)}</part></score-partwise>
            """;
    }

    private static string Document(string layout, params string[] measures) => Document(layout, measures, "1");

    /// <summary>A tab's data with <paramref name="notes"/> as (confidence, string or null for a note without a place, pitch).</summary>
    private static TabResult Data(params (double Confidence, int? String, int Pitch)[] notes)
    {
        var recorded = TabFixtures.Tab("bass-line");
        var model = recorded.Notes[0];
        return recorded with
        {
            Notes = [.. notes.Select(n => model with { Pitch = n.Pitch, Confidence = n.Confidence, String = n.String, Fret = n.String is null ? null : 0, OutOfRange = n.String is null })],
        };
    }

    private static (int Bar, int Onset, MarkKind Kind) Where(TabColumn c) => (c.Bar, c.Onset, c.Kind);

    [Fact]
    public void The_recorded_line_has_every_note_once_where_it_is_written()
    {
        var (xml, tab) = TabFixtures.Both("bass-line");
        var index = TabIndex.Parse(xml);
        Assert.Equal(15, index.Bars);
        Assert.Equal(1, index.Staves);
        Assert.Equal(0, index.TabStaff);
        Assert.Equal("Standard: E A D G", index.Header);
        Assert.Equal("Standard", index.TuningName);
        Assert.Equal(0, index.Capo);
        Assert.Equal(100, index.Tempo);
        // Every note of the data is on the page, once, with the string and fret the data gives it.
        Assert.Equal(Enumerable.Range(0, tab.Notes.Count), index.Pieces.Select(p => p.Note));
        for (int i = 0; i < tab.Notes.Count; i++)
        {
            var n = tab.Notes[i];
            var piece = Assert.Single(index.Of(i));
            Assert.Equal((n.Pitch, n.String, n.Fret), (piece.Pitch, piece.String, piece.Fret));
            Assert.True(piece.First);
            Assert.Null(piece.Confidence);
            // The line is in 2/4 with 24 ticks to the beat: the bar and the place in it follow from the start.
            Assert.Equal((n.Start / 48, n.Start % 48 * T / 24), (piece.Bar, piece.Onset));
        }
        Assert.Equal(3, index.Of(3).Single().String);
        Assert.Empty(index.NoPlace);
        // Nothing to check: no marks, from the data or from the page.
        foreach (var marks in new[] { TabMarks.Of(index, tab), TabMarks.Of(index, null) })
        {
            Assert.Empty(marks.Columns);
            Assert.Equal((0, 0, 0), (marks.Doubtful, marks.NoPlace, marks.Unplaced));
        }
    }

    [Fact]
    public void The_line_with_notes_to_check_has_its_marks_on_the_right_columns()
    {
        var (xml, tab) = TabFixtures.Both("bass-line-marks");
        var index = TabIndex.Parse(xml);
        // The doubtful note carries its confidence; the note below the lowest string is a rest with boxed words, and has no index.
        Assert.Equal(0.31, index.Of(5).Single().Confidence!.Value, 1e-9);
        Assert.Empty(index.Of(12));
        Assert.Equal([new TabNoPlace(0, 6, "7", 960, ["D1"], Beat: 2)], index.NoPlace);
        // The last note crosses the beat and the bar line: three tied pieces, all with its index, the first with the confidence.
        var tied = index.Of(28);
        Assert.Equal([(14, 480), (14, 960), (15, 0)], tied.Select(p => (p.Bar, p.Onset)));
        Assert.Equal([true, false, false], tied.Select(p => p.First));
        Assert.Equal([0.22, null, null], tied.Select(p => p.Confidence));

        var marks = TabMarks.Of(index, tab);
        Assert.Equal((2, 1, 0), (marks.Doubtful, marks.NoPlace, marks.Unplaced));
        Assert.Equal([(2, 960, MarkKind.Doubt), (6, 960, MarkKind.NoPlace), (14, 480, MarkKind.Doubt)], marks.Columns.Select(Where));
        Assert.Equal(["3", "7", "15"], marks.Columns.Select(c => c.BarNumber));
        Assert.Equal([2, 2, 1], marks.Columns.Select(c => c.Beat));
        Assert.Equal(new MarkedNote(MarkKind.Doubt, 5, String: 3, Fret: 2, Step: "B"), marks.Columns[0].Notes.Single());
        Assert.Equal(new MarkedNote(MarkKind.NoPlace, 12, Name: "D1", Why: NoPlaceWhy.TooLow), marks.Columns[1].Notes.Single());
        Assert.Equal(new MarkedNote(MarkKind.Doubt, 28, String: 4, Fret: 0, Step: "E"), marks.Columns[2].Notes.Single());

        // Without the data the page gives the same columns; it names the note without a place and not why.
        var own = TabMarks.Of(index, null);
        Assert.Equal(marks.Columns.Select(Where), own.Columns.Select(Where));
        Assert.Equal((2, 1, 0), (own.Doubtful, own.NoPlace, own.Unplaced));
        Assert.Equal(new MarkedNote(MarkKind.NoPlace, null, Name: "D1"), own.Columns[1].Notes.Single());

        // The threshold is the data's: a higher one marks more notes, none marks none but the note without a place.
        Assert.Equal(tab.Notes.Count - 1, TabMarks.Of(index, tab, threshold: 1.0).Columns.Count(c => c.Kind == MarkKind.Doubt));
        Assert.Equal([MarkKind.NoPlace], TabMarks.Of(index, tab, threshold: 0.0).Columns.Select(c => c.Kind));
    }

    [Fact]
    public void Single_notes_and_a_chord_are_found_by_measure_start_and_string()
    {
        string xml = Document("tab",
            Note(0, "E", 1, 24, 4, 0) + Words("?") + Note(1, "A", 1, 24, 3, 0, confidence: "0.20") + Note(2, "E", 2, 24, 2, 2, confidence: "0.35", chord: true) +
                Note(3, "D", 2, 24, 2, 0, alter: -1) + Rest(24),
            Note(4, "G", 1, 96, 4, 3));
        var index = TabIndex.Parse(xml);
        Assert.Equal(2, index.Bars);
        Assert.Equal([0, 960, 960, 1920, 0], index.Pieces.Select(p => p.Onset));
        Assert.Equal([0, 0, 0, 0, 1], index.Pieces.Select(p => p.Bar));
        // D-flat is spelled as the page spells it, and sounds a semitone under D.
        Assert.Equal(("D", -1, 37), index.Of(3).Single() is var d ? (d.Step, d.Alter, d.Pitch) : default);
        // Two doubtful notes that start together are one column with one mark, both notes under it, low to high as written.
        var marks = TabMarks.Of(index, Data((0.9, 4, 28), (0.2, 3, 33), (0.35, 2, 40), (0.9, 2, 37), (0.9, 4, 31)));
        var column = Assert.Single(marks.Columns);
        Assert.Equal((0, 960, 2), (column.Bar, column.Onset, column.Beat));
        Assert.Equal([(1, (int?)3), (2, 2)], column.Notes.Select(n => (n.Note!.Value, n.String)));
        Assert.Equal((2, 0, 0), (marks.Doubtful, marks.NoPlace, marks.Unplaced));
    }

    [Fact]
    public void A_note_tied_across_the_bar_line_is_marked_where_it_starts()
    {
        string xml = Document("tab",
            Rest(72) + Words("?") + Note(0, "A", 1, 24, 3, 0, tie: "start", confidence: "0.10"),
            Note(0, "A", 1, 48, 3, 0, tie: "stop start") + Rest(48),
            Note(0, "A", 1, 24, 3, 0, tie: "stop") + Note(1, "E", 1, 72, 4, 0));
        var index = TabIndex.Parse(xml);
        Assert.Equal([(0, 2880), (1, 0), (2, 0)], index.Of(0).Select(p => (p.Bar, p.Onset)));
        Assert.Equal([true, false, false], index.Of(0).Select(p => p.First));
        foreach (var tab in new[] { Data((0.1, 3, 33), (0.9, 4, 28)), null })
        {
            var column = Assert.Single(TabMarks.Of(index, tab).Columns);
            Assert.Equal((0, 2880, 4), (column.Bar, column.Onset, column.Beat));
        }
    }

    [Fact]
    public void A_note_moved_to_the_grid_and_split_into_pieces_keeps_its_index()
    {
        // The data's note 1 starts between two triplet sixteenths; the page writes it on the grid, as two tied pieces
        // across the beat. Its ticks no longer say where it is drawn; its index does.
        string xml = Document("tab",
            Note(0, "E", 1, 20, 4, 0) + Words("?") + Note(1, "G", 1, 4, 4, 3, tie: "start", confidence: "0.30") +
                Note(1, "G", 1, 20, 4, 3, tie: "stop") + Rest(52));
        var index = TabIndex.Parse(xml);
        Assert.Equal([800, 960], index.Of(1).Select(p => p.Onset));
        var data = Data((0.9, 4, 28), (0.3, 4, 31));
        var moved = data with { Notes = [data.Notes[0] with { Start = 0, Dur = 19 }, data.Notes[1] with { Start = 19, Dur = 25 }] };
        var column = Assert.Single(TabMarks.Of(index, moved).Columns);
        Assert.Equal((0, 800, 1), (column.Bar, column.Onset, column.Beat));
        Assert.Equal(1, column.Notes.Single().Note);
    }

    [Fact]
    public void In_a_pair_of_staves_the_marks_are_on_the_tab_staff()
    {
        // Notation above (staff 1), tab below (staff 2). The low D has no place: the notation staff writes it, with its
        // index; the tab staff has a rest and the boxed words.
        string xml = Document("pair",
            Note(0, "E", 1, 24, staff: 1) + Note(1, "D", 1, 24, staff: 1) + Note(2, "A", 1, 48, staff: 1, confidence: "0.25") + Backup(96) +
                Note(0, "E", 1, 24, 4, 0, staff: 2) + Words("! D1", 2, boxed: true) + Rest(24, 2) + Words("?", 2) + Note(2, "A", 1, 48, 3, 0, staff: 2, confidence: "0.25"));
        var index = TabIndex.Parse(xml);
        Assert.Equal(2, index.Staves);
        Assert.Equal(1, index.TabStaff);
        Assert.Equal(1, index.MarkStaff);
        Assert.Equal("Standard: E A D G", index.Header);
        Assert.Equal([0, 1], index.Of(0).Select(p => p.Staff));
        Assert.Equal([0], index.Of(1).Select(p => p.Staff));
        Assert.Equal([null, 3], index.Of(2).Select(p => p.String));
        Assert.Equal([new TabNoPlace(1, 0, "1", 960, ["D1"], Beat: 2)], index.NoPlace);

        var marks = TabMarks.Of(index, Data((0.9, 4, 28), (0.9, null, 26), (0.25, 3, 33)));
        Assert.Equal([(1, 960, MarkKind.NoPlace), (1, 1920, MarkKind.Doubt)], marks.Columns.Select(c => (c.Staff, c.Onset, c.Kind)));
        // The note without a place is found by its index on the notation staff, and spelled as it is written there.
        Assert.Equal(new MarkedNote(MarkKind.NoPlace, 1, Step: "D", Name: "D1", Why: NoPlaceWhy.TooLow), marks.Columns[0].Notes.Single());
        // The doubtful note is the tab staff's piece: it has the string and the fret.
        Assert.Equal(new MarkedNote(MarkKind.Doubt, 2, String: 3, Fret: 0, Step: "A"), marks.Columns[1].Notes.Single());
        Assert.Equal((1, 1, 0), (marks.Doubtful, marks.NoPlace, marks.Unplaced));
        // The page alone gives the same two columns.
        Assert.Equal(marks.Columns.Select(c => (c.Staff, c.Onset, c.Kind)), TabMarks.Of(index, null).Columns.Select(c => (c.Staff, c.Onset, c.Kind)));
    }

    [Fact]
    public void In_the_notation_layout_the_marks_are_on_the_notes()
    {
        string xml = Document("notation", Words("! D1", boxed: true) + Note(0, "D", 1, 48) + Words("?") + Note(1, "A", 1, 48, confidence: "0.25"));
        var index = TabIndex.Parse(xml);
        Assert.Null(index.TabStaff);
        Assert.Equal(0, index.MarkStaff);
        var marks = TabMarks.Of(index, Data((0.9, null, 26), (0.25, 3, 33)));
        Assert.Equal([(0, 0, MarkKind.NoPlace), (0, 1920, MarkKind.Doubt)], marks.Columns.Select(c => (c.Staff, c.Onset, c.Kind)));
        Assert.Null(marks.Columns[1].Notes.Single().String);
        Assert.Equal(0, marks.Unplaced);
    }

    [Fact]
    public void A_pickup_is_measure_nought_and_bars_are_counted_as_written()
    {
        string xml = Document("tab", [Words("?") + Note(0, "E", 1, 24, 4, 0, confidence: "0.10"), Note(1, "A", 1, 96, 3, 0)], first: "0", header: "Drop D: D A D G, Capo 3");
        var index = TabIndex.Parse(xml);
        Assert.Equal("Drop D", index.TuningName);
        Assert.Equal(3, index.Capo);
        var column = Assert.Single(TabMarks.Of(index, null).Columns);
        // alphaTab's first bar is the pickup. Its one quarter note is the fourth beat of the bar it leads into.
        Assert.Equal((0, "0"), (column.Bar, column.BarNumber));
        Assert.True(column.Pickup);
        Assert.Equal(4, column.Beat);
        Assert.False(index.Of(1).Single().Pickup);
        Assert.Equal((1, "1"), index.Of(1).Single() is var p ? (p.Bar, p.BarNumber) : default);
    }

    [Fact]
    public void A_beat_is_counted_in_the_time_signature_in_force()
    {
        // Two bars of 4/4, then 6/8: the third bar's notes are counted in eighths.
        const string six = "<attributes><time><beats>6</beats><beat-type>8</beat-type></time></attributes>";
        string xml = Document("tab",
            Rest(72) + Words("?") + Note(0, "E", 1, 24, 4, 0, confidence: "0.10"),
            Rest(96),
            six + Rest(36) + Words("?") + Note(1, "A", 1, 36, 3, 0, confidence: "0.10"));
        var columns = TabMarks.Of(TabIndex.Parse(xml), null).Columns;
        Assert.Equal([(0, 4), (2, 4)], columns.Select(c => (c.Bar, c.Beat)));
        Assert.Equal([false, false], columns.Select(c => c.Pickup));
    }

    [Fact]
    public void A_doubtful_note_with_no_place_is_counted_once_under_the_mark()
    {
        string xml = Document("tab", Words("! D1", boxed: true) + Rest(48) + Words("?") + Note(1, "A", 1, 48, 3, 0, confidence: "0.25"));
        var marks = TabMarks.Of(TabIndex.Parse(xml), Data((0.1, null, 26), (0.25, 3, 33)));
        Assert.Equal([MarkKind.NoPlace, MarkKind.Doubt], marks.Columns.Select(c => c.Kind));
        Assert.Equal((1, 1, 0), (marks.Doubtful, marks.NoPlace, marks.Unplaced));
    }

    [Fact]
    public void The_renderer_gets_the_page_without_its_header_words()
    {
        string xml = TabFixtures.MusicXml("bass-line-marks");
        var index = TabIndex.Parse(xml);
        string page = TabIndex.ForRenderer(xml, index.Header);
        Assert.DoesNotContain("Standard: E A D G", page);
        Assert.Contains("<metronome>", page);
        Assert.Equal(Regex.Count(xml, "<direction ") - 4, Regex.Count(page, "<direction "));
        Assert.Equal(index.Pieces, TabIndex.Parse(page).Pieces);
        // Words that are not the header stay.
        string ring = Document("tab", Words("let ring") + Note(0, "E", 1, 96, 4, 0));
        Assert.Contains("let ring", TabIndex.ForRenderer(ring, TabIndex.Parse(ring).Header));
    }

    [Fact]
    public void A_note_the_page_does_not_have_is_counted_not_drawn()
    {
        // Two notes of one pitch on one place are written once, with the first one's index: the second has no column.
        string xml = Document("tab", Words("?") + Note(0, "E", 1, 96, 4, 0, confidence: "0.10"));
        var marks = TabMarks.Of(TabIndex.Parse(xml), Data((0.1, 4, 28), (0.2, 4, 28), (0.9, null, 20)));
        Assert.Single(marks.Columns);
        // The lines above the tab count what is drawn: one "?", no "!".
        Assert.Equal((1, 0), (marks.Doubtful, marks.NoPlace));
        // The doubling, and the note without a place that the page has no boxed words for.
        Assert.Equal(2, marks.Unplaced);
        // Boxed words the data has no note for are counted too.
        string boxed = Document("tab", Words("! D1", boxed: true) + Rest(96));
        Assert.Equal(1, TabMarks.Of(TabIndex.Parse(boxed), Data((0.9, 4, 28))).Unplaced);
    }

    [Fact]
    public void The_page_goes_to_the_renderer_without_its_marks()
    {
        string xml = TabFixtures.MusicXml("bass-line-marks");
        string bare = TabIndex.WithoutMarks(xml);
        Assert.DoesNotContain("<words>?</words>", bare);
        Assert.DoesNotContain("! D1", bare);
        Assert.DoesNotContain("#9A5200", bare);
        // Only those: the header, the tempo and every note are still there, and it is still a document.
        Assert.Contains("<words>Standard: E A D G</words>", bare);
        Assert.Contains("<metronome>", bare);
        Assert.Equal(Regex.Count(xml, @"<note\b"), Regex.Count(bare, @"<note\b"));
        Assert.Equal(Regex.Count(xml, "<direction ") - 3, Regex.Count(bare, "<direction "));
        var again = TabIndex.Parse(bare);
        Assert.Equal(TabIndex.Parse(xml).Pieces, again.Pieces);
        Assert.Empty(again.NoPlace);
    }

    [Fact]
    public void Something_that_is_not_a_tab_gives_an_empty_index()
    {
        foreach (var text in new[] { "", "not xml", "<score-partwise version=\"4.0\"></score-partwise>" })
        {
            var index = TabIndex.Parse(text);
            Assert.Equal(0, index.Bars);
            Assert.Empty(TabMarks.Of(index, null).Columns);
        }
    }

    [Fact]
    public void The_page_reads_the_same_in_any_language_of_the_system()
    {
        string xml = TabFixtures.MusicXml("bass-line-marks");
        var invariant = TabIndex.Parse(xml);
        var was = CultureInfo.CurrentCulture;
        try
        {
            // Norwegian writes 0,31 for 0.31: the page's numbers are read as the page writes them.
            CultureInfo.CurrentCulture = new CultureInfo("nb-NO");
            var nb = TabIndex.Parse(xml);
            Assert.Equal(invariant.Pieces, nb.Pieces);
            Assert.Equal(0.31, nb.Of(5).Single().Confidence!.Value, 1e-9);
            Assert.Equal(100, nb.Tempo);
        }
        finally
        {
            CultureInfo.CurrentCulture = was;
        }
    }

    [Fact]
    public void The_engine_marks_the_page_at_the_threshold_the_marks_are_read_with() =>
        Assert.Equal(TabNote.Doubt, TabMarks.UncertainThreshold);
}
