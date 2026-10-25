using System.ComponentModel;
using Kalli.Scribe.Tab;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Kalli.Fretscribe.Views;

/// <summary>
/// Your instrument. Each row is a combo box of the row's words; the screen fills them from the view model, and a choice
/// goes back to it, which fills the rows that depend on it again (a bass has other strings and tunings than a guitar).
/// </summary>
public sealed partial class YourInstrumentPage : Page, IScreenPage
{
    private bool _filling;

    public YourInstrumentPage() => InitializeComponent();

    public YourInstrumentViewModel ViewModel { get; private set; } = null!;

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        ViewModel = ((TabFlowViewModel)e.Parameter).Instrument;
        ViewModel.PropertyChanged += OnViewModelChanged;
        Bindings.Update();
        Fill();
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e) => ViewModel.PropertyChanged -= OnViewModelChanged;

    public void FocusHeading() => Heading.Focus(FocusState.Programmatic);

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(YourInstrumentViewModel.Draft)) Fill();
    }

    /// <summary>Every row as the view model has it now.</summary>
    private void Fill()
    {
        _filling = true;
        try
        {
            Set(InstrumentBox, ViewModel.Instruments.Select(c => c.Label), ViewModel.Instruments.ToList().FindIndex(c => c == ViewModel.SelectedInstrument));
            Set(KindBox, ViewModel.Kinds.Select(c => c.Label), ViewModel.Kinds.ToList().FindIndex(c => c == ViewModel.SelectedKind));
            Set(TuningBox, ViewModel.Tunings.Select(c => c.Label), ViewModel.Tunings.ToList().FindIndex(c => c == ViewModel.SelectedTuning));
            Set(HandBox, ViewModel.Hands.Select(c => c.Label), ViewModel.Hands.ToList().FindIndex(c => c == ViewModel.SelectedHand));
            Set(ReadsBox, ViewModel.ReadsChoices.Select(c => c.Label), ViewModel.ReadsChoices.ToList().FindIndex(c => c == ViewModel.SelectedReads));
        }
        finally { _filling = false; }
    }

    private static void Set(ComboBox box, IEnumerable<string> labels, int selected)
    {
        var items = labels.ToList();
        if (!box.Items.Cast<object>().Select(o => o as string).SequenceEqual(items))
        {
            box.Items.Clear();
            foreach (var l in items) box.Items.Add(l);
        }
        box.SelectedIndex = selected;
    }

    private void OnInstrumentChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_filling && InstrumentBox.SelectedIndex is >= 0 and var i && i < ViewModel.Instruments.Count) ViewModel.SelectedInstrument = ViewModel.Instruments[i];
    }

    private void OnKindChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_filling && KindBox.SelectedIndex is >= 0 and var i && i < ViewModel.Kinds.Count) ViewModel.SelectedKind = ViewModel.Kinds[i];
    }

    private void OnTuningChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_filling && TuningBox.SelectedIndex is >= 0 and var i && i < ViewModel.Tunings.Count) ViewModel.SelectedTuning = ViewModel.Tunings[i];
    }

    private void OnHandChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_filling && HandBox.SelectedIndex is >= 0 and var i && i < ViewModel.Hands.Count) ViewModel.SelectedHand = ViewModel.Hands[i];
    }

    private void OnReadsChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_filling && ReadsBox.SelectedIndex is >= 0 and var i && i < ViewModel.ReadsChoices.Count) ViewModel.SelectedReads = ViewModel.ReadsChoices[i];
    }
}
