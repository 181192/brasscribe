using System.ComponentModel;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.Play.Dialogs;
using Brasscribe.Play.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media.Animation;
using Windows.System;

namespace Brasscribe.Play;

/// <summary>A flow step shown in the window's frame.</summary>
public interface IScreenPage
{
    /// <summary>Puts keyboard focus on the page heading (after every navigation, so screen readers start there).</summary>
    void FocusHeading();
}

/// <summary>
/// The shell (design/system.md §4, Windows): a title bar with Back, the page title and the page's
/// actions; a NavigationView whose pane holds the library on Home and while a score is made; and a
/// Frame that shows one flow step at a time. The view model's <see cref="MainViewModel.Screen"/>
/// decides the step; the frame keeps no back stack (Back goes through the view model).
/// </summary>
public sealed partial class MainWindow : Window
{
    private readonly IStrings _s;

    public MainWindow(MainViewModel viewModel, IStrings strings)
    {
        ViewModel = viewModel;
        _s = strings;
        InitializeComponent();
        Title = strings["AppWindowTitle"];
        AppWindow.SetIcon("Assets/AppIcon.ico");
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1440, 900));
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(DragRegion);

        // Ctrl+, opens settings (VK_OEM_COMMA has no XAML name).
        var settings = new KeyboardAccelerator { Key = (VirtualKey)188, Modifiers = VirtualKeyModifiers.Control };
        settings.Invoked += OnSettingsAccelerator;
        Root.KeyboardAccelerators.Add(settings);

        // The Back key (mouse and keyboard back button): XAML cannot parse "GoBack" as a VirtualKey
        // and the window fails to load, so it is added here.
        var back = new KeyboardAccelerator { Key = VirtualKey.GoBack };
        back.Invoked += OnBackAccelerator;
        Root.KeyboardAccelerators.Add(back);

        // Back goes through the view model. Clearing BackStack after Navigate throws when a
        // navigation is still in progress (a screen change during Loaded), so keep none at all.
        ContentFrame.IsNavigationStackEnabled = false;

        ViewModel.PropertyChanged += OnViewModelChanged;
        ViewModel.Score.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(ScoreViewModel.Title) or nameof(ScoreViewModel.SelectedPartIndex)) UpdateTitleBar();
        };
        ViewModel.Transcription.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(TranscriptionViewModel.Title)) UpdateTitleBar(); };
        ViewModel.Score.Stand.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(MusicStandViewModel.IsOpen)) ApplyMusicStand(ViewModel.Score.Stand.IsOpen); };
        Root.Loaded += (_, _) => Show(ViewModel.Screen);

        // The heartbeat runs while the window is in front: minimised stops it, restored checks at once.
        AppWindow.Changed += (sender, args) =>
        {
            if (!args.DidPresenterChange && !args.DidVisibilityChange && !args.DidSizeChange) return;
            bool minimized = sender.Presenter is Microsoft.UI.Windowing.OverlappedPresenter { State: Microsoft.UI.Windowing.OverlappedPresenterState.Minimized }
                             || !sender.IsVisible;
            if (!HeartbeatEnabled) return;
            if (minimized) ViewModel.Settings.Connection.Stop();
            else ViewModel.Settings.Connection.Start();
        };
        Closed += (_, _) => ViewModel.Settings.Connection.Stop();
    }

    /// <summary>Off for screenshots (the scenes show a fixed connection state).</summary>
    public bool HeartbeatEnabled { get; set; } = true;

    public MainViewModel ViewModel { get; }

    /// <summary>The element UIA notifications are raised from (see <see cref="Services.UiaAnnouncer"/>); the stand's band while the status line is hidden.</summary>
    public FrameworkElement AnnouncerHost =>
        ViewModel.Score.Stand.IsOpen && ContentFrame.Content is ScoreScreen score ? score.StandAnnouncerHost : StatusText;

    private Microsoft.UI.Windowing.AppWindowPresenter? _presenterBeforeStand;

    /// <summary>
    /// The music stand takes the window full screen, hides the title bar and the status line, and keeps
    /// the screen on; leaving gives back the window exactly as it was (a maximised window stays maximised).
    /// </summary>
    private void ApplyMusicStand(bool open)
    {
        AppTitleBar.Visibility = open ? Visibility.Collapsed : Visibility.Visible;
        StatusText.Visibility = open ? Visibility.Collapsed : Visibility.Visible;
        StandPlatform.KeepScreenOn(open);
        if (open)
        {
            if (AppWindow.Presenter.Kind == Microsoft.UI.Windowing.AppWindowPresenterKind.FullScreen) return;
            _presenterBeforeStand = AppWindow.Presenter;
            AppWindow.SetPresenter(Microsoft.UI.Windowing.AppWindowPresenterKind.FullScreen);
        }
        else if (_presenterBeforeStand is { } before)
        {
            _presenterBeforeStand = null;
            AppWindow.SetPresenter(before);
        }
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MainViewModel.Screen)) Show(ViewModel.Screen);
    }

    private static Type PageFor(Screen screen) => screen switch
    {
        Screen.FirstRun => typeof(FirstRunPage),
        Screen.SourceKind => typeof(WhatIsThisPage),
        Screen.Transcribing => typeof(TranscribingPage),
        Screen.Review => typeof(ReviewPage),
        Screen.ChooseOutput => typeof(ChooseOutputPage),
        Screen.Score => typeof(ScoreScreen),
        Screen.Error => typeof(ErrorPage),
        _ => typeof(HomePage),
    };

    private void Show(Screen screen)
    {
        var type = PageFor(screen);
        if (ContentFrame.Content?.GetType() != type)
        {
            // Reduced motion: no slide, only the page swap.
            bool motion = new Windows.UI.ViewManagement.UISettings().AnimationsEnabled && !ViewModel.Settings.ReduceMotion;
            NavigationTransitionInfo transition = motion ? new DrillInNavigationTransitionInfo() : new SuppressNavigationTransitionInfo();
            ContentFrame.Navigate(type, ViewModel, transition);
        }
        UpdateTitleBar();
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => (ContentFrame.Content as IScreenPage)?.FocusHeading());
    }

    /// <summary>Back label, page title and subtitle for the current step.</summary>
    private void UpdateTitleBar()
    {
        var score = ViewModel.Score;
        string song = score.Title;
        (string? back, string title, string subtitle) = ViewModel.Screen switch
        {
            Screen.SourceKind => (_s["Back_Home"], ViewModel.Kind.Source?.DisplayName ?? "", ""),
            Screen.Transcribing => (ViewModel.Transcription.IsRunning ? null : _s["Back_Home"], ViewModel.Transcription.Title, ""),
            Screen.Error => (_s["Back_Home"], ViewModel.Transcription.Title, ""),
            Screen.Review => (song, _s.Format("Title_CheckNotes", song), ""),
            Screen.ChooseOutput => (song, song, ""),
            Screen.Score when score.IsPartView => (_s["Back_FullScore"], song, ""),
            Screen.Score => (_s["Back_Home"], song, ViewModel.ScoreSubtitle),
            _ => ((string?)null, "", ""),
        };
        BackButton.Visibility = back is not null && ViewModel.BackCommand.CanExecute(null) ? Visibility.Visible : Visibility.Collapsed;
        BackLabel.Text = back ?? "";
        PageTitle.Text = title;
        PageSubtitle.Text = subtitle;
        Title = title.Length > 0 ? $"{title} – {_s["AppWindowTitle"]}" : _s["AppWindowTitle"];
    }

    private void OnLibraryItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
    {
        if (args.InvokedItemContainer?.DataContext is LibraryItem item) ViewModel.OpenLibraryItemCommand.Execute(item);
    }

    private void OnLibraryItemOptions(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: LibraryItem item } button) ScoreOptions.Show(ViewModel, item, button);
    }

    private void OnLibraryItemContextRequested(UIElement sender, Microsoft.UI.Xaml.Input.ContextRequestedEventArgs args)
    {
        if (sender is not FrameworkElement { DataContext: LibraryItem item } element) return;
        args.Handled = true;
        ScoreOptions.Show(ViewModel, item, element, args.TryGetPosition(element, out var point) ? point : null);
    }

    private void OnImportAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        if (ViewModel.Start.ImportCommand.CanExecute(null)) ViewModel.Start.ImportCommand.Execute(null);
    }

    private void OnRecordAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        var start = ViewModel.Start;
        if (start.IsRecording) start.StopRecordingCommand.Execute(null);
        else if (ViewModel.Screen == Screen.Start) start.RecordMicrophoneCommand.Execute(null);
    }

    private void OnPlayPauseAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        if (ViewModel.Score.IsLoaded) ViewModel.Score.Player.PlayPauseCommand.Execute(null);
    }

    private async void OnExportAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ShowExportAsync();
    }

    private async void OnGoToBarAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        if (ContentFrame.Content is ScoreScreen score) await score.ShowGoToBarAsync();
    }

    private void OnToggleTalkingScoreAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        if (ContentFrame.Content is not ScoreScreen score || ViewModel.Score.Stand.IsOpen) return;
        ViewModel.Score.ShowTalkingScore = !ViewModel.Score.ShowTalkingScore;
        score.FocusScore();
    }

    private async void OnSettingsAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await OpenSettingsAsync();
    }

    private async void OnShortcutsAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ShowShortcutsAsync();
    }

    private void OnBackAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (ViewModel.BackCommand.CanExecute(null))
        {
            ViewModel.BackCommand.Execute(null);
            args.Handled = true;
        }
    }

    private async void OnExportClick(object sender, RoutedEventArgs e) => await ShowExportAsync();
    private async void OnSettingsClick(object sender, RoutedEventArgs e) => await OpenSettingsAsync();
    private async void OnShortcutsClick(object sender, RoutedEventArgs e) => await ShowShortcutsAsync();

    /// <summary>"Share or print"; focus returns to the button that opened it.</summary>
    public async Task ShowExportAsync()
    {
        if (!ViewModel.OpenExportCommand.CanExecute(null)) return;
        ViewModel.OpenExportCommand.Execute(null);
        var dialog = new ExportDialog(ViewModel.Export) { XamlRoot = Content.XamlRoot, RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs };
        await dialog.ShowAsync();
        ExportButton.Focus(FocusState.Programmatic);
    }

    private bool _settingsOpen;

    /// <summary>Settings; with a brasscribe://pair link it pairs from the link while the dialog shows the progress.</summary>
    public async Task OpenSettingsAsync(string? pairingLink = null)
    {
        if (_settingsOpen)
        {
            if (pairingLink is not null) await ViewModel.Settings.PairFromLinkAsync(pairingLink);
            return;
        }
        _settingsOpen = true;
        try
        {
            var dialog = new SettingsDialog(ViewModel.Settings, ViewModel) { XamlRoot = Content.XamlRoot, RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs };
            if (pairingLink is not null) dialog.Opened += async (_, _) => await ViewModel.Settings.PairFromLinkAsync(pairingLink);
            await dialog.ShowAsync();
            ViewModel.Settings.CancelAsk();
        }
        finally { _settingsOpen = false; }
        SettingsButton.Focus(FocusState.Programmatic);
    }

    private async Task ShowShortcutsAsync()
    {
        var dialog = new ShortcutsDialog { XamlRoot = Content.XamlRoot, RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs };
        await dialog.ShowAsync();
        HelpButton.Focus(FocusState.Programmatic);
    }
}
