using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Tests;

public class TextRangeModelTests
{
    private const string Text = "bar 1, beat 1: quarter rest\nbeat 2: B-flat 4, eighth note, uncertain\nbeat 3: G 5, half note\n";

    [Fact]
    public void Line_units_follow_the_event_lines()
    {
        var r = new TextRangeModel(Text, 0, 0);
        r.ExpandToEnclosingUnit(TextUnitKind.Line);
        Assert.Equal("bar 1, beat 1: quarter rest\n", r.GetText(-1));
        Assert.Equal(1, r.Move(TextUnitKind.Line, 1));
        Assert.Equal("beat 2: B-flat 4, eighth note, uncertain\n", r.GetText(-1));
        Assert.Equal(1, r.Move(TextUnitKind.Line, 5)); // only one more line
        Assert.Equal("beat 3: G 5, half note\n", r.GetText(-1));
        Assert.Equal(-2, r.Move(TextUnitKind.Line, -2));
        Assert.StartsWith("bar 1", r.GetText(-1));
    }

    [Fact]
    public void Words_characters_and_document()
    {
        var r = new TextRangeModel(Text, 0, 0);
        r.ExpandToEnclosingUnit(TextUnitKind.Word);
        Assert.Equal("bar ", r.GetText(-1));
        r.Move(TextUnitKind.Word, 1);
        Assert.Equal("1, ", r.GetText(-1));
        r.ExpandToEnclosingUnit(TextUnitKind.Character);
        Assert.Equal("1", r.GetText(-1));
        r.ExpandToEnclosingUnit(TextUnitKind.Document);
        Assert.Equal(Text, r.GetText(-1));
        Assert.Equal("bar", r.GetText(3));
    }

    [Fact]
    public void Endpoints_move_and_find()
    {
        var r = new TextRangeModel(Text, 0, 0);
        Assert.Equal(2, r.MoveEndpointByUnit(false, TextUnitKind.Line, 2));
        Assert.Equal(2, r.LineOf(r.End));
        Assert.True(r.Find("B-flat", false, false) > 0);
        Assert.Equal(-1, r.Find("half note", false, false));
        Assert.Equal((28, 69), TextRangeModel.LineSpan(Text, 1));
    }
}
