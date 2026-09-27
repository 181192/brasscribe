using Brasscribe.Play.Core.Engine;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Views;

/// <summary>The connection status row on Home and in Settings (the same look as the other Play apps).</summary>
public sealed partial class ConnectionRow : UserControl
{
    /// <summary>Text scaled this much or more puts the button below the words.</summary>
    public const double WrapTextScale = 1.5;

    /// <summary>Narrower than this (in epx) the button goes below the words too.</summary>
    public const double WrapWidth = 520;

    private readonly Windows.UI.ViewManagement.UISettings _ui = new();

    public ConnectionRow()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Layout();
        _ui.TextScaleFactorChanged += (_, _) => DispatcherQueue.TryEnqueue(Layout);
        Loaded += (_, _) => Layout();
    }

    public ConnectionMonitor? Connection { get; private set; }

    /// <summary>Connect or Pair this PC again was chosen.</summary>
    public event EventHandler? ActionInvoked;

    public void Show(ConnectionMonitor connection)
    {
        Connection = connection;
        Bindings.Update();
    }

    private void OnAction(object sender, RoutedEventArgs e) => ActionInvoked?.Invoke(this, EventArgs.Empty);

    /// <summary>Side by side, or the button under the words (aligned with them) at large text or narrow widths.</summary>
    private void Layout()
    {
        bool below = _ui.TextScaleFactor >= WrapTextScale || ActualWidth > 0 && ActualWidth < WrapWidth;
        Grid.SetRow(ActionButton, below ? 1 : 0);
        Grid.SetColumn(ActionButton, below ? 1 : 2);
        ActionButton.HorizontalAlignment = below ? HorizontalAlignment.Left : HorizontalAlignment.Stretch;
    }
}
