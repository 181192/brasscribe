using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.TalkingScore;

namespace Brasscribe.Play.Core.Tests;

[Collection(AlphaTabCollection.Name)]
public class ScoreGeometryTests
{
    [Fact]
    public void Focus_cursor_bands_and_uncertain_heads_come_from_the_render()
    {
        var xml = File.ReadAllText(TestPaths.Fixture("two-parts.musicxml"));
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(System.Text.Encoding.UTF8.GetBytes(xml));
        var ts = MusicXmlTalkingScoreBuilder.Build(xml);
        var render = new ScoreRenderService("svg").Render(player.Score!, [0], 900);
        var bounds = render.Bounds!;

        var nav = new ScoreNavigator(ts);
        nav.NextNote(); // B-flat on beat 2 of bar 1
        var focus = ScoreGeometry.FocusBox(player.Score!, bounds, nav.PartIndex, nav.BarIndex, nav.TickInBar);
        var bar = ScoreGeometry.BarBox(bounds, 0, 0);
        Assert.NotNull(focus);
        Assert.NotNull(bar);
        Assert.True(focus!.Value.X > bar!.Value.X, "beat 2 sits right of the bar start");
        Assert.True(focus.Value.X < bar.Value.X + bar.Value.W);

        var loop = ScoreGeometry.RangeBoxes(bounds, 0, 1);
        Assert.NotEmpty(loop);

        var heads = ScoreGeometry.UncertainHeads(player.Score!, bounds, ts, [0]);
        Assert.Single(heads);
        Assert.Equal(Scores.Certainty.Uncertain, heads[0].Level);

        var cursor = ScoreGeometry.Cursor(player.TickLookup!, bounds, [0], 960 * 1.5);
        Assert.NotNull(cursor);
        Assert.Equal(3, cursor!.Value.Beat.W);
    }
}
