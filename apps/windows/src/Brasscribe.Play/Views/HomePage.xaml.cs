using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace Brasscribe.Play.Views;

/// <summary>Home: open a recording (the one primary), the other ways in as cards, and your scores.</summary>
public sealed partial class HomePage : Page, IScreenPage
{
    public HomePage() => InitializeComponent();

    public MainViewModel Main { get; private set; } = null!;
    public StartViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        ViewModel = Main.Start;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private async void OnAppFlyoutOpened(object sender, object e)
    {
        if (ViewModel.Apps.Count == 0) await ViewModel.RefreshAppsCommand.ExecuteAsync(null);
    }

    private void OnAppSelected(object sender, SelectionChangedEventArgs e) =>
        ViewModel.SelectedApp = AppPicker.SelectedItem as AudioApp;

    private void OnScoreCardClick(object sender, ItemClickEventArgs e)
    {
        if (e.ClickedItem is LibraryItem item) Main.OpenLibraryItemCommand.Execute(item);
    }

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
