using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Brasscribe.Play.Views;

/// <summary>
/// "How should the score be?": Which band? (full brass band, small band or quartet), How hard? (as played,
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
        Select(ViewModel.Lineup);
        (ViewModel.Difficulty switch { Difficulty.Easier => EasierChoice, Difficulty.Standard => StandardChoice, _ => FaithfulChoice }).IsChecked = true;
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private static int IndexOf(Lineup lineup) => lineup switch
    {
        Lineup.FullBand => 0,
        Lineup.MinimalBand => 1,
        Lineup.Quartet => 2,
        _ => throw new ArgumentOutOfRangeException(nameof(lineup), lineup, null),
    };

    private static Lineup? LineupAt(int index) => index switch
    {
        0 => Lineup.FullBand,
        1 => Lineup.MinimalBand,
        2 => Lineup.Quartet,
        _ => null,
    };

    private bool _selecting;

    /// <summary>Shows a lineup as chosen without treating it as the player's choice.</summary>
    private void Select(Lineup lineup)
    {
        _selecting = true;
        try { LineupChoices.SelectedIndex = IndexOf(lineup); }
        finally { _selecting = false; }
    }

    private void OnLineupChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_selecting || ViewModel is null || LineupAt(LineupChoices.SelectedIndex) is not { } chosen) return;
        // The quartet on a solo take, and the full band on a band take, are refused (and the reason said); the selection goes back.
        if (!ViewModel.TryChooseLineup(chosen)) Select(ViewModel.Lineup);
    }

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
