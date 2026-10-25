using Brasscribe.Play.Core.Engine;

namespace Brasscribe.Play.Core.Tests;

public class SseParserTests
{
    [Fact]
    public void Joins_data_lines_and_tracks_id_and_type()
    {
        var p = new ServerSentEventParser();
        Assert.Null(p.Feed(": comment"));
        Assert.Null(p.Feed("id: 7"));
        Assert.Null(p.Feed("event: stage"));
        Assert.Null(p.Feed("data: a"));
        Assert.Null(p.Feed("data:b"));
        var ev = p.Feed("");
        Assert.Equal(new ServerSentEvent("7", "stage", "a\nb"), ev);
        Assert.Equal("7", p.LastEventId);
    }

    [Fact]
    public void Blank_line_without_data_dispatches_nothing_and_default_type_is_message()
    {
        var p = new ServerSentEventParser();
        Assert.Null(p.Feed("event: x"));
        Assert.Null(p.Feed(""));
        p.Feed("data: z");
        Assert.Equal("message", p.Feed("")!.EventType);
    }
}
