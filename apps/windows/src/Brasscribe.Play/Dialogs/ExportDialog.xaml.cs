using System.ComponentModel;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Dialogs;

/// <summary>"Share or print": what (your part, every part, the conductor's score), as (PDF by default), then Print or Save.</summary>
public sealed partial class ExportDialog : ContentDialog
{
    public ExportDialog(ExportViewModel viewModel)
    {
        ViewModel = viewModel;
        InitializeComponent();
        MyPartChoice.IsChecked = viewModel.Scope == ExportScope.MyPart;
        EveryPartChoice.IsChecked = viewModel.Scope == ExportScope.EveryPart;
        ConductorChoice.IsChecked = viewModel.Scope == ExportScope.Conductor;
        viewModel.PropertyChanged += OnViewModelChanged;
        Closed += (_, _) => viewModel.PropertyChanged -= OnViewModelChanged;
        UpdateButtons();
    }

    public ExportViewModel ViewModel { get; }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(ExportViewModel.SaveLabel) or nameof(ExportViewModel.FileCount) or nameof(ExportViewModel.IsExporting)
            or nameof(ExportViewModel.CanPrintNow))
            UpdateButtons();
    }

    private void UpdateButtons()
    {
        SecondaryButtonText = ViewModel.SaveLabel;
        IsSecondaryButtonEnabled = ViewModel.SaveCommand.CanExecute(null);
        IsPrimaryButtonEnabled = ViewModel.PrintCommand.CanExecute(null);
    }

    private void OnScopeChecked(object sender, RoutedEventArgs e)
    {
        if (sender is RadioButton { Tag: string tag } && int.TryParse(tag, out int scope)) ViewModel.Scope = (ExportScope)scope;
    }

    private async void OnPrint(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        var deferral = args.GetDeferral();
        args.Cancel = true; // stay open to show the result; the player closes with Esc or Cancel
        await ViewModel.PrintCommand.ExecuteAsync(null);
        deferral.Complete();
    }

    private async void OnSave(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        var deferral = args.GetDeferral();
        args.Cancel = true;
        await ViewModel.SaveCommand.ExecuteAsync(null);
        deferral.Complete();
    }
}
