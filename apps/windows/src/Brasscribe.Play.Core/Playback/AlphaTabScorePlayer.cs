using AlphaTab;
using AlphaTab.Core.EcmaScript;
using AlphaTab.Importer;
using AlphaTab.Midi;
using AlphaTab.Model;
using AlphaTab.Synth;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// Plays MusicXML with alphaTab's synth (TinySoundFont on a SoundFont2 file). The synth writes into
/// a <see cref="BufferedSynthOutput"/> that the platform audio device drains. Transposing parts play
/// at concert pitch: alphaTab reads &lt;transpose&gt; as display-only.
/// </summary>
public sealed class AlphaTabScorePlayer : IScorePlayer
{
    public const double MinSpeed = 0.25, MaxSpeed = 1.5;

    private readonly AlphaSynth _synth;
    private readonly Settings _settings = new();
    private Score? _score;
    private MidiFile? _midi;
    private MidiTickLookup? _lookup;
    private readonly HashSet<int> _muted = [], _solo = [];
    private int _transpose;
    private bool _soundFontLoaded;
    private PlaybackState _state = PlaybackState.Stopped;

    public AlphaTabScorePlayer(BufferedSynthOutput output, double bufferMs = 500)
    {
        Output = output;
        _synth = new AlphaSynth(output, bufferMs);
        _synth.MetronomeVolume = 0;
        _synth.CountInVolume = 0;
        _synth.PositionChanged.On((PositionChangedEventArgs e) =>
        {
            Position = new PlaybackPosition(BarAt(e.CurrentTick), e.CurrentTick, e.CurrentTime / 1000.0, e.EndTime / 1000.0);
            PositionChanged?.Invoke(this, Position);
        });
        _synth.StateChanged.On((PlayerStateChangedEventArgs e) =>
        {
            SetState(e.State == PlayerState.Playing ? PlaybackState.Playing : e.Stopped ? PlaybackState.Stopped : PlaybackState.Paused);
        });
        _synth.Finished.On(() => Finished?.Invoke(this, EventArgs.Empty));
        _synth.SoundFontLoadFailed.On((Exception e) => LoadError = e);
        _synth.MidiLoadFailed.On((Exception e) => LoadError = e);
    }

    public BufferedSynthOutput Output { get; }
    public Exception? LoadError { get; private set; }
    public Score? Score => _score;
    public MidiTickLookup? TickLookup => _lookup;

    public IReadOnlyList<TrackInfo> Tracks { get; private set; } = [];
    public int BarCount => _score?.MasterBars.Count ?? 0;
    public bool IsReady => _synth.IsReadyForPlayback;
    public PlaybackState State => _state;
    public PlaybackPosition Position { get; private set; } = new(0, 0, 0, 0);

    public event EventHandler<PlaybackPosition>? PositionChanged;
    public event EventHandler<PlaybackState>? StateChanged;
    public event EventHandler? Finished;

    public double Speed
    {
        get => _synth.PlaybackSpeed;
        set => _synth.PlaybackSpeed = Math.Clamp(value, MinSpeed, MaxSpeed);
    }

    public bool Metronome
    {
        get => _synth.MetronomeVolume > 0;
        set => _synth.MetronomeVolume = value ? 1 : 0;
    }

    public bool CountIn
    {
        get => _synth.CountInVolume > 0;
        set => _synth.CountInVolume = value ? 1 : 0;
    }

    public int Transpose
    {
        get => _transpose;
        set
        {
            _transpose = Math.Clamp(value, -12, 12);
            foreach (var (track, channels) in Channels())
                if (!track.IsPercussion)
                    foreach (var ch in channels) _synth.SetChannelTranspositionPitch(ch, _transpose);
        }
    }

    public void LoadScore(byte[] musicXml)
    {
        _score = ScoreLoader.LoadScoreFromBytes(new Uint8Array(musicXml), _settings);
        Tracks = _score.Tracks.Select(t => new TrackInfo(
            (int)t.Index, t.Name.Replace('\u00A0', ' '), t.Staves.Any(s => s.IsPercussion),
            (int)(t.Staves.FirstOrDefault()?.DisplayTranspositionPitch ?? 0))).ToList();

        _midi = new MidiFile();
        var generator = new MidiFileGenerator(_score, _settings, new AlphaSynthMidiFileHandler(_midi, false));
        generator.Generate();
        _lookup = generator.TickLookup;
        _muted.Clear();
        _solo.Clear();
        _synth.LoadMidiFile(_midi);
        Transpose = _transpose;
    }

    public void LoadSoundFont(byte[] soundFont, bool append = false)
    {
        _synth.LoadSoundFont(new Uint8Array(soundFont), append);
        _soundFontLoaded = true;
    }

    public bool HasSoundFont => _soundFontLoaded;

    public void Play()
    {
        if (!_synth.IsReadyForPlayback) return;
        _synth.Play();
    }

    public void Pause() => _synth.Pause();

    public void Stop() => _synth.Stop();

    public void SeekToBar(int barIndex)
    {
        if (_lookup is null || _lookup.MasterBars.Count == 0) return;
        var mb = _lookup.MasterBars[Math.Clamp(barIndex, 0, _lookup.MasterBars.Count - 1)];
        _synth.TickPosition = mb.Start;
    }

    public (int First, int Last)? Loop { get; private set; }

    public void SetLoop(int? firstBar, int? lastBar)
    {
        if (_lookup is null || firstBar is null || lastBar is null)
        {
            _synth.PlaybackRange = null!;
            _synth.IsLooping = false;
            Loop = null;
            return;
        }
        int a = Math.Clamp(Math.Min(firstBar.Value, lastBar.Value), 0, _lookup.MasterBars.Count - 1);
        int b = Math.Clamp(Math.Max(firstBar.Value, lastBar.Value), 0, _lookup.MasterBars.Count - 1);
        _synth.PlaybackRange = new PlaybackRange { StartTick = _lookup.MasterBars[a].Start, EndTick = _lookup.MasterBars[b].End };
        _synth.IsLooping = true;
        Loop = (a, b);
    }

    public void SetMute(int track, bool mute)
    {
        if (mute) _muted.Add(track); else _muted.Remove(track);
        foreach (var ch in ChannelsOf(track)) _synth.SetChannelMute(ch, mute);
    }

    public void SetSolo(int track, bool solo)
    {
        if (solo) _solo.Add(track); else _solo.Remove(track);
        foreach (var ch in ChannelsOf(track)) _synth.SetChannelSolo(ch, solo);
    }

    public void SetVolume(int track, double volume)
    {
        foreach (var ch in ChannelsOf(track)) _synth.SetChannelVolume(ch, Math.Clamp(volume, 0, 1));
    }

    public bool IsMuted(int track) => _muted.Contains(track);
    public bool IsSolo(int track) => _solo.Contains(track);

    public byte[] ExportMidi()
    {
        if (_score is null) throw new InvalidOperationException("No score loaded");
        // The playback MIDI carries synth-only events; a Standard MIDI File needs SMF1 mode.
        var smf = new MidiFile { Format = MidiFileFormat.MultiTrack };
        new MidiFileGenerator(_score, _settings, new AlphaSynthMidiFileHandler(smf, true)).Generate();
        var bin = smf.ToBinary();
        var bytes = new byte[(int)bin.Length];
        for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)bin[i];
        return bytes;
    }

    /// <summary>Tick range of a bar, for highlighting and "listen to this bar".</summary>
    public (double Start, double End)? BarTicks(int barIndex) =>
        _lookup is null || barIndex < 0 || barIndex >= _lookup.MasterBars.Count
            ? null
            : (_lookup.MasterBars[barIndex].Start, _lookup.MasterBars[barIndex].End);

    public void Dispose() => _synth.Destroy();

    private int BarAt(double tick)
    {
        if (_lookup is null) return 0;
        var bars = _lookup.MasterBars;
        int lo = 0, hi = bars.Count - 1;
        while (lo < hi)
        {
            int mid = (lo + hi + 1) / 2;
            if (bars[mid].Start <= tick) lo = mid; else hi = mid - 1;
        }
        return lo;
    }

    private IEnumerable<(TrackInfo Track, double[] Channels)> Channels()
    {
        if (_score is null) yield break;
        foreach (var t in Tracks) yield return (t, ChannelsOf(t.Index));
    }

    private double[] ChannelsOf(int track)
    {
        if (_score is null || track < 0 || track >= _score.Tracks.Count) return [];
        var info = _score.Tracks[track].PlaybackInfo;
        return info.PrimaryChannel == info.SecondaryChannel ? [info.PrimaryChannel] : [info.PrimaryChannel, info.SecondaryChannel];
    }

    private void SetState(PlaybackState s)
    {
        if (_state == s) return;
        _state = s;
        StateChanged?.Invoke(this, s);
    }
}
