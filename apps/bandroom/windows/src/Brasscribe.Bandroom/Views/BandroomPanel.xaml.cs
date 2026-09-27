using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Brasscribe.Bandroom.Views;

/// <summary>What the More menu does outside the view model.</summary>
public interface IPanelHost
{
    bool StartAtLogin { get; set; }
    bool StartAtLoginChangeable { get; }
    void OpenRemoveSettings();
    void Quit();
}

/// <summary>The flyout content, bound to <see cref="FlyoutViewModel"/>; also used by the window form.</summary>
public sealed partial class BandroomPanel : UserControl
{
    private readonly IPanelHost _host;

    public BandroomPanel(FlyoutViewModel vm, IPanelHost host)
    {
        Vm = vm;
        _host = host;
        InitializeComponent();
        Mark.Source = new SvgImageSource(new Uri(ActualTheme == ElementTheme.Dark
            ? "ms-appx:///Assets/Brand/mark-on-dark.svg" : "ms-appx:///Assets/Brand/mark.svg"));
        ActualThemeChanged += (_, _) => Mark.Source = new SvgImageSource(new Uri(ActualTheme == ElementTheme.Dark
            ? "ms-appx:///Assets/Brand/mark-on-dark.svg" : "ms-appx:///Assets/Brand/mark.svg"));
        BuildMoreMenu();
        vm.FocusRequested += target => DispatcherQueue.TryEnqueue(() => MoveFocus(target));
        vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(FlyoutViewModel.View)) SizeChangedByContent?.Invoke();
        };
        Root.SizeChanged += (_, _) => SizeChangedByContent?.Invoke();
    }

    public FlyoutViewModel Vm { get; }

    /// <summary>The content's height changed (a sub-view, the Now card, the tech details).</summary>
    public event Action? SizeChangedByContent;

    private void BuildMoreMenu()
    {
        var s = Vm.Strings;
        var studio = new MenuFlyoutItem { Text = s["Action_OpenStudio"], Icon = new FontIcon { Glyph = "\uE8A7" } };
        studio.Click += (_, _) => Vm.OpenStudioCommand.Execute(null);
        var login = new ToggleMenuFlyoutItem { Text = s["More_Login"], IsChecked = _host.StartAtLogin, IsEnabled = _host.StartAtLoginChangeable };
        login.Click += (_, _) => { _host.StartAtLogin = login.IsChecked; login.IsChecked = _host.StartAtLogin; };
        var remove = new MenuFlyoutItem { Text = s["More_Remove"] };
        remove.Click += (_, _) => _host.OpenRemoveSettings();
        var quit = new MenuFlyoutItem { Text = s["More_Quit"], Icon = new FontIcon { Glyph = "\uE711" } };
        quit.Click += (_, _) => _host.Quit();
        MoreMenu.Items.Add(studio);
        MoreMenu.Items.Add(login);
        MoreMenu.Items.Add(new MenuFlyoutSeparator());
        MoreMenu.Items.Add(remove);
        MoreMenu.Items.Add(quit);
        MoreMenu.Opening += (_, _) => login.IsChecked = _host.StartAtLogin;
    }

    /// <summary>Keyboard focus starts on the primary button (§9, 2.1.1).</summary>
    public void FocusPrimary() => MoveFocus("Primary");

    private void MoveFocus(string target)
    {
        Control? c = target switch
        {
            "Primary" => PrimaryButton.Visibility == Visibility.Visible ? PrimaryButton : DevicesRow,
            "Back" or "DevicesHeading" => BackButton,
            "Devices" or "DevicesRow" => DevicesRow,
            "ConfirmTitle" => ConfirmSecondary,
            _ when target.StartsWith("Row:", StringComparison.Ordinal) && int.TryParse(target[4..], out int i) => RemoveButtonAt(i),
            _ => null,
        };
        if (target == "ConfirmTitle") Announce(Vm.ConfirmTitle + " " + Vm.ConfirmBody);
        if (target == "DevicesHeading") Announce(Vm.DevicesHeading + ". " + Vm.EmptyDevicesText);
        c?.Focus(FocusState.Programmatic);
    }

    private Button? RemoveButtonAt(int index)
    {
        DeviceList.UpdateLayout();
        return DeviceList.TryGetElement(index) is Grid row ? row.Children.OfType<Button>().FirstOrDefault() : null;
    }

    private void OnRemoveClick(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string id } && Vm.Devices.FirstOrDefault(d => d.Id == id) is { } row)
            Vm.RemoveDeviceCommand.Execute(row);
    }

    /// <summary>A polite announcement (UIA notification) without moving focus.</summary>
    public void Announce(string text)
    {
        if (FrameworkElementAutomationPeer.FromElement(AnnouncerHost) is not { } peer)
            peer = FrameworkElementAutomationPeer.CreatePeerForElement(AnnouncerHost);
        peer?.RaiseNotificationEvent(AutomationNotificationKind.Other, AutomationNotificationProcessing.MostRecent, text, "BandroomStatus");
    }

    // ----- x:Bind helpers -----

    public string StatusGlyph(DisplayState s) => s switch
    {
        DisplayState.Running or DisplayState.Busy => "\uE930",        // check circle
        DisplayState.NeedsAttention => "\uE7BA",                      // triangle
        DisplayState.Stopped => "\uE71A",                             // square
        DisplayState.Error => "\uEA39",                               // ✕ in a circle, never the triangle
        DisplayState.Updating => "\uE895",                            // circular arrow
        DisplayState.SettingUp => "\uE896",                           // down arrow
        _ => "\uE712",                                                // three dots
    };

    /// <summary>Status colour on the icon only; the words stay in text colour (§6.1).</summary>
    public Brush StatusBrush(DisplayState s)
    {
        string key = s switch
        {
            DisplayState.Running or DisplayState.Busy => "BcSuccessBrush",
            DisplayState.NeedsAttention => "BcWarningBrush",
            DisplayState.Error => "BcErrorBrush",
            _ => "BcTextBrush",
        };
        return Res(key);
    }

    /// <summary>A theme brush by key (theme dictionaries included), or the text colour.</summary>
    public static Brush Res(string key) =>
        Application.Current.Resources.TryGetValue(key, out var v) && v is Brush b ? b : new SolidColorBrush(Microsoft.UI.Colors.Gray);

    public Visibility HasText(string? s) => string.IsNullOrEmpty(s) ? Visibility.Collapsed : Visibility.Visible;

    public string Upper(string s) => s.ToUpper(Vm.Strings.Culture);

    public string Join(string a, string b) => string.IsNullOrEmpty(b) ? a : a + ", " + b;

    public string ReadyGlyph(bool ready) => ready ? "\uE930" : "\uE896";

    /// <summary>Filled for the segments up to the level; the meter never uses brass or a status colour.</summary>
    public Brush Segment(int level, int index) =>
        index <= level ? Res("BcTextMutedBrush") : new SolidColorBrush(Microsoft.UI.Colors.Transparent);
}

/// <summary>Glyph helpers usable from data templates.</summary>
public static class Glyphs
{
    public static string Device(bool tablet) => tablet ? "\uE70A" : "\uE8EA";
}
