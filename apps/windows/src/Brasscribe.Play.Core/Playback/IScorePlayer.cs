namespace Brasscribe.Play.Core.Playback;

public sealed record TrackInfo(int Index, string Name, bool IsPercussion, int DisplayTransposition);

/// <summary>Playback position: 0-based bar index, alphaTab MIDI tick and seconds.</summary>
public sealed record PlaybackPosition(int BarIndex, double Tick, double Seconds, double EndSeconds);

public enum PlaybackState { Stopped, Paused, Playing }

/// <summary>
/// Score playback as the practice screen needs it. The alphaTab implementation plays the arranged
/// MusicXML through its SoundFont synth; a realistic-tier implementation (sfizz) can replace it.
/// </summary>
public interface IScorePlayer : IDisposable
{
    IReadOnlyList<TrackInfo> Tracks { get; }
    int BarCount { get; }
    bool IsReady { get; }
    PlaybackState State { get; }
    PlaybackPosition Position { get; }

    /// <summary>25 to 150 percent, pitch unchanged.</summary>
    double Speed { get; set; }
    bool Metronome { get; set; }
    bool CountIn { get; set; }
    /// <summary>Semitones applied to every pitched track.</summary>
    int Transpose { get; set; }

    event EventHandler<PlaybackPosition>? PositionChanged;
    event EventHandler<PlaybackState>? StateChanged;
    event EventHandler? Finished;

    void LoadScore(byte[] musicXml);
    /// <summary>Loads a SoundFont2; append keeps the presets already loaded.</summary>
    void LoadSoundFont(byte[] soundFont, bool append = false);

    void Play();
    void Pause();
    void Stop();
    void SeekToBar(int barIndex);
    /// <summary>Seeks to a MIDI tick (960 per quarter), for switching back from the original recording.</summary>
    void SeekToTick(double tick);

    /// <summary>Loops bars first..last (0-based, inclusive); null clears the loop.</summary>
    void SetLoop(int? firstBar, int? lastBar);
    (int First, int Last)? Loop { get; }

    void SetMute(int track, bool mute);
    void SetSolo(int track, bool solo);
    void SetVolume(int track, double volume);
    bool IsMuted(int track);
    bool IsSolo(int track);

    /// <summary>Standard MIDI file of the score as played (for the MIDI export).</summary>
    byte[] ExportMidi();

    /// <summary>The beat (1-based) at a position and the beats in its bar.</summary>
    (int Beat, int Beats) BeatAt(PlaybackPosition position) => (1, 4);

    /// <summary>The written tempo (quarter notes per minute) of a bar, when the score marks one.</summary>
    double? TempoAt(int barIndex) => null;
}
