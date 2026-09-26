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
using Microsoft.UI.Xaml.Navigation;
using Windows.Foundation;
using Windows.Storage.Streams;

namespace Brasscribe.Play.Views;

/// <summary>
/// The score and the part view. Renders the selected part (or the full score) with alphaTab's Skia
/// engine into bitmaps, draws the design overlays from alphaTab's bounds, and keeps the notation, the
/// talking score and the player in step. With one part chosen it becomes the part view: a page with
/// the part's header, no parts panel, and the player's own part muted.
/// </summary>
public sealed partial class ScoreScreen : Page, IScreenPage
{
    private ScoreLayout? _layout;
    private readonly LazyScoreRenderer _renderer = ScoreRendering.Renderer;
    private readonly HashSet<string> _requested = [];
    private int[] _tracks = [];
    private bool _renderQueued;

    public ScoreScreen()
    {
        InitializeComponent();
        Notation.LeaveRequested += (_, _) => PlayButton.Focus(FocusState.Keyboard);
        Notation.MarkInvoked += (_, _) => Main?.CheckNotesCommand.Execute(null);
        Notation.GoToBarRequested += async (_, _) => await ShowGoToBarAsync();
        Notation.SizeChanged += (_, e) => { if (Math.Abs(e.NewSize.Width - e.PreviousSize.Width) > 20) QueueRender(); };
        Notation.LocalizedControlType = App.Strings["Score_ControlType"];
        ActualThemeChanged += (_, _) => QueueRender(); // the notation itself is drawn in the theme's ink
        Notation.ViewportChanged += (_, viewport) => RequestVisiblePages(viewport);
    }

    public ScoreViewModel ViewModel
    {
        get => (ScoreViewModel)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty =
        DependencyProperty.Register(nameof(ViewModel), typeof(ScoreViewModel), typeof(ScoreScreen), new PropertyMetadata(null, OnViewModelChanged));

    public MainViewModel? Main { get; private set; }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        if (!ReferenceEquals(ViewModel, Main.Score)) ViewModel = Main.Score;
        else Bindings.Update();
        FillPartPicker();
        SyncChoices();
    }

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
        // x:Bind on a property the parent sets: refresh the one-time bindings once it arrives.
        self.Bindings.Update();
    }

    public void FocusHeading()
    {
        if (ViewModel.IsPartView) PartHeading.Focus(FocusState.Programmatic);
        else Heading.Focus(FocusState.Programmatic);
    }

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
                AttachVideo();
                break;
            case nameof(ScoreViewModel.HasVideo):
                AttachVideo();
                break;
            case nameof(ScoreViewModel.SelectedPartIndex):
                ApplyPageLayout();
                UpdatePartPickerLabel();
                QueueRender();
                break;
            case nameof(ScoreViewModel.ZoomPercent) or nameof(ScoreViewModel.ConcertPitch):
                SyncChoices();
                QueueRender();
                break;
            case nameof(ScoreViewModel.ListeningTo):
                SyncChoices();
                break;
            case nameof(ScoreViewModel.UncertainLeft):
                QueueRender(); // a kept note loses its "?" and its colour
                break;
        }
    }

    /// <summary>"All parts" and each part as radio items; choosing one opens the part view.</summary>
    private void FillPartPicker()
    {
        PartMenu.Items.Clear();
        void Add(string name, int index)
        {
            var item = new RadioMenuFlyoutItem { Text = name, GroupName = "Parts", Tag = index, IsChecked = ViewModel.SelectedPartIndex == index };
            item.Click += (_, _) => ViewModel.SelectedPartIndex = index;
            PartMenu.Items.Add(item);
        }
        Add(App.Strings["Score_FullScore"], -1);
        foreach (var p in ViewModel.Parts) Add(p.Name, p.Index);
        UpdatePartPickerLabel();
        ApplyPageLayout();
    }

    private void UpdatePartPickerLabel()
    {
        int i = ViewModel.SelectedPartIndex;
        PartPickerLabel.Text = i >= 0 && i < ViewModel.Parts.Count ? ViewModel.Parts[i].Name : App.Strings["Score_FullScore"];
        foreach (var item in PartMenu.Items.OfType<RadioMenuFlyoutItem>()) item.IsChecked = item.Tag is int t && t == i;
    }

    /// <summary>The part view is a page on the paper, centred and at most 960 wide; the full score is full width.</summary>
    private void ApplyPageLayout()
    {
        bool part = ViewModel.IsPartView;
        PageFrame.Background = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[part ? "BcSurfaceBrush" : "BcBgBrush"];
        PageSheet.MaxWidth = part ? 960 : double.PositiveInfinity;
        PageSheet.Margin = part ? new Thickness(24, 24, 24, 0) : new Thickness(0);
        PageSheet.Background = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["BcBgBrush"];
    }

    private bool _syncing;

    /// <summary>The segments follow the view model (pitch, which audio plays).</summary>
    private void SyncChoices()
    {
        if (ViewModel is null) return;
        _syncing = true;
        WrittenChoice.IsChecked = !ViewModel.ConcertPitch;
        ConcertChoice.IsChecked = ViewModel.ConcertPitch;
        HearBand.IsChecked = ViewModel.ListeningTo == ListeningSource.Score;
        HearRecording.IsChecked = ViewModel.ListeningTo == ListeningSource.Original;
        _syncing = false;
    }

    private void OnPitchChecked(object sender, RoutedEventArgs e)
    {
        if (_syncing) return;
        ViewModel.ConcertPitch = ReferenceEquals(sender, ConcertChoice);
    }

    private void OnHearChecked(object sender, RoutedEventArgs e)
    {
        if (_syncing) return;
        var wanted = ReferenceEquals(sender, HearRecording) ? ListeningSource.Original : ListeningSource.Score;
        if (ViewModel.ListeningTo != wanted) ViewModel.SwitchSource();
        SyncChoices();
    }

    private void OnCheckThem(object sender, RoutedEventArgs e) => Main?.CheckNotesCommand.Execute(null);

    private void OnChooseOutput(object sender, RoutedEventArgs e) => Main?.ChooseOutputCommand.Execute(null);

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

    /// <summary>
    /// Lays out the score off the UI thread, then draws only the pages near the viewport. The UI
    /// thread only places page slots and decodes finished PNGs (BitmapImage decodes asynchronously).
    /// </summary>
    private async Task RenderAsync()
    {
        if (ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null || ViewModel.Document is null) return;
        var score = player.Score;
        var doc = ViewModel.Document;
        _tracks = ViewModel.SelectedPartIndex >= 0 ? [ViewModel.SelectedPartIndex] : player.Tracks.Select(t => t.Index).ToArray();
        bool concert = ViewModel.ConcertPitch;
        var display = player.Tracks.ToDictionary(t => t.Index, t => t.DisplayTransposition);
        var palette = Palette();
        // Above 200 % a single part reflows into one horizontal line so scrolling goes one way.
        var mode = ViewModel.ZoomPercent > 200 && ViewModel.SelectedPartIndex >= 0 ? AlphaTab.LayoutMode.Horizontal : AlphaTab.LayoutMode.Page;
        double width = Math.Max(400, Notation.ActualWidth - 24);

        var layout = await _renderer.LayoutAsync(score, _tracks, width, ViewModel.ZoomPercent / 100.0, mode, s =>
        {
            // Written pitch shows each part's transposition; concert pitch shows sounding pitch.
            foreach (var (index, transposition) in display)
                foreach (var staff in s.Tracks[index].Staves)
                    staff.DisplayTranspositionPitch = concert ? 0 : transposition;
            ScoreStyler.ApplyUncertainty(s, doc, palette);
        }, palette);
        if (layout.Generation != _renderer.Generation) return; // a newer render is on its way

        _layout = layout;
        _requested.Clear();
        Notation.ReduceMotion = !new Windows.UI.ViewManagement.UISettings().AnimationsEnabled;
        Notation.SetPageSlots(layout.Pages.Select(p => (p.Id, new Rect(p.X, p.Y, p.Width, p.Height))), layout.Width, layout.Height);
        DrawOverlays();
    }

    /// <summary>Asks for the pages in and around the viewport, nearest first.</summary>
    private void RequestVisiblePages(Rect viewport)
    {
        if (_layout is not { } layout) return;
        foreach (var released in Notation.ReleaseFarPages(viewport)) _requested.Remove(released);
        var ids = Notation.PagesNear(viewport)
            .Where(id => !_requested.Contains(id))
            .OrderBy(id => Math.Abs(layout.Pages.First(p => p.Id == id).Y - viewport.Y))
            .ToList();
        foreach (var id in ids)
        {
            _requested.Add(id);
            _ = LoadPageAsync(layout.Generation, id);
        }
    }

    private async Task LoadPageAsync(int generation, string id)
    {
        var png = await _renderer.RenderPageAsync(generation, id);
        if (png is null || generation != _renderer.Generation) return;
        var bitmap = new BitmapImage();
        using var stream = new InMemoryRandomAccessStream();
        await stream.WriteAsync(png.AsBuffer());
        stream.Seek(0);
        await bitmap.SetSourceAsync(stream);
        if (generation == _renderer.Generation) Notation.SetPageImage(id, bitmap);
    }

    /// <summary>The score colours of the current theme (a stand-in in contrast themes, where XAML uses system colours).</summary>
    private UncertaintyPalette Palette() =>
        ScoreView.IsHighContrast() ? UncertaintyPalette.HighContrast
        : UncertaintyPalette.For(ActualTheme == ElementTheme.Dark ? ThemeKind.Dark : ThemeKind.Light);

    private IReadOnlyList<Box> _loopBoxes = [];

    /// <summary>"?" marks, the repeated bars and the ad lib bars, planned in Core and drawn by the score view.</summary>
    private void DrawOverlays()
    {
        if (_layout?.Bounds is not { } bounds || ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null) return;
        var heads = ScoreGeometry.UncertainHeads(player.Score, bounds, ViewModel.Document!, _tracks);
        _loopBoxes = player.Loop is { } l ? ScoreGeometry.RangeBoxes(bounds, l.First, l.Last) : [];
        string? label = player.Loop is { } loop ? App.Strings.Format("Score_LoopLabel", loop.First + 1, loop.Last + 1) : null;
        Notation.SetOverlay(ScoreOverlay.Build(new(heads, _loopBoxes, label, ScoreGeometry.AdlibRegions(bounds, ViewModel.Document!),
            null, null, ScoreView.IsHighContrast())));
        UpdateFocus();
    }

    private void OnCursorMoved(object? sender, string text)
    {
        UpdateFocus();
        if (ViewModel.ShowTalkingScore) TalkingList.ScrollIntoView(TalkingList.SelectedItem);
    }

    private void UpdateFocus()
    {
        if (_layout?.Bounds is not { } bounds || ViewModel.Navigator is not { } nav || ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null) return;
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
        // While the score plays, the original video follows it (muted, at the score's speed).
        if (ViewModel.HasVideo && ViewModel.ListeningTo == ListeningSource.Score)
            _follower?.Follow(ViewModel.Player.Player.State, p.Tick, ViewModel.Player.Player.Speed);
        if (_layout?.Bounds is not { } bounds || ViewModel.Player.Player is not AlphaTabScorePlayer player || player.TickLookup is null) return;
        if (ScoreGeometry.Cursor(player.TickLookup, bounds, _tracks, p.Tick) is { } c)
        {
            Notation.SetCursor(ScoreOverlay.Cursor(c.Beat, c.Bar, _loopBoxes, ScoreView.IsHighContrast()));
        }
    }

    private static Rect ToRect(Box b) => new(b.X, b.Y, Math.Max(0, b.W), Math.Max(0, b.H));

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

    private VideoWindow? _pip;
    private VideoFollower? _follower;

    private Services.MediaPlayerOriginal? Media => ViewModel.Original as Services.MediaPlayerOriginal;

    /// <summary>Shows the original video in the parts panel once a score with a video loads.</summary>
    private void AttachVideo()
    {
        _follower = ViewModel.Original is { } o && ViewModel.TimeMap is { } map ? new VideoFollower(o, map) : null;
        if (Media is { } media && ViewModel.HasVideo && _pip is null) VideoView.SetMediaPlayer(media.Player);
        SyncChoices();
    }

    private void OnPictureInPicture(object sender, RoutedEventArgs e)
    {
        if (Media is not { } media) return;
        if (_pip is not null)
        {
            _pip.Close();
            return;
        }
        VideoView.SetMediaPlayer(null);
        _pip = new VideoWindow(media.Player, App.Strings["Pip_Title"]);
        _pip.Closed += (_, _) =>
        {
            _pip?.Detach();
            _pip = null;
            VideoView.SetMediaPlayer(media.Player);
            ViewMenuButton.Focus(FocusState.Programmatic);
        };
        _pip.Activate();
    }
}
