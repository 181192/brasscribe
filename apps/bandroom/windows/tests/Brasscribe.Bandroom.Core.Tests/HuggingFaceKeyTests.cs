using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>Saving the key starts the band writer's download, so its terms come first.</summary>
public sealed class HuggingFaceKeyTests
{
    [Fact]
    public void Saving_waits_for_the_terms()
    {
        var vm = new HuggingFaceKeyViewModel(Strings.En) { Key = "hf_abc" };
        Assert.False(vm.CanSave);
        vm.TermsAccepted = true;
        Assert.True(vm.CanSave);
        vm.TermsAccepted = false;
        Assert.False(vm.CanSave);
    }

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    public void An_empty_key_cant_be_saved(string key)
    {
        var vm = new HuggingFaceKeyViewModel(Strings.En) { Key = key, TermsAccepted = true };
        Assert.False(vm.CanSave);
    }

    [Fact]
    public void Ticking_the_box_updates_save()
    {
        var vm = new HuggingFaceKeyViewModel(Strings.En) { Key = "hf_abc" };
        var changed = new List<string?>();
        vm.PropertyChanged += (_, e) => changed.Add(e.PropertyName);
        vm.TermsAccepted = true;
        Assert.Contains(nameof(HuggingFaceKeyViewModel.CanSave), changed);
    }

    [Fact]
    public void The_terms_in_both_languages()
    {
        var en = new HuggingFaceKeyViewModel(Strings.En);
        Assert.Contains("non-commercial use (CC BY-NC 4.0)", en.Licence);
        Assert.StartsWith("By downloading it, you confirm you have the rights to the music", en.Terms);
        Assert.Contains("take responsibility", en.Terms);
        Assert.Equal("I'll use it only non-commercially, and only for music I have the rights to.", en.Agree);
        Assert.Equal("Read the full terms", en.ReadTerms);

        var nb = new HuggingFaceKeyViewModel(Strings.Nb);
        Assert.Contains("ikke-kommersiell bruk (CC BY-NC 4.0)", nb.Licence);
        Assert.StartsWith("Når du laster den ned, bekrefter du at du har rettighetene til musikken", nb.Terms);
        Assert.Contains("ta ansvaret", nb.Terms);
        Assert.Equal("Jeg bruker den bare ikke-kommersielt, og bare til musikk jeg har rettighetene til.", nb.Agree);
        Assert.Equal("Les alle vilkårene", nb.ReadTerms);
    }
}
