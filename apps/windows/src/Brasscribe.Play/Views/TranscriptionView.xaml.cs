using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Views;

public sealed partial class TranscriptionView : UserControl
{
    public TranscriptionView() => InitializeComponent();

    public TranscriptionViewModel ViewModel
    {
        get => (TranscriptionViewModel)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty =
        DependencyProperty.Register(nameof(ViewModel), typeof(TranscriptionViewModel), typeof(TranscriptionView), new PropertyMetadata(null));

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    /// <summary>Cancel asks first: Esc (Close) keeps going and returns focus to Cancel; "Stop" stops.</summary>
    private async void OnCancelClick(object sender, RoutedEventArgs e)
    {
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
        else CancelButton.Focus(FocusState.Programmatic);
    }
}
