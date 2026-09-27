using Brasscribe.Bandroom.Core.Appearance;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class AppearanceTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "bandroom-appearance-" + Guid.NewGuid().ToString("N"));
    private string File1 => Path.Combine(_dir, "bandroom", "appearance");

    public void Dispose()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, recursive: true);
    }

    [Theory]
    [InlineData("light", AppearanceChoice.Light)]
    [InlineData(" Dark\n", AppearanceChoice.Dark)]
    [InlineData("system", AppearanceChoice.System)]
    [InlineData("", AppearanceChoice.System)]
    [InlineData(null, AppearanceChoice.System)]
    [InlineData("sepia", AppearanceChoice.System)]
    public void Parse_falls_back_to_match_system(string? text, AppearanceChoice expected) =>
        Assert.Equal(expected, AppearanceRules.Parse(text));

    [Fact]
    public void Serialize_round_trips()
    {
        foreach (var c in AppearanceRules.Order)
            Assert.Equal(c, AppearanceRules.Parse(AppearanceRules.Serialize(c)));
    }

    [Theory]
    [InlineData(AppearanceChoice.System, false, ResolvedTheme.Default)]
    [InlineData(AppearanceChoice.Light, false, ResolvedTheme.Light)]
    [InlineData(AppearanceChoice.Dark, false, ResolvedTheme.Dark)]
    [InlineData(AppearanceChoice.System, true, ResolvedTheme.Default)]
    [InlineData(AppearanceChoice.Light, true, ResolvedTheme.Default)]
    [InlineData(AppearanceChoice.Dark, true, ResolvedTheme.Default)]
    public void A_contrast_theme_always_wins(AppearanceChoice choice, bool highContrast, ResolvedTheme expected) =>
        Assert.Equal(expected, AppearanceRules.Resolve(choice, highContrast));

    [Fact]
    public void The_store_defaults_to_match_system_and_keeps_the_choice()
    {
        var store = new AppearanceStore(File1);
        Assert.Equal(AppearanceChoice.System, store.Load());
        Assert.True(store.Save(AppearanceChoice.Dark));
        Assert.Equal("dark", File.ReadAllText(File1));
        Assert.Equal(AppearanceChoice.Dark, new AppearanceStore(File1).Load());
    }

    [Fact]
    public void Options_and_copy_in_both_languages()
    {
        var en = new AppearanceViewModel(Strings.En, null, highContrast: false);
        Assert.Equal("Appearance", en.Header);
        Assert.Equal(["Match system", "Light", "Dark"], en.Options);
        var nb = new AppearanceViewModel(Strings.Nb, null, highContrast: false);
        Assert.Equal("Utseende", nb.Header);
        Assert.Equal(["Følg systemet", "Lyst", "Mørkt"], nb.Options);
    }

    [Fact]
    public void Choosing_applies_at_once_and_is_stored()
    {
        var store = new AppearanceStore(File1);
        var vm = new AppearanceViewModel(Strings.En, store, highContrast: false);
        Assert.Equal(0, vm.SelectedIndex);
        Assert.Equal(ResolvedTheme.Default, vm.Resolved);
        var seen = new List<ResolvedTheme>();
        vm.ThemeChanged += seen.Add;

        vm.SelectedIndex = 2;
        vm.SelectedIndex = -1; // ignored: the ComboBox reports -1 while its items are replaced
        vm.SelectedIndex = 1;

        Assert.Equal([ResolvedTheme.Dark, ResolvedTheme.Light], seen);
        Assert.Equal(AppearanceChoice.Light, store.Load());
        Assert.Equal(AppearanceChoice.Light, new AppearanceViewModel(Strings.En, store, false).Choice);
    }

    [Fact]
    public void Under_a_contrast_theme_the_choice_is_kept_but_windows_follow_the_system()
    {
        var vm = new AppearanceViewModel(Strings.En, null, highContrast: false, initial: AppearanceChoice.Dark);
        Assert.False(vm.ShowsContrastNote);
        Assert.Equal("", vm.ContrastNote);
        var seen = new List<ResolvedTheme>();
        vm.ThemeChanged += seen.Add;

        vm.HighContrast = true;
        Assert.Equal(ResolvedTheme.Default, vm.Resolved);
        Assert.True(vm.ShowsContrastNote);
        Assert.Equal("Your contrast theme is on, so Windows chooses the colours.", vm.ContrastNote);
        Assert.Equal("Kontrasttemaet ditt er på, så Windows velger fargene.",
            new AppearanceViewModel(Strings.Nb, null, highContrast: true).ContrastNote);

        vm.SelectedIndex = 1; // the picker stays usable; nothing changes on screen yet
        vm.HighContrast = false;

        Assert.Equal([ResolvedTheme.Default, ResolvedTheme.Light], seen);
        Assert.Equal(AppearanceChoice.Light, vm.Choice);
    }

    [Fact]
    public void An_override_is_not_written_until_the_user_chooses()
    {
        var store = new AppearanceStore(File1);
        _ = new AppearanceViewModel(Strings.En, store, false, initial: AppearanceChoice.Dark);
        Assert.False(File.Exists(File1));
    }
}
