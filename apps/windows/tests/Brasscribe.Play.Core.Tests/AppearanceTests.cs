using System.ComponentModel;
using System.Xml.Linq;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>Settings › Display › Appearance (design/system.md §10): Match system, Light, Dark, and Pink light and Pink dark once unlocked; contrast themes win.</summary>
public class AppearanceTests
{
    private sealed class Silent : IAnnouncer
    {
        public List<string> Said { get; } = [];
        public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status) => Said.Add(text);
    }

    private static string Resw(string lang) => Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", lang, "Resources.resw");

    private static IStrings Strings() => new ReswStrings(ReswStrings.Parse(XDocument.Load(Resw("en-US"))));

    [Theory]
    [InlineData(null, Appearance.System)]
    [InlineData("", Appearance.System)]
    [InlineData("system", Appearance.System)]
    [InlineData("light", Appearance.Light)]
    [InlineData("Dark", Appearance.Dark)]
    [InlineData(" dark ", Appearance.Dark)]
    [InlineData("sepia", Appearance.System)]
    [InlineData("pink-light", Appearance.PinkLight)]
    [InlineData("Pink-Dark", Appearance.PinkDark)]
    [InlineData("pink", Appearance.System)] // an earlier version's value: migrated when settings load
    public void Parses_stored_values_and_falls_back_to_match_system(string? stored, Appearance expected) =>
        Assert.Equal(expected, AppearanceSetting.Parse(stored));

    [Theory]
    [InlineData(Appearance.System, "system")]
    [InlineData(Appearance.Light, "light")]
    [InlineData(Appearance.Dark, "dark")]
    [InlineData(Appearance.PinkLight, "pink-light")]
    [InlineData(Appearance.PinkDark, "pink-dark")]
    public void Serialises_to_a_stable_word_that_parses_back(Appearance value, string word)
    {
        Assert.Equal(word, AppearanceSetting.Serialise(value));
        Assert.Equal(value, AppearanceSetting.Parse(AppearanceSetting.Serialise(value)));
    }

    [Theory]
    [InlineData(Appearance.System, false, RootTheme.Default)]
    [InlineData(Appearance.Light, false, RootTheme.Light)]
    [InlineData(Appearance.Dark, false, RootTheme.Dark)]
    [InlineData(Appearance.System, true, RootTheme.Default)]
    [InlineData(Appearance.Light, true, RootTheme.Default)]
    [InlineData(Appearance.Dark, true, RootTheme.Default)]
    [InlineData(Appearance.PinkLight, false, RootTheme.Light)]
    [InlineData(Appearance.PinkDark, false, RootTheme.Dark)]
    [InlineData(Appearance.PinkLight, true, RootTheme.Default)]
    [InlineData(Appearance.PinkDark, true, RootTheme.Default)]
    public void A_contrast_theme_always_wins(Appearance choice, bool highContrast, RootTheme expected) =>
        Assert.Equal(expected, AppearanceSetting.Resolve(choice, highContrast));

    [Fact]
    public void Root_theme_values_match_ElementTheme()
    {
        // The app casts RootTheme to Microsoft.UI.Xaml.ElementTheme (Default = 0, Light = 1, Dark = 2).
        Assert.Equal(0, (int)RootTheme.Default);
        Assert.Equal(1, (int)RootTheme.Light);
        Assert.Equal(2, (int)RootTheme.Dark);
    }

    [Fact]
    public void Defaults_to_match_system_and_is_stored_under_its_key()
    {
        var store = new InMemorySettings();
        var vm = new SettingsViewModel(store, new Silent(), Strings());
        Assert.Equal(Appearance.System, vm.Appearance);
        Assert.Equal(RootTheme.Default, vm.RootTheme);

        vm.Appearance = Appearance.Dark;
        Assert.Equal("dark", store.Get<string?>(AppearanceSetting.Key, null));
        Assert.Equal(Appearance.Dark, new SettingsViewModel(store, new Silent(), Strings()).Appearance);
    }

    [Fact]
    public void Changing_the_choice_or_the_contrast_theme_raises_RootTheme_at_once()
    {
        var vm = new SettingsViewModel(new InMemorySettings(), new Silent(), Strings());
        var changed = new List<string?>();
        ((INotifyPropertyChanged)vm).PropertyChanged += (_, e) => changed.Add(e.PropertyName);

        vm.Appearance = Appearance.Light;
        Assert.Contains(nameof(SettingsViewModel.RootTheme), changed);
        Assert.Equal(RootTheme.Light, vm.RootTheme);

        changed.Clear();
        vm.HighContrast = true;
        Assert.Contains(nameof(SettingsViewModel.RootTheme), changed);
        Assert.Equal(RootTheme.Default, vm.RootTheme);
        // The choice is kept for when the contrast theme is turned off.
        Assert.Equal(Appearance.Light, vm.Appearance);

        vm.HighContrast = false;
        Assert.Equal(RootTheme.Light, vm.RootTheme);
    }

    [Theory]
    [InlineData("en-US", "Appearance", "Match system", "Light", "Dark", "Your contrast theme is on, so Windows chooses the colours.")]
    [InlineData("nb-NO", "Utseende", "Følg systemet", "Lyst", "Mørkt", "Kontrasttemaet ditt er på, så Windows velger fargene.")]
    public void Copy_follows_the_design_system(string lang, string header, string system, string light, string dark, string note)
    {
        var s = ReswStrings.Parse(XDocument.Load(Resw(lang)));
        Assert.Equal(header, s["AppearanceBox.Header"]);
        Assert.Equal(system, s["AppearanceSystem.Content"]);
        Assert.Equal(light, s["AppearanceLight.Content"]);
        Assert.Equal(dark, s["AppearanceDark.Content"]);
        Assert.Equal(note, s["AppearanceContrastNote.Text"]);
    }

    [Fact]
    public void Settings_offers_the_three_choices_in_one_native_ComboBox_in_order()
    {
        var xaml = XDocument.Load(Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Dialogs", "SettingsDialog.xaml"));
        XNamespace x = "http://schemas.microsoft.com/winfx/2006/xaml";
        var box = xaml.Descendants().Single(e => (string?)e.Attribute(x + "Uid") == "AppearanceBox");
        Assert.Equal("ComboBox", box.Name.LocalName);
        Assert.Equal(["AppearanceSystem", "AppearanceLight", "AppearanceDark"],
            box.Elements().Select(e => (string)e.Attribute(x + "Uid")!).ToArray());
    }

    // ---- Pink (hidden) ----

    [Fact]
    public void Five_activations_in_a_row_unlock_pink_and_a_pause_starts_again()
    {
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider();
        var unlock = new PinkUnlock(false, time);
        for (int i = 0; i < 4; i++) { Assert.False(unlock.Tap()); time.Advance(TimeSpan.FromMilliseconds(1400)); }
        time.Advance(TimeSpan.FromMilliseconds(200)); // 1.6 s since the fourth: the count starts again
        Assert.False(unlock.Tap());
        for (int i = 0; i < 3; i++) { time.Advance(TimeSpan.FromMilliseconds(1500)); Assert.False(unlock.Tap()); }
        time.Advance(TimeSpan.FromMilliseconds(1500));
        Assert.True(unlock.Tap()); // the fifth in a row, each within 1.5 s
        Assert.True(unlock.IsUnlocked);
        Assert.False(unlock.Tap()); // said only once
    }

    [Fact]
    public void Pink_is_listed_last_once_unlocked_kept_on_this_pc_and_said_once()
    {
        var store = new InMemorySettings();
        var said = new Silent();
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider();
        var vm = new SettingsViewModel(store, said, Strings(), time: time);
        Assert.False(vm.PinkUnlocked);
        Assert.Equal([Appearance.System, Appearance.Light, Appearance.Dark], vm.AppearanceChoices);
        int raised = 0;
        vm.PinkUnlockedNow += (_, _) => raised++;
        for (int i = 0; i < 6; i++) { vm.ActivateVersion(); time.Advance(TimeSpan.FromMilliseconds(300)); }
        Assert.True(vm.PinkUnlocked);
        Assert.Equal(1, raised);
        Assert.Equal(["🎺 Pink unlocked"], said.Said);
        Assert.Equal([Appearance.System, Appearance.Light, Appearance.Dark, Appearance.PinkLight, Appearance.PinkDark], vm.AppearanceChoices);
        Assert.Equal(Appearance.System, vm.Appearance); // nothing switches by itself
        Assert.True(new SettingsViewModel(store, new Silent(), Strings()).PinkUnlocked);

        // Pink light and Pink dark pick the theme themselves; a contrast theme still wins, and the choice is kept.
        vm.Appearance = Appearance.PinkLight;
        Assert.Equal(RootTheme.Light, vm.RootTheme);
        Assert.True(vm.UsesPink);
        vm.Appearance = Appearance.PinkDark;
        Assert.Equal(RootTheme.Dark, vm.RootTheme);
        Assert.Equal("pink-dark", store.Get<string?>(AppearanceSetting.Key, null));
        vm.HighContrast = true;
        Assert.False(vm.UsesPink);
        Assert.Equal(RootTheme.Default, vm.RootTheme);
        Assert.Equal(Appearance.PinkDark, vm.Appearance);
        vm.Appearance = Appearance.Light;
        Assert.True(vm.PinkUnlocked); // Pink stays listed
    }

    [Theory]
    [InlineData("pink-light", Appearance.PinkLight)]
    [InlineData("pink-dark", Appearance.PinkDark)]
    public void A_pc_with_pink_chosen_counts_as_unlocked(string stored, Appearance expected)
    {
        var store = new InMemorySettings();
        store.Set(AppearanceSetting.Key, stored);
        var vm = new SettingsViewModel(store, new Silent(), Strings());
        Assert.True(vm.PinkUnlocked);
        Assert.Equal(expected, vm.Appearance);
    }

    [Theory]
    [InlineData(true, Appearance.PinkDark, "pink-dark")]
    [InlineData(false, Appearance.PinkLight, "pink-light")]
    [InlineData(null, Appearance.PinkLight, "pink-light")]
    public void An_earlier_pink_becomes_pink_light_or_dark_by_the_system(bool? systemDark, Appearance expected, string word)
    {
        var store = new InMemorySettings();
        store.Set(AppearanceSetting.Key, "pink");
        var vm = new SettingsViewModel(store, new Silent(), Strings(), systemDark: systemDark);
        Assert.Equal(expected, vm.Appearance);
        Assert.True(vm.UsesPink);
        Assert.Equal(word, store.Get<string?>(AppearanceSetting.Key, null));
        // Written down, so an earlier version, which reads the new word as Match system, still lists Pink.
        Assert.True(store.Get(AppearanceSetting.PinkUnlockedKey, false));
        Assert.Equal(expected, new SettingsViewModel(store, new Silent(), Strings(), systemDark: !systemDark).Appearance);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("system")]
    [InlineData("light")]
    [InlineData("dark")]
    [InlineData("pink-light")]
    [InlineData("pink-dark")]
    [InlineData("sepia")]
    public void Migration_leaves_every_other_value_alone(string? stored) =>
        Assert.Null(AppearanceSetting.Migrate(stored, true));

    [Theory]
    [InlineData("en-US", "Pink light", "Pink dark", "🎺 Pink unlocked", "Version 1.2")]
    [InlineData("nb-NO", "Rosa lys", "Rosa mørk", "🎺 Rosa låst opp", "Versjon 1.2")]
    public void Pink_copy_follows_the_design_system(string lang, string pinkLight, string pinkDark, string unlocked, string version)
    {
        IStrings s = new ReswStrings(ReswStrings.Parse(XDocument.Load(Resw(lang))));
        Assert.Equal((pinkLight, pinkDark, unlocked, version),
            (s["Appearance_PinkLight"], s["Appearance_PinkDark"], s["Pink_Unlocked"], s.Format("Settings_AppVersion", "1.2")));
    }
}
