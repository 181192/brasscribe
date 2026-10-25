using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Kalli.Fretscribe.Dialogs;

/// <summary>Settings: Your instrument, language, appearance, Bandroom on the computer, and about.</summary>
public sealed partial class SettingsDialog : ContentDialog
{
    private readonly TabFlowViewModel _flow;

    public SettingsDialog(SettingsViewModel viewModel, TabFlowViewModel flow)
    {
        ViewModel = viewModel;
        _flow = flow;
        InitializeComponent();
        ConnectionStatus.Show(viewModel.Connection);
        LanguageBox.SelectedIndex = viewModel.Language switch { "en-US" => 1, "nb-NO" => 2, _ => 0 };
        AppearanceBox.SelectedIndex = Math.Min((int)viewModel.Appearance, AppearanceBox.Items.Count - 1);
        AppVersion.Text = App.Strings.Format("Settings_AppVersion", AppVersionText());
        InstrumentValue.Text = flow.InstrumentSummary;
    }

    public SettingsViewModel ViewModel { get; }

    /// <summary>Change on the Your instrument row: the window closes this dialog and opens Your instrument.</summary>
    public event EventHandler? InstrumentRequested;

    private void OnChangeInstrument(object sender, RoutedEventArgs e) => InstrumentRequested?.Invoke(this, EventArgs.Empty);

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

    /// <summary>Applies at once: the app's theme controller re-themes every window and this dialog; focus stays here.</summary>
    private void OnAppearanceChanged(object sender, SelectionChangedEventArgs e)
    {
        if (AppearanceBox.SelectedIndex >= 0) ViewModel.Appearance = (Appearance)AppearanceBox.SelectedIndex;
    }

    private async void OnConnect(object sender, RoutedEventArgs e) => await ViewModel.ConnectCommand.ExecuteAsync(_flow.Engine);

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
