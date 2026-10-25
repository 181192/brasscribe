using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace Kalli.Fretscribe.Views;

/// <summary>Home: record (the one primary), open a recording or record what's playing, and your songs.</summary>
public sealed partial class HomePage : Page, IScreenPage
{
    public HomePage()
    {
        InitializeComponent();
        ActualThemeChanged += (_, _) => Brand.ShowMark(EmptyMark, this);
        Brand.ShowMark(EmptyMark, this);
    }

    public TabFlowViewModel Main { get; private set; } = null!;
    public StartViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (TabFlowViewModel)e.Parameter;
        ViewModel = Main.Start;
        Bindings.Update();
        ConnectionStatus.Show(Main.Settings.Connection);
        _ = Main.LibraryView.RefreshComputerAsync();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    /// <summary>Connect or Pair again: Settings, where the computer is chosen and paired.</summary>
    private async void OnConnectionAction(object? sender, EventArgs e)
    {
        if (App.MainWindowInstance is { } window) await window.OpenSettingsAsync();
    }

    private void OnSongCardOptions(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: LibraryItem item } button) SongOptions.Show(Main, item, button);
    }

    private void OnSongCardContextRequested(UIElement sender, Microsoft.UI.Xaml.Input.ContextRequestedEventArgs args)
    {
        if (sender is not FrameworkElement { DataContext: LibraryItem item } element) return;
        args.Handled = true;
        SongOptions.Show(Main, item, element, args.TryGetPosition(element, out var point) ? point : null);
    }

    private void OnSongCardClick(object sender, ItemClickEventArgs e)
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
