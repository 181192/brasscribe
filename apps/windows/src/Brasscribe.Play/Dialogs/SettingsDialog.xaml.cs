using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Dialogs;

public sealed partial class SettingsDialog : ContentDialog
{
    private readonly MainViewModel _main;

    public SettingsDialog(SettingsViewModel viewModel, MainViewModel main)
    {
        ViewModel = viewModel;
        _main = main;
        InitializeComponent();
        ConnectionStatus.Show(viewModel.Connection);
        LanguageBox.SelectedIndex = viewModel.Language switch { "en-US" => 1, "nb-NO" => 2, _ => 0 };
        VerbosityBox.SelectedIndex = (int)viewModel.Verbosity;
        if (viewModel.PinkUnlocked) AddPinkChoices();
        AppearanceBox.SelectedIndex = (int)viewModel.Appearance;
        AppVersion.Content = App.Strings.Format("Settings_AppVersion", AppVersionText());
        viewModel.PinkUnlockedNow += OnPinkUnlocked;
        Closed += (_, _) => viewModel.PinkUnlockedNow -= OnPinkUnlocked;
        ShowSeat();
        // Without the core's seats there is nothing to choose from.
        SeatChangeButton.IsEnabled = main.Seats.IsAvailable;
        CoreVersion.Text = App.Strings.Format("Settings_CoreVersion", main.Core.IsNative ? main.Core.Version : App.Strings["Settings_CoreManaged"]);
    }

    public SettingsViewModel ViewModel { get; }

    private Brasscribe.Play.Core.Seats.SeatPickerViewModel? _seatPicker;

    private void ShowSeat() => SeatValue.Text = _main.Seats.Describe(ViewModel.SeatChoice);

    /// <summary>Change: the first run's questions, from the current answer.</summary>
    private void OnChangeSeat(object sender, RoutedEventArgs e)
    {
        _seatPicker = _main.NewSeatPicker();
        SeatPicker.Show(_seatPicker);
        SeatHint.Text = "";
        SeatEditor.Visibility = Visibility.Visible;
        SeatRow.Visibility = Visibility.Collapsed;
        DispatcherQueue.TryEnqueue(SeatPicker.FocusFirst);
    }

    private void OnSaveSeat(object sender, RoutedEventArgs e)
    {
        if (_seatPicker?.Choice is not { } choice)
        {
            SeatHint.Text = _seatPicker?.ContinueHint ?? "";
            return;
        }
        CloseSeat(choice);
    }

    private void OnConductSeat(object sender, RoutedEventArgs e) => CloseSeat(Brasscribe.Play.Core.Seats.SeatChoice.Conductor);

    private void OnCancelSeat(object sender, RoutedEventArgs e) => CloseSeat(null);

    /// <summary>Saves (or not) and puts focus back on the What you play row (design/system.md: focus returns where it came from).</summary>
    private void CloseSeat(Brasscribe.Play.Core.Seats.SeatChoice? choice)
    {
        // Existing scores keep their arrangement; only "your part" in them follows the new answer.
        if (choice is not null) ViewModel.SeatChoice = choice;
        _seatPicker = null;
        SeatEditor.Visibility = Visibility.Collapsed;
        SeatRow.Visibility = Visibility.Visible;
        ShowSeat();
        DispatcherQueue.TryEnqueue(() => SeatChangeButton.Focus(FocusState.Programmatic));
    }

    private void OnLanguageChanged(object sender, SelectionChangedEventArgs e)
    {
        if (LanguageBox.SelectedItem is ComboBoxItem { Tag: string tag }) ViewModel.Language = tag;
    }

    /// <summary>The app's version: the package's when installed, else the assembly's.</summary>
    private static string AppVersionText()
    {
        try
        {
            var v = Windows.ApplicationModel.Package.Current.Id.Version;
            return $"{v.Major}.{v.Minor}.{v.Build}";
        }
        catch (InvalidOperationException)
        {
            return typeof(SettingsDialog).Assembly.GetName().Version is { } a ? $"{a.Major}.{a.Minor}.{a.Build}" : "";
        }
    }

    private void OnVersion(object sender, RoutedEventArgs e) => ViewModel.ActivateVersion();

    /// <summary>Pink light and Pink dark go last in Appearance (nothing switches), and a small note says so for a few seconds.</summary>
    private void OnPinkUnlocked(object? sender, EventArgs e)
    {
        AddPinkChoices();
        PinkNote.Text = App.Strings["Pink_Unlocked"];
        PinkNote.Visibility = Visibility.Visible;
        var timer = DispatcherQueue.CreateTimer();
        timer.Interval = TimeSpan.FromSeconds(4);
        timer.IsRepeating = false;
        timer.Tick += (_, _) => PinkNote.Visibility = Visibility.Collapsed;
        timer.Start();
    }

    /// <summary>The items follow the enum's order, so an item's index is its <see cref="Appearance"/>.</summary>
    private void AddPinkChoices()
    {
        if (AppearanceBox.Items.Count > (int)Appearance.PinkLight) return;
        AppearanceBox.Items.Add(new ComboBoxItem { Content = App.Strings["Appearance_PinkLight"] });
        AppearanceBox.Items.Add(new ComboBoxItem { Content = App.Strings["Appearance_PinkDark"] });
    }

    /// <summary>Applies at once: the app's theme controller re-themes every window and this dialog; focus stays here.</summary>
    private void OnAppearanceChanged(object sender, SelectionChangedEventArgs e)
    {
        if (AppearanceBox.SelectedIndex >= 0) ViewModel.Appearance = (Appearance)AppearanceBox.SelectedIndex;
    }

    private void OnVerbosityChanged(object sender, SelectionChangedEventArgs e) =>
        ViewModel.Verbosity = (Verbosity)Math.Max(0, VerbosityBox.SelectedIndex);

    private async void OnConnect(object sender, RoutedEventArgs e) => await ViewModel.ConnectCommand.ExecuteAsync(_main.Engine);

    private async void OnFindEngines(object sender, RoutedEventArgs e) => await ViewModel.FindEnginesCommand.ExecuteAsync(null);

    private void OnEngineClicked(object sender, ItemClickEventArgs e) => ViewModel.UseEngineCommand.Execute(e.ClickedItem as DiscoveredEngine);

    private async void OnAskComputer(object sender, RoutedEventArgs e) => await ViewModel.AskComputerCommand.ExecuteAsync(null);

    private void OnCancelAsk(object sender, RoutedEventArgs e) => ViewModel.CancelAsk();

    private async void OnUnpair(object sender, RoutedEventArgs e) => await ViewModel.UnpairCommand.ExecuteAsync(null);

    /// <summary>Connect checks again at once; Pair again goes to the code box (or Allow on the computer next to it).</summary>
    private void OnConnectionAction(object? sender, EventArgs e)
    {
        if (ViewModel.Connection.State == ConnectionState.NeedsPairing) PairingCodeBox.Focus(FocusState.Programmatic);
        else
        {
            ViewModel.Connection.Kick();
            ViewModel.Connection.Start();
        }
    }
}
