using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Brasscribe.Play.Views;

/// <summary>"What do you play?" after Get started (docs/plan/my-instrument.md §3.1).</summary>
public sealed partial class WhatDoYouPlayPage : Page, IScreenPage
{
    public WhatDoYouPlayPage() => InitializeComponent();

    public MainViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        ViewModel = (MainViewModel)e.Parameter;
        if (ViewModel.FirstRunSeat is { } picker) Picker.Show(picker);
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);
}
