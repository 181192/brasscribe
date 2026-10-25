using System.ComponentModel;
using Kalli.Scribe.Tab;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;

namespace Kalli.Fretscribe.Views;

/// <summary>The tab screen: the page, its marks and the player under it; the keys move the song as the buttons do.</summary>
public sealed partial class TabScreenPage : Page, IScreenPage
{
    private TabFlowViewModel _flow = null!;
    private int _mark = -1;
    private DispatcherQueueTimer? _hide;

    public TabScreenPage()
    {
        InitializeComponent();
        // A tap or click anywhere on the tab, also on a note the view handles itself.
        Tab.AddHandler(TappedEvent, new TappedEventHandler((_, _) => ViewModel.TapTab()), true);
    }

    public TabPageViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        _flow = (TabFlowViewModel)e.Parameter;
        ViewModel = _flow.TabPage;
        ViewModel.PropertyChanged += OnViewModelChanged;
        ViewModel.Practice.PropertyChanged += OnPracticeChanged;
        Tab.ViewModel = ViewModel;
        Bindings.Update();
        UpdateRepeat();
        UpdatePlay();
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        ViewModel.PropertyChanged -= OnViewModelChanged;
        ViewModel.Practice.PropertyChanged -= OnPracticeChanged;
        _hide?.Stop();
    }

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(TabPageViewModel.RepeatText)) UpdateRepeat();
        if (e.PropertyName == nameof(TabPageViewModel.Sheet)) _mark = -1;
        if (e.PropertyName == nameof(TabPageViewModel.IsFullScreen) && ViewModel.IsFullScreen)
            // Narrator (or another screen reader) listening: the controls stay up in full screen.
            ViewModel.Assistive = AutomationPeer.ListenerExists(AutomationEvents.LiveRegionChanged);
        if (e.PropertyName == nameof(TabPageViewModel.FullScreenFocus)) MoveFocusFromHidden();
        if (e.PropertyName is nameof(TabPageViewModel.ControlsHide) or nameof(TabPageViewModel.FullScreenFocus)) ScheduleHide();
    }

    /// <summary>While it plays in full screen, the shown controls step aside after a few seconds without a tap.</summary>
    private void ScheduleHide()
    {
        _hide?.Stop();
        if (!ViewModel.ControlsHide) return;
        _hide ??= CreateHideTimer();
        _hide.Start();
    }

    private DispatcherQueueTimer CreateHideTimer()
    {
        var timer = DispatcherQueue.CreateTimer();
        timer.Interval = TabFocus.HideAfter;
        timer.IsRepeating = false;
        timer.Tick += (_, _) => ViewModel.HideControls();
        return timer;
    }

    /// <summary>Focus on a control that has just stepped aside goes to the one still there that does the same.</summary>
    private void MoveFocusFromHidden()
    {
        if (FocusManager.GetFocusedElement(XamlRoot) is not DependencyObject focused) return;
        if (ViewModel.MinimalShown && IsInside(focused, Header))
            LeaveFullScreenButton.Focus(FocusState.Programmatic);
        else if (ViewModel.MinimalShown && IsInside(focused, Player))
            MinimalPlayButton.Focus(FocusState.Programmatic);
        else if (ViewModel.ChromeShown && IsInside(focused, MinimalControls))
            FullScreenButton.Focus(FocusState.Programmatic);
    }

    private static bool IsInside(DependencyObject element, DependencyObject container)
    {
        for (var e = element; e is not null; e = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(e))
            if (e == container) return true;
        return false;
    }

    private void OnLeaveFullScreen(object sender, RoutedEventArgs e)
    {
        ViewModel.IsFullScreen = false;
        FullScreenButton.Focus(FocusState.Programmatic);
    }

    private void OnPracticeChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(PracticeModel.Playing)) UpdatePlay();
    }

    private void UpdatePlay() =>
        PlayGlyph.Glyph = MinimalPlayGlyph.Glyph = (string)Application.Current.Resources[ViewModel.Practice.Playing ? "FsIconPause" : "FsIconPlay"];

    private void UpdateRepeat()
    {
        RepeatLabel.Text = ViewModel.RepeatText ?? App.Strings["Tab_Practice_Repeat"];
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(RepeatButton, RepeatLabel.Text);
    }

    private void OnSpace(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        // A focused button or text box takes Space itself.
        if (FocusManager.GetFocusedElement(XamlRoot) is ButtonBase or TextBox) return;
        args.Handled = true;
        if (ViewModel.CanPlay) ViewModel.PlayPauseCommand.Execute(null);
    }

    private void OnLeft(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (FocusManager.GetFocusedElement(XamlRoot) is TextBox or ComboBox or Slider) return;
        args.Handled = true;
        if (ViewModel.Practice.Repeat is not null) ViewModel.ToStartCommand.Execute(null);
        else ViewModel.PreviousBarCommand.Execute(null);
    }

    private void OnRight(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (FocusManager.GetFocusedElement(XamlRoot) is TextBox or ComboBox or Slider) return;
        args.Handled = true;
        ViewModel.NextBarCommand.Execute(null);
    }

    private void OnFullScreen(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        ViewModel.FullScreenCommand.Execute(null);
    }

    private void OnEscape(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (!ViewModel.IsFullScreen) return;
        args.Handled = true;
        ViewModel.IsFullScreen = false;
        FullScreenButton.Focus(FocusState.Programmatic);
    }

    /// <summary>Next ?: focus goes to the next mark on the page, which says which note it is.</summary>
    private void OnNextMark(object sender, RoutedEventArgs e)
    {
        var marks = Tab.MarkButtons;
        if (marks.Count == 0) return;
        _mark = (_mark + 1) % marks.Count;
        marks[_mark].StartBringIntoView();
        marks[_mark].Focus(FocusState.Keyboard);
    }

    private async void OnShare(object sender, RoutedEventArgs e)
    {
        if (App.MainWindowInstance is { } window) await window.ShowExportAsync();
        ShareButton.Focus(FocusState.Programmatic);
    }

    private async void OnFetch(object sender, RoutedEventArgs e) => await ViewModel.Practice.FetchAsync(_flow.Engine);

    /// <summary>Repeat bars: from and to, as numbers; Stop repeating when bars are repeated.</summary>
    private async void OnRepeat(object sender, RoutedEventArgs e)
    {
        var s = App.Strings;
        int bars = ViewModel.Bars;
        if (bars == 0) return;
        var now = ViewModel.Practice.Repeat;
        var from = new NumberBox { Header = s["Tab_Practice_From"], Minimum = 1, Maximum = bars, Value = (now?.First ?? ViewModel.Bar) + 1, SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline };
        var to = new NumberBox { Header = s["Tab_Practice_To"], Minimum = 1, Maximum = bars, Value = (now?.Last ?? Math.Min(ViewModel.Bar + 3, bars - 1)) + 1, SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline };
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            RequestedTheme = Kalli.Scribe.Controls.ThemeController.ForDialogs,
            Title = s["Tab_Practice_RepeatTitle"],
            Content = new StackPanel { Spacing = 12, Children = { from, to } },
            PrimaryButtonText = s["Tab_Practice_RepeatSet"],
            SecondaryButtonText = now is null ? "" : s["Tab_Practice_RepeatStop"],
            CloseButtonText = s["Song_Cancel"],
            DefaultButton = ContentDialogButton.Primary,
        };
        var result = await Kalli.Scribe.WinUI.DialogGate.ShowAsync(dialog);
        if (result == ContentDialogResult.Primary && !double.IsNaN(from.Value) && !double.IsNaN(to.Value))
            ViewModel.RepeatBars((int)from.Value - 1, (int)to.Value - 1);
        else if (result == ContentDialogResult.Secondary) ViewModel.StopRepeatCommand.Execute(null);
        RepeatButton.Focus(FocusState.Programmatic);
    }
}
