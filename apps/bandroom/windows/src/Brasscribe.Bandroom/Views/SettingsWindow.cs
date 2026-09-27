using Brasscribe.Bandroom.Core;
using Brasscribe.Bandroom.Core.Appearance;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics;

namespace Brasscribe.Bandroom.Views;

/// <summary>
/// Settings (server-app.md, "Settings page in the window"): SettingsCard-style rows for Appearance
/// (design/system.md §10) and Start when I log in. Appearance is a ComboBox, as in Windows Settings ›
/// Personalisation › Choose your mode; it applies at once, and focus stays on it.
/// </summary>
internal sealed class SettingsWindow : Window
{
    private static Style S(string key) => (Style)Application.Current.Resources[key];

    public SettingsWindow(AppearanceViewModel appearance, IPanelHost host, IStrings s, ThemedWindows themes)
    {
        // ----- Appearance -----
        var appearanceHeader = new TextBlock { Text = appearance.Header, Style = S("StrongStyle") };
        var contrastNote = new TextBlock { Style = S("MutedStyle"), TextWrapping = TextWrapping.Wrap };
        var picker = new ComboBox { ItemsSource = appearance.Options, SelectedIndex = appearance.SelectedIndex, MinWidth = 200, VerticalAlignment = VerticalAlignment.Center };
        AutomationProperties.SetLabeledBy(picker, appearanceHeader);
        picker.SelectionChanged += (_, _) => appearance.SelectedIndex = picker.SelectedIndex;

        void ShowContrast()
        {
            contrastNote.Text = appearance.ContrastNote;
            contrastNote.Visibility = appearance.ShowsContrastNote ? Visibility.Visible : Visibility.Collapsed;
            // The line is read with the picker, so a screen reader hears why the colours don't change.
            AutomationProperties.SetHelpText(picker, appearance.ContrastNote);
        }
        ShowContrast();
        void OnChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
        {
            if (e.PropertyName == nameof(AppearanceViewModel.ContrastNote)) ShowContrast();
            if (e.PropertyName == nameof(AppearanceViewModel.SelectedIndex) && picker.SelectedIndex != appearance.SelectedIndex)
                picker.SelectedIndex = appearance.SelectedIndex;
        }
        appearance.PropertyChanged += OnChanged;
        Closed += (_, _) => appearance.PropertyChanged -= OnChanged;

        // ----- Start when I log in -----
        var loginHeader = new TextBlock { Text = s["Settings_Login"], Style = S("StrongStyle"), VerticalAlignment = VerticalAlignment.Center };
        var login = new ToggleSwitch { IsOn = host.StartAtLogin, IsEnabled = host.StartAtLoginChangeable, VerticalAlignment = VerticalAlignment.Center, MinWidth = 0 };
        AutomationProperties.SetLabeledBy(login, loginHeader);
        login.Toggled += (_, _) => { host.StartAtLogin = login.IsOn; login.IsOn = host.StartAtLogin; };

        var title = new TextBlock { Text = s["Settings_Title"], Style = S("DisplayHeadingStyle") };
        AutomationProperties.SetHeadingLevel(title, Microsoft.UI.Xaml.Automation.Peers.AutomationHeadingLevel.Level1);
        var root = new Grid
        {
            Style = S("WindowRootStyle"),
            Children =
            {
                new ScrollViewer
                {
                    VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                    Content = new StackPanel
                    {
                        Padding = new Thickness(24),
                        Spacing = 8,
                        Children =
                        {
                            title,
                            Card(new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center, Children = { appearanceHeader, contrastNote } }, picker),
                            Card(loginHeader, login),
                        },
                    },
                },
            },
        };
        themes.Track(this, root);
        Content = root;
        Title = s["Settings_Title"];
        double scale = WindowSizing.Scale(this);
        AppWindow.Resize(new SizeInt32((int)(560 * scale), (int)(360 * scale)));
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico"));
        root.Loaded += (_, _) => picker.Focus(FocusState.Programmatic);
    }

    /// <summary>A SettingsCard: the name (and its one line) on the left, the control on the right.</summary>
    private static Border Card(FrameworkElement label, FrameworkElement control)
    {
        var grid = new Grid
        {
            ColumnSpacing = 16,
            MinHeight = 44,
            ColumnDefinitions = { new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }, new ColumnDefinition { Width = GridLength.Auto } },
            Children = { label, control },
        };
        Grid.SetColumn(control, 1);
        return new Border { Style = S("CardStyle"), Child = grid };
    }
}
