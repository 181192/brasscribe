using Brasscribe.Play.Core.Engine;
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
        LanguageBox.SelectedIndex = viewModel.Language switch { "en-US" => 1, "nb-NO" => 2, _ => 0 };
        VerbosityBox.SelectedIndex = (int)viewModel.Verbosity;
        CoreVersion.Text = App.Strings.Format("Settings_CoreVersion", main.Core.IsNative ? main.Core.Version : App.Strings["Settings_CoreManaged"]);
    }

    public SettingsViewModel ViewModel { get; }

    private void OnLanguageChanged(object sender, SelectionChangedEventArgs e)
    {
        if (LanguageBox.SelectedItem is ComboBoxItem { Tag: string tag }) ViewModel.Language = tag;
    }

    private void OnVerbosityChanged(object sender, SelectionChangedEventArgs e) =>
        ViewModel.Verbosity = (Verbosity)Math.Max(0, VerbosityBox.SelectedIndex);

    private async void OnConnect(object sender, RoutedEventArgs e) => await ViewModel.ConnectCommand.ExecuteAsync(_main.Engine);

    private async void OnFindEngines(object sender, RoutedEventArgs e) => await ViewModel.FindEnginesCommand.ExecuteAsync(null);

    private void OnEngineClicked(object sender, ItemClickEventArgs e) => ViewModel.UseEngineCommand.Execute(e.ClickedItem as DiscoveredEngine);
}
