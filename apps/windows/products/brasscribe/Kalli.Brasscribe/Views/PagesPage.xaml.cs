using Kalli.Scribe.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace Kalli.Brasscribe.Views;

/// <summary>Sheet music from a picture: the pages in order, each moved or removed, and Read the notes.</summary>
public sealed partial class PagesPage : Page, IScreenPage
{
    public PagesPage() => InitializeComponent();

    public MainViewModel Main { get; private set; } = null!;
    public PagesViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        ViewModel = Main.Pages!;
        Bindings.Update();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private void OnMoveUp(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: PageItem page }) ViewModel.MoveUpCommand.Execute(page);
    }

    private void OnMoveDown(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: PageItem page }) ViewModel.MoveDownCommand.Execute(page);
    }

    private void OnRemove(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: PageItem page }) ViewModel.RemoveCommand.Execute(page);
    }

    private void OnDragOver(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems)) e.AcceptedOperation = DataPackageOperation.Copy;
    }

    /// <summary>Pictures or PDFs dropped here are added after the pages in hand, in the order given.</summary>
    private async void OnDrop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems)) return;
        var items = await e.DataView.GetStorageItemsAsync();
        ViewModel.Add(items.OfType<StorageFile>().Select(f => f.Path).ToList());
    }
}
