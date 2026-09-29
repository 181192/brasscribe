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
        ViewModel.PropertyChanged -= OnViewModelChanged;
        ViewModel.PropertyChanged += OnViewModelChanged;
        Bindings.Update();
        SyncScope();
        if (ViewModel.Current is { } current) OnCurrentChanged(this, current);
    }

    private bool _scopeSync;

    private void OnViewModelChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(ReviewViewModel.Scope)) SyncScope();
    }

    private void SyncScope()
    {
        _scopeSync = true;
        MyPartScope.IsChecked = ViewModel.Scope == ReviewScope.MyPart;
        AllPartsScope.IsChecked = ViewModel.Scope == ReviewScope.AllParts;
        _scopeSync = false;
    }

    private void OnScopeChecked(object sender, RoutedEventArgs e)
    {
        if (_scopeSync) return;
        ViewModel.Scope = ReferenceEquals(sender, AllPartsScope) ? ReviewScope.AllParts : ReviewScope.MyPart;
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
            var png = await ScoreRendering.Renderer.SnippetAsync(player.Score, item.Part, item.BarIndex + 1, Math.Clamp(item.EndBarIndex - item.BarIndex + 1, 2, 4), 1.3, palette,
                output => ScoreOverlay.Build(new(ScoreGeometry.UncertainHeads(player.Score, output.Bounds!, doc, [item.Part]), [], null, [], null, null, contrast)
                    {
                        Groups = ScoreGeometry.GroupBrackets(player.Score, output.Bounds!, doc, [item.Part]),
                        Selection = ScoreGeometry.FocusBox(player.Score, output.Bounds!, item.Part, item.BarIndex, item.Event.Tick) is { } note
                                    && ScoreGeometry.BarBox(output.Bounds!, item.BarIndex, item.Part) is { } bar ? (note, bar) : null,
                    }),
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
            RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs,
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

    /// <summary>
    /// "Change note…": the note moved by semitones or to what a transcriber heard; Save writes the score
    /// and stays on the note, which stays open until Keep (the same on every platform).
    /// </summary>
    private async void OnChangeNote(object sender, RoutedEventArgs e)
    {
        if (ViewModel.Current is null) return;
        var strings = App.Strings;
        int shift = 0;
        var name = new TextBlock { Style = (Style)Application.Current.Resources["BcTitle1TextBlockStyle"], HorizontalAlignment = HorizontalAlignment.Center };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetLiveSetting(name, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        var choices = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        ContentDialog? dialog = null;
        void Update()
        {
            name.Text = ViewModel.ChangeLabel(shift);
            if (dialog is not null) dialog.IsPrimaryButtonEnabled = shift != 0;
            foreach (var child in choices.Children.OfType<ToggleButton>()) child.IsChecked = (int)child.Tag == shift;
        }
        var down = new Button { Content = strings["ChangeNote_Down"], Style = (Style)Application.Current.Resources["SecondaryButtonStyle"] };
        var up = new Button { Content = strings["ChangeNote_Up"], Style = (Style)Application.Current.Resources["SecondaryButtonStyle"] };
        down.Click += (_, _) => { shift--; Update(); };
        up.Click += (_, _) => { shift++; Update(); };
        foreach (var choice in ViewModel.ChangeChoices())
        {
            var chip = new ToggleButton { Content = choice.Label, Tag = choice.Shift };
            chip.Click += (_, _) => { shift = choice.Shift; Update(); };
            choices.Children.Add(chip);
        }
        var content = new StackPanel { Spacing = 16, MinWidth = 360 };
        content.Children.Add(name);
        var steps = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Center };
        steps.Children.Add(down);
        steps.Children.Add(up);
        content.Children.Add(steps);
        if (choices.Children.Count > 0)
        {
            content.Children.Add(new TextBlock { Text = strings["ChangeNote_Heard"], Style = (Style)Application.Current.Resources["OverlineStyle"] });
            content.Children.Add(choices);
        }
        dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            RequestedTheme = Brasscribe.Play.Services.ThemeController.ForDialogs,
            Title = strings["ChangeNote_Title"],
            Content = content,
            PrimaryButtonText = strings["ChangeNote_Save"],
            CloseButtonText = strings["Score_CancelTitle"],
            DefaultButton = ContentDialogButton.Primary,
        };
        Update();
        // Save stays on the note: focus goes to "Changed to …" (the change is also announced), else back to Change note….
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && ViewModel.ChangeNote(shift) && ViewModel.IsChanged)
            ChangedLine.Focus(FocusState.Programmatic);
        else ChangeNoteButton.Focus(FocusState.Programmatic);
    }

    /// <summary>Undo hides its own row: focus goes back to Change note… instead of being lost.</summary>
    private void OnUndoChange(object sender, RoutedEventArgs e) => ChangeNoteButton.Focus(FocusState.Programmatic);

    /// <summary>K keeps and Space listens, only while single-key shortcuts are on (WCAG 2.1.4) and no text box or list item has focus.</summary>
    private bool SingleKeysAllowed(bool space) =>
        Main.Settings.SingleKeyShortcuts
        && FocusManager.GetFocusedElement(XamlRoot) is not (TextBox or SelectorItem)
        && !(space && FocusManager.GetFocusedElement(XamlRoot) is ButtonBase);

    private void OnKeepKey(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (!SingleKeysAllowed(space: false)) return;
        args.Handled = true;
        ViewModel.KeepCommand.Execute(null);
    }

    private void OnListenKey(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (!SingleKeysAllowed(space: true)) return;
        args.Handled = true;
        ViewModel.ListenCommand.Execute(null);
    }
}
