using System.ComponentModel;
using System.Runtime.InteropServices.WindowsRuntime;
using Brasscribe.Play.Controls;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Review;
using Brasscribe.Play.Core.Stand;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.Play.Dialogs;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
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
        // The part menu is built as it opens, never while one of its own items is being invoked.
        PartMenu.Opening += (_, _) => FillPartMenu();
        Notation.LeaveRequested += (_, _) => PlayButton.Focus(FocusState.Keyboard);
        Notation.MarkInvoked += (_, _) => Main?.CheckNotesCommand.Execute(null);
        Notation.GoToBarRequested += async (_, _) => await ShowGoToBarAsync();
        // The stand's pages also depend on the height (whole systems per page).
        Notation.SizeChanged += (_, e) =>
        {
            if (Math.Abs(e.NewSize.Width - e.PreviousSize.Width) > 20
                || ViewModel?.Stand.IsOpen == true && Math.Abs(e.NewSize.Height - e.PreviousSize.Height) > 20) QueueRender();
        };
        Notation.LocalizedControlType = App.Strings["Score_ControlType"];
        // The notation itself is drawn in the theme's ink, and the page is the theme's paper (Appearance can
        // change while the score is open: design/system.md §10).
        ActualThemeChanged += (_, _) =>
        {
            if (ViewModel is null) return;
            ApplyPageLayout();
            QueueRender();
        };
        Notation.ViewportChanged += (_, viewport) => RequestVisiblePages(viewport);

        // The music stand.
        Notation.StandTapped += OnStandTapped;
        Notation.StandTabbed += OnStandTabbed;
        Notation.StandKey += (_, _) => StandInteraction(showLayer: true);
        Notation.SpreadFailed += (_, _) => { _spreadFailed = true; QueueRender(); };
        StandLayer.ObscuredChanged += (_, _) => ApplyStandWindow(fade: false);
        _hideTimer = DispatcherQueue.CreateTimer();
        _hideTimer.Interval = StandLayer_HideDelay;
        _hideTimer.IsRepeating = false;
        _hideTimer.Tick += (_, _) => OnHideTimer();
        // "4 s after the last touch": any press in the stand starts the wait again.
        AddHandler(PointerPressedEvent, new PointerEventHandler((_, _) =>
        {
            if (ViewModel?.Stand.IsOpen != true) return;
            ViewModel.Stand.Touched(); // Tab or Space kept the layer up until now
            RestartHideTimer();
        }), handledEventsToo: true);
    }

    private static readonly TimeSpan StandLayer_HideDelay = Brasscribe.Play.Core.Stand.StandLayer.HideDelay;

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
            old.Stand.PropertyChanged -= self.OnStandPropertyChanged;
            old.Stand.PageChanged -= self.OnStandPageChanged;
            old.Stand.Opened -= self.OnStandOpened;
            old.Stand.Closed -= self.OnStandClosed;
            old.Player.PropertyChanged -= self.OnPlayerPropertyChanged;
        }
        if (e.NewValue is ScoreViewModel vm)
        {
            vm.PropertyChanged += self.OnViewModelPropertyChanged;
            vm.CursorMoved += self.OnCursorMoved;
            vm.Stand.PropertyChanged += self.OnStandPropertyChanged;
            vm.Stand.PageChanged += self.OnStandPageChanged;
            vm.Stand.Opened += self.OnStandOpened;
            vm.Stand.Closed += self.OnStandClosed;
            vm.Stand.DetectScreenReader = StandPlatform.ScreenReaderRunning;
            vm.Player.PropertyChanged += self.OnPlayerPropertyChanged;
            self.StandBand.Show(vm);
            self.StandLayer.Show(vm);
            vm.Player.Player.PositionChanged += (_, p) => self.DispatcherQueue.TryEnqueue(() => self.OnPlaybackPosition(p));
            self.Notation.ViewModel = vm;
        }
        // x:Bind on a property the parent sets: refresh the one-time bindings once it arrives.
        self.Bindings.Update();
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        // Leaving the page always gives the window back (full screen, the screen kept awake).
        ViewModel?.Stand.Leave(announce: false);
        base.OnNavigatedFrom(e);
    }

    /// <summary>The element stand announcements are raised from while the window's status line is hidden.</summary>
    public FrameworkElement StandAnnouncerHost => StandBand.Announcer;

    public void FocusHeading()
    {
        if (ViewModel.Stand.IsOpen)
        {
            Notation.Focus(FocusState.Programmatic);
            return;
        }
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
        var dialog = new GoToBarDialog(ViewModel.CurrentBar, Math.Max(1, ViewModel.Player.BarCount)) { XamlRoot = XamlRoot, RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs };
        if (await Brasscribe.Play.Services.DialogGate.ShowAsync(dialog) == ContentDialogResult.Primary && dialog.Bar is { } bar)
        {
            ViewModel.GoToBar(bar);
        }
        FocusScore();
    }

    private async void OnEditTitle(object sender, RoutedEventArgs e)
    {
        if (Main is null) return;
        var input = new TextBox { Text = ViewModel.Title, MaxLength = 160, Width = 360 };
        var strings = App.Strings;
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs,
            Title = strings["Score_EditTitle"],
            Content = input,
            PrimaryButtonText = strings["Score_SaveTitle"],
            CloseButtonText = strings["Score_CancelTitle"],
            DefaultButton = ContentDialogButton.Primary,
        };
        if (await Brasscribe.Play.Services.DialogGate.ShowAsync(dialog) == ContentDialogResult.Primary) Main.RenameCurrentScore(input.Text);
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

    /// <summary>The part picker's label and the page layout for the part shown.</summary>
    private void FillPartPicker()
    {
        UpdatePartPickerLabel();
        ApplyPageLayout();
    }

    /// <summary>
    /// "All parts" and each part as radio items (the player's marked "(you)"); choosing one opens the part view.
    /// In the part view of another part, "Make this my part" follows.
    /// </summary>
    private void FillPartMenu()
    {
        PartMenu.Items.Clear();
        void Add(string name, int index)
        {
            var item = new RadioMenuFlyoutItem { Text = name, GroupName = "Parts", Tag = index, IsChecked = ViewModel.SelectedPartIndex == index };
            item.Click += (_, _) => ViewModel.SelectedPartIndex = index;
            PartMenu.Items.Add(item);
        }
        Add(App.Strings["Score_FullScore"], -1);
        foreach (var p in ViewModel.Parts)
            Add(p.Index == ViewModel.MyPartIndex ? App.Strings.Format("Stand_PartYours", p.Name) : p.Name, p.Index);
        if (ViewModel.CanMakeShownMine)
        {
            PartMenu.Items.Add(new MenuFlyoutSeparator());
            var mine = new MenuFlyoutItem { Text = App.Strings["Score_MakeMine"] };
            mine.Click += (_, _) => ViewModel.MakeMine(ViewModel.SelectedPartIndex);
            PartMenu.Items.Add(mine);
        }
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
        if (ViewModel.Stand.IsOpen)
        {
            // The stand: the music alone on the paper, edge to edge with a small margin.
            PageFrame.Background = Brasscribe.Play.Controls.ThemedResources.Brush(this, "BcBgBrush");
            PageSheet.MaxWidth = double.PositiveInfinity;
            PageSheet.Margin = new Thickness(24, 0, 24, 0);
            PageSheet.Background = Brasscribe.Play.Controls.ThemedResources.Brush(this, "BcBgBrush");
            return;
        }
        bool part = ViewModel.IsPartView;
        PageFrame.Background = Brasscribe.Play.Controls.ThemedResources.Brush(this, part ? "BcSurfaceBrush" : "BcBgBrush");
        PageSheet.MaxWidth = part ? 960 : double.PositiveInfinity;
        PageSheet.Margin = part ? new Thickness(24, 24, 24, 0) : new Thickness(0);
        PageSheet.Background = Brasscribe.Play.Controls.ThemedResources.Brush(this, "BcBgBrush");
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
            try
            {
                await RenderAsync();
            }
            catch (Exception e) when (e is not OutOfMemoryException)
            {
                // alphaTab could not lay out this score (or this part at this zoom): no notes rather than no app.
                System.Diagnostics.Trace.TraceWarning($"Score layout failed: {e}");
                _layout = null;
                _requested.Clear();
                Notation.SetPageSlots([], 0, 0);
                App.MainWindowInstance?.ShowProblem(App.Strings["Score_RenderFailed"]);
            }
        });
    }

    /// <summary>
    /// Lays out the score off the UI thread, then draws only the pages near the viewport. The UI
    /// thread only places page slots and decodes finished PNGs (BitmapImage decodes asynchronously).
    /// </summary>
    private async Task RenderAsync()
    {
        if (ViewModel.Player.Player is not AlphaTabScorePlayer player || player.Score is null || ViewModel.Document is null) return;
        if (ViewModel.Stand.IsOpen)
        {
            await RenderStandAsync(player);
            return;
        }
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

    // ---- the music stand (design/music-stand.md) ----

    /// <summary>Space kept above the first system and below the last one of a page.</summary>
    private const double StandPad = 8;

    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _hideTimer;
    private Microsoft.UI.Xaml.Controls.Primitives.FlyoutBase? _notationFlyout;
    private double _standScale = 1.0;
    private bool _spreadFailed;

    private void OnMusicStand(object sender, RoutedEventArgs e) => ViewModel.Stand.Enter();

    private void OnStandAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        if (ViewModel.IsLoaded) ViewModel.Stand.Toggle();
    }

    private void OnStandOpened(object? sender, EventArgs e)
    {
        _notationFlyout = Notation.ContextFlyout;
        Notation.ContextFlyout = null; // no "Listen to this bar" or "Keep" on the stand
        Notation.IsStand = true;
        _spreadFailed = false;
        ApplyPageLayout();
        QueueRender();
        RestartHideTimer();
        // Focus lands on the score; the next Tab reaches Leave, then the controls.
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => Notation.Focus(FocusState.Programmatic));
    }

    private void OnStandClosed(object? sender, EventArgs e)
    {
        _hideTimer.Stop();
        Notation.IsStand = false;
        Notation.ContextFlyout = _notationFlyout;
        Notation.BottomObscuredHeight = 96;
        ApplyPageLayout();
        QueueRender();
        // Focus goes back to the button that opened it (the system.md focus rule).
        if (Main?.Screen == Screen.Score)
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => MusicStandButton.Focus(FocusState.Programmatic));
    }

    private void OnStandPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MusicStandViewModel.IsLayerShown))
        {
            if (ViewModel.Stand.IsLayerShown) RestartHideTimer();
            // Wait for the card's new size before moving the window (ObscuredChanged follows).
            DispatcherQueue.TryEnqueue(() => ApplyStandWindow(fade: false));
        }
    }

    private void OnStandPageChanged(object? sender, bool byPlayer) => ApplyStandWindow(fade: true);

    private void OnPlayerPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        // The current system may move under the layer without a page turn.
        if (e.PropertyName == nameof(PlayerViewModel.CurrentBar) && ViewModel.Stand.IsOpen) ApplyStandWindow(fade: false);
        if (e.PropertyName == nameof(PlayerViewModel.IsPlaying) && ViewModel.Stand.IsOpen) RestartHideTimer();
    }

    /// <summary>A tap on the music: the layer toggles. If focus is in the layer, it moves to the score first, so it never lands on nothing.</summary>
    private void OnStandTapped(object? sender, EventArgs e)
    {
        if (ViewModel.Stand.IsLayerShown && StandLayer.HasFocusWithin()) Notation.Focus(FocusState.Programmatic);
        ViewModel.Stand.Tap();
        RestartHideTimer();
    }

    /// <summary>Tab from the score shows the layer and goes to Leave; Shift+Tab goes to the layer's last control.</summary>
    private void OnStandTabbed(object? sender, bool back)
    {
        StandInteraction(showLayer: true);
        DispatcherQueue.TryEnqueue(() => (back ? StandLayer.Last : StandBand.Leave).Focus(FocusState.Keyboard));
    }

    private void StandInteraction(bool showLayer)
    {
        if (showLayer) ViewModel.Stand.KeyPressed();
        RestartHideTimer();
    }

    /// <summary>Keys pressed on the stand's controls (focus off the score): pages, Esc and the rest of the stand's keys.</summary>
    private void OnRootKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Handled || ViewModel?.Stand.IsOpen != true) return;
        var mapped = ScoreView.MapKey(e.Key);
        // Tab and Space show the layer and start its wait again; a pedal's page keys leave both as they are.
        if (e.Key == Windows.System.VirtualKey.Tab || Brasscribe.Play.Core.Stand.StandLayer.ShowsLayer(mapped)) StandInteraction(showLayer: true);
        if (XamlRoot is not null && FocusManager.GetFocusedElement(XamlRoot) is TextBox or NumberBox) return;
        if (mapped is not { } key || key == ScoreKey.Space) return; // Space presses the focused button
        // Single-key shortcuts (F, L, -, +) work only while the score has focus (WCAG 2.1.4).
        if (ScoreKeyMap.Map(key, ScoreView.Modifiers(), singleKeyShortcuts: false, stand: true) is not { } command) return;
        ViewModel.Execute(command);
        e.Handled = true;
    }

    private void RestartHideTimer()
    {
        _hideTimer.Stop();
        if (ViewModel?.Stand.IsOpen == true) _hideTimer.Start();
    }

    private void OnHideTimer()
    {
        if (!ViewModel.Stand.IsOpen) return;
        var context = new StandContext(
            Playing: ViewModel.Player.IsPlaying,
            ScreenReader: StandPlatform.ScreenReaderRunning(),
            FocusInLayer: StandLayer.HasFocusWithin(),
            TextInputOrTouchKeyboard: StandPlatform.TextInputOrTouchKeyboard(XamlRoot));
        if (!ViewModel.Stand.AutoHide(context) && ViewModel.Stand.IsLayerShown) RestartHideTimer(); // look again later
    }

    /// <summary>
    /// Lays out the stand from the §3 sizing contract: 4 bars per system (fewer at large text or zoom),
    /// the staff size fitted so a page holds the target systems, two pages side by side when wide.
    /// </summary>
    private async Task RenderStandAsync(AlphaTabScorePlayer player)
    {
        var score = player.Score!;
        var doc = ViewModel.Document!;
        double viewW = Notation.ActualWidth, viewH = Notation.ActualHeight;
        if (viewW <= 0 || viewH <= 0) return;
        _tracks = ViewModel.SelectedPartIndex >= 0 ? [ViewModel.SelectedPartIndex] : player.Tracks.Select(t => t.Index).ToArray();
        bool concert = ViewModel.ConcertPitch;
        var display = player.Tracks.ToDictionary(t => t.Index, t => t.DisplayTransposition);
        var palette = Palette();
        bool spread = !_spreadFailed && StandSizing.UseSpread(viewW, viewH);
        Notation.IsSpread = spread;
        double width = Notation.StandColumnWidth(spread) - 24;
        double textScale = new Windows.UI.ViewManagement.UISettings().TextScaleFactor;
        int bars = StandSizing.BarsPerRow(textScale, ViewModel.ZoomPercent / 100.0);
        double pageHeight = Math.Max(100, viewH - 2 * StandPad);
        double target = StandSizing.TargetSystems(upright: viewH > viewW, staves: _tracks.Length, textScale);

        Task<ScoreLayout> Layout(double scale) => _renderer.LayoutAsync(score, _tracks, width, scale, AlphaTab.LayoutMode.Page, s =>
        {
            foreach (var (index, transposition) in display)
                foreach (var staff in s.Tracks[index].Staves)
                    staff.DisplayTranspositionPitch = concert ? 0 : transposition;
            ScoreStyler.ApplyUncertainty(s, doc, palette);
        }, palette, bars);

        var layout = await Layout(_standScale);
        if (layout.Generation != _renderer.Generation || layout.Bounds is null) return;
        var systems = ScoreGeometry.Systems(layout.Bounds);
        if (systems.Count > 0)
        {
            double typical = systems.Select(x => x.Height).Order().ElementAt(systems.Count / 2);
            double fitted = StandSizing.FitScale(_standScale, typical, pageHeight, target, width, bars);
            if (StandSizing.NeedsRelayout(_standScale, fitted))
            {
                _standScale = fitted;
                layout = await Layout(fitted);
                if (layout.Generation != _renderer.Generation || layout.Bounds is null) return;
                systems = ScoreGeometry.Systems(layout.Bounds);
            }
        }
        if (!ViewModel.Stand.IsOpen) return; // left while laying out

        _layout = layout;
        _requested.Clear();
        Notation.ReduceMotion = ReduceMotion();
        Notation.SetPageSlots(layout.Pages.Select(p => (p.Id, new Rect(p.X, p.Y, p.Width, p.Height))), layout.Width, layout.Height);
        DrawOverlays();
        ViewModel.Stand.SetPages(StandPages.Build(systems, pageHeight, spread));
    }

    /// <summary>No animation when Windows or the app's own setting reduces motion (WCAG 2.2.2, 2.3.3).</summary>
    private bool ReduceMotion() => !new Windows.UI.ViewManagement.UISettings().AnimationsEnabled || Main?.Settings.ReduceMotion == true;

    /// <summary>
    /// Shows the stand's page (and the next one on the right in a spread). The window moves down when the
    /// current system would be under the control layer (§4.3); nothing is laid out again.
    /// </summary>
    private void ApplyStandWindow(bool fade)
    {
        if (ViewModel?.Stand.IsOpen != true) return;
        var pages = ViewModel.Stand.Pages;
        if (pages.Count == 0) return;
        int page = pages.Clamp(ViewModel.Stand.Page);
        var left = pages.Pages[page];
        double obscured = StandLayer.ObscuredHeight;
        Notation.BottomObscuredHeight = obscured;
        int system = pages.SystemOf(ViewModel.Stand.CurrentBar - 1);
        StandSystem? current = system >= left.FirstSystem && system <= left.LastSystem ? pages.Systems[system] : null;
        double top = StandPages.WindowTop(left.Top - StandPad, current, Notation.ActualHeight, obscured);
        double? right = pages.IsSpread && page + 1 < pages.Count ? pages.Pages[page + 1].Top - StandPad : null;
        Notation.ShowStandWindow(top, right, fade && !ReduceMotion());
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
        byte[]? png;
        try { png = await _renderer.RenderPageAsync(generation, id); }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            // One page that cannot be drawn stays blank; it is asked for again when it scrolls back into view.
            System.Diagnostics.Trace.TraceWarning($"Score page {id} failed: {e}");
            _requested.Remove(id);
            return;
        }
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
            null, null, ScoreView.IsHighContrast()) { Groups = ScoreGeometry.GroupBrackets(player.Score, bounds, ViewModel.Document!, _tracks) }));
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
        var staff = ScoreGeometry.BarBox(bounds, nav.BarIndex, nav.PartIndex);
        Notation.SetFocusRect(box is { } f ? ToRect(f) : null, items, staff is { } st ? ToRect(st) : null);
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
        (Application.Current as App)?.Theme?.Attach(_pip);
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
