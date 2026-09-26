using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>One number of the beat counter ("1 2 3 4"); the current one is underlined, never flashed.</summary>
public sealed record BeatCell(int Number, bool IsCurrent);

/// <summary>One mixer row: mute, solo and volume for a part.</summary>
public sealed partial class MixerPartViewModel(IScorePlayer player, TrackInfo track, string muteLabel = "", string soloLabel = "") : ObservableObject
{
    public int Index { get; } = track.Index;
    public string Name { get; } = track.Name;
    /// <summary>Accessible names of the M and S buttons ("Mute Solo Cornet").</summary>
    public string MuteLabel { get; } = muteLabel;
    public string SoloLabel { get; } = soloLabel;
    public bool IsPercussion { get; } = track.IsPercussion;

    [ObservableProperty] public partial bool IsMuted { get; set; }
    [ObservableProperty] public partial bool IsSolo { get; set; }
    [ObservableProperty] public partial double Volume { get; set; } = 100;

    /// <summary>The player's own part ("your part" in the list; Mute my part silences it).</summary>
    [ObservableProperty] public partial bool IsMine { get; set; }

    partial void OnIsMutedChanged(bool value) => player.SetMute(Index, value);
    partial void OnIsSoloChanged(bool value) => player.SetSolo(Index, value);
    partial void OnVolumeChanged(double value) => player.SetVolume(Index, value / 100.0);
}

/// <summary>
/// Transport and practice controls: play/pause, speed 25–150 % in 5 % steps, a bar loop set with
/// number fields (no dragging needed), count-in, metronome, transpose, per-part mixer and play-along
/// (mute your own part). Position changes are exposed as text for the status region.
/// </summary>
public sealed partial class PlayerViewModel : ObservableObject
{
    public const int SpeedStep = 5;

    private readonly IScorePlayer _player;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly IUiDispatcher _ui;
    private int _lastBar = -1;

    public PlayerViewModel(IScorePlayer player, IAnnouncer announcer, IStrings strings, IUiDispatcher ui)
    {
        _player = player;
        _announcer = announcer;
        _s = strings;
        _ui = ui;
        _player.StateChanged += (_, st) => _ui.Post(() => IsPlaying = st == PlaybackState.Playing);
        _player.PositionChanged += (_, p) => _ui.Post(() => OnPosition(p));
        _player.Finished += (_, _) => _ui.Post(() => IsPlaying = false);
    }

    public IScorePlayer Player => _player;
    public ObservableCollection<MixerPartViewModel> Parts { get; } = [];

    [ObservableProperty] public partial bool IsPlaying { get; set; }
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(LastBar))]
    public partial int BarCount { get; set; }

    /// <summary>The highest bar number as a double, for NumberBox.Maximum.</summary>
    public double LastBar => Math.Max(1, BarCount);
    [ObservableProperty] public partial int CurrentBar { get; set; } = 1;
    [ObservableProperty] public partial string PositionText { get; set; } = "";

    [ObservableProperty] public partial double SpeedPercent { get; set; } = 100;
    [ObservableProperty] public partial bool CountIn { get; set; }
    [ObservableProperty] public partial bool Metronome { get; set; }
    [ObservableProperty] public partial int Transpose { get; set; }

    [ObservableProperty] public partial double LoopStart { get; set; } = 1;
    [ObservableProperty] public partial double LoopEnd { get; set; } = 1;
    [ObservableProperty] public partial bool IsLooping { get; set; }
    [ObservableProperty] public partial string LoopText { get; set; } = "";

    /// <summary>The part the player plays themself; muted while play-along is on.</summary>
    [ObservableProperty] public partial MixerPartViewModel? PlayAlongPart { get; set; }

    partial void OnPlayAlongPartChanged(MixerPartViewModel? oldValue, MixerPartViewModel? newValue)
    {
        if (oldValue is not null) oldValue.IsMine = false;
        if (newValue is not null) newValue.IsMine = true;
    }
    [ObservableProperty] public partial bool IsPlayingAlong { get; set; }

    public void Load(byte[] musicXml)
    {
        _player.LoadScore(musicXml);
        Parts.Clear();
        foreach (var t in _player.Tracks)
            Parts.Add(new MixerPartViewModel(_player, t, _s.Format("Mixer_Mute", t.Name), _s.Format("Mixer_Solo", t.Name)));
        BarCount = _player.BarCount;
        LoopStart = 1;
        LoopEnd = Math.Min(4, BarCount);
        IsLooping = false;
        LoopText = _s["Player_LoopOff"];
        UpdatePositionText(0);
    }

    [RelayCommand]
    private void PlayPause()
    {
        if (!_player.IsReady)
        {
            _announcer.Announce(_s["Player_NotReady"], AnnouncementKind.Important);
            return;
        }
        if (_player.State == PlaybackState.Playing) _player.Pause();
        else _player.Play();
    }

    [RelayCommand]
    private void Stop()
    {
        _player.Stop();
        IsPlayingAlong = false;
    }

    [RelayCommand] private void SlowerBy5() => SpeedPercent -= SpeedStep;
    [RelayCommand] private void FasterBy5() => SpeedPercent += SpeedStep;
    [RelayCommand] private void ResetSpeed() => SpeedPercent = 100;

    partial void OnSpeedPercentChanged(double value)
    {
        double snapped = Math.Clamp(Math.Round(value / SpeedStep) * SpeedStep, 25, 150);
        if (Math.Abs(snapped - value) > 1e-9)
        {
            SpeedPercent = snapped;
            return;
        }
        _player.Speed = snapped / 100.0;
        UpdateTempoText(Math.Max(0, CurrentBar - 1));
    }

    partial void OnCountInChanged(bool value) => _player.CountIn = value;
    partial void OnMetronomeChanged(bool value) => _player.Metronome = value;
    partial void OnTransposeChanged(int value) => _player.Transpose = value;

    [RelayCommand]
    private void SetLoop()
    {
        int a = (int)Math.Clamp(Math.Round(LoopStart), 1, Math.Max(1, BarCount));
        int b = (int)Math.Clamp(Math.Round(LoopEnd), 1, Math.Max(1, BarCount));
        if (b < a) (a, b) = (b, a);
        LoopStart = a;
        LoopEnd = b;
        _player.SetLoop(a - 1, b - 1);
        IsLooping = true;
        LoopText = _s.Format("Player_LoopSet", a, b);
        _announcer.Announce(LoopText);
    }

    [RelayCommand]
    private void ClearLoop()
    {
        _player.SetLoop(null, null);
        IsLooping = false;
        LoopText = _s["Player_LoopOff"];
        _announcer.Announce(LoopText);
    }

    [RelayCommand]
    private void ToggleLoop()
    {
        if (IsLooping) ClearLoop(); else SetLoop();
    }

    /// <summary>Loop start/end at a bar (the [ and ] keys in the score).</summary>
    public void SetLoopStartAt(int bar)
    {
        LoopStart = bar;
        if (LoopEnd < bar) LoopEnd = bar;
        _announcer.Announce(_s.Format("Player_LoopStartAt", bar));
    }

    public void SetLoopEndAt(int bar)
    {
        LoopEnd = bar;
        if (LoopStart > bar) LoopStart = bar;
        SetLoop();
    }

    public void SeekToBar(int bar) => _player.SeekToBar(bar - 1);

    [RelayCommand]
    private void PreviousBar() => SeekToBar(Math.Max(1, CurrentBar - 1));

    [RelayCommand]
    private void NextBar() => SeekToBar(Math.Min(Math.Max(1, BarCount), CurrentBar + 1));

    /// <summary>Plays one bar, looped (the "Listen to this bar" action).</summary>
    public void PlayBar(int bar)
    {
        _player.SetLoop(bar - 1, bar - 1);
        _player.SeekToBar(bar - 1);
        _player.Play();
        IsLooping = true;
        LoopStart = LoopEnd = bar;
        LoopText = _s.Format("Player_LoopSet", bar, bar);
    }

    /// <summary>Plays from a bar to the end (Shift+P in the score).</summary>
    public void PlayFrom(int bar)
    {
        if (IsLooping) ClearLoop();
        _player.SeekToBar(bar - 1);
        _player.Play();
    }

    [RelayCommand]
    private void TogglePlayAlong()
    {
        IsPlayingAlong = !IsPlayingAlong;
        if (PlayAlongPart is { } part) part.IsMuted = IsPlayingAlong;
        _announcer.Announce(IsPlayingAlong
            ? _s.Format("Player_PlayAlongOn", PlayAlongPart?.Name ?? "")
            : _s["Player_PlayAlongOff"]);
        if (IsPlayingAlong)
        {
            _player.CountIn = true;
            if (_player.State != PlaybackState.Playing) _player.Play();
        }
        else
        {
            _player.CountIn = CountIn;
        }
    }

    public void ToggleMute(int partIndex)
    {
        if (partIndex < 0 || partIndex >= Parts.Count) return;
        var p = Parts[partIndex];
        p.IsMuted = !p.IsMuted;
        _announcer.Announce(_s.Format(p.IsMuted ? "Player_Muted" : "Player_Unmuted", p.Name));
    }

    public void ToggleSolo(int partIndex)
    {
        if (partIndex < 0 || partIndex >= Parts.Count) return;
        var p = Parts[partIndex];
        p.IsSolo = !p.IsSolo;
        _announcer.Announce(_s.Format(p.IsSolo ? "Player_Soloed" : "Player_Unsoloed", p.Name));
    }

    /// <summary>"Mute my part": the player's own part is silent so they can play it (on by default in the part view).</summary>
    [ObservableProperty] public partial bool MuteMyPart { get; set; }

    partial void OnMuteMyPartChanged(bool value)
    {
        if (PlayAlongPart is { } part) part.IsMuted = value;
        IsPlayingAlong = value;
        _announcer.Announce(value ? _s.Format("Player_PlayAlongOn", PlayAlongPart?.Name ?? "") : _s["Player_PlayAlongOff"]);
    }

    /// <summary>"Bar 13, beat 2".</summary>
    [ObservableProperty] public partial string BarBeatText { get; set; } = "";

    /// <summary>"of 64 · ♩ = 102 (slowed from 136)".</summary>
    [ObservableProperty] public partial string PositionDetail { get; set; } = "";

    public ObservableCollection<BeatCell> BeatCounter { get; } = [];

    private int _lastBeat = -1;

    private void OnPosition(PlaybackPosition p)
    {
        var (beat, beats) = _player.BeatAt(p);
        if (p.BarIndex == _lastBar && beat == _lastBeat) return;
        bool newBar = p.BarIndex != _lastBar;
        _lastBar = p.BarIndex;
        _lastBeat = beat;
        if (newBar) UpdatePositionText(p.BarIndex);
        BarBeatText = _s.Format("Player_BarBeat", p.BarIndex + 1, beat);
        if (BeatCounter.Count != beats) { BeatCounter.Clear(); for (int i = 1; i <= beats; i++) BeatCounter.Add(new BeatCell(i, i == beat)); }
        else for (int i = 0; i < beats; i++) if (BeatCounter[i].IsCurrent != (i + 1 == beat)) BeatCounter[i] = new BeatCell(i + 1, i + 1 == beat);
    }

    private void UpdatePositionText(int barIndex)
    {
        CurrentBar = barIndex + 1;
        PositionText = _s.Format("Player_Position", CurrentBar, Math.Max(1, BarCount));
        if (BarBeatText.Length == 0 || _lastBeat < 0) BarBeatText = _s.Format("Player_BarBeat", CurrentBar, 1);
        UpdateTempoText(barIndex);
    }

    private void UpdateTempoText(int barIndex)
    {
        string of = _s.Format("Player_Of", Math.Max(1, BarCount));
        if (_player.TempoAt(barIndex) is not { } tempo)
        {
            PositionDetail = of;
            return;
        }
        int written = (int)Math.Round(tempo), played = (int)Math.Round(tempo * SpeedPercent / 100);
        string t = played == written ? _s.Format("Player_Tempo", written)
            : _s.Format(played < written ? "Player_TempoSlowed" : "Player_TempoFaster", played, written);
        PositionDetail = of + " · " + t;
    }
}
