using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Brasscribe.Play.Views;

/// <summary>Making the score: the plain-language steps, percentage, time left and Cancel (which asks first).</summary>
public sealed partial class TranscribingPage : Page, IScreenPage
{
    public TranscribingPage() => InitializeComponent();

    public MainViewModel Main { get; private set; } = null!;
    public TranscriptionViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        ViewModel = Main.Transcription;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    /// <summary>"Stop making this score? The recording stays in Your scores." Esc keeps going and returns focus to Cancel.</summary>
    private async void OnCancelClick(object sender, RoutedEventArgs e)
    {
        ViewModel.AskCancelCommand.Execute(null);
        var strings = App.Strings;
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = strings["CancelDialog_Title"],
            Content = strings["CancelDialog_Content"],
            PrimaryButtonText = strings["CancelDialog_Stop"],
            CloseButtonText = strings["CancelDialog_Keep"],
            DefaultButton = ContentDialogButton.Close,
        };
        var result = await dialog.ShowAsync();
        if (result == ContentDialogResult.Primary) await ViewModel.CancelCommand.ExecuteAsync(null);
        else
        {
            ViewModel.KeepGoingCommand.Execute(null);
            CancelButton.Focus(FocusState.Programmatic);
        }
    }
}
