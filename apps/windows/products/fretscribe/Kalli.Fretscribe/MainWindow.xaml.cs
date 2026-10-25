using System.ComponentModel;
using Kalli.Scribe.Services;
using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Kalli.Scribe.WinUI;
using Kalli.Fretscribe.Dialogs;
using Kalli.Fretscribe.Views;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media.Animation;
using Windows.System;

namespace Kalli.Fretscribe;

/// <summary>A flow step shown in the window's frame.</summary>
public interface IScreenPage
{
    /// <summary>Puts keyboard focus on the page heading (after every navigation, so screen readers start there).</summary>
    void FocusHeading();
}

/// <summary>
/// The shell: a title bar with Back, the page title and Settings; a NavigationView whose pane holds Your songs on Home
/// and while a tab is written; and a Frame that shows one flow step at a time. The view model's
/// <see cref="TabFlowViewModel.Screen"/> decides the step; the frame keeps no back stack (Back goes through the view model).
/// </summary>
public sealed partial class MainWindow : Window
{
    private readonly IStrings _s;

    public MainWindow(TabFlowViewModel viewModel, IStrings strings)
    {
        ViewModel = viewModel;
        _s = strings;
        InitializeComponent();
        Title = strings["AppWindowTitle"];
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico")); // not the working directory: "Open with" starts elsewhere
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1440, 900));
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(DragRegion);

        // Ctrl+, opens settings (VK_OEM_COMMA has no XAML name).
        var settings = new KeyboardAccelerator { Key = (VirtualKey)188, Modifiers = VirtualKeyModifiers.Control };
        settings.Invoked += OnSettingsAccelerator;
        Root.KeyboardAccelerators.Add(settings);
        // The Back key (mouse and keyboard back button): XAML cannot parse "GoBack" as a VirtualKey.
        var back = new KeyboardAccelerator { Key = VirtualKey.GoBack };
        back.Invoked += OnBackAccelerator;
        Root.KeyboardAccelerators.Add(back);

        ContentFrame.IsNavigationStackEnabled = false;
        ViewModel.PropertyChanged += OnViewModelChanged;
        ViewModel.ProblemNoticed += (_, text) => ShowProblem(text);
        ViewModel.Transcription.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(TranscriptionViewModel.Title) or nameof(TranscriptionViewModel.IsRunning)) UpdateTitleBar();
        };
        ViewModel.TabPage.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(TabPageViewModel.IsFullScreen)) ApplyFullScreen(ViewModel.TabPage.IsFullScreen);
            if (e.PropertyName == nameof(TabPageViewModel.Title)) UpdateTitleBar();
        };
        Root.Loaded += (_, _) => Show(ViewModel.Screen);
        Root.ActualThemeChanged += (_, _) => Brand.ShowMark(Mark, Root);
        Brand.ShowMark(Mark, Root);

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

    public TabFlowViewModel ViewModel { get; }

    /// <summary>The element UIA notifications are raised from (see <see cref="UiaAnnouncer"/>).</summary>
    public FrameworkElement AnnouncerHost => Root;

    private Microsoft.UI.Windowing.AppWindowPresenter? _presenterBefore;

    /// <summary>The tab takes the window full screen without the title bar; leaving gives the window back as it was.</summary>
    private void ApplyFullScreen(bool on)
    {
        AppTitleBar.Visibility = on ? Visibility.Collapsed : Visibility.Visible;
        if (on)
        {
            if (AppWindow.Presenter.Kind == Microsoft.UI.Windowing.AppWindowPresenterKind.FullScreen) return;
            _presenterBefore = AppWindow.Presenter;
            AppWindow.SetPresenter(Microsoft.UI.Windowing.AppWindowPresenterKind.FullScreen);
        }
        else if (_presenterBefore is { } before)
        {
            _presenterBefore = null;
            AppWindow.SetPresenter(before);
        }
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(TabFlowViewModel.Screen)) Show(ViewModel.Screen);
        if (e.PropertyName == nameof(TabFlowViewModel.Title)) UpdateTitleBar();
    }

    /// <summary>The page in the frame now (the screen catalogue checks it is the one for the step asked for).</summary>
    internal object? ShownPage => ContentFrame.Content;

    internal static Type PageFor(TabScreen screen) => screen switch
    {
        TabScreen.FirstRun => typeof(FirstRunPage),
        TabScreen.YourInstrument => typeof(YourInstrumentPage),
        TabScreen.WhatIsThis => typeof(WhatIsThisPage),
        TabScreen.Transcribing => typeof(TranscribingPage),
        TabScreen.CheckTheSong => typeof(CheckTheSongPage),
        TabScreen.Tab => typeof(TabScreenPage),
        TabScreen.Error => typeof(ErrorPage),
        _ => typeof(HomePage),
    };

    private void Show(TabScreen screen)
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

    /// <summary>Back label and page title for the current step.</summary>
    private void UpdateTitleBar()
    {
        string? back = ViewModel.Screen switch
        {
            TabScreen.WhatIsThis or TabScreen.Error or TabScreen.CheckTheSong => _s["Back_Home"],
            TabScreen.Transcribing => ViewModel.Transcription.IsRunning ? null : _s["Back_Home"],
            TabScreen.Tab => ViewModel.LastResult is not null ? _s["Back_CheckTheSong"] : _s["Back_Home"],
            TabScreen.YourInstrument when ViewModel.Settings.FirstRunDone => _s["Back"],
            _ => null,
        };
        BackButton.Visibility = back is not null && ViewModel.BackCommand.CanExecute(null) ? Visibility.Visible : Visibility.Collapsed;
        BackLabel.Text = back ?? "";
        string title = ViewModel.Title;
        PageTitle.Text = title;
        Title = title.Length > 0 ? $"{title} – {_s["AppWindowTitle"]}" : _s["AppWindowTitle"];
    }

    private void OnLibraryItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
    {
        if (args.InvokedItemContainer?.DataContext is LibraryItem item) ViewModel.OpenLibraryItemCommand.Execute(item);
    }

    private void OnLibraryItemOptions(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: LibraryItem item } button) SongOptions.Show(ViewModel, item, button);
    }

    private void OnLibraryItemContextRequested(UIElement sender, ContextRequestedEventArgs args)
    {
        if (sender is not FrameworkElement { DataContext: LibraryItem item } element) return;
        args.Handled = true;
        SongOptions.Show(ViewModel, item, element, args.TryGetPosition(element, out var point) ? point : null);
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
        else if (ViewModel.Screen == TabScreen.Home) start.RecordMicrophoneCommand.Execute(null);
    }

    private async void OnExportAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ShowExportAsync();
    }

    /// <summary>Share or print, for the tab on screen.</summary>
    public async Task ShowExportAsync()
    {
        if (!ViewModel.CanExport || DialogGate.IsOpen) return;
        ViewModel.PrepareExport();
        var dialog = new ExportDialog(ViewModel.Export) { XamlRoot = Content.XamlRoot, RequestedTheme = Kalli.Scribe.Controls.ThemeController.ForDialogs };
        await DialogGate.ShowAsync(dialog);
    }

    private async void OnSettingsAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await OpenSettingsAsync();
    }

    private void OnBackAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (ViewModel.BackCommand.CanExecute(null))
        {
            ViewModel.BackCommand.Execute(null);
            args.Handled = true;
        }
    }

    private async void OnSettingsClick(object sender, RoutedEventArgs e) => await OpenSettingsAsync();

    private bool _settingsOpen;
    private string? _waitingLink;

    /// <summary>
    /// Settings; with a scribe://pair link it pairs from the link while the dialog shows the progress. A link that
    /// arrives while another dialog is open waits until that dialog closes.
    /// </summary>
    public async Task OpenSettingsAsync(string? pairingLink = null)
    {
        if (_settingsOpen)
        {
            if (pairingLink is not null) await ViewModel.Settings.PairFromLinkAsync(pairingLink);
            return;
        }
        if (DialogGate.IsOpen)
        {
            if (pairingLink is null) return;
            if (_waitingLink is null) DialogGate.Closed += OnDialogClosed;
            _waitingLink = pairingLink;
            return;
        }
        _settingsOpen = true;
        bool instrument = false;
        try
        {
            var dialog = new SettingsDialog(ViewModel.Settings, ViewModel) { XamlRoot = Content.XamlRoot, RequestedTheme = Kalli.Scribe.Controls.ThemeController.ForDialogs };
            dialog.InstrumentRequested += (_, _) => { instrument = true; dialog.Hide(); };
            if (pairingLink is not null) dialog.Opened += async (_, _) => await ViewModel.Settings.PairFromLinkAsync(pairingLink);
            await DialogGate.ShowAsync(dialog);
            ViewModel.Settings.CancelAsk();
        }
        finally { _settingsOpen = false; }
        if (instrument) ViewModel.ChangeInstrumentCommand.Execute(null);
        else SettingsButton.Focus(FocusState.Programmatic);
    }

    private void OnDialogClosed(object? sender, EventArgs e)
    {
        DialogGate.Closed -= OnDialogClosed;
        // After the closing dialog has gone from the screen.
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, async () =>
        {
            if (_waitingLink is not { } link) return;
            _waitingLink = null;
            await OpenSettingsAsync(link);
        });
    }

    /// <summary>
    /// Something failed that the app could carry on from: a bar at the bottom of the window says so (read out by
    /// screen readers as it opens) instead of the app closing.
    /// </summary>
    public void ShowProblem(string? message = null)
    {
        ProblemBar.Message = message ?? _s["Notice_Problem"];
        ProblemBar.IsOpen = false; // a second problem is announced again
        ProblemBar.IsOpen = true;
    }
}
