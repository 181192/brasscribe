using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace Brasscribe.Play.Views;

public sealed partial class StartView : UserControl
{
    public StartView() => InitializeComponent();

    public StartViewModel ViewModel
    {
        get => (StartViewModel)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty =
        DependencyProperty.Register(nameof(ViewModel), typeof(StartViewModel), typeof(StartView),
            new PropertyMetadata(null, (d, _) => ((StartView)d).Bindings.Update()));

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private async void OnAppPickerOpened(object sender, object e)
    {
        if (ViewModel.Apps.Count == 0) await ViewModel.RefreshAppsCommand.ExecuteAsync(null);
    }

    private void OnAppSelected(object sender, SelectionChangedEventArgs e) =>
        ViewModel.SelectedApp = AppPicker.SelectedItem as AudioApp;

    private void OnDragOver(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems)) e.AcceptedOperation = DataPackageOperation.Copy;
    }

    private async void OnDrop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems)) return;
        var items = await e.DataView.GetStorageItemsAsync();
        if (items.FirstOrDefault() is StorageFile file) await ViewModel.OpenPathAsync(file.Path);
    }
}
