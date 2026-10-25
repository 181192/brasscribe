using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;

namespace Kalli.Scribe.Tab;

/// <summary>One choice of a row on Your instrument: its value and its words.</summary>
public sealed record Choice<T>(T Value, string Label);

/// <summary>
/// "Your instrument": what new tabs are written for. One question per row (instrument, strings or size, tuning, which
/// hand frets, what the player reads), all on one screen; nothing is kept until Save. A song already written keeps
/// the instrument it was made for.
/// </summary>
public sealed partial class YourInstrumentViewModel : ObservableObject
{
    private readonly YourInstrumentStore _store;
    private readonly IStrings _s;
    private bool _filling;

    public YourInstrumentViewModel(YourInstrumentStore store, IStrings strings)
    {
        _store = store;
        _s = strings;
        Instruments = [.. Tab.Instruments.All.Select(i => new Choice<Instrument>(i, InstrumentName(i)))];
        Hands = [.. Enum.GetValues<FrettingHand>().Select(h => new Choice<FrettingHand>(h, strings[$"Tab_Hand_{h}"]))];
        ReadsChoices = [.. Enum.GetValues<Reads>().Select(r => new Choice<Reads>(r, strings[$"Tab_Reads_{r}"]))];
        Reset();
    }

    /// <summary>The answer as it is stored.</summary>
    public YourInstrument Stored => _store.Load();

    /// <summary>The answer on screen, not yet saved.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KindLabel), nameof(HandNote))]
    public partial YourInstrument Draft { get; set; } = YourInstrument.Default;

    public IReadOnlyList<Choice<Instrument>> Instruments { get; }
    public ObservableCollection<Choice<FrettedInstrument>> Kinds { get; } = [];
    public ObservableCollection<Choice<string>> Tunings { get; } = [];
    public IReadOnlyList<Choice<FrettingHand>> Hands { get; }
    public IReadOnlyList<Choice<Reads>> ReadsChoices { get; }

    [ObservableProperty] public partial Choice<Instrument>? SelectedInstrument { get; set; }
    [ObservableProperty] public partial Choice<FrettedInstrument>? SelectedKind { get; set; }
    [ObservableProperty] public partial Choice<string>? SelectedTuning { get; set; }
    [ObservableProperty] public partial Choice<FrettingHand>? SelectedHand { get; set; }
    [ObservableProperty] public partial Choice<Reads>? SelectedReads { get; set; }

    /// <summary>"Strings" for a guitar or a bass, "Size" for a ukulele; a mandolin has one kind and no row.</summary>
    public string KindLabel => Draft.Instrument == Instrument.Ukulele ? _s["Tab_Size"] : _s["Tab_Strings"];

    /// <summary>The instrument has more than one kind to choose from.</summary>
    public bool HasKinds => Kinds.Count > 1;

    /// <summary>Under the hand row: tab looks the same either way.</summary>
    public string HandNote => _s["Tab_Hand_Note"];

    /// <summary>Saved, or Not now: the screen is done.</summary>
    public event EventHandler? Done;

    /// <summary>The screen starts again from what is stored: choices left without Save are gone.</summary>
    public void Reset() => Fill(_store.Load());

    private void Fill(YourInstrument value)
    {
        _filling = true;
        try
        {
            var v = value.Valid();
            SelectedInstrument = Instruments.First(i => i.Value == v.Instrument);
            Kinds.Clear();
            foreach (var k in v.Instrument.Kinds()) Kinds.Add(new Choice<FrettedInstrument>(k, KindName(k)));
            OnPropertyChanged(nameof(HasKinds));
            SelectedKind = Kinds.First(k => k.Value == v.Kind);
            Tunings.Clear();
            foreach (var t in v.Tunings) Tunings.Add(new Choice<string>(t, TuningName(t, _s)));
            SelectedTuning = Tunings.FirstOrDefault(t => t.Value == v.Tuning) ?? Tunings.FirstOrDefault();
            SelectedHand = Hands.First(h => h.Value == v.Hand);
            SelectedReads = ReadsChoices.First(r => r.Value == v.Reads);
            // Last: the screen fills its rows again when it changes, from everything above.
            Draft = v;
        }
        finally { _filling = false; }
    }

    partial void OnSelectedInstrumentChanged(Choice<Instrument>? value)
    {
        if (!_filling && value is not null) Fill(Draft.WithInstrument(value.Value));
    }

    partial void OnSelectedKindChanged(Choice<FrettedInstrument>? value)
    {
        if (!_filling && value is not null) Fill(Draft.WithKind(value.Value));
    }

    partial void OnSelectedTuningChanged(Choice<string>? value)
    {
        if (!_filling && value is not null) Draft = (Draft with { Tuning = value.Value }).Valid();
    }

    partial void OnSelectedHandChanged(Choice<FrettingHand>? value)
    {
        if (!_filling && value is not null) Draft = Draft with { Hand = value.Value };
    }

    partial void OnSelectedReadsChanged(Choice<Reads>? value)
    {
        if (!_filling && value is not null) Draft = Draft with { Reads = value.Value };
    }

    /// <summary>The answer is kept now, not while choosing (WCAG 3.2.2).</summary>
    [RelayCommand]
    private void Save()
    {
        _store.Save(Draft);
        OnPropertyChanged(nameof(Stored));
        Done?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>Nothing is kept: tabs are written for what is stored (a six-string guitar in standard tuning before anything is).</summary>
    [RelayCommand]
    private void NotNow()
    {
        Reset();
        Done?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>What Settings shows as the value of its "Your instrument" row: "Guitar, 6 strings · Drop D".</summary>
    public string Summary(YourInstrument value)
    {
        var v = value.Valid();
        string instrument = v.Instrument switch
        {
            Instrument.Guitar or Instrument.Bass when v.Strings is { } n => _s.Format("Tab_InstrumentWithStrings", InstrumentName(v.Instrument), n),
            Instrument.Ukulele => KindName(v.Kind),
            _ => InstrumentName(v.Instrument),
        };
        return _s.Format("Tab_InstrumentValue", instrument, TuningName(v.Tuning, _s));
    }

    private string InstrumentName(Instrument i) => _s[$"Tab_Instrument_{i}"];

    private string KindName(FrettedInstrument kind) =>
        YourInstrument.StringsOf(kind) is { } n ? _s.Format("Tab_StringsCount", n) : _s[$"Tab_Kind_{kind}"];

    /// <summary>A tuning's name ("Drop D"); the id itself for one this version has no words for.</summary>
    public static string TuningName(string id, IStrings s)
    {
        string key = "Tab_Tuning_" + string.Concat(id.Split('-').Select(p => p.Length == 0 ? p : char.ToUpperInvariant(p[0]) + p[1..]));
        string name = s[key];
        return name == key ? id : name;
    }
}
