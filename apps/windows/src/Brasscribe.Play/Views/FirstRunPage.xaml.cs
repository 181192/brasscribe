using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Brasscribe.Play.Views;

public sealed partial class FirstRunPage : Page, IScreenPage
{
    public FirstRunPage() => InitializeComponent();

    public MainViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        ViewModel = (MainViewModel)e.Parameter;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);
}
