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

        ViewModel.PropertyChanged += OnViewModelChanged;
        ViewModel.Score.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(ScoreViewModel.Title) or nameof(ScoreViewModel.SelectedPartIndex)) UpdateTitleBar();
        };
        ViewModel.Transcription.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(TranscriptionViewModel.Title)) UpdateTitleBar(); };
        Root.Loaded += (_, _) => Show(ViewModel.Screen);
    }

    public MainViewModel ViewModel { get; }

    /// <summary>The element UIA notifications are raised from (see <see cref="Services.UiaAnnouncer"/>).</summary>
    public FrameworkElement AnnouncerHost => StatusText;

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
            ContentFrame.BackStack.Clear();
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
            Screen.Score => (_s["Back_Home"], song, _s.Format("Title_ScoreSubtitle", _s[score.Parts.Count <= 6 ? "Library_SmallBand" : "Library_FullBand"], score.Player.BarCount)),
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
        if (ContentFrame.Content is not ScoreScreen score) return;
        ViewModel.Score.ShowTalkingScore = !ViewModel.Score.ShowTalkingScore;
        score.FocusScore();
    }

    private async void OnSettingsAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await ShowSettingsAsync();
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
    private async void OnSettingsClick(object sender, RoutedEventArgs e) => await ShowSettingsAsync();
    private async void OnShortcutsClick(object sender, RoutedEventArgs e) => await ShowShortcutsAsync();

    /// <summary>"Share or print"; focus returns to the button that opened it.</summary>
    public async Task ShowExportAsync()
    {
        if (!ViewModel.OpenExportCommand.CanExecute(null)) return;
        ViewModel.OpenExportCommand.Execute(null);
        var dialog = new ExportDialog(ViewModel.Export) { XamlRoot = Content.XamlRoot };
        await dialog.ShowAsync();
        ExportButton.Focus(FocusState.Programmatic);
    }

    private async Task ShowSettingsAsync()
    {
        var dialog = new SettingsDialog(ViewModel.Settings, ViewModel) { XamlRoot = Content.XamlRoot };
        await dialog.ShowAsync();
        SettingsButton.Focus(FocusState.Programmatic);
    }

    private async Task ShowShortcutsAsync()
    {
        var dialog = new ShortcutsDialog { XamlRoot = Content.XamlRoot };
        await dialog.ShowAsync();
        HelpButton.Focus(FocusState.Programmatic);
    }
}
