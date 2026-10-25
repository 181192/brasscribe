using Kalli.Scribe.Tab;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Kalli.Fretscribe.Views;

/// <summary>"What is this?": the instrument alone or a full song; Continue waits for an answer and for the computer.</summary>
public sealed partial class WhatIsThisPage : Page, IScreenPage
{
    public WhatIsThisPage() => InitializeComponent();

    public TabFlowViewModel Main { get; private set; } = null!;
    public WhatIsThisViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (TabFlowViewModel)e.Parameter;
        ViewModel = Main.WhatIsThis;
        Bindings.Update();
        ConnectionStatus.Show(Main.Settings.Connection);
        SourceLine.Text = ViewModel.Source is { } s ? $"{s.DisplayName} · {Main.Start.DurationText(s.Duration)}" : "";
    }

    public void FocusHeading()
    {
        Options.SelectedIndex = ViewModel.Choices.ToList().FindIndex(c => c.IsSelected);
        Heading.Focus(FocusState.Programmatic);
    }

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (Options.SelectedItem is RecordingChoice choice && !choice.IsSelected) ViewModel.ChooseCommand.Execute(choice);
    }

    private async void OnConnectionAction(object? sender, EventArgs e)
    {
        if (App.MainWindowInstance is { } window) await window.OpenSettingsAsync();
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        if (Main.BackCommand.CanExecute(null)) Main.BackCommand.Execute(null);
    }
}
