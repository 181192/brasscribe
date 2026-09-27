using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;

namespace Brasscribe.Play.Views;

/// <summary>
/// The music stand's control layer: transport, pages, speed, Repeat and Only my part. It reports the
/// height it covers at the bottom of the music, so the current system is never under it (§4.3).
/// </summary>
public sealed partial class MusicStandLayer : UserControl
{
    private readonly Windows.UI.ViewManagement.UISettings _ui = new();
    private Flyout? _repeatFlyout;

    public MusicStandLayer()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Arrange();
        Card.SizeChanged += (_, _) => ObscuredChanged?.Invoke(this, EventArgs.Empty);
        _ui.TextScaleFactorChanged += (_, _) => DispatcherQueue.TryEnqueue(Arrange);
    }

    public ScoreViewModel? Score { get; private set; }

    /// <summary>The height the card covers at the bottom changed (it showed, hid or grew).</summary>
    public event EventHandler? ObscuredChanged;

    public void Show(ScoreViewModel score)
    {
        Score = score;
        Bindings.Update();
        Arrange();
    }

    /// <summary>Epx covered at the bottom of the music: the card and its margin, or nothing while hidden.</summary>
    public double ObscuredHeight => Card.Visibility == Visibility.Visible ? Card.ActualHeight + Card.Margin.Bottom + 8 : 0;

    /// <summary>Keyboard focus is on one of the layer's controls (or its Repeat flyout is open).</summary>
    public bool HasFocusWithin()
    {
        if (_repeatFlyout?.IsOpen == true) return true;
        if (XamlRoot is null || Microsoft.UI.Xaml.Input.FocusManager.GetFocusedElement(XamlRoot) is not DependencyObject focused) return false;
        for (var d = focused; d is not null; d = VisualTreeHelper.GetParent(d))
            if (ReferenceEquals(d, Card)) return true;
        return false;
    }

    /// <summary>The first control in reading order (Tab into the layer).</summary>
    public Control First => PreviousPageButton;

    /// <summary>The last visible control (Shift+Tab into the layer).</summary>
    public Control Last => OnlyMineToggle.Visibility == Visibility.Visible ? OnlyMineToggle : RepeatToggle;

    /// <summary>One row when it fits; otherwise the groups stack and the card grows upwards (never clipped).</summary>
    private void Arrange()
    {
        if (ActualWidth <= 0) return;
        Rows.Orientation = Orientation.Horizontal;
        Rows.Measure(new Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity));
        double available = ActualWidth - Card.Margin.Left - Card.Margin.Right - Card.Padding.Left - Card.Padding.Right - 2;
        bool stack = Rows.DesiredSize.Width > available || _ui.TextScaleFactor >= 1.5 && Rows.DesiredSize.Width > available * 0.9;
        Rows.Orientation = stack ? Orientation.Vertical : Orientation.Horizontal;
        Rows.Spacing = stack ? 10 : 16;
        Toggles.Orientation = stack && Toggles.DesiredSize.Width > available ? Orientation.Vertical : Orientation.Horizontal;
    }

    private void OnPreviousPage(object sender, RoutedEventArgs e) => Score?.Stand.PreviousPage();
    private void OnNextPage(object sender, RoutedEventArgs e) => Score?.Stand.NextPage();

    /// <summary>Repeat: off, or the bars chosen before; with none chosen yet, the bar fields (typed, no dragging).</summary>
    private void OnRepeat(object sender, RoutedEventArgs e)
    {
        if (Score is not { } score) return;
        if (!score.Stand.ToggleRepeat()) ShowRepeatFields(score);
        RepeatToggle.IsChecked = score.Player.IsLooping; // the toggle follows the player, not the click
    }

    private void ShowRepeatFields(ScoreViewModel score)
    {
        var s = App.Strings;
        var player = score.Player;
        int bar = Math.Max(1, player.CurrentBar);
        var from = new NumberBox
        {
            Header = s["Stand_RepeatFrom"], Minimum = 1, Maximum = player.LastBar, Value = bar, Width = 120,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Hidden,
        };
        var to = new NumberBox
        {
            Header = s["Stand_RepeatTo"], Minimum = 1, Maximum = player.LastBar, Value = Math.Min(player.LastBar, bar + 1), Width = 120,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Hidden,
        };
        var repeat = new Button { Content = s["Stand_RepeatSet"], Style = (Style)Application.Current.Resources["ActionButtonStyle"], MinHeight = 44 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetHelpText(repeat, s["Stand_RepeatSetHelp"]);
        var flyout = new Flyout
        {
            Content = new StackPanel
            {
                Spacing = 12,
                Children = { new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12, Children = { from, to } }, repeat },
            },
        };
        repeat.Click += (_, _) =>
        {
            if (double.IsNaN(from.Value) || double.IsNaN(to.Value)) return;
            player.LoopStart = from.Value;
            player.LoopEnd = to.Value;
            player.SetLoopCommand.Execute(null);
            RepeatToggle.IsChecked = player.IsLooping;
            flyout.Hide();
        };
        flyout.Closed += (_, _) =>
        {
            _repeatFlyout = null;
            RepeatToggle.Focus(FocusState.Programmatic);
        };
        _repeatFlyout = flyout;
        flyout.ShowAt(RepeatToggle, new FlyoutShowOptions { Placement = FlyoutPlacementMode.Top });
    }
}
