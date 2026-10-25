using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>Cleared number boxes and scores with nothing in them: the app carries on with a sensible value.</summary>
public class EmptyInputTests
{
    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    [Fact]
    public void A_cleared_zoom_box_goes_back_to_100_percent()
    {
        var strings = ConnectionMonitorTests.Strings();
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(new ScriptedPlayer(), new Said(), strings, new Inline()), new Said(), strings);
        score.ZoomPercent = 150;
        score.ZoomPercent = double.NaN;
        Assert.Equal(100, score.ZoomPercent);
    }

    [Fact]
    public void Cleared_bar_boxes_repeat_from_the_first_bar_or_just_the_start_bar()
    {
        var vm = new PlayerViewModel(new ScriptedPlayer(), new Said(), ConnectionMonitorTests.Strings(), new Inline());
        vm.Load([]);

        vm.LoopStart = double.NaN;
        vm.LoopEnd = 3;
        vm.SetLoopCommand.Execute(null);
        Assert.Equal((1, 3), ((int)vm.LoopStart, (int)vm.LoopEnd));

        vm.LoopStart = 5;
        vm.LoopEnd = double.NaN;
        vm.SetLoopCommand.Execute(null);
        Assert.Equal((5, 5), ((int)vm.LoopStart, (int)vm.LoopEnd));
        Assert.DoesNotContain(" 0 ", vm.LoopText);
    }

    private const string NoParts = """
        <?xml version="1.0" encoding="UTF-8"?>
        <score-partwise version="4.0"><part-list/></score-partwise>
        """;

    [Fact]
    public async Task A_part_export_of_a_score_without_parts_is_refused_not_thrown()
    {
        var sources = new ExportSources(NoParts, null, null, null, null, []);
        using var output = new MemoryStream();
        var e = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            new ExportService().ExportAsync(ExportFormat.MusicXmlPart, sources, output, 0, new()));
        Assert.Equal(ExportService.ReasonNoScore, e.Message);
    }

    [Fact]
    public void A_talking_score_export_skips_parts_that_are_not_there()
    {
        var doc = MusicXmlTalkingScoreBuilder.Build(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), nameNb: ScoreNavigatorTests.FixtureNb);
        var text = TalkingScoreExport.ToText(doc, new TalkingScoreSettings(), [7]);
        Assert.DoesNotContain("Bar 1", text);
    }
}
