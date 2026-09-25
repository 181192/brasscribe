using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Dialogs;

public sealed partial class ExportDialog : ContentDialog
{
    public ExportDialog(ExportViewModel viewModel)
    {
        ViewModel = viewModel;
        InitializeComponent();
        FormatList.SelectedItem = viewModel.SelectedFormat;
        PartBox.SelectedItem = viewModel.SelectedPart;
        IsPrimaryButtonEnabled = viewModel.SelectedFormat is { Available: true };
    }

    public ExportViewModel ViewModel { get; }

    private void OnFormatChanged(object sender, SelectionChangedEventArgs e)
    {
        ViewModel.SelectedFormat = FormatList.SelectedItem as ExportChoice;
        IsPrimaryButtonEnabled = ViewModel.SelectedFormat is { Available: true };
    }

    private void OnPartChanged(object sender, SelectionChangedEventArgs e) =>
        ViewModel.SelectedPart = PartBox.SelectedItem as ScorePartItem;

    private async void OnExport(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        var deferral = args.GetDeferral();
        args.Cancel = true; // stay open to show the result; the user closes with Esc or Close
        await ViewModel.ExportCommand.ExecuteAsync(null);
        deferral.Complete();
    }
}
