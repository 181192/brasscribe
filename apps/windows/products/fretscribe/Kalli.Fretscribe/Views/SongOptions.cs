using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;

namespace Kalli.Fretscribe.Views;

/// <summary>The "more" menu on a row of Your songs (pane and Home): Edit title, Delete. Delete asks first.</summary>
internal static class SongOptions
{
    public static void Show(TabFlowViewModel main, LibraryItem item, FrameworkElement target, Windows.Foundation.Point? at = null)
    {
        var flyout = Build(main, item, target.XamlRoot);
        if (at is { } point) flyout.ShowAt(target, new FlyoutShowOptions { Position = point });
        else flyout.ShowAt(target, new FlyoutShowOptions { Placement = FlyoutPlacementMode.BottomEdgeAlignedRight });
    }

    private static MenuFlyout Build(TabFlowViewModel main, LibraryItem item, XamlRoot root)
    {
        var s = App.Strings;
        var edit = new MenuFlyoutItem { Text = s["SongOptions_EditTitle"], Icon = new FontIcon { Glyph = Glyph("FsIconTextSize") } };
        edit.Click += async (_, _) => await RenameAsync(main, item, root);
        var delete = new MenuFlyoutItem { Text = s["SongOptions_Delete"], Icon = new FontIcon { Glyph = Glyph("FsIconDelete") } };
        delete.Click += async (_, _) => await DeleteAsync(main, item, root);
        var flyout = new MenuFlyout();
        flyout.Items.Add(edit);
        flyout.Items.Add(new MenuFlyoutSeparator());
        flyout.Items.Add(delete);
        return flyout;
    }

    private static async Task RenameAsync(TabFlowViewModel main, LibraryItem item, XamlRoot root)
    {
        var s = App.Strings;
        var input = new TextBox { Text = item.Title, MaxLength = 160, Width = 360, Header = s["Song_EditTitle"] };
        input.SelectAll();
        var dialog = new ContentDialog
        {
            XamlRoot = root,
            RequestedTheme = Kalli.Scribe.Controls.ThemeController.ForDialogs,
            Title = s["Song_EditTitle"],
            Content = input,
            PrimaryButtonText = s["Song_SaveTitle"],
            CloseButtonText = s["Song_Cancel"],
            DefaultButton = ContentDialogButton.Primary,
        };
        input.TextChanged += (_, _) => dialog.IsPrimaryButtonEnabled = input.Text.Trim().Length > 0;
        if (await Kalli.Scribe.WinUI.DialogGate.ShowAsync(dialog) == ContentDialogResult.Primary) await main.RenameLibraryItemAsync(item, input.Text);
    }

    private static async Task DeleteAsync(TabFlowViewModel main, LibraryItem item, XamlRoot root)
    {
        var s = App.Strings;
        var dialog = new ContentDialog
        {
            XamlRoot = root,
            RequestedTheme = Kalli.Scribe.Controls.ThemeController.ForDialogs,
            Title = s.Format("SongOptions_DeleteTitle", item.Title),
            Content = s[item.OnComputer ? "SongOptions_DeleteComputer" : item.Id.StartsWith("kept:", StringComparison.Ordinal) ? "SongOptions_DeleteKept" : "SongOptions_DeleteThisPc"],
            PrimaryButtonText = s["SongOptions_Delete"],
            CloseButtonText = s["Song_Cancel"],
            DefaultButton = ContentDialogButton.Close,
        };
        if (await Kalli.Scribe.WinUI.DialogGate.ShowAsync(dialog) == ContentDialogResult.Primary) await main.DeleteLibraryItemAsync(item);
    }

    private static string Glyph(string key) => (string)Application.Current.Resources[key];
}
