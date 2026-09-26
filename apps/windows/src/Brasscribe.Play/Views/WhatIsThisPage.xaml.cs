using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Brasscribe.Play.Views;

/// <summary>"What is this?": four answers, nothing chosen until the player chooses (Continue waits for it).</summary>
public sealed partial class WhatIsThisPage : Page, IScreenPage
{
    public WhatIsThisPage() => InitializeComponent();

    public MainViewModel Main { get; private set; } = null!;
    public SourceKindViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        ViewModel = Main.Kind;
        Bindings.Update();
    }

    public void FocusHeading()
    {
        Options.SelectedIndex = ViewModel.Selected is { } s ? ViewModel.Options.IndexOf(s) : -1;
        Heading.Focus(FocusState.Programmatic);
    }

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs e) =>
        ViewModel.Selected = Options.SelectedItem as SourceKindOption;

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        if (Main.BackCommand.CanExecute(null)) Main.BackCommand.Execute(null);
    }
}
