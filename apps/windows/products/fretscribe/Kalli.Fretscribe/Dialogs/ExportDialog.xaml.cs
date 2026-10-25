using Kalli.Scribe.Tab;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Kalli.Fretscribe.Dialogs;

/// <summary>Share or print the tab on screen; Print is the dialog's primary button while a PDF can be had.</summary>
public sealed partial class ExportDialog : ContentDialog
{
    public ExportDialog(TabExportViewModel viewModel)
    {
        ViewModel = viewModel;
        InitializeComponent();
        IsPrimaryButtonEnabled = viewModel.CanPrint;
        PrimaryButtonClick += async (_, args) =>
        {
            // Printing opens the PDF app's own dialog; this one stays open for another format.
            args.Cancel = true;
            await ViewModel.PrintCommand.ExecuteAsync(null);
        };
    }

    public TabExportViewModel ViewModel { get; }

    private async void OnSave(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: TabExportOption option }) await ViewModel.SaveCommand.ExecuteAsync(option);
    }
}
