using Brasscribe.Bandroom.Core;
using Brasscribe.Bandroom.Core.Appearance;
using Brasscribe.Bandroom.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics;

namespace Brasscribe.Bandroom.Views;

/// <summary>What Settings changes outside Appearance: the name phones see and the Hugging Face key.</summary>
public interface ISettingsHost
{
    /// <summary>The device name Windows has (Settings › System › About).</summary>
    string SystemComputerName { get; }
    /// <summary>The name set in Settings, or null.</summary>
    string? CustomComputerName { get; }
    /// <summary>Stores the name (empty removes it) and restarts Brasscribe when nothing is being made.</summary>
    void SetCustomComputerName(string? name);
    /// <summary>HF_TOKEN is set on this PC, so the saved key isn't used.</summary>
    bool HuggingFaceKeyFromEnvironment { get; }
    bool HuggingFaceKeySaved { get; }
    /// <returns>False when Credential Manager refused.</returns>
    bool SaveHuggingFaceKey(string key);
    /// <summary>The MuScriptor page on Hugging Face, where the licence is accepted and the full terms are.</summary>
    void OpenModelPage();
}

/// <summary>
/// Settings (server-app.md, "Settings page in the window"): SettingsCard-style rows for Name shown to phones
/// (only when the device name looks machine-made, or one is set), Hugging Face access (the band writer's terms,
/// accepted before a key is saved, since saving starts its download), Appearance
/// (design/system.md §10) and Start when I log in. Appearance is a ComboBox, as in Windows Settings ›
/// Personalisation › Choose your mode; it applies at once, and focus stays on it.
/// </summary>
internal sealed class SettingsWindow : Window
{
    private static Style S(string key) => (Style)Application.Current.Resources[key];

    public SettingsWindow(AppearanceViewModel appearance, IPanelHost host, ISettingsHost settings, IStrings s, ThemedWindows themes)
    {
        // ----- Name shown to phones -----
        Border? nameCard = null;
        if (ComputerName.OffersCustomName(settings.SystemComputerName, settings.CustomComputerName))
        {
            var nameHeader = new TextBlock { Text = s["Settings_Name"], Style = S("StrongStyle") };
            var nameBox = new TextBox { Text = settings.CustomComputerName ?? "", PlaceholderText = settings.SystemComputerName, MinWidth = 240 };
            AutomationProperties.SetLabeledBy(nameBox, nameHeader);
            var nameNote = new TextBlock { Style = S("MutedStyle"), TextWrapping = TextWrapping.Wrap };
            var useName = new Button { Content = s["Settings_Name_Use"], Style = S("OutlineButtonStyle") };
            void ShowName()
            {
                nameNote.Text = s.Format("Settings_Name_Note", ComputerName.Shown(settings.SystemComputerName, settings.CustomComputerName));
                useName.IsEnabled = nameBox.Text.Trim() != (settings.CustomComputerName ?? "");
            }
            ShowName();
            nameBox.TextChanged += (_, _) => ShowName();
            void Use()
            {
                settings.SetCustomComputerName(nameBox.Text);
                ShowName();
            }
            useName.Click += (_, _) => Use();
            nameBox.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter && useName.IsEnabled) { Use(); e.Handled = true; } };
            nameCard = Stacked(nameHeader, nameBox, Row(nameNote, useName));
        }

        // ----- Hugging Face access -----
        var hf = new HuggingFaceKeyViewModel(s);
        var hfHeader = new TextBlock { Text = s["Settings_Hf"], Style = S("StrongStyle") };
        var licence = new TextBlock { Text = hf.Licence, Style = S("BodyStyle"), TextWrapping = TextWrapping.Wrap };
        var terms = new TextBlock { Text = hf.Terms, Style = S("BodyStyle"), TextWrapping = TextWrapping.Wrap };
        var agree = new CheckBox
        {
            Content = new TextBlock { Text = hf.Agree, TextWrapping = TextWrapping.Wrap },
            IsEnabled = !settings.HuggingFaceKeyFromEnvironment,
        };
        AutomationProperties.SetName(agree, hf.Agree);
        var keyLabel = new TextBlock { Text = s["Setup_2_Key_Label"], Style = S("BodyStyle") };
        var keyBox = new PasswordBox { MinWidth = 240, IsEnabled = !settings.HuggingFaceKeyFromEnvironment };
        AutomationProperties.SetLabeledBy(keyBox, keyLabel);
        var keyNote = new TextBlock { Text = s["Settings_Hf_Note"], Style = S("MutedStyle"), TextWrapping = TextWrapping.Wrap };
        var keyState = new TextBlock { Style = S("MutedStyle"), TextWrapping = TextWrapping.Wrap };
        var saveKey = new Button { Content = s["Settings_Save"], Style = S("OutlineButtonStyle"), IsEnabled = false };
        var openPage = new Button { Content = hf.ReadTerms, Style = S("PlainButtonStyle") };
        void ShowKey()
        {
            keyState.Text = settings.HuggingFaceKeyFromEnvironment ? s["Settings_Hf_FromEnvironment"]
                : settings.HuggingFaceKeySaved ? s["Settings_Hf_Saved"] : "";
            keyState.Visibility = keyState.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        }
        ShowKey();
        keyBox.PasswordChanged += (_, _) => hf.Key = keyBox.Password;
        agree.Checked += (_, _) => hf.TermsAccepted = true;
        agree.Unchecked += (_, _) => hf.TermsAccepted = false;
        hf.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(HuggingFaceKeyViewModel.CanSave)) saveKey.IsEnabled = hf.CanSave; };
        saveKey.Click += (_, _) =>
        {
            if (!hf.CanSave || !settings.SaveHuggingFaceKey(keyBox.Password)) return;
            keyBox.Password = "";
            ShowKey();
            AutomationProperties.SetHelpText(keyBox, keyState.Text);
        };
        openPage.Click += (_, _) => settings.OpenModelPage();
        var hfCard = Stacked(hfHeader, licence, keyNote, keyLabel, keyBox, terms, agree, Row(openPage, saveKey), keyState);

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
                            nameCard ?? new Border { Visibility = Visibility.Collapsed },
                            hfCard,
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
        AppWindow.Resize(new SizeInt32((int)(560 * scale), (int)(640 * scale)));
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico"));
        root.Loaded += (_, _) => picker.Focus(FocusState.Programmatic);
    }

    /// <summary>A card of rows, top to bottom: the name first.</summary>
    private static Border Stacked(params FrameworkElement[] rows)
    {
        var panel = new StackPanel { Spacing = 8 };
        foreach (var r in rows) panel.Children.Add(r);
        return new Border { Style = S("CardStyle"), Child = panel };
    }

    /// <summary>Two controls side by side; the first takes the room.</summary>
    private static Grid Row(FrameworkElement first, FrameworkElement second)
    {
        var grid = new Grid
        {
            ColumnSpacing = 12,
            ColumnDefinitions = { new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }, new ColumnDefinition { Width = GridLength.Auto } },
            Children = { first, second },
        };
        second.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(second, 1);
        return grid;
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
