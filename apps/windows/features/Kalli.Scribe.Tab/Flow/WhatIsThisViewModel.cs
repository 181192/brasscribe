using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tab;

/// <summary>One answer of What is this?: the instrument alone, or a full song it is picked out of.</summary>
public sealed partial class RecordingChoice(Recording recording, string label, string description) : ObservableObject
{
    public Recording Recording { get; } = recording;
    public string Label { get; } = label;
    public string Description { get; } = description;
    [ObservableProperty] public partial bool IsSelected { get; set; }
}

/// <summary>
/// "What is this?": the instrument alone, or a full song it is picked out of. For a guitar or a bass nothing is chosen
/// until the player chooses; a ukulele or a mandolin starts on the instrument alone, as the computer takes it. The
/// answer stays with the recording. The computer writes the notes down for both, so the screen says whether it is
/// there, and nothing is sent until it has said which profiles it has.
/// </summary>
public sealed partial class WhatIsThisViewModel : ObservableObject
{
    private readonly IStrings _s;
    private readonly SongAnswers<SourceAudio> _answers;
    private readonly ComputerProfiles _profiles;
    private readonly Target _target;
    private YourInstrument _instrument = YourInstrument.Default;

    public WhatIsThisViewModel(IStrings strings, SongAnswers<SourceAudio> answers, ComputerProfiles profiles, Target target)
    {
        _s = strings;
        _answers = answers;
        _profiles = profiles;
        _target = target;
        profiles.PropertyChanged += (_, _) => Update();
    }

    [ObservableProperty] public partial SourceAudio? Source { get; set; }

    /// <summary>The two answers, for the instrument the recording is written down for.</summary>
    public System.Collections.ObjectModel.ObservableCollection<RecordingChoice> Choices { get; } = [];

    /// <summary>The computer is connected: it writes the notes down.</summary>
    [ObservableProperty] public partial bool ComputerThere { get; set; }

    /// <summary>What is still missing before Continue, in words; null when nothing is.</summary>
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ContinueCommand))]
    public partial string? Missing { get; set; }

    /// <summary>Continue: the recording is written down with this answer.</summary>
    public event EventHandler<SourceAudio>? Chosen;

    /// <summary>The screen opens for <paramref name="source"/>, to be written down for <paramref name="instrument"/>.</summary>
    public void Open(SourceAudio source, YourInstrument instrument, bool computerThere)
    {
        _instrument = instrument.Valid();
        Source = source;
        ComputerThere = computerThere;
        var given = _answers.Of(source);
        var answer = given.Recording ?? TabSong.StartingAnswer(_instrument);
        Choices.Clear();
        Choices.Add(new RecordingChoice(Recording.Instrument, _s["Tab_What_Instrument"], _s["Tab_What_Instrument_Desc"]) { IsSelected = answer == Recording.Instrument });
        Choices.Add(new RecordingChoice(Recording.Song, _s["Tab_What_Song"], _s[$"Tab_What_Song_Desc_{_instrument.Instrument}"]) { IsSelected = answer == Recording.Song });
        if (given.Recording is null && answer is not null) _answers.Set(source, given with { Recording = answer });
        Update();
    }

    /// <summary>The connection came or went while the screen is open.</summary>
    public void ComputerChanged(bool there)
    {
        ComputerThere = there;
        Update();
    }

    [RelayCommand]
    private void Choose(RecordingChoice? choice)
    {
        if (choice is null || Source is null) return;
        foreach (var c in Choices) c.IsSelected = ReferenceEquals(c, choice);
        _answers.Set(Source, _answers.Of(Source) with { Recording = choice.Recording });
        Update();
    }

    /// <summary>The computer has said what it can write, or could not be asked.</summary>
    private bool Asking => ComputerThere && _profiles.Answer is not { Asking: false };

    private bool TooOld => ComputerThere && !Asking && TabSong.Profile(_instrument.Kind, _profiles.Listed) is null;

    private void Update()
    {
        bool inHand = Source is { } s && File.Exists(s.WavPath);
        Missing = !inHand ? _s["Tab_What_NoRecording"]
            : !ComputerThere ? _s["Tab_What_ConnectFirst"]
            : Asking ? _s["Tab_What_Asking"]
            : TooOld ? _s[$"Tab_TooOld_{_instrument.Instrument}"]
            : _answers.Of(Source).Recording is null ? _s["Tab_What_ChooseOne"]
            : null;
    }

    private bool CanContinue() => Missing is null;

    [RelayCommand(CanExecute = nameof(CanContinue))]
    private void Continue()
    {
        if (Source is { } source) Chosen?.Invoke(this, source);
    }

    /// <summary>The target whose profiles the computer is asked about.</summary>
    public Target Target => _target;
}
