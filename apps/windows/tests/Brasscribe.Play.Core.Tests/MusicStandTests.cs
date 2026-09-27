using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.Stand;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>The music stand's keys, pages, control layer, sizing and view model (design/music-stand.md).</summary>
public class MusicStandKeyTests
{
    [Fact]
    public void F_and_F11_open_the_stand_and_F_follows_the_single_key_setting()
    {
        Assert.Equal(ScoreCommand.ToggleStand, ScoreKeyMap.Map(ScoreKey.F, KeyModifiers.None));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.F, KeyModifiers.None, singleKeyShortcuts: false));
        Assert.Equal(ScoreCommand.ToggleStand, ScoreKeyMap.Map(ScoreKey.F11, KeyModifiers.None, singleKeyShortcuts: false));
        Assert.Equal(ScoreCommand.ToggleStand, ScoreKeyMap.Map(ScoreKey.F11, KeyModifiers.None, stand: true));
        Assert.Equal(ScoreCommand.LeaveStand, ScoreKeyMap.Map(ScoreKey.F, KeyModifiers.None, stand: true));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.F, KeyModifiers.None, singleKeyShortcuts: false, stand: true));
    }

    [Fact]
    public void Esc_leaves_the_stand_before_the_score()
    {
        Assert.Equal(ScoreCommand.LeaveScore, ScoreKeyMap.Map(ScoreKey.Escape, KeyModifiers.None));
        Assert.Equal(ScoreCommand.LeaveStand, ScoreKeyMap.Map(ScoreKey.Escape, KeyModifiers.None, stand: true));
    }

    [Theory]
    [InlineData(ScoreKey.Right, ScoreCommand.NextPage)]
    [InlineData(ScoreKey.Down, ScoreCommand.NextPage)]
    [InlineData(ScoreKey.PageDown, ScoreCommand.NextPage)]
    [InlineData(ScoreKey.Left, ScoreCommand.PreviousPage)]
    [InlineData(ScoreKey.Up, ScoreCommand.PreviousPage)]
    [InlineData(ScoreKey.PageUp, ScoreCommand.PreviousPage)]
    [InlineData(ScoreKey.Home, ScoreCommand.FirstPage)]
    [InlineData(ScoreKey.End, ScoreCommand.LastPage)]
    [InlineData(ScoreKey.Space, ScoreCommand.PlayPause)]
    public void Page_turner_keys_turn_pages_in_the_stand(ScoreKey key, ScoreCommand expected)
    {
        Assert.Equal(expected, ScoreKeyMap.Map(key, KeyModifiers.None, stand: true));
        // Arrows keep turning pages without single-key shortcuts: pedals need no setting.
        Assert.Equal(expected, ScoreKeyMap.Map(key, KeyModifiers.None, singleKeyShortcuts: false, stand: true));
    }

    [Fact]
    public void Bars_move_with_ctrl_and_nothing_moves_a_note_cursor_in_the_stand()
    {
        Assert.Equal(ScoreCommand.NextBar, ScoreKeyMap.Map(ScoreKey.Down, KeyModifiers.Ctrl, stand: true));
        Assert.Equal(ScoreCommand.PreviousBar, ScoreKeyMap.Map(ScoreKey.Up, KeyModifiers.Ctrl, stand: true));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.Right, KeyModifiers.Ctrl, stand: true));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.Down, KeyModifiers.Ctrl | KeyModifiers.Shift, stand: true));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.U, KeyModifiers.None, stand: true));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.C, KeyModifiers.None, stand: true));
        Assert.Null(ScoreKeyMap.Map(ScoreKey.G, KeyModifiers.Ctrl, stand: true));
        Assert.Equal(ScoreCommand.ToggleLoop, ScoreKeyMap.Map(ScoreKey.L, KeyModifiers.None, stand: true));
        Assert.Equal(ScoreCommand.Faster, ScoreKeyMap.Map(ScoreKey.Plus, KeyModifiers.None, stand: true));
    }

    [Fact]
    public void Outside_the_stand_every_existing_key_is_unchanged()
    {
        var expected = new Dictionary<(ScoreKey, KeyModifiers), ScoreCommand?>
        {
            [(ScoreKey.Right, KeyModifiers.None)] = ScoreCommand.NextNote,
            [(ScoreKey.Left, KeyModifiers.None)] = ScoreCommand.PreviousNote,
            [(ScoreKey.Right, KeyModifiers.Ctrl)] = ScoreCommand.NextBeat,
            [(ScoreKey.Down, KeyModifiers.Ctrl)] = ScoreCommand.NextBar,
            [(ScoreKey.Down, KeyModifiers.Ctrl | KeyModifiers.Shift)] = ScoreCommand.NextPart,
            [(ScoreKey.Home, KeyModifiers.None)] = ScoreCommand.FirstBar,
            [(ScoreKey.End, KeyModifiers.None)] = ScoreCommand.LastBar,
            [(ScoreKey.Space, KeyModifiers.None)] = ScoreCommand.PlayPause,
            [(ScoreKey.U, KeyModifiers.Shift)] = ScoreCommand.PreviousUncertain,
            [(ScoreKey.G, KeyModifiers.Ctrl)] = ScoreCommand.GoToBar,
            [(ScoreKey.O, KeyModifiers.None)] = ScoreCommand.SwitchSource,
            [(ScoreKey.Up, KeyModifiers.None)] = null,
            [(ScoreKey.Down, KeyModifiers.None)] = null,
            [(ScoreKey.PageUp, KeyModifiers.None)] = null,
            [(ScoreKey.PageDown, KeyModifiers.None)] = null,
            [(ScoreKey.F, KeyModifiers.Alt)] = null,
        };
        foreach (var ((key, mods), command) in expected) Assert.Equal(command, ScoreKeyMap.Map(key, mods));
    }
}

public class StandPagesTests
{
    /// <summary>n systems of 100 epx, 4 bars each, stacked from y = 0.</summary>
    private static List<StandSystem> Systems(int n) =>
        Enumerable.Range(0, n).Select(i => new StandSystem(i * 100, i * 100 + 100, i * 4, i * 4 + 3)).ToList();

    [Fact]
    public void A_single_page_keeps_its_last_system_on_the_next_page()
    {
        var pages = StandPages.Build(Systems(10), pageHeight: 350, spread: false);
        Assert.Equal([(0, 2), (2, 4), (4, 6), (6, 8), (8, 9)], pages.Pages.Select(p => (p.FirstSystem, p.LastSystem)));
        Assert.Equal(200, pages.Pages[1].Top);
        Assert.Equal(4, pages.LastLeftPage);
    }

    [Fact]
    public void A_spread_follows_on_without_overlap_and_ends_on_the_last_two_pages()
    {
        var pages = StandPages.Build(Systems(10), pageHeight: 350, spread: true);
        Assert.Equal([(0, 2), (3, 5), (6, 8), (9, 9)], pages.Pages.Select(p => (p.FirstSystem, p.LastSystem)));
        Assert.Equal(2, pages.LastLeftPage);
        Assert.Equal(2, pages.PageOfBar(39)); // the last page is on the right of the last view
        Assert.True(pages.IsInView(2, 39));
        Assert.Equal((24, 39), pages.BarsInView(2));
    }

    [Fact]
    public void The_page_is_the_one_whose_top_system_holds_the_bar_which_is_the_turn_rule()
    {
        var pages = StandPages.Build(Systems(10), 350, spread: false);
        Assert.Equal(0, pages.PageOfBar(0));
        Assert.Equal(0, pages.PageOfBar(7));
        // Bar 9 is on the last system of page 1 and the first of page 2: reaching it turns.
        Assert.Equal(1, pages.PageOfBar(9));
        Assert.Equal(1, pages.PageOfBar(12));
        Assert.Equal(4, pages.PageOfBar(99));

        var spread = StandPages.Build(Systems(10), 350, spread: true);
        Assert.Equal(0, spread.PageOfBar(11));
        Assert.Equal(1, spread.PageOfBar(12)); // the start of the right-hand page moves it to the left
    }

    [Fact]
    public void A_system_taller_than_the_page_is_a_page_of_its_own()
    {
        var tall = new List<StandSystem> { new(0, 500, 0, 3), new(500, 1000, 4, 7) };
        var pages = StandPages.Build(tall, 300, spread: false);
        Assert.Equal(2, pages.Count);
        Assert.Equal(1, pages.PageOfBar(5));
    }

    [Fact]
    public void The_window_moves_so_the_current_system_is_never_under_the_layer()
    {
        var current = new StandSystem(200, 300, 8, 11);
        // Clear of a 100 epx layer in a 450 epx viewport: the page stays where it is.
        Assert.Equal(0, StandPages.WindowTop(0, current, 450, 100));
        // A 200 epx layer would cover it: the window moves down just enough, not a new layout.
        double top = StandPages.WindowTop(0, current, 450, 200);
        Assert.Equal(62, top);
        Assert.True(current.Bottom <= top + 450 - 200);
        // Never so far that the system leaves the top.
        Assert.Equal(200, StandPages.WindowTop(0, current, 150, 100));
        Assert.Equal(0, StandPages.WindowTop(0, null, 450, 200));
    }

    [Fact]
    public void An_empty_layout_has_one_page_zero()
    {
        var pages = StandPages.Build([], 400, false);
        Assert.Equal(0, pages.Count);
        Assert.Equal(0, pages.PageOfBar(3));
        Assert.False(pages.IsInView(0, 3));
    }
}

public class StandLayerTests
{
    private static readonly StandContext Playing = new(Playing: true);
    private static readonly StandContext Paused = new(Playing: false);

    [Fact]
    public void Shows_on_entry_while_paused_and_not_while_playing()
    {
        var layer = new StandLayer();
        layer.Enter(Paused);
        Assert.True(layer.IsShown);
        layer.Enter(Playing);
        Assert.False(layer.IsShown);
        layer.Enter(Playing with { ScreenReader = true });
        Assert.True(layer.IsShown);
    }

    [Fact]
    public void Hides_by_itself_only_while_playing_and_never_with_assistive_tech_focus_or_the_setting()
    {
        var layer = new StandLayer();
        layer.Enter(Paused);
        Assert.False(layer.AutoHide(Paused));
        Assert.False(layer.AutoHide(Playing with { ScreenReader = true }));
        Assert.False(layer.AutoHide(Playing with { FocusInLayer = true }));
        Assert.False(layer.AutoHide(Playing with { KeepVisible = true }));
        Assert.False(layer.AutoHide(Playing with { TextInputOrTouchKeyboard = true }));
        Assert.True(layer.IsShown);
        Assert.True(layer.AutoHide(Playing));
        Assert.False(layer.IsShown);
        Assert.False(layer.AutoHide(Playing)); // already hidden
    }

    [Fact]
    public void A_tap_toggles_and_a_key_shows()
    {
        var layer = new StandLayer(hintSeen: true);
        layer.Enter(Paused);
        layer.Tap();
        Assert.False(layer.IsShown);
        layer.Tap();
        Assert.True(layer.IsShown);
        layer.Tap();
        layer.Key();
        Assert.True(layer.IsShown);
    }

    [Fact]
    public void The_hint_comes_the_first_time_the_layer_hides_and_goes_for_good_on_a_tap()
    {
        var layer = new StandLayer();
        int changes = 0;
        layer.Changed += (_, _) => changes++;
        layer.Enter(Paused);
        layer.AutoHide(Playing);
        Assert.True(layer.HintShown);
        layer.Tap();
        Assert.False(layer.HintShown);
        Assert.True(layer.HintSeen);
        Assert.True(layer.IsShown);
        layer.AutoHide(Playing);
        Assert.False(layer.HintShown);
        Assert.True(changes >= 4);

        var seen = new StandLayer(hintSeen: true);
        seen.Enter(Paused);
        seen.Tap();
        Assert.False(seen.HintShown);
    }
}

public class StandSizingTests
{
    [Theory]
    [InlineData(1.0, 1.0, 4)]
    [InlineData(1.25, 1.0, 4)]
    [InlineData(1.5, 1.0, 3)]
    [InlineData(1.0, 1.6, 3)]
    [InlineData(2.0, 1.0, 2)]
    [InlineData(1.5, 1.5, 2)]
    [InlineData(0.8, 0.5, 4)]
    public void Bars_per_system_drop_first_as_text_or_zoom_grows(double text, double zoom, int bars) =>
        Assert.Equal(bars, StandSizing.BarsPerRow(text, zoom));

    [Fact]
    public void Pages_keep_at_least_two_systems()
    {
        Assert.Equal(7, StandSizing.TargetSystems(upright: true, staves: 1));
        Assert.Equal(5, StandSizing.TargetSystems(upright: false, staves: 1));
        Assert.Equal(2, StandSizing.TargetSystems(upright: false, staves: 6));
        Assert.Equal(2.5, StandSizing.TargetSystems(upright: false, staves: 1, textScale: 2));
        Assert.Equal(2, StandSizing.TargetSystems(upright: false, staves: 1, textScale: 4));
    }

    [Fact]
    public void The_scale_fits_the_page_height_within_the_width()
    {
        // 100 epx systems at scale 1, 1000 epx page, 5 systems: twice the size.
        Assert.Equal(2.0, StandSizing.FitScale(1.0, 100, 1000, 5, width: 2000, barsPerRow: 4), 3);
        // A narrow page caps it: 4 bars of at least 150 epx in 900 epx.
        Assert.Equal(1.5, StandSizing.FitScale(1.0, 100, 1000, 5, width: 900, barsPerRow: 4), 3);
        Assert.Equal(0.6, StandSizing.FitScale(1.0, 1000, 100, 5, 2000, 4));
        Assert.Equal(1.2, StandSizing.FitScale(1.2, 0, 1000, 5, 2000, 4));
        Assert.True(StandSizing.NeedsRelayout(1.0, 1.2));
        Assert.False(StandSizing.NeedsRelayout(1.0, 1.05));
    }

    [Fact]
    public void Two_pages_side_by_side_only_on_a_wide_landscape_screen()
    {
        Assert.True(StandSizing.UseSpread(1920, 1080));
        Assert.False(StandSizing.UseSpread(1080, 1920));
        Assert.False(StandSizing.UseSpread(900, 500));
        Assert.False(StandSizing.UseSpread(1100, 1000));
    }
}

public class MusicStandViewModelTests
{
    private sealed class Inline : IUiDispatcher { public void Post(Action action) => action(); }

    private static (ScoreViewModel Score, ScriptedPlayer Player, Said Said) Make()
    {
        var strings = ConnectionMonitorTests.Strings();
        var said = new Said();
        var player = new ScriptedPlayer();
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(player, said, strings, new Inline()), said, strings);
        score.Load(File.ReadAllText(TestPaths.Fixture("two-parts.musicxml")), null);
        said.Items.Clear();
        return (score, player, said);
    }

    private static StandPages FivePages() =>
        StandPages.Build(Enumerable.Range(0, 5).Select(i => new StandSystem(i * 100, i * 100 + 100, i, i)).ToList(), 100, spread: false);

    [Fact]
    public void Opens_on_your_part_quietly_and_leaves_the_mix_and_the_parts_as_they_were()
    {
        var (score, _, said) = Make();
        bool muted = score.Player.MuteMyPart;
        var along = score.Player.PlayAlongPart;
        score.Stand.Enter();
        Assert.True(score.Stand.IsOpen);
        Assert.True(score.Stand.HasMyPart);
        Assert.Equal(score.MyPartIndex, score.SelectedPartIndex);
        Assert.Equal(muted, score.Player.MuteMyPart);
        Assert.Same(along, score.Player.PlayAlongPart);
        Assert.Single(said.Items);
        Assert.Equal("Music stand. Solo Cornet (you), bar 1 of 8. Tap the music to show the controls.", said.Items[0]);
        Assert.StartsWith("Solo Cornet (you) · bar 1 · page 1 of 1", score.Stand.PositionDetail);

        score.Stand.OnlyMyPart = false;
        Assert.Equal(-1, score.SelectedPartIndex);
        Assert.StartsWith("All parts · bar 1", score.Stand.PositionDetail);

        score.Stand.Leave();
        Assert.False(score.Stand.IsOpen);
        Assert.Equal(-1, score.SelectedPartIndex);
        Assert.Equal("Music stand closed.", said.Items[^1]);
    }

    [Fact]
    public void A_screen_reader_hears_no_touch_hint_and_the_layer_stays()
    {
        var (score, _, said) = Make();
        score.Stand.Enter(screenReader: true);
        Assert.Equal("Music stand. Solo Cornet (you), bar 1 of 8.", said.Items[0]);
        Assert.True(score.Stand.IsLayerShown);
        Assert.False(score.Stand.AutoHide(new StandContext(Playing: true, ScreenReader: true)));
    }

    [Fact]
    public void Turns_made_by_the_player_are_announced_and_stop_at_the_ends()
    {
        var (score, _, said) = Make();
        score.Stand.Enter();
        score.Stand.SetPages(FivePages());
        said.Items.Clear();
        Assert.True(score.Execute(ScoreCommand.NextPage));
        Assert.Equal(1, score.Stand.Page);
        Assert.Equal("Page 2 of 5, bars 2 to 2.", said.Items[^1]);
        score.Execute(ScoreCommand.LastPage);
        Assert.Equal(4, score.Stand.Page);
        score.Execute(ScoreCommand.NextPage);
        Assert.Equal("Last page.", said.Items[^1]);
        score.Execute(ScoreCommand.FirstPage);
        score.Execute(ScoreCommand.PreviousPage);
        Assert.Equal("First page.", said.Items[^1]);
        Assert.Contains("page 1 of 5", score.Stand.PositionDetail);
    }

    [Fact]
    public void Playback_turns_the_pages_silently_unless_the_setting_is_off()
    {
        var (score, player, said) = Make();
        score.Stand.Enter();
        score.Stand.SetPages(FivePages());
        var turns = new List<bool>();
        score.Stand.PageChanged += (_, byPlayer) => turns.Add(byPlayer);
        score.Player.PlayPauseCommand.Execute(null);
        said.Items.Clear();
        player.MoveTo(2);
        Assert.Equal(2, score.Stand.Page);
        Assert.Equal([false], turns);
        Assert.DoesNotContain(said.Items, s => s.StartsWith("Page"));

        score.Stand.TurnPagesWhilePlaying = false;
        player.MoveTo(3);
        Assert.Equal(2, score.Stand.Page);
    }

    [Fact]
    public void A_page_the_player_turned_ahead_is_kept_while_the_music_plays_on_the_same_page()
    {
        var (score, player, _) = Make();
        score.Stand.Enter();
        var systems = Enumerable.Range(0, 4).Select(i => new StandSystem(i * 100, i * 100 + 100, i * 2, i * 2 + 1)).ToList();
        score.Stand.SetPages(StandPages.Build(systems, 100, false));
        score.Player.PlayPauseCommand.Execute(null);
        score.Stand.NextPage(); // looking ahead
        player.MoveTo(1); // still in the first system
        Assert.Equal(1, score.Stand.Page);
    }

    [Fact]
    public void In_the_stand_bar_keys_move_the_player_and_esc_leaves_the_stand()
    {
        var (score, player, _) = Make();
        score.Stand.Enter();
        Assert.True(score.Execute(ScoreCommand.NextBar));
        Assert.Contains("seek 1", player.Calls);
        Assert.True(score.Execute(ScoreCommand.LeaveStand));
        Assert.False(score.Stand.IsOpen);
        Assert.True(score.Execute(ScoreCommand.ToggleStand));
        Assert.True(score.Stand.IsOpen);
    }

    [Fact]
    public void Repeat_asks_for_bars_when_none_are_chosen()
    {
        var (score, _, _) = Make();
        score.Stand.Enter();
        Assert.Equal("Repeat", score.Stand.RepeatText);
        Assert.False(score.Stand.ToggleRepeat());
        score.Player.LoopStart = 2;
        score.Player.LoopEnd = 3;
        score.Player.SetLoopCommand.Execute(null); // the bar fields' Repeat
        Assert.Equal("Repeat 2–3", score.Stand.RepeatText);
        Assert.True(score.Stand.ToggleRepeat());
        Assert.Equal("Repeat", score.Stand.RepeatText);
        Assert.True(score.Stand.ToggleRepeat());
        Assert.Equal("Repeat 2–3", score.Stand.RepeatText);
        Assert.Matches(@"^Speed 100\u00A0?%$", score.Stand.SpeedText);
    }

    [Fact]
    public void Nothing_opens_before_a_score_is_loaded()
    {
        var strings = ConnectionMonitorTests.Strings();
        var said = new Said();
        var score = new ScoreViewModel(new ManagedCoreBridge(), new PlayerViewModel(new ScriptedPlayer(), said, strings, new Inline()), said, strings);
        score.Stand.Enter();
        Assert.False(score.Stand.IsOpen);
        Assert.Empty(said.Items);
    }
}

/// <summary>The stand's layout from alphaTab itself: bars per system are fixed and the systems cover every bar before any page is drawn.</summary>
[Collection(AlphaTabCollection.Name)]
public class StandLayoutTests(Xunit.Abstractions.ITestOutputHelper log)
{
    [Theory]
    [InlineData("two-parts")]
    [InlineData("old-hundredth")]
    public async Task Systems_hold_at_most_the_bars_per_row_and_cover_the_score(string which)
    {
        string? path = which == "two-parts" ? TestPaths.Fixture("two-parts.musicxml") : TestPaths.RepoFile("apps/fixtures/old-hundredth/brass-band.musicxml");
        if (path is null) return;
        using var player = new AlphaTabScorePlayer(new BufferedSynthOutput());
        player.LoadScore(File.ReadAllBytes(path));
        using var renderer = new LazyScoreRenderer();
        var layout = await renderer.LayoutAsync(player.Score!, [0], 1200, 1.0, AlphaTab.LayoutMode.Page, barsPerRow: 4);
        var systems = ScoreGeometry.Systems(layout.Bounds!);
        log.WriteLine($"{which}: {player.BarCount} bars, {systems.Count} systems, {layout.Pages.Count} partials; " +
                      string.Join(" ", systems.Select(s => $"[{s.FirstBar}-{s.LastBar} {s.Top:0}-{s.Bottom:0}]")));
        Assert.NotEmpty(systems);
        Assert.All(systems, s => Assert.InRange(s.LastBar - s.FirstBar + 1, 1, 4));
        Assert.Equal(0, systems[0].FirstBar);
        Assert.Equal(player.BarCount - 1, systems[^1].LastBar);
        for (int i = 1; i < systems.Count; i++)
        {
            Assert.Equal(systems[i - 1].LastBar + 1, systems[i].FirstBar);
            Assert.True(systems[i].Top >= systems[i - 1].Bottom - 1, "systems tile top to bottom");
        }
        var pages = StandPages.Build(systems, systems[0].Height * 3.5, spread: false);
        Assert.Equal(pages.LastLeftPage, pages.PageOfBar(player.BarCount - 1));
    }
}
