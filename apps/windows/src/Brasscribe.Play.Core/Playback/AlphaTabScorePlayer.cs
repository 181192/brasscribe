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

    /// <summary>Synth master gain: unity; the output stage (<see cref="OutputStage"/>) sets the level.</summary>
    public const double MasterVolume = 1.0;

    private readonly AlphaSynth _synth;
    private readonly Settings _settings = new();
    private Score? _score;
    private MidiFile? _midi;
    private MidiTickLookup? _lookup;
    private byte[]? _musicXml;
    private readonly HashSet<int> _muted = [], _solo = [];
    private int _transpose;
    private bool _soundFontLoaded;
    private PlaybackState _state = PlaybackState.Stopped;

    public AlphaTabScorePlayer(BufferedSynthOutput output, double bufferMs = 500)
    {
        Output = output;
        _synth = new AlphaSynth(output, bufferMs);
        // alphaTab is not thread-safe: every synth call below holds Output.SyncRoot, the lock the
        // audio thread takes when it asks the synth for samples.
        _synth.MetronomeVolume = 0;
        _synth.CountInVolume = 0;
        // The band's level is the output stage's make-up gain; its soft limiter catches the tutti peaks.
        _synth.MasterVolume = MasterVolume;
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
    private object Gate => Output.SyncRoot;
    public Exception? LoadError { get; private set; }
    public Score? Score => _score;
    public MidiTickLookup? TickLookup => _lookup;

    public IReadOnlyList<TrackInfo> Tracks { get; private set; } = [];
    public int BarCount => _score?.MasterBars.Count ?? 0;
    public bool IsReady { get { lock (Gate) return _synth.IsReadyForPlayback; } }
    public PlaybackState State => _state;
    public PlaybackPosition Position { get; private set; } = new(0, 0, 0, 0);

    public event EventHandler<PlaybackPosition>? PositionChanged;
    public event EventHandler<PlaybackState>? StateChanged;
    public event EventHandler? Finished;

    public double Speed
    {
        get { lock (Gate) return _synth.PlaybackSpeed; }
        set { lock (Gate) _synth.PlaybackSpeed = Math.Clamp(value, MinSpeed, MaxSpeed); }
    }

    public bool Metronome
    {
        get { lock (Gate) return _synth.MetronomeVolume > 0; }
        set { lock (Gate) _synth.MetronomeVolume = value ? Math.Pow(10, PlaybackLevels.MetronomeGainDb / 20) : 0; }
    }

    public bool CountIn
    {
        get { lock (Gate) return _synth.CountInVolume > 0; }
        set { lock (Gate) _synth.CountInVolume = value ? 1 : 0; }
    }

    public int Transpose
    {
        get => _transpose;
        set
        {
            _transpose = Math.Clamp(value, -12, 12);
            lock (Gate)
                foreach (var (track, channels) in Channels())
                    if (!track.IsPercussion)
                        foreach (var ch in channels) _synth.SetChannelTranspositionPitch(ch, _transpose);
        }
    }

    public void LoadScore(byte[] musicXml)
    {
        _musicXml = musicXml;
        _score = ScoreLoader.LoadScoreFromBytes(new Uint8Array(musicXml), _settings);
        Tracks = _score.Tracks.Select(t => new TrackInfo(
            (int)t.Index, t.Name.Replace('\u00A0', ' '), t.Staves.Any(s => s.IsPercussion),
            (int)(t.Staves.FirstOrDefault()?.DisplayTranspositionPitch ?? 0))).ToList();

        _gains = Prepare(_score, forMidiFile: false);

        _midi = new MidiFile();
        var generator = new MidiFileGenerator(_score, _settings, new AlphaSynthMidiFileHandler(_midi, false));
        generator.Generate();
        _lookup = generator.TickLookup;
        // Score-exact velocities and times: the humanizer moves only the MIDI.
        BandEstimateLufs = PlaybackLevels.BandEstimateLufs(PitchedNotes(_score));
        RecordingLevel.SetArrangement(BandEstimateLufs);
        HumanizedNotes = Humanizer is { } humanize
            ? MidiHumanizer.Apply(_midi, Tracks.Select(t => new MidiHumanizer.Track(t.Index, t.Name, t.IsPercussion,
                ChannelsOf(t.Index).Select(c => (int)c).ToList())).ToList(), humanize, PerformanceJson)
            : 0;
        AddReleaseTail(_midi);
        _muted.Clear();
        _solo.Clear();
        lock (Gate) _synth.LoadMidiFile(_midi);
        _volumes = Tracks.Select(_ => 1.0).ToArray();
        for (int t = 0; t < Tracks.Count; t++) ApplyVolume(t);
        Transpose = _transpose;
    }

    public void LoadSoundFont(byte[] soundFont, bool append = false)
    {
        lock (Gate) _synth.LoadSoundFont(new Uint8Array(soundFont), append);
        _soundFontLoaded = true;
    }

    public bool HasSoundFont => _soundFontLoaded;

    /// <summary>
    /// Where the band sounds were expected when they are missing (null when they loaded). The UI
    /// shows <see cref="SoundsMissingKey"/> with this path under details.
    /// </summary>
    public string? SoundsMissingFrom { get; set; }

    /// <summary>Resource key of the one-line message for missing band sounds; its details key adds "_Details" ({0} = path).</summary>
    public const string SoundsMissingKey = "Player_SoundsMissing";

    /// <summary>
    /// Humanizes the playback timing and velocity of each part when a score loads (the Rust core's
    /// humanizer); null plays the score's exact timing. MIDI export always stays score-exact.
    /// </summary>
    public Humanize? Humanizer { get; set; }

    /// <summary>Composition JSON of the score, so the humanizer can follow the recording's ensemble timing.</summary>
    public string? PerformanceJson { get; set; }

    /// <summary>Notes the humanizer moved in the loaded score.</summary>
    public int HumanizedNotes { get; private set; }

    /// <summary>
    /// The loaded arrangement's estimated band loudness (<see cref="PlaybackLevels.BandEstimateLufs"/>),
    /// null without pitched notes. Loading a score hands it to <see cref="RecordingLevel"/>.
    /// </summary>
    public double? BandEstimateLufs { get; private set; }

    /// <summary>
    /// The pitched notes of a loaded score as (start, end, velocity), times in quarter notes: every
    /// note of every beat as the MIDI generator places it (tied pieces each count), grace notes, rests
    /// and percussion tracks left out. The velocity is the one alphaTab plays: the note's dynamics
    /// plus one step per accent, two per marcato (<see cref="AccentSteps"/>).
    /// </summary>
    public static List<(double Start, double End, double Velocity)> PitchedNotes(Score score)
    {
        const double ticksPerQuarter = 960; // MidiUtils.QuarterTime
        var notes = new List<(double, double, double)>();
        foreach (var track in score.Tracks)
        {
            if (track.Staves.Any(s => s.IsPercussion)) continue;
            foreach (var staff in track.Staves)
                foreach (var bar in staff.Bars)
                    foreach (var voice in bar.Voices)
                        foreach (var beat in voice.Beats)
                        {
                            if (beat.IsRest || beat.GraceType != GraceType.None || beat.PlaybackDuration <= 0) continue;
                            double start = beat.AbsolutePlaybackStart / ticksPerQuarter, end = start + beat.PlaybackDuration / ticksPerQuarter;
                            foreach (var note in beat.Notes)
                            {
                                double v = DynamicVelocity(note.Dynamics) + 16 * AccentSteps(note.Accentuated);
                                notes.Add((start, end, Math.Clamp(v, 1, 127)));
                            }
                        }
        }
        return notes;
    }

    /// <summary>
    /// The velocity of a dynamics mark (dynamics.velocity, alphaTab's MidiUtils.dynamicToVelocity,
    /// which is internal): looked up by the mark's name.
    /// </summary>
    internal static int DynamicVelocity(DynamicValue d) =>
        PlaybackLevels.DynamicsVelocity.TryGetValue(d.ToString().ToLowerInvariant(), out int v) ? v : PlaybackLevels.DynamicsVelocity["f"];

    /// <summary>dynamics.accent_steps: an accent one step (16) up, a marcato (heavy accent) two.</summary>
    private static int AccentSteps(AccentuationType a) => a switch
    {
        AccentuationType.Normal => 1,
        AccentuationType.Heavy => 2,
        _ => 0,
    };

    /// <summary>The MIDI the synth plays (after humanization).</summary>
    internal MidiFile? PlaybackMidi => _midi;

    /// <summary>Optional MIDI program per part name (0-based), applied when a score loads.</summary>
    public Func<string, int?>? ProgramMap { get; set; }

    /// <summary>
    /// Optional preset and balance per part (the band SoundFont), from the part name and its
    /// 0-based MusicXML program; wins over <see cref="ProgramMap"/>.
    /// </summary>
    public Func<string, int?, TrackSound?>? SoundMap { get; set; }

    /// <summary>MIDI channel of each track as the synth plays it.</summary>
    public IReadOnlyList<int> TrackChannels => _score?.Tracks.Select(t => (int)t.PlaybackInfo.PrimaryChannel).ToList() ?? [];

    /// <summary>Linear balance gain of each track from the sound map (1 when none).</summary>
    public IReadOnlyList<double> TrackGains => _gains;

    private double[] _gains = [];
    private double[] _volumes = [];

    /// <summary>
    /// Channels, presets, balance and drum notes for a freshly loaded score. Returns each track's
    /// linear gain. For a MIDI file the channels fit into 16 and the balance goes into CC 7.
    /// </summary>
    private double[] Prepare(Score score, bool forMidiFile)
    {
        var sounds = score.Tracks.Select(t =>
        {
            string name = t.Name.Replace('\u00A0', ' ');
            // ProgramMap numbers are private to the loaded SoundFonts (not GM), so they stay out of files.
            return SoundMap?.Invoke(name, (int)t.PlaybackInfo.Program)
                ?? (!forMidiFile && ProgramMap?.Invoke(name) is int p ? new TrackSound(p, 0) : null);
        }).ToList();
        var parts = score.Tracks.Select((t, i) => new ChannelPlan.Part(i, t.Staves.Any(st => st.IsPercussion),
            sounds[i]?.Program ?? (int)t.PlaybackInfo.Program, sounds[i]?.GainDb ?? 0)).ToList();
        var channels = forMidiFile ? ChannelPlan.ForMidiFile(parts) : ChannelPlan.ForPlayback(parts);
        var gains = new double[score.Tracks.Count];
        for (int i = 0; i < score.Tracks.Count; i++)
        {
            var track = score.Tracks[i];
            track.PlaybackInfo.PrimaryChannel = channels[i];
            track.PlaybackInfo.SecondaryChannel = channels[i];
            if (sounds[i] is { } sound)
            {
                track.PlaybackInfo.Program = sound.Percussion ? 0 : sound.Program;
                track.PlaybackInfo.Bank = sound.Percussion ? 0 : sound.Bank;
                RemoveInstrumentChanges(track);
            }
            double db = sounds[i]?.GainDb ?? 0;
            gains[i] = Math.Pow(10, db / 20);
            if (forMidiFile) track.PlaybackInfo.Volume = Math.Clamp(Math.Round(16 * Math.Pow(10, db / 40)), 0, 16);
            if (parts[i].Percussion) MapDrums(track);
        }
        return gains;
    }

    /// <summary>
    /// The MusicXML importer turns &lt;midi-instrument&gt; into per-beat instrument and bank changes
    /// that would override the part's preset; the preset map replaces them.
    /// </summary>
    private static void RemoveInstrumentChanges(Track track)
    {
        foreach (var staff in track.Staves)
            foreach (var bar in staff.Bars)
                foreach (var voice in bar.Voices)
                    foreach (var beat in voice.Beats)
                        for (int a = beat.Automations.Count - 1; a >= 0; a--)
                            if (beat.Automations[a].Type is AutomationType.Instrument or AutomationType.Bank)
                                beat.Automations.RemoveAt(a);
    }

    /// <summary>Gives unpitched notes without a MIDI number the GM drum of their staff position.</summary>
    private static void MapDrums(Track track)
    {
        var display = new Dictionary<int, int>();
        foreach (var staff in track.Staves)
            foreach (var bar in staff.Bars)
                foreach (var voice in bar.Voices)
                    foreach (var beat in voice.Beats)
                        foreach (var note in beat.Notes)
                            if (note.PercussionArticulation >= 0)
                                display.TryAdd((int)note.PercussionArticulation, (int)(note.Octave * 12 + note.Tone));
        for (int i = 0; i < track.PercussionArticulations.Count; i++)
        {
            var art = track.PercussionArticulations[i];
            if (art.OutputMidiNumber > 0 || !display.TryGetValue(i, out int pitch)) continue;
            art.OutputMidiNumber = DrumMap.ForDisplay(pitch);
        }
    }

    private void ApplyVolume(int track)
    {
        if (track < 0 || track >= _volumes.Length) return;
        double v = Math.Clamp(_volumes[track], 0, 1) * (track < _gains.Length ? _gains[track] : 1);
        lock (Gate) foreach (var ch in ChannelsOf(track)) _synth.SetChannelVolume(ch, v);
    }

    public void Play()
    {
        lock (Gate)
        {
            if (!_synth.IsReadyForPlayback) return;
            _synth.Play();
        }
    }

    public void Pause()
    {
        lock (Gate) _synth.Pause();
    }

    public void Stop()
    {
        lock (Gate) _synth.Stop();
    }

    public void SeekToBar(int barIndex)
    {
        if (_lookup is null || _lookup.MasterBars.Count == 0) return;
        var mb = _lookup.MasterBars[Math.Clamp(barIndex, 0, _lookup.MasterBars.Count - 1)];
        lock (Gate) _synth.TickPosition = mb.Start;
    }

    public void SeekToTick(double tick)
    {
        lock (Gate) _synth.TickPosition = Math.Max(0, tick);
    }

    public (int First, int Last)? Loop { get; private set; }

    public void SetLoop(int? firstBar, int? lastBar)
    {
        if (_lookup is null || firstBar is null || lastBar is null)
        {
            lock (Gate)
            {
                _synth.PlaybackRange = null!;
                _synth.IsLooping = false;
            }
            Loop = null;
            return;
        }
        int a = Math.Clamp(Math.Min(firstBar.Value, lastBar.Value), 0, _lookup.MasterBars.Count - 1);
        int b = Math.Clamp(Math.Max(firstBar.Value, lastBar.Value), 0, _lookup.MasterBars.Count - 1);
        lock (Gate)
        {
            _synth.PlaybackRange = new PlaybackRange { StartTick = _lookup.MasterBars[a].Start, EndTick = _lookup.MasterBars[b].End };
            _synth.IsLooping = true;
        }
        Loop = (a, b);
    }

    public void SetMute(int track, bool mute)
    {
        if (mute) _muted.Add(track); else _muted.Remove(track);
        lock (Gate) foreach (var ch in ChannelsOf(track)) _synth.SetChannelMute(ch, mute);
    }

    public void SetSolo(int track, bool solo)
    {
        if (solo) _solo.Add(track); else _solo.Remove(track);
        lock (Gate) foreach (var ch in ChannelsOf(track)) _synth.SetChannelSolo(ch, solo);
    }

    public void SetVolume(int track, double volume)
    {
        if (track < 0 || track >= _volumes.Length) return;
        _volumes[track] = Math.Clamp(volume, 0, 1);
        ApplyVolume(track);
    }

    public bool IsMuted(int track) => _muted.Contains(track);
    public bool IsSolo(int track) => _solo.Contains(track);

    public byte[] ExportMidi()
    {
        if (_musicXml is null) throw new InvalidOperationException("No score loaded");
        // From a fresh load: the playback model has remapped programs and display styling that
        // must not leak into the file. The playback MIDI also carries synth-only events, so the
        // export is generated in SMF1 mode.
        var score = ScoreLoader.LoadScoreFromBytes(new Uint8Array(_musicXml), new Settings());
        Prepare(score, forMidiFile: true);
        var smf = new MidiFile { Format = MidiFileFormat.MultiTrack };
        new MidiFileGenerator(score, new Settings(), new AlphaSynthMidiFileHandler(smf, true)).Generate();
        KeepSharedUnisons(smf);
        var bin = smf.ToBinary();
        var bytes = new byte[(int)bin.Length];
        for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)bin[i];
        return bytes;
    }

    /// <summary>Seconds of silence after the last note, long enough for every release tail to sound.</summary>
    public const double ReleaseTailSeconds = 1.5;

    /// <summary>
    /// alphaSynth stops every voice dead when it reaches the last MIDI event, so the final note of
    /// a piece (and of every phrase played alone) lost its release. A no-op controller event after
    /// the last note moves the end of the song past the tail.
    /// </summary>
    public static void AddReleaseTail(MidiFile midi)
    {
        if (midi.Events.Count == 0) return;
        double last = midi.Events.Max(e => e.Tick);
        double usPerBeat = midi.Events.OfType<TempoChangeEvent>().Where(e => e.Tick <= last).OrderBy(e => e.Tick)
            .LastOrDefault()?.MicroSecondsPerQuarterNote ?? 500000;
        double tail = Math.Round(ReleaseTailSeconds * 1e6 / usPerBeat * midi.Division);
        midi.AddEvent(new ControlChangeEvent(0, last + tail, 0, ControllerType.ExpressionControllerFine, 0));
    }

    /// <summary>
    /// Parts that share a channel in the file can hold the same pitch at once (unisons are
    /// everywhere in band scores). A receiver ends the sounding note at the first note-off, which
    /// would cut the other part's note short, so a note-off is dropped while another note-on of
    /// that key on that channel is still open.
    /// </summary>
    /// <remarks>For a multi-track file only (the events live in its tracks).</remarks>
    internal static int KeepSharedUnisons(MidiFile smf)
    {
        var notes = new List<(MidiTrack Track, NoteEvent Event, int Order)>();
        int order = 0;
        foreach (var track in smf.Tracks)
            foreach (var e in track.Events)
                if (e is NoteOnEvent or NoteOffEvent) notes.Add((track, (NoteEvent)e, order++));
        var open = new Dictionary<(double, double), int>();
        var drop = new HashSet<MidiEvent>(ReferenceEqualityComparer.Instance);
        foreach (var (_, e, _) in notes.OrderBy(n => n.Event.Tick).ThenBy(n => n.Event is NoteOnEvent ? 1 : 0).ThenBy(n => n.Order))
        {
            var key = (e.Channel, e.NoteKey);
            open.TryGetValue(key, out int count);
            if (e is NoteOnEvent) open[key] = count + 1;
            else if (count > 1) { open[key] = count - 1; drop.Add(e); }
            else open[key] = 0;
        }
        foreach (var track in smf.Tracks)
            for (int i = track.Events.Count - 1; i >= 0; i--)
                if (drop.Contains(track.Events[i])) track.Events.RemoveAt(i);
        return drop.Count;
    }

    public (int Beat, int Beats) BeatAt(PlaybackPosition position)
    {
        if (_score is null || _lookup is null || position.BarIndex < 0 || position.BarIndex >= _lookup.MasterBars.Count) return (1, 4);
        var mb = _score.MasterBars[position.BarIndex];
        int beats = Math.Max(1, (int)mb.TimeSignatureNumerator);
        double beatTicks = 960 * 4 / Math.Max(1, mb.TimeSignatureDenominator);
        double into = position.Tick - _lookup.MasterBars[position.BarIndex].Start;
        return (Math.Clamp((int)(into / beatTicks) + 1, 1, beats), beats);
    }

    public double? TempoAt(int barIndex)
    {
        if (_score is null || _score.MasterBars.Count == 0) return null;
        double? tempo = _score.Tempo > 0 ? _score.Tempo : null;
        for (int i = 0; i <= Math.Min(barIndex, _score.MasterBars.Count - 1); i++)
            foreach (var a in _score.MasterBars[i].TempoAutomations)
                tempo = a.Value;
        return tempo;
    }

    /// <summary>Tick range of a bar, for highlighting and "listen to this bar".</summary>
    public (double Start, double End)? BarTicks(int barIndex) =>
        _lookup is null || barIndex < 0 || barIndex >= _lookup.MasterBars.Count
            ? null
            : (_lookup.MasterBars[barIndex].Start, _lookup.MasterBars[barIndex].End);

    public void Dispose()
    {
        lock (Gate) _synth.Destroy();
    }

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
