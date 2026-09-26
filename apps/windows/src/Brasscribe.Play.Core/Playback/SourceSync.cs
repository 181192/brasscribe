using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// Score position ↔ time in the original recording, through the Composition's beat map (beat_times;
/// inside free-time passages the beats are synthetic and follow the performance). alphaTab counts
/// 960 MIDI ticks per quarter from bar 1; the Composition counts ticks_per_beat per beat from its
/// tick 0, the first downbeat, which is where bar 1 starts. A beat is a quarter for these scores.
/// </summary>
public sealed class ScoreTimeMap(Composition composition)
{
    public const double MidiTicksPerQuarter = 960;

    public double SecondsAtTick(double midiTick) =>
        Math.Max(0, composition.SecondsAt(midiTick / MidiTicksPerQuarter * composition.TicksPerBeat));

    public double TickAtSeconds(double seconds) =>
        Math.Max(0, composition.TickAt(seconds) / composition.TicksPerBeat * MidiTicksPerQuarter);
}

public enum ListeningSource { Score, Original }

/// <summary>
/// Keeps the video (or recording) of the original in step with score playback: it plays muted at
/// the score's speed and is re-seeked when it drifts more than <see cref="Tolerance"/> from the
/// score's position. Pausing the score pauses it.
/// </summary>
public sealed class VideoFollower(IOriginalPlayer original, ScoreTimeMap map)
{
    public static readonly TimeSpan Tolerance = TimeSpan.FromMilliseconds(250);

    /// <summary>Returns true when it had to seek.</summary>
    public bool Follow(PlaybackState state, double midiTick, double speed)
    {
        if (!original.HasMedia) return false;
        if (state != PlaybackState.Playing)
        {
            if (original.IsPlaying) original.Pause();
            return false;
        }
        original.IsMuted = true;
        original.Rate = speed;
        var target = TimeSpan.FromSeconds(map.SecondsAtTick(midiTick));
        bool seek = (original.Position - target).Duration() > Tolerance;
        if (seek) original.Position = target;
        if (!original.IsPlaying) original.Play();
        return seek;
    }
}
