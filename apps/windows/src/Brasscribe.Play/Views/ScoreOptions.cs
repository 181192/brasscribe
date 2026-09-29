using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;

namespace Brasscribe.Play.Views;

/// <summary>
/// The "more" menu on a row of "Your scores" (sidebar and Home): Edit title, Check the notes, Open on
/// the music stand, Delete. Delete asks first.
/// </summary>
internal static class ScoreOptions
{
    public static void Show(MainViewModel main, LibraryItem item, FrameworkElement target, Windows.Foundation.Point? at = null)
    {
        var flyout = Build(main, item, target.XamlRoot);
        if (at is { } point) flyout.ShowAt(target, new FlyoutShowOptions { Position = point });
        else flyout.ShowAt(target, new FlyoutShowOptions { Placement = FlyoutPlacementMode.BottomEdgeAlignedRight });
    }

    private static MenuFlyout Build(MainViewModel main, LibraryItem item, XamlRoot root)
    {
        var s = App.Strings;
        var edit = new MenuFlyoutItem { Text = s["ScoreOptions_EditTitle"], Icon = new FontIcon { Glyph = Glyph("BcIconTextSize") } };
        edit.Click += async (_, _) => await RenameAsync(main, item, root);
        var check = new MenuFlyoutItem
        {
            Text = s["ScoreOptions_CheckNotes"],
            Icon = new PathIcon { Data = (Geometry)XamlBindingHelper.ConvertValue(typeof(Geometry), Glyph("BcIconPathNextUncertain")) },
        };
        check.Click += async (_, _) => await main.OpenLibraryItemAsync(item, review: true);
        var stand = new MenuFlyoutItem { Text = s["ScoreOptions_OpenOnStand"], Icon = new FontIcon { Glyph = Glyph("BcIconMusicStand") } };
        stand.Click += async (_, _) => await main.OpenOnMusicStandAsync(item);
        var delete = new MenuFlyoutItem { Text = s["ScoreOptions_Delete"], Icon = new FontIcon { Glyph = Glyph("BcIconDelete") } };
        delete.Click += async (_, _) => await DeleteAsync(main, item, root);
        var flyout = new MenuFlyout();
        flyout.Items.Add(edit);
        flyout.Items.Add(check);
        flyout.Items.Add(stand);
        flyout.Items.Add(new MenuFlyoutSeparator());
        flyout.Items.Add(delete);
        return flyout;
    }

    private static async Task RenameAsync(MainViewModel main, LibraryItem item, XamlRoot root)
    {
        var s = App.Strings;
        var input = new TextBox { Text = item.Title, MaxLength = 160, Width = 360, Header = s["Score_EditTitle"] };
        input.SelectAll();
        var dialog = new ContentDialog
        {
            XamlRoot = root,
            Title = s["Score_EditTitle"],
            Content = input,
            PrimaryButtonText = s["Score_SaveTitle"],
            CloseButtonText = s["Score_CancelTitle"],
            DefaultButton = ContentDialogButton.Primary,
        };
        input.TextChanged += (_, _) => dialog.IsPrimaryButtonEnabled = input.Text.Trim().Length > 0;
        if (await dialog.ShowAsync() == ContentDialogResult.Primary) await main.RenameLibraryItemAsync(item, input.Text);
    }

    private static async Task DeleteAsync(MainViewModel main, LibraryItem item, XamlRoot root)
    {
        var s = App.Strings;
        var dialog = new ContentDialog
        {
            XamlRoot = root,
            Title = s.Format("ScoreOptions_DeleteTitle", item.Title),
            Content = s[item.OnComputer ? "ScoreOptions_DeleteComputer" : "ScoreOptions_DeleteThisPc"],
            PrimaryButtonText = s["ScoreOptions_Delete"],
            CloseButtonText = s["Score_CancelTitle"],
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary) await main.DeleteLibraryItemAsync(item);
    }

    private static string Glyph(string key) => (string)Application.Current.Resources[key];
}
