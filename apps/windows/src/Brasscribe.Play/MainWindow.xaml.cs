using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.Play.Dialogs;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.System;

namespace Brasscribe.Play;

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
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1280, 860));

        // Ctrl+, opens settings (VK_OEM_COMMA has no XAML name).
        var settings = new KeyboardAccelerator { Key = (VirtualKey)188, Modifiers = VirtualKeyModifiers.Control };
        settings.Invoked += OnSettingsAccelerator;
        Root.KeyboardAccelerators.Add(settings);

        ViewModel.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(MainViewModel.Screen)) FocusScreenHeading();
        };
        Root.Loaded += (_, _) => StartScreen.FocusHeading();
    }

    public MainViewModel ViewModel { get; }

    /// <summary>The element UIA notifications are raised from (see <see cref="Services.UiaAnnouncer"/>).</summary>
    public FrameworkElement AnnouncerHost => StatusText;

    private void FocusScreenHeading()
    {
        switch (ViewModel.Screen)
        {
            case Screen.Start: StartScreen.FocusHeading(); break;
            case Screen.SourceKind: SourceKindScreen.FocusHeading(); break;
            case Screen.Transcribing: TranscriptionScreen.FocusHeading(); break;
            case Screen.Score: ScoreScreenView.FocusHeading(); break;
        }
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
        if (ViewModel.Screen == Screen.Score) await ScoreScreenView.ShowGoToBarAsync();
    }

    private void OnToggleTalkingScoreAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        if (ViewModel.Screen != Screen.Score) return;
        ViewModel.Score.ShowTalkingScore = !ViewModel.Score.ShowTalkingScore;
        ScoreScreenView.FocusScore();
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

    private async Task ShowExportAsync()
    {
        if (!ViewModel.OpenExportCommand.CanExecute(null)) return;
        ViewModel.OpenExportCommand.Execute(null);
        var dialog = new ExportDialog(ViewModel.Export) { XamlRoot = Content.XamlRoot };
        await dialog.ShowAsync();
        ExportButton.Focus(FocusState.Programmatic); // focus returns to the Export button
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
