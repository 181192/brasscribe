using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Dialogs;

public sealed partial class ShortcutsDialog : ContentDialog
{
    /// <summary>Shortcut rows: resource key of the action and the keys (same on every language).</summary>
    public static readonly (string Section, (string Action, string Keys)[] Rows)[] Table =
    [
        ("Shortcuts_Global", [
            ("Shortcut_Import", "Ctrl+O"), ("Shortcut_Record", "Ctrl+Shift+R"), ("Shortcut_PlayPauseGlobal", "Ctrl+Shift+Space"),
            ("Shortcut_Export", "Ctrl+E"), ("Shortcut_GoToBar", "Ctrl+G"), ("Shortcut_TalkingScore", "Ctrl+T"),
            ("Shortcut_Settings", "Ctrl+,"), ("Shortcut_Help", "F1"), ("Shortcut_Close", "Esc"),
        ]),
        ("Shortcuts_Score", [
            ("Shortcut_PlayPause", "Space"), ("Shortcut_Note", "→ / ←"), ("Shortcut_Beat", "Ctrl+→ / Ctrl+←"),
            ("Shortcut_Bar", "Ctrl+↓ / Ctrl+↑"), ("Shortcut_Part", "Ctrl+Shift+↓ / Ctrl+Shift+↑"), ("Shortcut_FirstLast", "Home / End"),
            ("Shortcut_Uncertain", "U / Shift+U"), ("Shortcut_Checked", "C"), ("Shortcut_ReadBar", "R"),
            ("Shortcut_PlayBar", "P / Shift+P"), ("Shortcut_WhereAmI", "W"), ("Shortcut_Loop", "[ / ] / L"),
            ("Shortcut_Speed", "- / = / 0"), ("Shortcut_MuteSolo", "M / S"), ("Shortcut_CountInMetronome", "K / T"), ("Shortcut_SwitchSource", "O"),
            ("Shortcut_Zoom", "Ctrl+- / Ctrl+= / Ctrl+0"), ("Shortcut_Leave", "Tab / Shift+Tab / Esc"),
            ("Shortcut_Stand", "F / F11"),
        ]),
        ("Shortcuts_Stand", [
            ("Shortcut_StandPage", "→ ↓ Page Down / ← ↑ Page Up"), ("Shortcut_StandFirstLast", "Home / End"),
            ("Shortcut_PlayPause", "Space"), ("Shortcut_Bar", "Ctrl+↓ / Ctrl+↑"), ("Shortcut_StandLeave", "Esc / F / F11"),
        ]),
    ];

    public ShortcutsDialog()
    {
        InitializeComponent();
        var s = App.Strings;
        foreach (var (section, rows) in Table)
        {
            var heading = new TextBlock { Text = s[section], Style = (Style)Application.Current.Resources["SectionHeadingStyle"] };
            AutomationProperties.SetHeadingLevel(heading, AutomationHeadingLevel.Level2);
            Sections.Children.Add(heading);
            foreach (var (action, keys) in rows)
            {
                var row = new Grid { ColumnSpacing = 16 };
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                var a = new TextBlock { Text = s[action], TextWrapping = TextWrapping.Wrap };
                var k = new TextBlock { Text = keys, FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas") };
                Grid.SetColumn(k, 1);
                row.Children.Add(a);
                row.Children.Add(k);
                AutomationProperties.SetName(row, $"{s[action]}: {keys}");
                Sections.Children.Add(row);
            }
        }
    }
}
