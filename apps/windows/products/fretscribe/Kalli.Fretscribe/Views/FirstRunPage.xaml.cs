using Kalli.Scribe.Tab;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Kalli.Fretscribe.Views;

/// <summary>First run: what Fretscribe does, where it does it, and that the notes it is not sure of are marked.</summary>
public sealed partial class FirstRunPage : Page, IScreenPage
{
    public FirstRunPage()
    {
        InitializeComponent();
        ActualThemeChanged += (_, _) => Brand.ShowMark(Mark, this);
        Brand.ShowMark(Mark, this);
    }

    public TabFlowViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        ViewModel = (TabFlowViewModel)e.Parameter;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);
}
