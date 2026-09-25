using System.ComponentModel;
using System.Runtime.InteropServices.WindowsRuntime;
using Brasscribe.Play.Controls;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Review;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.Play.Dialogs;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Foundation;
using Windows.Storage.Streams;

namespace Brasscribe.Play.Views;

/// <summary>
/// Review and practice screen. Renders the selected part (or the full score) with alphaTab's Skia
/// engine into bitmaps, draws the overlays from alphaTab's bounds, and keeps the notation, the
/// talking score and the player in step.
/// </summary>
public sealed partial class ScoreScreen : UserControl
{
    private RenderOutput? _render;
    private readonly ScoreRenderService _renderer = new("skia");
    private int[] _tracks = [];
    private bool _renderQueued;
    private int _lastCursorBar = -1;

    public ScoreScreen()
    {
        InitializeComponent();
        Notation.LeaveRequested += (_, _) => PlayButton.Focus(FocusState.Keyboard);
        Notation.GoToBarRequested += async (_, _) => await ShowGoToBarAsync();
        Notation.SizeChanged += (_, e) => { if (Math.Abs(e.NewSize.Width - e.PreviousSize.Width) > 20) QueueRender(); };
        Notation.ToScreen = ToScreen;
        Notation.LocalizedControlType = App.Strings["Score_ControlType"];
    }

    public ScoreViewModel ViewModel
    {
        get => (ScoreViewModel)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty =
        DependencyProperty.Register(nameof(ViewModel), typeof(ScoreViewModel), typeof(ScoreScreen), new PropertyMetadata(null, OnViewModelChanged));

    public OutputOptionsViewModel Output
    {
        get => (OutputOptionsViewModel)GetValue(OutputProperty);
        set => SetValue(OutputProperty, value);
    }

    public static readonly DependencyProperty OutputProperty =
        DependencyProperty.Register(nameof(Output), typeof(OutputOptionsViewModel), typeof(ScoreScreen), new PropertyMetadata(null));

    private static void OnViewModelChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        var self = (ScoreScreen)d;
        if (e.OldValue is ScoreViewModel old)
        {
            old.PropertyChanged -= self.OnViewModelPropertyChanged;
            old.CursorMoved -= self.OnCursorMoved;
        }
        if (e.NewValue is ScoreViewModel vm)
        {
            vm.PropertyChanged += self.OnViewModelPropertyChanged;
            vm.CursorMoved += self.OnCursorMoved;
            vm.Player.Player.PositionChanged += (_, p) => self.DispatcherQueue.TryEnqueue(() => self.OnPlaybackPosition(p));
            self.Notation.ViewModel = vm;
        }
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    public void FocusScore()
    {
        if (ViewModel.ShowTalkingScore) TalkingList.Focus(FocusState.Programmatic);
        else Notation.Focus(FocusState.Programmatic);
    }

    public async Task ShowGoToBarAsync()
    {
        var dialog = new GoToBarDialog(ViewModel.CurrentBar, Math.Max(1, ViewModel.Player.BarCount)) { XamlRoot = XamlRoot };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && dialog.Bar is { } bar)
        {
            ViewModel.GoToBar(bar);
        }
        FocusScore();
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        switch (e.PropertyName)
        {
            case nameof(ScoreViewModel.IsLoaded) or nameof(ScoreViewModel.Title):
                FillPartPicker();
                QueueRender();
                break;
            case nameof(ScoreViewModel.SelectedPartIndex) or nameof(ScoreViewModel.ZoomPercent) or nameof(ScoreViewModel.ConcertPitch)
                or nameof(ScoreViewModel.UncertainLeft):
                QueueRender();
                break;
        }
    }

    private void FillPartPicker()
    {
        PartPicker.Items.Clear();
        PartPicker.Items.Add(new ComboBoxItem { Content = App.Strings["Score_FullScore"], Tag = -1 });
        foreach (var p in ViewModel.Parts) PartPicker.Items.Add(new ComboBoxItem { Content = p.Name, Tag = p.Index });
        PartPicker.SelectedIndex = ViewModel.SelectedPartIndex + 1;
    }

    private void OnPartSelected(object sender, SelectionChangedEventArgs e)
    {
        if (PartPicker.SelectedItem is ComboBoxItem { Tag: int index }) ViewModel.SelectedPartIndex = index;
    }

    /// <summary>Renders once per UI turn however many settings changed.</summary>
    private void QueueRender()
    {
        if (_renderQueued) return;
        _renderQueued = true;
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, async () =>
        {
            _renderQueued = false;
            await RenderAsync();
        });
    }

    private async Task RenderAsync()
    {
        if (ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null || ViewModel.Document is null) return;
        var score = player.Score;

        _tracks = ViewModel.SelectedPartIndex >= 0 ? [ViewModel.SelectedPartIndex] : player.Tracks.Select(t => t.Index).ToArray();

        // Written pitch shows each part's transposition; concert pitch shows sounding pitch.
        foreach (var t in player.Tracks)
            foreach (var staff in score.Tracks[t.Index].Staves)
                staff.DisplayTranspositionPitch = ViewModel.ConcertPitch ? 0 : t.DisplayTransposition;

        var palette = UncertaintyPalette.For(ActualTheme == ElementTheme.Dark ? ThemeKind.Dark : ThemeKind.Light);
        if (new Windows.UI.ViewManagement.AccessibilitySettings().HighContrast) palette = UncertaintyPalette.HighContrast;
        ScoreStyler.ApplyUncertainty(score, ViewModel.Document, palette);

        _renderer.Scale = ViewModel.ZoomPercent / 100.0;
        // Above 200 % a single part reflows into one horizontal line so scrolling goes one way.
        _renderer.Settings.Display.LayoutMode = ViewModel.ZoomPercent > 200 && ViewModel.SelectedPartIndex >= 0
            ? AlphaTab.LayoutMode.Horizontal : AlphaTab.LayoutMode.Page;

        double width = Math.Max(400, Notation.ActualWidth - 24);
        if (_render is not null) ScoreRenderService.Release(_render);
        _render = _renderer.Render(score, _tracks, width);

        var pages = new List<ScorePage>();
        foreach (var partial in _render.Partials)
        {
            if (ScoreRenderService.ToPng(partial.Result) is not { } png) continue;
            var bitmap = new BitmapImage();
            using var stream = new InMemoryRandomAccessStream();
            await stream.WriteAsync(png.AsBuffer());
            stream.Seek(0);
            await bitmap.SetSourceAsync(stream);
            pages.Add(new ScorePage(bitmap, new Rect(partial.X, partial.Y, partial.Width, partial.Height)));
        }
        Notation.SetPages(pages, _render.TotalWidth, _render.TotalHeight);
        Notation.ReduceMotion = !new Windows.UI.ViewManagement.UISettings().AnimationsEnabled;
        DrawOverlays();
    }

    private void DrawOverlays()
    {
        if (_render?.Bounds is not { } bounds || ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null) return;
        Notation.SetNoteMarks(ScoreGeometry.UncertainHeads(player.Score, bounds, ViewModel.Document!, _tracks)
            .Select(h => new NoteMark(ToRect(h.Head), h.Level)));

        var loop = player.Loop is { } l ? ScoreGeometry.RangeBoxes(bounds, l.First, l.Last).Select(ToRect) : [];
        var adlib = ViewModel.Document!.FreeRegions.SelectMany(r => ScoreGeometry.RangeBoxes(bounds, r.StartBar - 1, r.EndBar - 1)).Select(ToRect);
        Notation.SetBands(loop, adlib);
        UpdateFocus();
    }

    private void OnCursorMoved(object? sender, string text)
    {
        UpdateFocus();
        if (ViewModel.ShowTalkingScore) TalkingList.ScrollIntoView(TalkingList.SelectedItem);
    }

    private void UpdateFocus()
    {
        if (_render?.Bounds is not { } bounds || ViewModel.Navigator is not { } nav || ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null) return;
        var box = ScoreGeometry.FocusBox(player.Score, bounds, nav.PartIndex, nav.BarIndex, nav.TickInBar);
        var items = new List<ScoreEventItem>();
        foreach (var ev in nav.Bar.Events)
        {
            var b = ScoreGeometry.FocusBox(player.Score, bounds, nav.PartIndex, nav.BarIndex, ev.Tick);
            items.Add(new ScoreEventItem(Brief(nav, ev), b is { } r ? ToRect(r) : default, ReferenceEquals(ev, nav.Event)));
        }
        Notation.SetFocusRect(box is { } f ? ToRect(f) : null, items);
    }

    private static string Brief(Brasscribe.Play.Core.TalkingScore.ScoreNavigator nav, Brasscribe.Play.Core.TalkingScore.TsEvent ev)
    {
        var part = nav.Part;
        var s = nav.Settings with { Verbosity = Brasscribe.Play.Core.TalkingScore.Verbosity.Brief };
        return Brasscribe.Play.Core.TalkingScore.Announcer.Announce(
            new(part.Name, part.NameNb, part.Instrument, part.InstrumentNb, part.Transpose),
            new(nav.Bar.Number, nav.Bar.KeyFifths), ev, new(part.Name, nav.Bar.Number, s.PitchMode), s);
    }

    /// <summary>Playback cursor: a line per beat and a tint of the bar; follows by page turn when motion is reduced.</summary>
    private void OnPlaybackPosition(PlaybackPosition p)
    {
        if (_render?.Bounds is not { } bounds || ViewModel.Player.Player is not AlphaTabScorePlayer player || player.TickLookup is null) return;
        if (ScoreGeometry.Cursor(player.TickLookup, bounds, _tracks, p.Tick) is { } c)
        {
            Notation.SetCursor(ToRect(c.Beat), ToRect(c.Bar));
            if (p.BarIndex != _lastCursorBar)
            {
                _lastCursorBar = p.BarIndex;
                if (player.Loop is null) DrawOverlays();
            }
        }
    }

    private static Rect ToRect(Box b) => new(b.X, b.Y, Math.Max(0, b.W), Math.Max(0, b.H));

    private Rect ToScreen(Rect local)
    {
        var transform = Notation.TransformToVisual(null);
        var topLeft = transform.TransformPoint(new Point(local.X, local.Y));
        double scale = XamlRoot?.RasterizationScale ?? 1.0;
        var window = App.MainWindowInstance?.AppWindow.Position ?? new Windows.Graphics.PointInt32(0, 0);
        return new Rect(window.X + topLeft.X * scale, window.Y + topLeft.Y * scale, local.Width * scale, local.Height * scale);
    }

    private void OnZoomOut(object sender, RoutedEventArgs e) => ViewModel.Execute(ScoreCommand.ZoomOut);
    private void OnZoomIn(object sender, RoutedEventArgs e) => ViewModel.Execute(ScoreCommand.ZoomIn);
    private void OnListenToBar(object sender, RoutedEventArgs e) => ViewModel.ListenToBarCommand.Execute(null);
    private void OnMarkChecked(object sender, RoutedEventArgs e) => ViewModel.MarkCheckedCommand.Execute(null);
    private void OnReadBar(object sender, RoutedEventArgs e) => ViewModel.Execute(ScoreCommand.ReadBar);
    private async void OnGoToBarItem(object sender, RoutedEventArgs e) => await ShowGoToBarAsync();

    private void OnLoopStartItem(object sender, RoutedEventArgs e)
    {
        ViewModel.Execute(ScoreCommand.LoopStartHere);
        DrawOverlays();
    }

    private void OnLoopEndItem(object sender, RoutedEventArgs e)
    {
        ViewModel.Execute(ScoreCommand.LoopEndHere);
        DrawOverlays();
    }

    private void OnPlayAlong(object sender, RoutedEventArgs e) => ViewModel.Player.TogglePlayAlongCommand.Execute(null);

    private void OnLineupChanged(object sender, SelectionChangedEventArgs e)
    {
        if (Output is not null) Output.Lineup = LineupBox.SelectedIndex == 1 ? Lineup.MinimalBand : Lineup.FullBand;
    }

    private void OnApplyOutput(object sender, RoutedEventArgs e) => Output.ApplyCommand.Execute(ViewModel.Composition);
}
