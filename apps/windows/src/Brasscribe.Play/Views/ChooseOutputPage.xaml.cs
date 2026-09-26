using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Brasscribe.Play.Views;

/// <summary>
/// "How should the score be?": Which band? (full brass band or small band), How hard? (as played,
/// a bit easier, easier) and the key. "Show the score" arranges again only when a choice changed.
/// </summary>
public sealed partial class ChooseOutputPage : Page, IScreenPage
{
    public ChooseOutputPage() => InitializeComponent();

    public MainViewModel Main { get; private set; } = null!;
    public OutputOptionsViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        ViewModel = Main.Output;
        Bindings.Update();
        LineupChoices.SelectedIndex = ViewModel.Lineup == Lineup.MinimalBand ? 1 : 0;
        (ViewModel.Difficulty switch { Difficulty.Easier => EasierChoice, Difficulty.Standard => StandardChoice, _ => FaithfulChoice }).IsChecked = true;
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private void OnLineupChanged(object sender, SelectionChangedEventArgs e) =>
        ViewModel.Lineup = LineupChoices.SelectedIndex == 1 ? Lineup.MinimalBand : Lineup.FullBand;

    private void OnDifficultyChecked(object sender, RoutedEventArgs e)
    {
        if (sender is RadioButton { Tag: string tag } && int.TryParse(tag, out int d)) ViewModel.Difficulty = (Difficulty)d;
    }

    private async void OnShowScore(object sender, RoutedEventArgs e) => await ViewModel.ShowScoreCommand.ExecuteAsync(Main.Score.Composition);

    private void OnBack(object sender, RoutedEventArgs e)
    {
        if (Main.BackCommand.CanExecute(null)) Main.BackCommand.Execute(null);
    }
}
