using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Kalli.Fretscribe.Views;

public sealed partial class ErrorPage : Page, IScreenPage
{
    public ErrorPage() => InitializeComponent();

    public ErrorViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        ViewModel = ((TabFlowViewModel)e.Parameter).Error;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);
}
