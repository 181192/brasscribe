using System.Runtime.InteropServices.WindowsRuntime;
using Brasscribe.Play.Controls;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Review;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Navigation;
using Windows.Storage.Streams;

namespace Brasscribe.Play.Views;

/// <summary>
/// "Check the notes": the list of notes Brasscribe wasn't sure about in the sidebar, one note at a
/// time on the right with its bars drawn (the same "?" marks as the score), Listen, Skip and the
/// primary Keep. "Finish later (N left)" asks first.
/// </summary>
public sealed partial class ReviewPage : Page, IScreenPage
{
    private readonly CollectionViewSource _groups = new() { IsSourceGrouped = true, ItemsPath = new PropertyPath("Items") };
    private bool _syncing;

    public ReviewPage() => InitializeComponent();

    public MainViewModel Main { get; private set; } = null!;
    public ReviewViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        Main = (MainViewModel)e.Parameter;
        if (ViewModel is not null) ViewModel.CurrentChanged -= OnCurrentChanged;
        ViewModel = Main.Review;
        ViewModel.CurrentChanged += OnCurrentChanged;
        _groups.Source = ViewModel.Groups;
        NoteList.ItemsSource = _groups.View;
        Bindings.Update();
        if (ViewModel.Current is { } current) OnCurrentChanged(this, current);
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private void OnNoteSelected(object sender, SelectionChangedEventArgs e)
    {
        if (_syncing || NoteList.SelectedItem is not ReviewItem item || ReferenceEquals(item, ViewModel.Current)) return;
        ViewModel.Select(item);
    }

    private async void OnCurrentChanged(object? sender, ReviewItem item)
    {
        _syncing = true;
        NoteList.SelectedItem = item;
        NoteList.ScrollIntoView(item);
        _syncing = false;
        await DrawSnippetAsync(item);
    }

    /// <summary>Two bars of the note's part, drawn off the UI thread with the design overlays.</summary>
    private async Task DrawSnippetAsync(ReviewItem item)
    {
        if (Main.Score.Player.Player is not AlphaTabScorePlayer player || player.Score is null || Main.Score.Document is not { } doc) return;
        var palette = ScoreView.IsHighContrast() ? UncertaintyPalette.HighContrast
            : UncertaintyPalette.For(ActualTheme == ElementTheme.Dark ? ThemeKind.Dark : ThemeKind.Light);
        bool contrast = ScoreView.IsHighContrast();
        try
        {
            var png = await ScoreRendering.Renderer.SnippetAsync(player.Score, item.Part, item.BarIndex + 1, 2, 1.3, palette,
                output => ScoreOverlay.Build(new(ScoreGeometry.UncertainHeads(player.Score, output.Bounds!, doc, [item.Part]), [], null, [], null, null, contrast)),
                s => ScoreStyler.ApplyUncertainty(s, doc, palette));
            if (!ReferenceEquals(item, ViewModel.Current)) return;
            var bitmap = new BitmapImage();
            using var stream = new InMemoryRandomAccessStream();
            await stream.WriteAsync(png.AsBuffer());
            stream.Seek(0);
            await bitmap.SetSourceAsync(stream);
            Snippet.Source = bitmap;
        }
        catch (InvalidOperationException)
        {
            Snippet.Source = null; // the notation could not be drawn; the words above still say everything
        }
    }

    /// <summary>"Finish checking later? 9 notes keep their ? marks. You can check them any time from the score."</summary>
    private async void OnFinishLater(object sender, RoutedEventArgs e)
    {
        ViewModel.FinishLaterCommand.Execute(null);
        if (!ViewModel.IsConfirmingFinish) return;
        var strings = App.Strings;
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = strings["FinishLater_Title"],
            Content = ViewModel.ConfirmText,
            PrimaryButtonText = strings["FinishLater_Confirm"],
            CloseButtonText = strings["FinishLater_Keep"],
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary) ViewModel.ConfirmFinishCommand.Execute(null);
        else
        {
            ViewModel.CancelFinishCommand.Execute(null);
            FinishLaterButton.Focus(FocusState.Programmatic);
        }
    }

    private void OnKeepKey(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (FocusManager.GetFocusedElement(XamlRoot) is TextBox) return;
        args.Handled = true;
        ViewModel.KeepCommand.Execute(null);
    }

    private void OnListenKey(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (FocusManager.GetFocusedElement(XamlRoot) is TextBox or ButtonBase) return;
        args.Handled = true;
        ViewModel.ListenCommand.Execute(null);
    }
}
