using Kalli.Scribe.Tab;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Navigation;

namespace Kalli.Fretscribe.Views;

/// <summary>Check the song: a row's button writes the song down again with its change; one with choices asks which first.</summary>
public sealed partial class CheckTheSongPage : Page, IScreenPage
{
    public CheckTheSongPage() => InitializeComponent();

    public SongCheckViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        ViewModel = ((TabFlowViewModel)e.Parameter).Check;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private void OnChange(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: SongCheckRow { Change: { } change } } button) return;
        if (change.Choices is not { } choices)
        {
            ViewModel.ChangeCommand.Execute(change);
            return;
        }
        // The choices in a menu, the one the tab has now checked; nothing is written down again until one is chosen.
        var menu = new MenuFlyout();
        foreach (var choice in choices)
        {
            var item = new ToggleMenuFlyoutItem { Text = choice.Label, IsChecked = choice.Value == change.Selected };
            item.Click += (_, _) => ViewModel.Choose(change, choice.Value);
            menu.Items.Add(item);
        }
        menu.ShowAt(button, new FlyoutShowOptions { Placement = FlyoutPlacementMode.Bottom });
    }
}
