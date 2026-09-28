using Brasscribe.Play.Core.Seats;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Views;

/// <summary>
/// The instrument, part and clef questions of "What do you play?", on the first run and in Settings. The radio
/// items are built here from <see cref="SeatPickerViewModel"/>, so a changed instrument always starts its part
/// question with nothing chosen and its clef question on the band's own clef.
/// </summary>
public sealed partial class SeatPickerView : UserControl
{
    /// <summary>Text scaled this much or more puts the instruments in one column and the parts in a list.</summary>
    public const double OneColumnTextScale = 1.5;

    private readonly Windows.UI.ViewManagement.UISettings _ui = new();
    private bool _filling;

    public SeatPickerView()
    {
        InitializeComponent();
        _ui.TextScaleFactorChanged += (_, _) => DispatcherQueue.TryEnqueue(Layout);
    }

    public SeatPickerViewModel? ViewModel { get; private set; }

    public void Show(SeatPickerViewModel viewModel)
    {
        ViewModel = viewModel;
        _filling = true;
        InstrumentChoices.Items.Clear();
        foreach (var tile in viewModel.Tiles) InstrumentChoices.Items.Add(Choice(tile.Label, tile.SpokenLabel, 56, tile.Detail));
        InstrumentChoices.SelectedIndex = viewModel.InstrumentIndex;
        _filling = false;
        FillFollowUps();
        Layout();
    }

    /// <summary>Moves keyboard focus to the first question (Settings opens the picker there).</summary>
    public void FocusFirst()
    {
        if (InstrumentChoices.Items.Count == 0) return;
        var target = InstrumentChoices.SelectedIndex >= 0 ? InstrumentChoices.Items[InstrumentChoices.SelectedIndex] : InstrumentChoices.Items[0];
        (target as Control)?.Focus(FocusState.Programmatic);
    }

    private RadioButton Choice(string text, string spoken, double minHeight, string detail = "")
    {
        object content = text;
        if (detail.Length > 0)
        {
            var lines = new StackPanel { Spacing = 2 };
            lines.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap });
            var sub = new TextBlock { Text = detail, TextWrapping = TextWrapping.Wrap };
            if (Application.Current.Resources.TryGetValue("MutedStyle", out var muted)) sub.Style = (Style)muted;
            lines.Children.Add(sub);
            content = lines;
        }
        var button = new RadioButton { Content = content, MinHeight = minHeight, MinWidth = 160, Margin = new Thickness(0, 0, 8, 8) };
        if (Resources.TryGetValue("ChoiceCardStyle", out var style) || Application.Current.Resources.TryGetValue("ChoiceCardStyle", out style))
            button.Style = (Style)style;
        // The accessible name contains the visible words (2.5.3); ♭ is read as "flat".
        if (spoken != text || detail.Length > 0) AutomationProperties.SetName(button, spoken);
        return button;
    }

    private void OnInstrumentChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_filling || ViewModel is null) return;
        ViewModel.InstrumentIndex = InstrumentChoices.SelectedIndex;
        FillFollowUps();
        Layout();
    }

    private void OnPartChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_filling || ViewModel is null) return;
        ViewModel.PartIndex = PartChoices.SelectedIndex;
    }

    private void OnReadsChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_filling || ViewModel is null || ReadsChoices.SelectedIndex < 0) return;
        ViewModel.ReadsIndex = ReadsChoices.SelectedIndex;
    }

    /// <summary>Which part? and You read for the chosen instrument: shown only when there is a choice.</summary>
    private void FillFollowUps()
    {
        if (ViewModel is null) return;
        _filling = true;
        PartChoices.Items.Clear();
        foreach (var name in ViewModel.PartChoices) PartChoices.Items.Add(Choice(name, ViewModel.Catalog.Spoken(name), 44));
        PartChoices.SelectedIndex = ViewModel.PartIndex;
        PartChoices.Visibility = ViewModel.ShowsParts ? Visibility.Visible : Visibility.Collapsed;
        ReadsChoices.Items.Clear();
        foreach (var label in ViewModel.ReadsChoices) ReadsChoices.Items.Add(Choice(label, ViewModel.Catalog.Spoken(label), 44));
        ReadsChoices.SelectedIndex = ViewModel.ShowsReads ? Math.Max(0, ViewModel.ReadsIndex) : -1;
        ReadsChoices.Visibility = ViewModel.ShowsReads ? Visibility.Visible : Visibility.Collapsed;
        _filling = false;
    }

    /// <summary>Two columns of instruments and a row of parts; one column and a list at large text (1.4.4, 1.4.10).</summary>
    private void Layout()
    {
        bool large = _ui.TextScaleFactor >= OneColumnTextScale;
        InstrumentChoices.MaxColumns = large ? 1 : 2;
        PartChoices.MaxColumns = large ? 1 : Math.Max(1, PartChoices.Items.Count);
        ReadsChoices.MaxColumns = large ? 1 : Math.Max(1, ReadsChoices.Items.Count);
    }
}
